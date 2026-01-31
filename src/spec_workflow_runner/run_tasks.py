"""Interactive runner that loops through spec-workflow tasks via AI providers."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import textwrap
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from .completion_verify import run_verification
from .git_hooks import block_commits
from .providers import ClaudeProvider, Provider, create_provider, get_supported_models
from .subprocess_helpers import format_command_string, popen_command
from .utils import (
    Config,
    RunnerError,
    TaskStats,
    check_clean_working_tree,
    check_mcp_server_exists,
    choose_option,
    discover_projects,
    discover_specs,
    display_claude_flow_status,
    display_overall_progress,
    display_spec_queue,
    get_active_claude_account,
    get_all_spec_progress,
    get_current_commit,
    has_claude_flow_activity,
    has_uncommitted_changes,
    is_context_limit_error,
    is_no_messages_error,
    is_rate_limit_error,
    is_timeout_error,
    list_unfinished_specs,
    load_config,
    monitor_claude_flow_workers,
    read_task_details,
    read_task_stats,
    reduce_spec_context,
    rotate_claude_account,
)
from .validation_check import run_validation

logger = logging.getLogger(__name__)


def safe_print(text: str, **kwargs) -> None:
    """Print text safely, handling Unicode encoding errors on Windows."""
    try:
        print(text, **kwargs)
    except UnicodeEncodeError:
        # Replace problematic characters with ASCII equivalents
        print(text.encode('ascii', errors='replace').decode('ascii'), **kwargs)


class AllSpecsSentinel:
    """Marker object representing the 'run all specs' selection."""


class MultipleSpecsSentinel:
    """Marker object representing multiple selected specs."""

    def __init__(self, specs: list[tuple[str, Path]]) -> None:
        self.specs = specs


class PollPendingTasksSentinel:
    """Marker object representing the 'poll for pending tasks' selection."""


ALL_SPECS_SENTINEL = AllSpecsSentinel()
POLL_PENDING_TASKS_SENTINEL = PollPendingTasksSentinel()
SpecOption = tuple[str, Path] | AllSpecsSentinel | MultipleSpecsSentinel | PollPendingTasksSentinel


def parse_args() -> argparse.Namespace:
    """Return CLI arguments for the runner."""
    parser = argparse.ArgumentParser(
        description="Run AI provider against remaining spec tasks until finished.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path.cwd() / "config.json",
        help="Path to config.json (default: ./config.json).",
    )
    parser.add_argument(
        "--project",
        type=Path,
        help="Optional project path to skip project selection.",
    )
    parser.add_argument(
        "--spec",
        type=str,
        help="Optional spec name to skip spec selection.",
    )
    parser.add_argument(
        "--provider",
        type=str,
        choices=["claude", "codex", "gemini"],
        help="AI provider to use (prompts if not specified).",
    )
    parser.add_argument(
        "--model",
        type=str,
        help=(
            "AI model to use (prompts if not specified). "
            "Codex: gpt-5.1-codex-max, gpt-5.1-codex, etc. "
            "Claude: sonnet, haiku, opus. "
            "Gemini: gemini-3-pro-preview, gemini-2.5-pro, gemini-2.5-flash."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip execution; useful for smoke testing.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Force refresh of project cache, ignoring existing cache.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output (verbose logging).",
    )
    return parser.parse_args()


def ensure_spec(project: Path, cfg: Config, spec_name: str | None) -> tuple[str, Path]:
    """Return the spec name and directory, optionally prompting the user."""
    specs = discover_specs(project, cfg)
    if spec_name:
        for candidate, path in specs:
            if candidate == spec_name:
                return candidate, path
        raise RunnerError(f"Spec '{spec_name}' not found under {project}")
    name, spec_path = choose_option(
        f"Select spec within {project}",
        specs,
        label=lambda pair: pair[0],
    )
    return name, spec_path


def _label_option(option: SpecOption) -> str:
    if isinstance(option, AllSpecsSentinel):
        return "All unfinished specs"
    if isinstance(option, MultipleSpecsSentinel):
        return "Multiple specs (custom order)"
    if isinstance(option, PollPendingTasksSentinel):
        return "Poll for pending tasks"
    return option[0]


def _parse_spec_indices(input_str: str, specs: list[tuple[str, Path]]) -> list[tuple[str, Path]]:
    """Parse comma-separated indices and return selected specs in order."""
    try:
        indices = [int(idx.strip()) for idx in input_str.split(",")]
    except ValueError:
        raise RunnerError(f"Invalid index format: '{input_str}'. Use comma-separated numbers like '1,3,5'")

    selected = []
    for idx in indices:
        if idx < 1 or idx > len(specs):
            raise RunnerError(f"Index {idx} out of range (1-{len(specs)})")
        selected.append(specs[idx - 1])

    return selected


def _choose_spec_or_all(
    project: Path,
    cfg: Config,
    spec_name: str | None,
) -> SpecOption:
    """Return either a spec tuple, ALL_SPECS_SENTINEL, MultipleSpecsSentinel, or PollPendingTasksSentinel."""
    specs = discover_specs(project, cfg)
    if spec_name:
        if spec_name.lower() == "all":
            return ALL_SPECS_SENTINEL
        if spec_name.lower() == "poll":
            return POLL_PENDING_TASKS_SENTINEL
        # Check if it's comma-separated indices like "1,3,5"
        if "," in spec_name:
            selected_specs = _parse_spec_indices(spec_name, specs)
            return MultipleSpecsSentinel(selected_specs)
        # Single spec by name
        for candidate, path in specs:
            if candidate == spec_name:
                return candidate, path
        raise RunnerError(f"Spec '{spec_name}' not found under {project}")

    # Interactive selection
    print(f"\nAvailable specs in {project}:")
    for idx, (name, _) in enumerate(specs, start=1):
        print(f"  {idx}. {name}")
    print("\nOptions:")
    print("  - Enter 'all' for all unfinished specs (sorted by creation time)")
    print("  - Enter 'poll' to poll every 10s until pending tasks are found")
    print("  - Enter a single number (e.g., '3') for one spec")
    print("  - Enter comma-separated numbers (e.g., '2,5,1') for custom order")
    print("  - Enter spec name directly")

    choice = input("\nYour choice: ").strip()

    if choice.lower() == "all":
        return ALL_SPECS_SENTINEL

    if choice.lower() == "poll":
        return POLL_PENDING_TASKS_SENTINEL

    # Check if it's comma-separated indices
    if "," in choice:
        selected_specs = _parse_spec_indices(choice, specs)
        return MultipleSpecsSentinel(selected_specs)

    # Check if it's a single index
    try:
        idx = int(choice)
        if 1 <= idx <= len(specs):
            return specs[idx - 1]
        raise RunnerError(f"Index {idx} out of range (1-{len(specs)})")
    except ValueError:
        pass

    # Try as spec name
    for candidate, path in specs:
        if candidate == choice:
            return candidate, path

    raise RunnerError(f"Invalid selection: '{choice}'")


def poll_for_pending_tasks(project: Path, cfg: Config) -> None:
    """Poll every 10 seconds until specs with pending tasks are found."""
    print("\n🔍 Polling for specs with pending tasks every 10 seconds...")
    print("Press Ctrl+C to stop polling.\n")

    poll_count = 0
    while True:
        poll_count += 1
        current_time = datetime.now().strftime("%H:%M:%S")
        print(f"[{current_time}] Poll #{poll_count}: Checking for pending tasks...")

        unfinished = list_unfinished_specs(project, cfg)
        if unfinished:
            print(f"\n[OK] Found {len(unfinished)} spec(s) with pending tasks!")
            for idx, (name, spec_path) in enumerate(unfinished, start=1):
                tasks_path = spec_path / cfg.tasks_filename
                stats = read_task_stats(tasks_path)
                print(f"  {idx}. {name} - {stats.summary()}")
            return

        print("  No pending tasks found. Waiting 10 seconds...")
        time.sleep(10)


def run_multiple_specs(
    provider: Provider,
    cfg: Config,
    project: Path,
    specs: list[tuple[str, Path]],
    dry_run: bool,
) -> None:
    """Run multiple specs in the specified order."""
    if dry_run:
        print("\n[DRY-RUN MODE] Selected specs in order:")
        print(f"{'='*90}")
        print(f"{'#':<6}{'Spec Name':<40}{'Status':<25}{'Created'}")
        print(f"{'-'*90}")

        for idx, (name, spec_path) in enumerate(specs, start=1):
            tasks_path = spec_path / cfg.tasks_filename
            if tasks_path.exists():
                stats = read_task_stats(tasks_path)
                ctime = spec_path.stat().st_ctime
                created_date = datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M")
                status = f"{stats.done}/{stats.total} tasks ({stats.in_progress} in progress)"
            else:
                created_date = "N/A"
                status = "No tasks.md found"
            print(f"{idx:<6}{name:<40}{status:<25}{created_date}")

        print(f"{'-'*90}")
        print(f"Total: {len(specs)} spec(s) will be processed in this order\n")
        return

    print(f"\nRunning {len(specs)} specs in specified order...")
    for idx, (spec_name, spec_path) in enumerate(specs, start=1):
        print(f"\n{'='*90}")
        print(f"Processing spec {idx}/{len(specs)}: '{spec_name}'")
        print(f"{'='*90}")
        run_loop(provider, cfg, project, spec_name, spec_path, dry_run)
        print(f"[OK] Completed spec '{spec_name}' ({idx}/{len(specs)})")


def run_all_specs(
    provider: Provider,
    cfg: Config,
    project: Path,
    dry_run: bool,
) -> None:
    """Sequentially run provider for every unfinished spec, polling every 10 minutes when all complete."""
    if dry_run:
        print("\n[DRY-RUN MODE] Displaying spec queue without executing...")
        display_spec_queue(project, cfg)
        print("\n[DRY-RUN MODE] Would continuously poll every 10 minutes for new specs after all tasks complete.")
        return

    print("\nRunning unfinished specs in sequence.")
    print("Will poll every 10 minutes for new specs when all tasks are complete.\n")

    while True:
        # Display overall progress summary
        display_overall_progress(project, cfg)

        # Display claude-flow worker status if available
        display_claude_flow_status(project)

        unfinished = list_unfinished_specs(project, cfg)
        if not unfinished:
            current_time = datetime.now().strftime("%H:%M:%S")
            print(f"\n[{current_time}] No unfinished specs remaining. All caught up!")
            print("Polling every 10 minutes for new specs. Press Ctrl+C to stop.")
            time.sleep(600)  # 10 minutes = 600 seconds
            continue
        spec_name, spec_path = unfinished[0]
        print(f"\n==> Processing spec '{spec_name}'")
        run_loop(provider, cfg, project, spec_name, spec_path, dry_run)


def ensure_project(cfg: Config, explicit_path: Path | None, refresh_cache: bool) -> Path:
    """Resolve the project directory."""
    if explicit_path:
        return explicit_path.resolve()
    projects = discover_projects(cfg, force_refresh=refresh_cache)
    return choose_option(
        "Select project",
        projects,
        label=lambda path: f"{path.name}  ({path})",
    )


def ensure_provider(explicit_provider: str | None) -> str:
    """Resolve the provider to use, prompting if not specified."""
    if explicit_provider:
        return explicit_provider
    providers = [
        ("codex", "Codex with MCP server support"),
        ("claude", "Claude CLI (automation mode, no prompts)"),
        ("gemini", "Google Gemini CLI (maximum risk/efficiency mode)"),
    ]
    return choose_option(
        "Select AI provider",
        providers,
        label=lambda pair: f"{pair[0]:8} - {pair[1]}",
    )[0]


def ensure_model(provider_name: str, explicit_model: str | None) -> str | None:
    """Resolve the model to use for the provider, prompting if not specified."""
    if explicit_model:
        return explicit_model

    supported_models = get_supported_models(provider_name)
    model_descriptions = {
        "gpt-5.1-codex-max": "Latest frontier agentic coding model (recommended)",
        "gpt-5.1-codex": "Reasoning model with strong performance",
        "gpt-5.1-codex-mini": "Smaller, cost-effective version",
        "gpt-5-codex": "Previous generation model",
        "sonnet": "Latest Sonnet - best coding model (recommended)",
        "haiku": "Fast and cost-effective (3x cheaper, 2x faster)",
        "opus": "Most intelligent for complex tasks",
        "gemini-3-pro-preview": "Gemini 3 Pro - Most intelligent, state-of-the-art (recommended)",
        "gemini-3-flash-preview": "Gemini 3 Flash - Fast preview with high intelligence",
        "gemini-2.5-pro": "Gemini 2.5 Pro - 1M token context, advanced reasoning",
        "gemini-2.5-flash": "Gemini 2.5 Flash - Lightning-fast, high capability",
        "gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite - Ultra-fast, lightweight",
        "gemini-2.0-flash-exp": "Gemini 2.0 Flash Experimental - Latest experimental features",
        "gemini-1.5-pro": "Gemini 1.5 Pro - Stable, proven performance",
        "gemini-1.5-flash": "Gemini 1.5 Flash - Fast and reliable",
        "gemini-1.5-flash-8b": "Gemini 1.5 Flash 8B - Compact, efficient model",
    }

    models_with_desc = [(model, model_descriptions.get(model, "")) for model in supported_models]

    return choose_option(
        f"Select model for {provider_name}",
        models_with_desc,
        label=lambda pair: f"{pair[0]:20} - {pair[1]}" if pair[1] else pair[0],
    )[0]


def mark_task_status(tasks_file: Path, task_id: str, new_status: str) -> bool:
    """Mark a task with a new status in tasks.md.

    Args:
        tasks_file: Path to tasks.md
        task_id: Task ID (e.g., "1", "4.2" for checkbox format, or "MEM-001" for heading format)
        new_status: New status: " " (pending), "-" (in-progress), "x" (completed)
                    OR "Pending", "In Progress", "Completed" for heading format

    Returns:
        True if task was found and updated, False otherwise
    """
    if not tasks_file.exists():
        return False

    content = tasks_file.read_text(encoding="utf-8")
    import re

    # Try checkbox format first: - [ ] 1. Task title
    task_pattern = re.compile(rf"^(-\s+\[)[ x\-](\]\s+{re.escape(task_id)}\.\s+.+)$", re.MULTILINE)
    match = task_pattern.search(content)

    if match:
        # Checkbox format
        new_line = f"{match.group(1)}{new_status}{match.group(2)}"
        content = task_pattern.sub(new_line, content, count=1)
        tasks_file.write_text(content, encoding="utf-8")
        return True

    # Try heading format: ### MEM-001: Title ... **Status**: Pending
    status_map = {" ": "Pending", "-": "In Progress", "x": "Completed"}
    status_word = status_map.get(new_status, new_status)

    heading_pattern = re.compile(rf"^### {re.escape(task_id)}:.+?(\*\*Status\*\*:\s*)\w+", re.MULTILINE | re.DOTALL)
    match = heading_pattern.search(content)

    if match:
        # Heading format - replace **Status**: Old with **Status**: New
        old_status_pattern = re.compile(rf"(\*\*Status\*\*:\s*)\w+")
        # Find the status line after the heading
        task_start = content.find(f"### {task_id}:")
        task_section = content[task_start:task_start+500]  # Look in next 500 chars
        status_match = old_status_pattern.search(task_section)

        if status_match:
            old_text = status_match.group(0)
            new_text = f"{status_match.group(1)}{status_word}"
            content = content.replace(old_text, new_text, 1)
            tasks_file.write_text(content, encoding="utf-8")
            return True

    return False


def parse_tasks_alternate_format(tasks_file: Path) -> list[dict]:
    """Parse tasks.md with ### heading format and **Status** field.

    Returns list of task dicts with: id, title, status, content
    """
    import re

    if not tasks_file.exists():
        return []

    content = tasks_file.read_text(encoding="utf-8")
    tasks = []

    # Find all ### Task headings
    task_pattern = re.compile(r'^### ([A-Z]+-\d+): (.+)$', re.MULTILINE)
    status_pattern = re.compile(r'\*\*Status\*\*:\s*(\w+)', re.IGNORECASE)

    matches = list(task_pattern.finditer(content))

    for i, match in enumerate(matches):
        task_id = match.group(1)
        task_title = match.group(2)
        start_pos = match.end()

        # Find end of this task (next ### or end of file)
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        task_content = content[start_pos:end_pos]

        # Extract status
        status_match = status_pattern.search(task_content)
        status = status_match.group(1).lower() if status_match else "pending"

        tasks.append({
            "id": task_id,
            "title": task_title,
            "status": status,
            "content": task_content.strip()
        })

    return tasks


def build_prompt(cfg: Config, spec_name: str, spec_path: Path, stats: TaskStats) -> str:
    """Format the prompt using the config template with task details.

    Parses tasks.md to find the first pending task and includes its details in the prompt.
    """
    from .tui.task_parser import parse_tasks_file, TaskStatus

    # Parse tasks.md to find first pending task
    tasks_file = spec_path / cfg.tasks_filename

    # Try standard format first
    tasks, warnings = parse_tasks_file(tasks_file)
    pending_task = next((t for t in tasks if t.status == TaskStatus.PENDING), None)

    # If no tasks found, try alternate format (### headings with **Status**)
    if not pending_task:
        alt_tasks = parse_tasks_alternate_format(tasks_file)
        alt_pending = next((t for t in alt_tasks if t["status"] == "pending"), None)

        if alt_pending:
            # Convert to Task-like structure
            from dataclasses import dataclass
            @dataclass
            class AltTask:
                id: str
                title: str
                description: list[str]

            pending_task = AltTask(
                id=alt_pending["id"],
                title=alt_pending["title"],
                description=[alt_pending["content"]]
            )

    if not pending_task:
        # No pending tasks - return a simple message
        return f"All tasks for spec '{spec_name}' are complete or in progress. Nothing to do."

    # Format task description (join the description lines)
    task_desc = "\n".join(pending_task.description) if pending_task.description else "No additional details provided."

    remaining = stats.total - stats.done
    context = {
        "spec_name": spec_name,
        "task_id": pending_task.id,
        "task_title": pending_task.title,
        "task_description": task_desc,
        "tasks_total": stats.total,
        "tasks_done": stats.done,
        "tasks_remaining": remaining,
        "tasks_in_progress": stats.in_progress,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    return cfg.prompt_template.format(**context)


def _build_log_header(iteration: int, spec_name: str, command: list[str], prompt: str) -> str:
    """Build the log file header with metadata."""
    started = datetime.now(UTC).isoformat()
    formatted_command = format_command_string(command)
    return textwrap.dedent(
        f"""\
        # Iteration {iteration}
        # Started {started}
        # Spec {spec_name}
        # Command
        {formatted_command}

        # Prompt
        {prompt}

        # Output (stdout + stderr)
        """
    )


def _write_dry_run_log(log_path: Path, header: str, command: str) -> None:
    """Write a dry-run simulation to the log file."""
    simulated = f"[dry-run] Would run: {command}\n"
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(header)
        handle.write(simulated)
        handle.write("# Exit Code\n0\n")
    print(simulated.strip())
    print(f"Saved log: {log_path}")


def _get_latest_file_mtime(project_path: Path, ignore_dirs: tuple[str, ...]) -> float:
    """Get the most recent file modification time in project directory.

    Args:
        project_path: Project directory to scan
        ignore_dirs: Directory names to skip

    Returns:
        Most recent modification timestamp, or 0.0 if no files found
    """
    latest_mtime = 0.0
    try:
        for root, dirs, files in os.walk(project_path):
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if d not in ignore_dirs]

            for file in files:
                try:
                    file_path = Path(root) / file
                    mtime = file_path.stat().st_mtime
                    if mtime > latest_mtime:
                        latest_mtime = mtime
                except (OSError, PermissionError):
                    # Skip files we can't access
                    continue
    except Exception:
        # If scan fails, return 0 to avoid breaking timeout logic
        pass

    return latest_mtime


def _execute_provider_command(
    command: list[str],
    project_path: Path,
    header: str,
    log_path: Path,
    activity_timeout_seconds: int | None = None,
    activity_check_interval_seconds: int = 300,
    ignore_dirs: tuple[str, ...] = ()
) -> int:
    """Execute provider command and stream output to log with activity-based timeout.

    Args:
        command: Command to execute
        project_path: Working directory for command
        header: Log file header
        log_path: Path to write log file
        activity_timeout_seconds: Max seconds of inactivity before timeout, None for no timeout
        activity_check_interval_seconds: How often to check for activity (default: 300s)
        ignore_dirs: Directories to ignore when checking file activity

    Raises:
        RunnerError: If command fails or times out due to inactivity
    """
    import threading

    formatted_command = format_command_string(command)

    # Save command to file for debugging
    import tempfile
    cmd_file = Path(tempfile.gettempdir()) / "last_command.txt"
    cmd_file.write_text(formatted_command, encoding="utf-8")

    print("\nRunning:", formatted_command)
    if activity_timeout_seconds:
        print(f"Activity timeout: {activity_timeout_seconds}s ({activity_timeout_seconds // 60} minutes of inactivity)")
        print(f"Checking activity every: {activity_check_interval_seconds}s ({activity_check_interval_seconds // 60} minutes)")

    output_lines: list[str] = []
    early_termination_flag = {"triggered": False}  # Use dict for mutability across threads
    spawned_agents: list[dict] = []  # Track agent info spawned via Task tool
    pending_tool_uses: dict[str, str] = {}  # Map tool_use id -> tool name

    def read_output(proc: subprocess.Popen, handle: TextIO, output_lines: list[str]) -> None:
        """Read process output in background thread.

        Detects "No messages returned" error and kills the process early
        to avoid waiting for timeout.
        """
        assert proc.stdout is not None
        no_messages_detected = False

        import sys

        line_count = 0
        while True:
            import sys
            sys.stderr.flush()
            line = proc.stdout.readline()
            sys.stderr.flush()
            if not line:  # Empty bytes means EOF
                break
            decoded = line.decode("utf-8", errors="replace").strip()

            # Write raw JSONL to log file
            handle.write(decoded + "\n")
            handle.flush()
            output_lines.append(decoded)

            # Parse and display stream-json format
            try:
                data = json.loads(decoded)
                msg_type = data.get("type")

                # Handle different message types
                if msg_type == "system":
                    # Show MCP server connection status
                    if "mcp_servers" in data:
                        for server in data["mcp_servers"]:
                            status = server.get("status", "unknown")
                            name = server.get("name", "unknown")
                            print(f"[MCP: {name} - {status}]", flush=True)

                elif msg_type == "assistant":
                    # Display assistant message content
                    if "message" in data and "content" in data["message"]:
                        content = data["message"]["content"]
                        if isinstance(content, list):
                            for item in content:
                                if item.get("type") == "text":
                                    text = item.get("text", "")
                                    # Handle Unicode encoding errors on Windows
                                    try:
                                        print(text, flush=True)
                                    except UnicodeEncodeError:
                                        # Replace problematic characters with ASCII equivalents
                                        print(text.encode('ascii', errors='replace').decode('ascii'), flush=True)
                                elif item.get("type") == "tool_use":
                                    tool_name = item.get("name", "unknown")
                                    tool_use_id = item.get("id")
                                    print(f"[Using tool: {tool_name}]", flush=True)
                                    # Track tool use for later result matching
                                    if tool_use_id:
                                        pending_tool_uses[tool_use_id] = tool_name
                                elif item.get("type") == "thinking":
                                    thinking = item.get("thinking", "")[:150]
                                    try:
                                        print(f"[Thinking: {thinking}...]", flush=True)
                                    except UnicodeEncodeError:
                                        print(f"[Thinking: {thinking.encode('ascii', errors='replace').decode('ascii')}...]", flush=True)

                elif msg_type == "result":
                    # Show final result
                    if "result" in data:
                        safe_print(f"\n[Result: {data['result'][:100]}...]")

                elif msg_type == "tool_result":
                    # Check if this is a result from a Task tool
                    tool_use_id = data.get("tool_use_id")
                    if tool_use_id and pending_tool_uses.get(tool_use_id) == "Task":
                        # Extract agent information from Task tool result
                        content = data.get("content", "")
                        # Try to parse agent ID from the result
                        import re
                        # Look for patterns like "agent ID: xyz" or similar
                        if isinstance(content, str):
                            agent_match = re.search(r'agent[_\s]+(?:ID|id)[\s:]+([a-zA-Z0-9_-]+)', content, re.IGNORECASE)
                            if agent_match:
                                agent_id = agent_match.group(1)
                                spawned_agents.append({
                                    "agent_id": agent_id,
                                    "tool_use_id": tool_use_id,
                                    "content": content[:200]
                                })
                                print(f"[!]  Task agent detected: {agent_id}", flush=True)
                            else:
                                # No clear agent ID, but still record the Task spawn
                                spawned_agents.append({
                                    "agent_id": f"unknown_{tool_use_id}",
                                    "tool_use_id": tool_use_id,
                                    "content": content[:200]
                                })
                                print(f"[!]  Task agent spawned (id: {tool_use_id})", flush=True)

                # If message type not handled, silently skip (don't spam console)

            except (json.JSONDecodeError, KeyError, TypeError):
                # If not valid JSON, just print the line
                print(decoded, flush=True)

            line_count += 1

            # Detect "No messages returned" error early
            if "no messages returned" in decoded.lower() and not no_messages_detected:
                no_messages_detected = True
                early_termination_flag["triggered"] = True
                # Give it a moment to finish output, then kill
                import time
                time.sleep(2)
                if proc.poll() is None:  # Still running
                    try:
                        proc.terminate()  # Try graceful termination first
                        time.sleep(1)
                        if proc.poll() is None:  # Still alive
                            proc.kill()  # Force kill if terminate didn't work
                    except Exception as e:
                        pass  # Ignore errors during termination
                break  # Exit the loop immediately after killing


    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(header)
        proc = popen_command(
            command,
            cwd=project_path,
            stdin=subprocess.DEVNULL,  # Close stdin to prevent blocking
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Merge stderr into stdout
            clean_claude_env=True,
            env_additions={"PYTHONUNBUFFERED": "1"},
        )


        # Start output reading thread
        reader_thread = threading.Thread(
            target=read_output,
            args=(proc, handle, output_lines),
            daemon=True
        )
        reader_thread.start()

        # Note: Session monitoring only works for interactive mode, not --print mode
        # In --print mode, we can only monitor file system changes
        print(f"[MONITOR] Monitoring file system activity (--print mode has no session logs)...")
        print(f"\n{'='*80}")
        print(f"Claude Output:")
        print(f"{'='*80}\n")
        session_started = False
        session_monitor = None

        # Wait for process with activity-based timeout monitoring
        returncode = None
        last_mtime = _get_latest_file_mtime(project_path, ignore_dirs)

        # Use short intervals for checking/displaying updates (5 seconds)
        # But only do timeout checks at activity_check_interval_seconds
        display_interval = 5  # Check for updates every 5 seconds
        last_timeout_check = time.time()

        while returncode is None:
            try:
                # Check process status with short timeout for responsive display
                returncode = proc.wait(timeout=display_interval)
            except subprocess.TimeoutExpired:
                    # Process hasn't finished yet - check for file modifications
                    current_time = time.time()
                    current_mtime = _get_latest_file_mtime(project_path, ignore_dirs)
                    file_has_activity = current_mtime > last_mtime

                    if file_has_activity:
                        last_mtime = current_mtime
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] [FILE] File modified - Claude is working")

                    # Check for timeout at configured interval
                    if activity_timeout_seconds and (current_time - last_timeout_check) >= activity_check_interval_seconds:
                        last_timeout_check = current_time
                        inactivity_seconds = int(current_time - last_mtime)

                        if inactivity_seconds > activity_timeout_seconds:
                            # Inactivity timeout - kill the process
                            print(f"\n[!]  No file changes for {inactivity_seconds}s (>{activity_timeout_seconds}s). Terminating process...")
                            proc.kill()
                            reader_thread.join(timeout=5)
                            handle.write(f"\n# Inactivity Timeout\nProcess terminated after {inactivity_seconds} seconds of inactivity\n")
                            handle.write(f"\n# Exit Code\nINACTIVITY_TIMEOUT\n")
                            raise RunnerError(
                                f"Provider command timed out due to {inactivity_seconds} seconds of inactivity "
                                f"(threshold: {activity_timeout_seconds}s = {activity_timeout_seconds // 60} minutes). "
                                f"The AI may be stuck or waiting for input."
                            )
                        else:
                            # Show periodic status
                            mins = inactivity_seconds // 60
                            secs = inactivity_seconds % 60
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] [WAIT] Running... (no file changes for {mins}m {secs}s, max: {activity_timeout_seconds // 60}m)")

                    # Continue loop
                    continue

        # Wait for output thread to finish (with timeout to avoid hanging)
        reader_thread.join(timeout=10)
        if reader_thread.is_alive():
            print("[WARNING] Reader thread did not finish in time - process may have hung")

        # Write note about early termination if it occurred (before closing file)
        if early_termination_flag["triggered"]:
            handle.write(f"\n# Note\nProcess killed early due to 'No messages returned' error\n")

        handle.write(f"\n# Exit Code\n{returncode}\n")

    # Check if "No messages returned" was detected in output
    output_text = "".join(output_lines)
    has_no_messages_error = "no messages returned" in output_text.lower()

    if returncode != 0:
        # If process was killed due to "No messages returned", treat as potentially successful
        if has_no_messages_error and returncode == -9:  # -9 = SIGKILL
            print(f"[!]  Process terminated due to 'No messages returned' error")
            print(f"   Treating as potentially successful. Circuit breaker will stop if no progress.")
            print(f"Saved log: {log_path}")
            return 0  # Don't raise error - let circuit breaker handle it

        # Include output in error message for better error detection
        raise RunnerError(f"Provider command failed. Output: {output_text}")
    print(f"Saved log: {log_path}")

    # No agents spawned - normal completion
    if not spawned_agents:
        return 0

    # Check if Claude spawned Task agents despite instructions
    if spawned_agents:
        print(f"\n{'='*80}")
        print(f"[!]  WARNING: Claude spawned {len(spawned_agents)} Task agent(s) despite instructions!")
        print(f"{'='*80}")
        for i, agent_info in enumerate(spawned_agents, 1):
            agent_id = agent_info["agent_id"]
            print(f"  {i}. Agent: {agent_id}")

        print(f"\n[WAIT] Waiting for spawned agents to complete...")
        print(f"   Monitoring file system activity and commits")
        print(f"   Will wait up to 10 minutes, or until 60s of inactivity\n")

        # Monitor for agent completion
        start_time = time.time()
        max_total_wait = 600  # 10 minutes maximum
        inactivity_threshold = 60  # 60 seconds of no activity = done

        initial_commit = get_current_commit(project_path)
        last_activity_time = time.time()
        last_mtime = _get_latest_file_mtime(project_path, ignore_dirs)
        commits_detected = []

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting agent monitoring...")

        while True:
            elapsed = time.time() - start_time
            inactivity = time.time() - last_activity_time

            # Check for maximum timeout
            if elapsed > max_total_wait:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] [TIMEOUT] Maximum wait time reached (10 minutes)")
                break

            # Check for file system activity
            current_mtime = _get_latest_file_mtime(project_path, ignore_dirs)
            if current_mtime > last_mtime:
                last_mtime = current_mtime
                last_activity_time = time.time()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] [FILE] File activity detected (agents working...)")

            # Check for new commits
            current_commit = get_current_commit(project_path)
            if current_commit != initial_commit and current_commit not in commits_detected:
                commits_detected.append(current_commit)
                initial_commit = current_commit
                last_activity_time = time.time()
                # Get commit message
                try:
                    result = subprocess.run(
                        ["git", "log", "-1", "--pretty=%s"],
                        cwd=project_path,
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    commit_msg = result.stdout.strip()
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] [OK] New commit detected: {commit_msg}")
                except Exception:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] [OK] New commit detected: {current_commit[:8]}")

            # Check for inactivity threshold
            if inactivity > inactivity_threshold:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] [DONE] No activity for {int(inactivity)}s - agents appear complete")
                break

            # Show periodic status
            if int(elapsed) % 10 == 0 and int(elapsed) > 0:
                mins_elapsed = int(elapsed) // 60
                secs_elapsed = int(elapsed) % 60
                inactive_secs = int(inactivity)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] [WAIT] Waiting... ({mins_elapsed}m {secs_elapsed}s elapsed, {inactive_secs}s inactive, {len(commits_detected)} commits)")

            time.sleep(5)  # Check every 5 seconds

        print(f"\n{'='*80}")
        print(f"[DONE] Agent monitoring complete")
        print(f"  - Total time: {int(elapsed)}s")
        print(f"  - Commits detected: {len(commits_detected)}")
        print(f"{'='*80}\n")

        # Return number of commits detected during agent work
        return len(commits_detected)


def run_provider(
    provider: Provider,
    cfg: Config,
    project_path: Path,
    prompt: str,
    dry_run: bool,
    *,
    spec_name: str,
    iteration: int,
    log_path: Path,
) -> int:
    """Execute the provider command and stream output into a log file."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    provider_cmd = provider.build_command(prompt, project_path, cfg.codex_config_overrides)
    command = provider_cmd.to_list()
    header = _build_log_header(iteration, spec_name, command, prompt)
    formatted_command = format_command_string(command)

    if dry_run:
        _write_dry_run_log(log_path, header, formatted_command)
        return 0

    # Retry loop with exponential backoff
    last_error: Exception | None = None
    attempt = 1
    starting_claude_account: str | None = None  # Track starting account for rotation cycle

    while True:
        try:
            commits_from_agents = _execute_provider_command(
                command,
                project_path,
                header,
                log_path,
                activity_timeout_seconds=cfg.activity_timeout_seconds,
                activity_check_interval_seconds=cfg.activity_check_interval_seconds,
                ignore_dirs=cfg.ignore_dirs
            )
            if attempt > 1:
                logger.info(
                    "Provider command succeeded on retry",
                    extra={
                        "extra_context": {
                            "attempt": attempt,
                            "spec_name": spec_name,
                            "iteration": iteration,
                        }
                    },
                )
            return commits_from_agents  # Success - exit retry loop
        except RunnerError as err:
            last_error = err

            # Check error type
            error_message = str(err)
            is_rate_error = is_rate_limit_error(error_message)
            is_context_error = is_context_limit_error(error_message)
            is_timeout = is_timeout_error(error_message)
            is_no_messages = is_no_messages_error(error_message)

            # Handle "No messages returned" error - treat as potentially successful
            if is_no_messages:
                logger.warning(
                    "Claude CLI returned 'No messages returned' error - treating as potentially successful",
                    extra={
                        "extra_context": {
                            "attempt": attempt,
                            "spec_name": spec_name,
                            "iteration": iteration,
                            "error": error_message,
                        }
                    },
                )
                print(
                    "[!]  Claude CLI error: 'No messages returned'. "
                    "This may indicate completion or a transient issue."
                )
                print("   Continuing to next iteration. Circuit breaker will stop if no progress.")
                # Return successfully - let circuit breaker handle repeated no-commit scenarios
                return 0

            # Handle timeout errors
            if is_timeout:
                logger.warning(
                    "Activity timeout exceeded, attempting recovery",
                    extra={
                        "extra_context": {
                            "attempt": attempt,
                            "timeout_seconds": cfg.activity_timeout_seconds,
                            "spec_name": spec_name,
                            "iteration": iteration,
                            "error": error_message,
                        }
                    },
                )

                # Try to reduce context by archiving implementation logs
                print("[!]  Activity timeout (no file changes detected). Attempting to reduce context...")
                context_reduced = reduce_spec_context(project_path, spec_name, cfg)

                if context_reduced:
                    logger.info(
                        "Context reduced after timeout, retrying immediately",
                        extra={
                            "extra_context": {
                                "attempt": attempt,
                                "spec_name": spec_name,
                                "iteration": iteration,
                            }
                        },
                    )
                    print("[OK] Context reduced by archiving implementation logs. Retrying...")
                    # Retry immediately after reducing context, but increment attempt
                    attempt += 1
                    if attempt > cfg.max_retries:
                        logger.error(
                            "Timeout persists after context reduction and retries",
                            extra={
                                "extra_context": {
                                    "attempts": attempt,
                                    "spec_name": spec_name,
                                    "iteration": iteration,
                                    "timeout_seconds": cfg.activity_timeout_seconds,
                                }
                            },
                        )
                        raise RunnerError(
                            f"Activity timeout occurred repeatedly after {attempt - 1} retries "
                            f"({cfg.activity_timeout_seconds}s = {cfg.activity_timeout_seconds // 60} min). "
                            f"The task may be too complex or the AI is stuck. "
                            f"Consider breaking down the task or increasing activity_timeout_seconds."
                        )
                    continue

                # No logs to archive - fail after one retry attempt
                if attempt < 2:
                    wait_seconds = 30
                    logger.info(
                        f"No context to reduce, waiting {wait_seconds}s before retry",
                        extra={
                            "extra_context": {
                                "attempt": attempt,
                                "spec_name": spec_name,
                                "iteration": iteration,
                            }
                        },
                    )
                    print(f"[!]  No logs to archive. Waiting {wait_seconds}s before retry...")
                    time.sleep(wait_seconds)
                    attempt += 1
                    continue
                else:
                    logger.error(
                        "Timeout persists without ability to reduce context",
                        extra={
                            "extra_context": {
                                "attempts": attempt,
                                "spec_name": spec_name,
                                "iteration": iteration,
                                "timeout_seconds": cfg.activity_timeout_seconds,
                            }
                        },
                    )
                    raise RunnerError(
                        f"Activity timeout occurred after {attempt} attempts "
                        f"({cfg.activity_timeout_seconds}s = {cfg.activity_timeout_seconds // 60} min). "
                        f"The task may be too complex or the AI is stuck. "
                        f"Consider breaking down the task or increasing activity_timeout_seconds."
                    )

            # Handle rate limit errors
            if is_rate_error:
                logger.warning(
                    "Rate limit exceeded, waiting before retry",
                    extra={
                        "extra_context": {
                            "attempt": attempt,
                            "spec_name": spec_name,
                            "iteration": iteration,
                            "error": error_message,
                        }
                    },
                )

                # For Claude provider: try rotating accounts
                if isinstance(provider, ClaudeProvider):
                    if starting_claude_account is None:
                        starting_claude_account = get_active_claude_account()
                        logger.info(f"Tracking starting Claude account: {starting_claude_account}")

                    print("[!]  Rate limit exceeded. Rotating Claude account...")
                    if rotate_claude_account():
                        current_account = get_active_claude_account()

                        # Check if we've cycled through all accounts
                        if current_account == starting_claude_account:
                            logger.warning(
                                "All Claude accounts exhausted, waiting before retry",
                                extra={
                                    "extra_context": {
                                        "starting_account": starting_claude_account,
                                        "spec_name": spec_name,
                                        "iteration": iteration,
                                    }
                                },
                            )
                            backoff_seconds = cfg.context_limit_wait_seconds
                            wait_minutes = backoff_seconds // 60
                            print(
                                f"[!]  All Claude accounts exhausted. "
                                f"Waiting {wait_minutes} minutes ({backoff_seconds}s) before retry..."
                            )
                            time.sleep(backoff_seconds)
                            # Reset starting account for next cycle
                            starting_claude_account = get_active_claude_account()
                        else:
                            logger.info(
                                f"Rotated to Claude account: {current_account}, retrying",
                                extra={
                                    "extra_context": {
                                        "current_account": current_account,
                                        "starting_account": starting_claude_account,
                                        "spec_name": spec_name,
                                        "iteration": iteration,
                                    }
                                },
                            )
                        # Retry with new account
                        continue
                    else:
                        # Rotation failed, fall through to wait
                        print("[!]  Account rotation not available. Falling back to wait...")

                # For non-Claude providers or if rotation not available: wait before retrying
                backoff_seconds = cfg.context_limit_wait_seconds
                wait_minutes = backoff_seconds // 60
                print(
                    f"[!]  Rate limit exceeded. "
                    f"Waiting {wait_minutes} minutes ({backoff_seconds}s) before retry..."
                )
                time.sleep(backoff_seconds)
                # Do not increment attempt for rate limits - retry infinitely
                continue

            # Handle context limit errors
            if is_context_error:
                # Try to reduce context by archiving implementation logs
                print("[!]  Context limit exceeded. Attempting to reduce context...")
                context_reduced = reduce_spec_context(project_path, spec_name, cfg)

                if context_reduced:
                    logger.info(
                        "Context reduced by archiving logs, retrying immediately",
                        extra={
                            "extra_context": {
                                "attempt": attempt,
                                "spec_name": spec_name,
                                "iteration": iteration,
                            }
                        },
                    )
                    print("[OK] Context reduced by archiving implementation logs. Retrying...")
                    # Retry immediately after reducing context
                    continue

                # For Claude provider: rotate accounts before waiting
                if isinstance(provider, ClaudeProvider):
                    # Track starting account on first context limit hit
                    if starting_claude_account is None:
                        starting_claude_account = get_active_claude_account()
                        logger.info(f"Tracking starting Claude account: {starting_claude_account}")

                    # Rotate to next account
                    print("[!]  Context limit exceeded. Rotating Claude account...")
                    if rotate_claude_account():
                        current_account = get_active_claude_account()

                        # Check if we've cycled through all accounts
                        if current_account == starting_claude_account:
                            logger.warning(
                                "All Claude accounts exhausted, waiting before retry",
                                extra={
                                    "extra_context": {
                                        "starting_account": starting_claude_account,
                                        "spec_name": spec_name,
                                        "iteration": iteration,
                                    }
                                },
                            )
                            backoff_seconds = cfg.context_limit_wait_seconds
                            wait_minutes = backoff_seconds // 60
                            print(
                                f"[!]  All Claude accounts exhausted. "
                                f"Waiting {wait_minutes} minutes ({backoff_seconds}s) before retry..."
                            )
                            time.sleep(backoff_seconds)
                            # Reset starting account for next cycle
                            starting_claude_account = get_active_claude_account()
                        else:
                            logger.info(
                                f"Rotated to Claude account: {current_account}, retrying",
                                extra={
                                    "extra_context": {
                                        "current_account": current_account,
                                        "starting_account": starting_claude_account,
                                        "spec_name": spec_name,
                                        "iteration": iteration,
                                    }
                                },
                            )
                        # Retry with new account
                        continue
                    else:
                        # Rotation failed, fall through to wait
                        print("[!]  Account rotation failed. Falling back to wait...")

                # For non-Claude providers or if rotation failed: wait before retrying
                backoff_seconds = cfg.context_limit_wait_seconds
                wait_minutes = backoff_seconds // 60
                logger.warning(
                    "Context limit exceeded, waiting before retry",
                    extra={
                        "extra_context": {
                            "attempt": attempt,
                            "max_retries": cfg.max_retries,
                            "wait_seconds": backoff_seconds,
                            "wait_minutes": wait_minutes,
                            "spec_name": spec_name,
                            "iteration": iteration,
                            "error": error_message,
                        }
                    },
                )
                print(
                    f"[!]  Context limit exceeded (no logs to archive). "
                    f"Waiting {wait_minutes} minutes ({backoff_seconds}s) before retry..."
                )
                time.sleep(backoff_seconds)
                # Do not increment attempt for context limits - retry infinitely
                continue

            if attempt < cfg.max_retries:
                # Calculate exponential backoff for other errors: 2^(attempt-1) seconds
                backoff_seconds = 2 ** (attempt - 1)
                logger.warning(
                    "Provider command failed, retrying with backoff",
                    extra={
                        "extra_context": {
                            "attempt": attempt,
                            "max_retries": cfg.max_retries,
                            "backoff_seconds": backoff_seconds,
                            "spec_name": spec_name,
                            "iteration": iteration,
                            "error": error_message,
                        }
                    },
                )
                print(
                    f"[!]  Attempt {attempt}/{cfg.max_retries} failed. "
                    f"Retrying in {backoff_seconds}s..."
                )
                time.sleep(backoff_seconds)
                attempt += 1
            else:
                logger.error(
                    "Provider command failed after all retries",
                    extra={
                        "extra_context": {
                            "attempts": attempt,
                            "spec_name": spec_name,
                            "iteration": iteration,
                            "error": str(err),
                        }
                    },
                )
                # All retries exhausted - raise the last error
                raise last_error


