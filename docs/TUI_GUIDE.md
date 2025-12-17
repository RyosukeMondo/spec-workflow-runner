# TUI Usage Guide

A comprehensive guide to using the spec-workflow-tui terminal interface for managing and monitoring spec workflows.

## Table of Contents

- [Getting Started](#getting-started)
- [Basic Navigation](#basic-navigation)
- [Starting and Monitoring Runners](#starting-and-monitoring-runners)
- [Managing Multiple Runners](#managing-multiple-runners)
- [Advanced Features](#advanced-features)
- [Configuration](#configuration)
- [FAQ](#faq)
- [Troubleshooting](#troubleshooting)

## Getting Started

### Prerequisites

Before using the TUI, ensure you have:

1. **Installed spec-workflow-runner**:
   ```bash
   cd /path/to/spec-workflow-runner
   source .venv/bin/activate
   pip install -e '.[dev]'
   ```

2. **Valid config.json**: Create a `config.json` in your working directory:
   ```json
   {
     "repos_root": "/path/to/your/projects",
     "cache_dir": "~/.cache/spec-workflow-runner",
     "cache_max_age_days": 7,
     "prompt_template": "Work on the single next task for spec {spec_name}...",
     "tui_refresh_seconds": 2,
     "tui_log_tail_lines": 200,
     "tui_min_terminal_cols": 80,
     "tui_min_terminal_rows": 24
   }
   ```

3. **Projects with specs**: Ensure your projects under `repos_root` contain `.spec-workflow/specs/` directories with task definitions.

### Launching the TUI

From your project directory or any directory with a `config.json`:

```bash
# Basic launch
spec-workflow-tui

# Custom config path
spec-workflow-tui --config /path/to/config.json

# Debug mode (verbose logging)
spec-workflow-tui --debug

# View help
spec-workflow-tui --help
```

### First Look

When the TUI launches, you'll see a multi-panel interface:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ LEFT PANEL          │ RIGHT PANEL (TOP)                                  │
│ Project Tree        │ Status Panel                                       │
│                     │                                                    │
│ ▼ my-project        │ Project: /home/user/projects/my-project           │
│   ▶ feature-spec    │ Spec: feature-spec                                 │
│   ✓ completed-spec  │ Tasks: ████████░░ 8/10 (80%)                       │
│                     │                                                    │
│ ▼ another-project   │ Provider: Codex (claude-sonnet-4.5)                │
│   ⚠ crashed-spec    │ Running: 00:05:23  PID: 12345                      │
│                     │                                                    │
├─────────────────────┼────────────────────────────────────────────────────┤
│                     │ RIGHT PANEL (BOTTOM)                               │
│                     │ Log Viewer                                         │
│                     │                                                    │
│                     │ [2025-01-15 10:30] INFO: Starting task 3.1         │
│                     │ [2025-01-15 10:30] DEBUG: Reading file...          │
│                     │                                                    │
└─────────────────────┴────────────────────────────────────────────────────┘
│ Footer: 2 runners active | Press ? for help                              │
└───────────────────────────────────────────────────────────────────────────┘
```

**Layout breakdown**:
- **Left Panel (30%)**: Hierarchical tree of all projects and specs
- **Right Top (42%)**: Status panel showing selected spec details
- **Right Bottom (28%)**: Log viewer with auto-scrolling output
- **Footer**: Status bar with runner count and help hint

## Basic Navigation

### Moving Through the Tree

Use arrow keys or vim-style keybindings to navigate:

| Key | Action | Example |
|-----|--------|---------|
| `↓` or `j` | Move down | Highlight next project/spec |
| `↑` or `k` | Move up | Highlight previous project/spec |
| `Enter` | Select/Expand | Expand a project, or select a spec |
| `g` | Jump to top | Go to first project in list |
| `G` | Jump to bottom | Go to last spec in tree |

**Navigation tips**:
- Press `Enter` on a project to expand/collapse its specs
- Press `Enter` on a spec to view its details in the status panel
- Selection is highlighted with a reverse color scheme

### Filtering Specs

Quickly find specs by name:

1. **Enter filter mode**: Press `/`
2. **Type search text**: The tree filters in real-time
3. **Navigate results**: Use arrow keys to move between matches
4. **Exit filter mode**: Press `Esc` to clear filter

**Example workflow**:
```
# You want to find all specs related to "auth"
1. Press /
2. Type "auth"
3. Tree shows only: auth-login, auth-signup, oauth-integration
4. Navigate with ↑/↓ and press Enter to select
5. Press Esc to show all specs again
```

### View Filtering

Show only relevant specs:

| Key | Action | What it shows |
|-----|--------|---------------|
| `u` | Toggle unfinished | Only specs with pending or in-progress tasks |
| `a` | Show all active | List of all currently running specs across projects |

**When to use**:
- Use `u` when you have many completed specs cluttering the view
- Use `a` to get a quick overview of all active work across projects

## Starting and Monitoring Runners

### How to Start a Workflow

**Step-by-step tutorial**:

1. **Navigate to a spec** with unfinished tasks
   ```
   Use ↓ to highlight the spec
   ```

2. **Press `s`** to start the runner
   ```
   The TUI will prompt: "Select AI provider"
   ```

3. **Choose a provider**
   ```
   1. codex    - Codex with MCP server support
   2. claude   - Claude CLI (automation mode, no prompts)
   Select option:
   ```

4. **Provider validation**:
   - The TUI checks if your working tree is clean (no uncommitted changes)
   - For Codex, it verifies the `spec-workflow` MCP server is configured
   - If validation fails, an error message appears in the footer

5. **Runner starts**:
   ```
   Status changes to: ▶ Running
   Duration counter starts: 00:00:01, 00:00:02...
   Log panel shows: "Starting spec workflow for feature-spec..."
   ```

### Monitoring Progress

Once a runner is active, the status panel shows:

**Task Progress**:
- Progress bar: `████████░░ 8/10 (80%)`
- Task breakdown: 8 completed, 1 in-progress, 1 pending

**Runner Information**:
- Provider: `Codex (claude-sonnet-4.5)`
- Running duration: `00:15:42` (updates every second)
- Process ID: `PID: 12345`
- Last commit: `abc1234 feat: add authentication module`

**Live Logs**:
- Log panel auto-scrolls as new lines appear
- Last 200 lines visible (configurable)
- ANSI color codes preserved for readability

### Stopping a Runner

**To stop a running spec**:

1. **Select the spec** with an active runner
2. **Press `x`** to stop
3. **Confirm the prompt**: "Stop runner? (y/n)"
   - `y`: Sends SIGTERM, waits 5 seconds, then SIGKILL if needed
   - `n`: Cancels the stop operation

**What happens when stopped**:
- Process receives SIGTERM (graceful shutdown)
- If process doesn't exit in 5 seconds, SIGKILL is sent
- Status changes to: `■ Stopped`
- Log panel shows: "Runner stopped by user"

### Restarting a Runner

**To restart a stopped or completed spec**:

1. **Select the spec**
2. **Press `r`** to restart
3. The runner starts with the last-used provider (no prompt)

**When to restart**:
- After fixing an issue that caused a crash
- After manually completing tasks outside the TUI
- To resume work on a completed spec with new tasks

## Managing Multiple Runners

### Running Multiple Specs Concurrently

The TUI supports running multiple specs simultaneously:

**Example workflow: Parallel feature development**

1. **Start first spec**:
   ```
   Navigate to: project-a / feature-auth
   Press: s → Select provider → Codex
   Status: ▶ Running (00:01:15)
   ```

2. **Start second spec** (different project):
   ```
   Navigate to: project-b / refactor-api
   Press: s → Select provider → Claude
   Status: ▶ Running (00:00:45)
   ```

3. **Monitor both**:
   ```
   Footer shows: "2 runners active"
   Switch between specs with ↑/↓ to view logs
   ```

**Performance considerations**:
- Each runner is an independent subprocess
- 5+ concurrent runners may slow down your system
- TUI will show a performance warning at 5+ runners

### Viewing All Active Runners

**Press `a` to see the "All Active Runners" view**:

```
╭─ All Active Runners ────────────────────────────────╮
│                                                      │
│  1. project-a / feature-auth                         │
│     Provider: Codex  Running: 00:15:32  PID: 12345  │
│                                                      │
│  2. project-b / refactor-api                         │
│     Provider: Claude  Running: 00:08:17  PID: 12346 │
│                                                      │
│  3. project-c / fix-bug                              │
│     Provider: Codex  Running: 00:02:01  PID: 12347  │
│                                                      │
╰──────────────────────────────────────────────────────╯
```

**What you see**:
- Project and spec names
- Provider and model
- Running duration
- Process ID (PID)

**Use cases**:
- Quick overview of all work in progress
- Identify long-running specs that might need attention
- Find PIDs for manual process management

### Switching Between Active Specs

**To monitor different runners**:

1. Navigate to the spec in the tree (↑/↓)
2. Press `Enter` to select it
3. Status panel and log viewer update immediately

**The TUI preserves**:
- Individual runner states
- Separate log files for each spec
- Progress tracking per spec

## Advanced Features

### Log Panel Controls

The log viewer provides several controls:

| Key | Action | Behavior |
|-----|--------|----------|
| `l` | Toggle logs | Show/hide the log panel |
| `L` | Re-enable auto-scroll | Resume auto-scrolling to newest logs |
| Mouse scroll | Manual scroll | Auto-scroll disables when you scroll up |

**Auto-scroll behavior**:
- By default, logs auto-scroll to show newest entries
- Scrolling up disables auto-scroll (view old logs)
- Press `L` to jump back to newest logs and resume auto-scroll

**Example use case**:
```
# You notice an error in old logs
1. Scroll up with mouse or Page Up
2. Read the error context (auto-scroll disabled)
3. Press L to return to live logs
```

### Filtering by Task Status

**Show only unfinished specs** with `u`:

```
Before (all specs):
▼ my-project
  ▶ active-spec (5/10 tasks)
  ✓ completed-spec (10/10 tasks)
  ■ stopped-spec (3/10 tasks)

After pressing 'u':
▼ my-project
  ▶ active-spec (5/10 tasks)
  ■ stopped-spec (3/10 tasks)
```

**Benefits**:
- Focus on work in progress
- Reduce visual clutter
- Quickly identify next actionable spec

### Help and Configuration Panels

**View keybindings** with `?`:

```
╭─ Keybindings ────────────────────────────────────╮
│                                                   │
│  Navigation                                       │
│    ↑/k        Move up                             │
│    ↓/j        Move down                           │
│    Enter      Select/Expand                       │
│    g          Jump to top                         │
│    G          Jump to bottom                      │
│    /          Filter mode                         │
│                                                   │
│  Runner Control                                   │
│    s          Start runner                        │
│    x          Stop runner                         │
│    r          Restart runner                      │
│                                                   │
│  View Control                                     │
│    l          Toggle logs                         │
│    L          Re-enable auto-scroll               │
│    u          Toggle unfinished                   │
│    a          Show all active                     │
│                                                   │
│  Meta                                             │
│    ?          Help (this panel)                   │
│    c          Config                              │
│    q          Quit                                │
│                                                   │
╰───────────────────────────────────────────────────╯
```

**View configuration** with `c`:

```
╭─ Configuration ───────────────────────────────────╮
│                                                   │
│  Config file: /home/user/project/config.json     │
│                                                   │
│  TUI Settings:                                    │
│    Refresh interval: 2 seconds                    │
│    Log tail lines: 200                            │
│    Min terminal size: 80 x 24                     │
│                                                   │
│  Project Settings:                                │
│    Repos root: /home/user/projects                │
│    Cache dir: ~/.cache/spec-workflow-runner       │
│    Cache max age: 7 days                          │
│                                                   │
╰───────────────────────────────────────────────────╯
```

### Understanding Status Badges

The tree view uses visual indicators:

| Badge | Meaning | Details |
|-------|---------|---------|
| `✓` (green) | Complete | All tasks done, no runner active |
| `▶` (yellow) | Running | Runner is actively executing |
| `⚠` (red) | Crashed | Runner exited with non-zero code |
| `■` (dim) | Stopped | Runner was stopped or hasn't started |

**Additional indicators**:
- Task ratio: `(8/10 tasks)` shows completed vs. total
- In-progress count: `▶ Active (2 in-progress)` shows current work

## Configuration

### TUI-Specific Settings

Add these to your `config.json`:

```json
{
  "tui_refresh_seconds": 2,
  "tui_log_tail_lines": 200,
  "tui_min_terminal_cols": 80,
  "tui_min_terminal_rows": 24
}
```

**Setting explanations**:

#### `tui_refresh_seconds` (default: 2)
- How often to poll for file changes (tasks.md, logs)
- Lower values = more responsive, higher CPU usage
- Recommended range: 1-5 seconds
- Example: Set to `1` for sub-second responsiveness

#### `tui_log_tail_lines` (default: 200)
- Maximum log lines to display in viewer
- Higher values = more history, more memory
- Recommended range: 100-500 lines
- Example: Set to `500` for debugging long workflows

#### `tui_min_terminal_cols` (default: 80)
- Minimum terminal width required
- TUI shows warning if terminal is narrower
- Recommended minimum: 80 (standard terminal)
- Example: Set to `120` if you always use wide terminals

#### `tui_min_terminal_rows` (default: 24)
- Minimum terminal height required
- TUI shows warning if terminal is shorter
- Recommended minimum: 24 (standard terminal)
- Example: Set to `40` for more vertical space

### Performance Tuning

**For fast systems with many projects**:
```json
{
  "tui_refresh_seconds": 1,
  "tui_log_tail_lines": 500
}
```

**For slower systems or limited resources**:
```json
{
  "tui_refresh_seconds": 5,
  "tui_log_tail_lines": 100
}
```

**For debugging and troubleshooting**:
```bash
spec-workflow-tui --debug
```

Debug mode enables:
- Verbose logging to `~/.cache/spec-workflow-runner/tui.log`
- Performance metrics (poll timings, memory usage)
- File system operation details

### Logs Location

All TUI logs are written to:
```
~/.cache/spec-workflow-runner/tui.log
```

**Log format** (structured JSON):
```json
{"timestamp": "2025-01-15T10:30:00Z", "level": "info", "event": "runner_start", "context": {"project": "/home/user/projects/my-project", "spec": "feature-spec", "provider": "codex", "pid": 12345}}
{"timestamp": "2025-01-15T10:35:00Z", "level": "info", "event": "runner_stop", "context": {"pid": 12345, "exit_code": 0}}
```

**Log rotation**:
- Max size: 10MB per file
- Backups: 3 old logs kept
- Files: `tui.log`, `tui.log.1`, `tui.log.2`, `tui.log.3`

## FAQ

### What happens to runners if the TUI crashes?

**Answer**: Runners continue running in the background.

The TUI persists runner state to `~/.cache/spec-workflow-runner/runner_state.json`. When you restart the TUI:
1. It reads the state file
2. Checks if PIDs are still running
3. Restores runners as "Running" if processes exist
4. Cleans up stale entries if processes are gone

**Example recovery**:
```bash
# TUI crashed, but runners are still going
ps aux | grep spec-workflow-run
# Shows PIDs: 12345, 12346

# Restart TUI
spec-workflow-tui

# TUI shows: "2 runners restored from previous session"
```

### How do I see all active runners across projects?

**Answer**: Press `a` to view the "All Active Runners" panel.

This shows:
- All running specs across all projects
- Provider, duration, and PID for each
- Quick way to assess total workload

### Can I run multiple TUIs simultaneously?

**Answer**: Yes, but with caveats.

**Same config.json**:
- Both TUIs will share the same `runner_state.json`
- State updates may conflict (last write wins)
- Not recommended for controlling the same runners

**Different config.json**:
- Separate TUIs with different `repos_root` work fine
- Each has its own state file (based on config hash)
- Safe for managing different project sets

**Recommended approach**: Use one TUI instance per `repos_root`.

### How do I stop a runner that's stuck?

**Answer**: Use the TUI's stop command (`x`) with SIGKILL fallback.

**Step-by-step**:
1. Select the stuck spec
2. Press `x` to stop
3. TUI sends SIGTERM and waits 5 seconds
4. If process doesn't exit, TUI sends SIGKILL
5. Process is forcefully terminated

**Manual fallback** (if TUI can't stop it):
```bash
# Press 'a' to see all runners and find the PID
# Then manually kill:
kill -9 <PID>

# Clean up state:
rm ~/.cache/spec-workflow-runner/runner_state.json
```

### Can I edit tasks.md while a runner is active?

**Answer**: Yes, but be careful.

**Safe edits**:
- Marking completed tasks: `[x]` (won't confuse the runner)
- Adding new tasks at the end
- Fixing typos in task descriptions

**Risky edits**:
- Changing task IDs or order (runner may lose track)
- Deleting in-progress tasks (runner may fail)
- Modifying task content the runner is currently working on

**Best practice**: Let the runner complete its current task before editing.

### What if I need to make commits while the runner is active?

**Answer**: The runner is configured to commit automatically.

The `prompt_template` in `config.json` instructs the AI to:
- Run `git add` and `git commit` when work is done
- Make atomic commits for logical units of work
- Never ask for permission (autonomous mode)

**If you need to commit manually**:
1. Stop the runner (`x`)
2. Make your commits
3. Restart the runner (`r`)

The TUI tracks commits made since runner start and displays them in the status panel.

### How do I clear orphaned runner processes?

**Answer**: Use the TUI's state recovery or manual cleanup.

**Automatic cleanup** (on TUI restart):
```bash
spec-workflow-tui
# TUI checks PIDs, cleans up stale entries automatically
```

**Manual cleanup**:
```bash
# Find orphaned processes
ps aux | grep spec-workflow-run

# Kill them
kill <PID>

# Clear state file
rm ~/.cache/spec-workflow-runner/runner_state.json
```

**Prevent orphans**: Always quit the TUI with `q` (not Ctrl+Z or terminal close).

## Troubleshooting

### Terminal too small

**Problem**: Footer shows "Terminal too small (current: 70x20, minimum: 80x24)"

**Solutions**:
1. **Resize terminal**: Drag window corners or maximize
2. **Adjust config**: Lower minimum size in `config.json`:
   ```json
   {
     "tui_min_terminal_cols": 70,
     "tui_min_terminal_rows": 20
   }
   ```
3. **Use a different terminal**: Some terminals have size restrictions

**Impact**: Layout may be cramped if terminal is too small.

### No projects found

**Problem**: Tree view shows "No projects with .spec-workflow found under {repos_root}"

**Diagnosis**:
1. **Check config.json**:
   ```bash
   cat config.json | grep repos_root
   ```
   Ensure path is correct

2. **Check directory structure**:
   ```bash
   ls -la /path/to/repos_root/*/\.spec-workflow
   ```
   Projects need `.spec-workflow/specs/` directories

3. **Verify permissions**:
   ```bash
   ls -ld /path/to/repos_root
   ```
   Ensure read/execute permissions

**Solutions**:
- Update `repos_root` in `config.json`
- Create `.spec-workflow/specs/` in your projects
- Fix permissions: `chmod -R u+rx /path/to/repos_root`

### Config errors on startup

**Problem**: TUI exits with "Error loading config: ..."

**Common causes**:

1. **Malformed JSON**:
   ```
   Error: Expecting property name enclosed in double quotes
   ```
   **Solution**: Validate JSON syntax
   ```bash
   python -m json.tool config.json
   ```

2. **Missing required fields**:
   ```
   Error: Missing required field: repos_root
   ```
   **Solution**: Add required fields to `config.json`

3. **Invalid paths**:
   ```
   Error: repos_root path does not exist
   ```
   **Solution**: Use absolute paths or verify relative paths

**Debug steps**:
```bash
# Validate config
python -c "import json; print(json.load(open('config.json')))"

# Use debug mode
spec-workflow-tui --debug
# Check logs: ~/.cache/spec-workflow-runner/tui.log
```

### Orphaned runners after crash

**Problem**: Runners continue after TUI exits unexpectedly

**Diagnosis**:
```bash
# Find orphaned processes
ps aux | grep spec-workflow-run

# Check state file
cat ~/.cache/spec-workflow-runner/runner_state.json
```

**Solutions**:

1. **Restart TUI** (auto-recovery):
   ```bash
   spec-workflow-tui
   # TUI restores or cleans up runners
   ```

2. **Manual cleanup**:
   ```bash
   # Kill processes
   pkill -f spec-workflow-run

   # Or kill specific PIDs
   kill 12345 12346

   # Clear state
   rm ~/.cache/spec-workflow-runner/runner_state.json
   ```

**Prevention**: Always quit with `q`, not `Ctrl+Z` or closing terminal.

### Logs not updating

**Problem**: Log panel shows old content or "Waiting for logs..."

**Diagnosis**:

1. **Check log file exists**:
   ```bash
   ls -la .spec-workflow/specs/my-spec/Implementation\ Logs/
   ```

2. **Check file is being written**:
   ```bash
   tail -f .spec-workflow/specs/my-spec/Implementation\ Logs/latest.log
   ```

3. **Check auto-scroll state**:
   - Did you scroll up? (disables auto-scroll)

**Solutions**:
1. **Re-enable auto-scroll**: Press `L`
2. **Increase refresh rate**:
   ```json
   {"tui_refresh_seconds": 1}
   ```
3. **Restart runner**: Press `x` then `r`
4. **Check file permissions**: Ensure TUI can read log files

### Runner won't start

**Problem**: Press `s` but runner shows error

**Common errors**:

1. **"Working tree not clean"**:
   ```
   Error: Uncommitted changes detected. Commit or stash before starting.
   ```
   **Solution**:
   ```bash
   git status
   git add .
   git commit -m "WIP: save changes"
   ```

2. **"spec-workflow MCP server not found"** (Codex only):
   ```
   Error: MCP server check failed. Run: codex mcp
   ```
   **Solution**:
   ```bash
   codex mcp
   # Configure spec-workflow server
   ```

3. **"No unfinished tasks"**:
   ```
   Warning: Spec has no pending tasks
   ```
   **Solution**: Add tasks to `tasks.md` or select a different spec

### Slow performance / High CPU

**Problem**: TUI feels sluggish, CPU usage high

**Diagnosis**:
```bash
# Run in debug mode
spec-workflow-tui --debug

# Check logs for poll timings
grep "poll_cycle" ~/.cache/spec-workflow-runner/tui.log
```

**Solutions**:

1. **Reduce refresh rate**:
   ```json
   {"tui_refresh_seconds": 5}
   ```

2. **Reduce log buffer**:
   ```json
   {"tui_log_tail_lines": 100}
   ```

3. **Close other programs**: Free up CPU/memory

4. **Limit concurrent runners**: Stop runners you're not actively monitoring

**Expected performance**:
- CPU idle: <5%
- CPU with 2 runners: 5-15%
- Startup time: <500ms with cache

### State file corrupted

**Problem**: TUI shows error about `runner_state.json`

**Symptoms**:
```
Warning: Corrupted state file detected. Deleting and continuing with empty state.
```

**What happened**: The JSON file was malformed (incomplete write, manual edit, etc.)

**Impact**: Harmless. TUI deletes the file and starts fresh.

**Prevention**: Don't manually edit `runner_state.json`

---

## Additional Resources

- **Main README**: See [README.md](../README.md) for installation and basic usage
- **Requirements**: See [requirements.md](../.spec-workflow/specs/tui-unified-runner/requirements.md) for detailed feature specifications
- **Issue tracking**: Report bugs at [GitHub Issues](https://github.com/your-org/spec-workflow-runner/issues)

## Quick Reference Card

```
Navigation         │ Runner Control    │ View Control
───────────────────┼──────────────────┼──────────────
↑/k    Move up     │ s   Start runner │ l   Toggle logs
↓/j    Move down   │ x   Stop runner  │ L   Auto-scroll
Enter  Select      │ r   Restart      │ u   Unfinished
g      Jump top    │                  │ a   All active
G      Jump bottom │ Meta             │
/      Filter      │ ?   Help         │
                   │ c   Config       │
                   │ q   Quit         │
```

**Most Common Workflow**:
1. Launch: `spec-workflow-tui`
2. Navigate: `↓` to find spec
3. Start: `s` → choose provider
4. Monitor: Watch status panel and logs
5. Stop: `x` when done
6. Quit: `q`