def _display_dry_run_spec_status(spec_name: str, spec_path: Path, stats: TaskStats) -> None:
    """Display dry-run status for a single spec."""
    print(f"\n[DRY-RUN MODE] Spec: {spec_name}")
    print(f"{'='*90}")
    print(f"Status: {stats.summary()}")
    print(f"Path: {spec_path}")
    ctime = spec_path.stat().st_ctime
    created_date = datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M:%S")
    print(f"Created: {created_date}")
    print(f"{'='*90}")
    if stats.done >= stats.total:
        print("[OK] All tasks complete. Nothing to run.")
    else:
        print(f"Would run provider to complete {stats.total - stats.done} remaining task(s).")


def _check_commit_progress(
    project_path: Path,
    last_commit: str,
    no_commit_streak: int,
    cfg: Config,
) -> tuple[str, int]:
    """Check for new commits and update streak counter. Returns (new_last_commit, new_streak)."""
    new_commit = get_current_commit(project_path)
    if new_commit != last_commit:
        print(f"Detected new commit: {new_commit}")
        return new_commit, 0

    no_commit_streak += 1
    has_changes = has_uncommitted_changes(project_path)
    if has_changes:
        print(
            f"[!]  No new commit detected, but uncommitted changes exist! "
            f"Streak: {no_commit_streak}/{cfg.no_commit_limit}"
        )
        print("   The AI may have created/modified files but didn't commit them.")
        print("   Check 'git status' to see what changed.")
    else:
        print(f"No new commit detected. Streak: {no_commit_streak}/{cfg.no_commit_limit}")

    if no_commit_streak >= cfg.no_commit_limit:
        if has_changes:
            raise RunnerError(
                "Circuit breaker: reached consecutive no-commit limit. "
                "Uncommitted changes exist - the AI is not committing as instructed!"
            )
        raise RunnerError("Circuit breaker: reached consecutive no-commit limit.")

    return last_commit, no_commit_streak


def run_pre_session_validation(
    provider: Provider,
    cfg: Config,
    project_path: Path,
    spec_name: str,
    spec_path: Path,
) -> None:
    """
    Run pre-session validation to ensure tasks.md is synced with codebase.

    This validates and updates tasks.md before any work begins:
    - Verifies format matches tasks-template.md
    - Checks codebase to see what's actually complete
    - Updates checkboxes and status fields to reflect reality
    - Commits the synced tasks.md
    """
    if not cfg.enable_pre_session_validation:
        return

    print(f"\n{'='*80}")
    print(f"PRE-SESSION VALIDATION: {spec_name}")
    print(f"{'='*80}\n")
    print("Validating and syncing tasks.md with codebase status...\n")

    prompt = cfg.pre_session_validation_prompt.format(spec_name=spec_name)
    log_dir = project_path / cfg.log_dir_name / spec_name
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "validation.log"

    # Run validation session
    try:
        _ = run_provider(
            provider=provider,
            cfg=cfg,
            project_path=project_path,
            prompt=prompt,
            dry_run=False,
            spec_name=spec_name,
            iteration=0,
            log_path=log_path,
        )
        print("\n[OK] Pre-session validation complete - tasks.md is synced\n")
    except Exception as e:
        print("\n[!]  Pre-session validation failed, but continuing anyway...")
        print(f"    Error: {e}")
        print(f"    Check {log_path} for details\n")


def run_three_phase_iteration(
    provider: Provider,
    cfg: Config,
    project_path: Path,
    spec_name: str,
    spec_path: Path,
    iteration: int,
    log_dir: Path,
) -> tuple[bool, int]:
    """Run a single 3-phase workflow iteration.

    Args:
        provider: Provider instance
        cfg: Configuration
        project_path: Path to project root
        spec_name: Name of spec
        spec_path: Path to spec directory
        iteration: Current iteration number
        log_dir: Directory for logs

    Returns:
        Tuple of (progress_made, agent_commits)
    """
    tasks_path = spec_path / cfg.tasks_filename

    # ===================================================================
    # PHASE 1: PRE-SESSION VALIDATION
    # ===================================================================
    print(f"\n{'='*80}")
    print(f"PHASE 1: PRE-SESSION VALIDATION")
    print(f"{'='*80}\n")

    validation_log = log_dir / f"validation_{iteration}.log"
    validation_log.parent.mkdir(parents=True, exist_ok=True)

    try:
        validation_result = run_validation(
            spec_name=spec_name,
            spec_path=spec_path,
            project_path=project_path,
            tasks_filename=cfg.tasks_filename,
        )

        # Log validation results
        with validation_log.open("w") as f:
            f.write(f"Iteration {iteration} - Validation Results\n")
            f.write(f"{'='*80}\n\n")
            f.write(validation_result.summary() + "\n\n")

            for val in validation_result.validations:
                if not val.is_valid:
                    f.write(f"Task: {val.task_id} - {val.title}\n")
                    for issue in val.issues:
                        f.write(f"  - {issue}\n")
                    f.write("\n")

        print(validation_result.summary())
        if validation_result.tasks_reset > 0:
            print(f"\n⚠️  {validation_result.tasks_reset} task(s) reset to in-progress")
            print(f"   Check {validation_log} for details")

    except Exception as e:
        logger.warning(f"Validation check failed: {e}")
        print(f"⚠️  Validation check failed: {e}")
        print("   Continuing with implementation phase...")

    # ===================================================================
    # PHASE 2: IMPLEMENTATION SESSION
    # ===================================================================
    print(f"\n{'='*80}")
    print(f"PHASE 2: IMPLEMENTATION SESSION")
    print(f"{'='*80}\n")

    # Get current stats
    stats = read_task_stats(tasks_path)
    progress_summary = f"{stats.done}/{stats.total} tasks complete ({stats.pending} pending, {stats.in_progress} in progress)"

    # Use implementation prompt
    prompt = cfg.implementation_prompt.format(
        spec_name=spec_name,
        progress_summary=progress_summary,
    )

    log_path = log_dir / cfg.log_file_template.format(index=iteration)

    # Run implementation with commit blocking
    agent_commits = 0
    last_commit_before = get_current_commit(project_path)

    try:
        if cfg.block_commits_during_implementation:
            print("🔒 Git commits blocked during implementation\n")
            with block_commits(project_path):
                agent_commits = run_provider(
                    provider,
                    cfg,
                    project_path,
                    prompt,
                    False,  # not dry_run
                    spec_name=spec_name,
                    iteration=iteration,
                    log_path=log_path,
                )
            print("\n🔓 Git commits allowed again\n")
        else:
            agent_commits = run_provider(
                provider,
                cfg,
                project_path,
                prompt,
                False,  # not dry_run
                spec_name=spec_name,
                iteration=iteration,
                log_path=log_path,
            )
    except Exception as e:
        logger.error(f"Implementation session failed: {e}")
        raise

    # ===================================================================
    # PHASE 3: POST-SESSION VERIFICATION
    # ===================================================================
    print(f"\n{'='*80}")
    print(f"PHASE 3: POST-SESSION VERIFICATION")
    print(f"{'='*80}\n")

    verification_log = log_dir / f"verification_{iteration}.log"

    try:
        verification_result = run_verification(
            spec_name=spec_name,
            spec_path=spec_path,
            project_path=project_path,
            make_commits=True,
            tasks_filename=cfg.tasks_filename,
        )

        # Log verification results
        with verification_log.open("w") as f:
            f.write(f"Iteration {iteration} - Verification Results\n")
            f.write(f"{'='*80}\n\n")
            f.write(verification_result.summary() + "\n\n")

            completed = [v for v in verification_result.verifications if v.should_mark_complete]
            incomplete = [v for v in verification_result.verifications if not v.should_mark_complete]

            if completed:
                f.write("✅ Verified and marked complete:\n\n")
                for task in completed:
                    f.write(f"  {task.task_id}: {task.title}\n")
                    if task.files_modified:
                        f.write(f"    Files: {', '.join(task.files_modified)}\n")
                f.write("\n")

            if incomplete:
                f.write("⏸️  Still in progress:\n\n")
                for task in incomplete:
                    f.write(f"  {task.task_id}: {task.title}\n")
                    for issue in task.issues:
                        f.write(f"    - {issue}\n")
                f.write("\n")

            if verification_result.commits_made:
                f.write(f"📝 Commits created:\n")
                for sha in verification_result.commits_made:
                    f.write(f"  {sha}\n")

        print(verification_result.summary())
        if verification_result.tasks_completed > 0:
            print(f"✅ {verification_result.tasks_completed} task(s) verified and marked complete")
        if verification_result.tasks_incomplete > 0:
            print(f"⏸️  {verification_result.tasks_incomplete} task(s) still in progress")
        if verification_result.commits_made:
            print(f"📝 Created {len(verification_result.commits_made)} commit(s)")
        print(f"   Check {verification_log} for details")

    except Exception as e:
        logger.warning(f"Verification failed: {e}")
        print(f"⚠️  Verification failed: {e}")

    # Determine if progress was made
    last_commit_after = get_current_commit(project_path)
    has_new_commit = last_commit_after != last_commit_before
    has_agent_commits = agent_commits > 0
    has_verified_work = verification_result.tasks_completed > 0 if 'verification_result' in locals() else False

    progress_made = has_new_commit or has_agent_commits or has_verified_work

    return progress_made, agent_commits


def run_loop(
    provider: Provider,
    cfg: Config,
    project_path: Path,
    spec_name: str,
    spec_path: Path,
    dry_run: bool,
) -> None:
    """Main orchestration loop."""
    tasks_path = spec_path / cfg.tasks_filename
    if not tasks_path.exists():
        raise RunnerError(f"tasks.md not found at {tasks_path}")
    stats = read_task_stats(tasks_path)
    if stats.total == 0:
        raise RunnerError("No tasks detected in tasks.md.")
    if dry_run:
        _display_dry_run_spec_status(spec_name, spec_path, stats)
        return

    no_commit_streak = 0
    iteration = 0
    log_dir = project_path / cfg.log_dir_name / spec_name
    last_commit = get_current_commit(project_path)

    while True:
        # === Check completion status ===
        stats = read_task_stats(tasks_path)
        remaining = stats.total - stats.done

        # Display enhanced progress information
        safe_print(f"\n{'=' * 80}")
        safe_print(f"SPEC: {spec_name}")
        safe_print(f"{'=' * 80}")
        safe_print(f"Progress: {stats.summary()}")
        safe_print(f"{stats.progress_bar()}")

        # Show next pending tasks
        task_details = read_task_details(tasks_path)
        pending_tasks = [t for t in task_details if t.status == "pending"]
        in_progress_tasks = [t for t in task_details if t.status == "in_progress"]

        if in_progress_tasks:
            safe_print(f"\nIn Progress:")
            for task in in_progress_tasks[:3]:  # Show up to 3
                safe_print(f"  - {task.task_id}: {task.title[:60]}")

        if pending_tasks:
            safe_print(f"\nNext Pending Tasks:")
            for task in pending_tasks[:3]:  # Show up to 3
                safe_print(f"  - {task.task_id}: {task.title[:60]}")

        safe_print(f"{'=' * 80}\n")

        if remaining <= 0:
            print("[OK] All tasks complete. Nothing more to run.")
            return

        iteration += 1

        # === Run iteration based on workflow mode ===
        if cfg.enable_three_phase_workflow:
            # 3-PHASE WORKFLOW
            print(f"\n[Iteration {iteration}] Running 3-phase workflow (validate → implement → verify)...")

            try:
                progress_made, agent_commits = run_three_phase_iteration(
                    provider=provider,
                    cfg=cfg,
                    project_path=project_path,
                    spec_name=spec_name,
                    spec_path=spec_path,
                    iteration=iteration,
                    log_dir=log_dir,
                )

                if progress_made:
                    print(f"\n[OK] Progress made in 3-phase workflow")
                    no_commit_streak = 0
                else:
                    print(f"\n[!]  No verified progress this iteration")
                    no_commit_streak += 1
                    print(f"     Circuit breaker streak: {no_commit_streak}/{cfg.no_commit_limit}")

                    if no_commit_streak >= cfg.no_commit_limit:
                        print(f"\n[!]  No progress for {cfg.no_commit_limit} consecutive iterations. Stopping.")
                        return

            except Exception as e:
                logger.error(f"3-phase workflow iteration failed: {e}")
                print(f"\n❌ Iteration failed: {e}")
                no_commit_streak += 1
                if no_commit_streak >= cfg.no_commit_limit:
                    print(f"\n[!]  Too many failures. Stopping.")
                    return

        else:
            # LEGACY WORKFLOW
            # Run pre-session validation before each iteration to sync tasks.md with codebase
            if cfg.enable_pre_session_validation:
                run_pre_session_validation(provider, cfg, project_path, spec_name, spec_path)

            # Build prompt with progress summary (no specific task assignment)
            progress_summary = f"{stats.done}/{stats.total} tasks complete ({stats.pending} pending, {stats.in_progress} in progress)"
            prompt = cfg.prompt_template.format(
                spec_name=spec_name,
                progress_summary=progress_summary
            )

            log_path = log_dir / cfg.log_file_template.format(index=iteration)
            print(f"\n[Iteration {iteration}] Letting Claude choose what to work on...")

            agent_commits = run_provider(
                provider,
                cfg,
                project_path,
                prompt,
                dry_run,
                spec_name=spec_name,
                iteration=iteration,
                log_path=log_path,
            )

            new_last_commit, no_commit_streak = _check_commit_progress(
                project_path, last_commit, no_commit_streak, cfg
            )

            # Check if progress was made (multiple signals)
            has_new_commit = new_last_commit != last_commit
            has_agent_commits = agent_commits > 0
            has_worker_activity = has_claude_flow_activity(project_path, since_seconds=300)

            if has_new_commit or has_agent_commits or has_worker_activity:
                # Progress made - reset circuit breaker
                if has_agent_commits:
                    print(f"[OK] Progress made (agents: {agent_commits} commit(s))")
                elif has_worker_activity:
                    print(f"[OK] Progress made (claude-flow workers active)")
                else:
                    print(f"[OK] Progress made (new commit)")
                no_commit_streak = 0
            else:
                # No commits, no worker activity
                print(f"[!]  No commits detected this iteration")
                print(f"     Circuit breaker streak: {no_commit_streak}/{cfg.no_commit_limit}")

            last_commit = new_last_commit


def main() -> int:
    """Script entry point."""
    args = parse_args()
    cfg = load_config(args.config)

    try:
        provider_name = ensure_provider(args.provider)
        model = ensure_model(provider_name, args.model)
        provider = create_provider(provider_name, cfg.codex_command, model)
        project = ensure_project(cfg, args.project, args.refresh_cache)

        if not args.dry_run:
            check_clean_working_tree(project)
            # Note: No longer checking for spec-workflow MCP server
            # We parse tasks.md directly instead

        selection = _choose_spec_or_all(project, cfg, args.spec)
        if isinstance(selection, AllSpecsSentinel):
            run_all_specs(provider, cfg, project, args.dry_run)
        elif isinstance(selection, MultipleSpecsSentinel):
            run_multiple_specs(provider, cfg, project, selection.specs, args.dry_run)
        elif isinstance(selection, PollPendingTasksSentinel):
            if args.dry_run:
                print("\n[DRY-RUN MODE] Would poll for pending tasks every 10 seconds.")
                print("When found, would automatically start executing them.")
            else:
                poll_for_pending_tasks(project, cfg)
                run_all_specs(provider, cfg, project, args.dry_run)
        else:
            spec_name, spec_path = selection
            run_loop(provider, cfg, project, spec_name, spec_path, args.dry_run)
        return 0
    except KeyboardInterrupt:
        print("\nAborted by user.")
        return 130
    except (RunnerError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
