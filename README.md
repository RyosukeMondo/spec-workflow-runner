# spec-workflow-runner

Tools that keep the spec-workflow loop moving:

- `spec-workflow-run` – orchestrates AI provider runs (Codex or Claude) until all tasks in a spec are complete.
- `spec-workflow-monitor` – Rich-based dashboard to watch progress in real time.
- `spec-workflow-pipx` – bootstraps/updates the pipx install used for global access.

## Installation

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e '.[dev]'
```

The editable install provides both CLIs on your `$PATH` and pulls in the dev-only tooling
configured in `pyproject.toml`.

## Usage

Each CLI ships with `--help`, but the common flows look like:

```bash
# Interactive mode (prompts for provider, project, and spec)
spec-workflow-run

# Specify everything via CLI arguments
spec-workflow-run --project /path/to/repo --spec my-spec --provider claude

# Mix interactive and CLI arguments
spec-workflow-run --provider codex  # will prompt for project and spec
spec-workflow-run --project /path/to/repo  # will prompt for provider and spec

# Other options
spec-workflow-run --dry-run  # simulate only
spec-workflow-run --refresh-cache  # force refresh project cache
spec-workflow-monitor --project /path/to/repo --spec my-spec
```

### Providers

The runner supports multiple AI providers via the `--provider` flag:

- **codex**: Uses the Codex backend with full MCP server support
- **claude**: Uses the Claude CLI with `--dangerously-skip-permissions` (automation mode, no prompts)

If `--provider` is not specified, the CLI will prompt you interactively to choose:

```
Select AI provider
  1. codex    - Codex with MCP server support
  2. claude   - Claude CLI (automation mode, no prompts)
Select option (or q to quit):
```

Example using Claude:
```bash
spec-workflow-run --project /path/to/repo --spec my-spec --provider claude
```

Both commands expect to find a `config.json` in the working directory unless a different
`--config` path is provided.

## TUI Mode

The `spec-workflow-tui` command provides an interactive terminal UI for managing and monitoring multiple spec workflows simultaneously.

### Features

- Real-time monitoring of multiple projects and specs
- Start, stop, and restart runners with keyboard shortcuts
- Live log tailing with auto-scroll
- Task progress tracking with visual indicators
- Status badges showing runner state (running, stopped, crashed, completed)
- Multi-panel layout (project tree, status panel, log viewer, footer)
- Filter and navigate hierarchical project/spec structure

### Usage

Launch the TUI from your project directory:

```bash
# Basic usage (uses ./config.json by default)
spec-workflow-tui

# Specify custom config path
spec-workflow-tui --config /path/to/config.json

# Enable debug logging
spec-workflow-tui --debug

# Show help
spec-workflow-tui --help
```

The TUI expects a `config.json` in the current directory or the path specified by `--config`.

### Keybindings

The TUI uses vim-style keybindings for navigation:

| Key | Action | Description |
|-----|--------|-------------|
| **Navigation** | | |
| `↑` / `k` | Move up | Navigate up in the project/spec tree |
| `↓` / `j` | Move down | Navigate down in the project/spec tree |
| `Enter` | Select/Expand | Select spec or expand project |
| `g` | Jump to top | Jump to the first project |
| `G` | Jump to bottom | Jump to the last spec |
| `/` | Filter mode | Enter filter mode to search specs |
| **Runner Control** | | |
| `s` | Start runner | Start a runner for the selected spec |
| `x` | Stop runner | Stop the active runner for selected spec |
| `r` | Restart runner | Restart the runner for selected spec |
| **View Control** | | |
| `l` | Toggle logs | Show/hide the log panel |
| `L` | Re-enable auto-scroll | Re-enable auto-scrolling for logs |
| `u` | Toggle unfinished | Show only specs with unfinished tasks |
| `a` | Show all active | List all active runners across projects |
| **Meta** | | |
| `?` | Help | Show help panel with keybindings |
| `c` | Config | Show configuration panel |
| `q` | Quit | Exit the TUI (prompts if runners active) |

### Configuration

Add these optional settings to your `config.json` to customize TUI behavior:

```json
{
  "tui_refresh_seconds": 2,
  "tui_log_tail_lines": 200,
  "tui_min_terminal_cols": 80,
  "tui_min_terminal_rows": 24
}
```

**TUI Settings:**

- `tui_refresh_seconds` (default: `2`): How often to poll for file changes (in seconds)
- `tui_log_tail_lines` (default: `200`): Maximum number of log lines to display in the log viewer
- `tui_min_terminal_cols` (default: `80`): Minimum terminal width required
- `tui_min_terminal_rows` (default: `24`): Minimum terminal height required

All TUI settings must be positive integers. If your terminal is smaller than the minimum size, the TUI will show a warning in the footer.

### Usage Examples

**Monitor multiple projects:**
```bash
# Launch TUI and navigate to different projects
spec-workflow-tui
# Use ↑/↓ to navigate, Enter to expand projects
# Press 'a' to see all active runners
```

**Start a workflow:**
```bash
# Navigate to a spec with unfinished tasks
# Press 's' to start the runner
# Press 'l' to toggle the log panel and watch progress
```

**Debug mode:**
```bash
# Enable detailed logging for troubleshooting
spec-workflow-tui --debug
# Logs are written to ~/.cache/spec-workflow-runner/tui.log
```

### Troubleshooting

**Terminal too small:**
- **Problem**: Warning message "Terminal too small" appears in footer
- **Solution**: Resize your terminal window or adjust `tui_min_terminal_cols`/`tui_min_terminal_rows` in config.json

**No projects found:**
- **Problem**: TUI shows empty project tree
- **Solution**: Verify your `repos_root` in config.json points to the correct directory containing spec-workflow projects

**Config errors:**
- **Problem**: TUI fails to start with config error
- **Solution**: Validate your config.json syntax and ensure all required fields are present. Check the error message for specific issues.

**Orphaned runners:**
- **Problem**: Runner processes remain after TUI crash
- **Solution**: The TUI tracks active runners in `~/.cache/spec-workflow-runner/runner_state.json`. Manually kill orphaned processes with `ps aux | grep spec-workflow-run` and `kill <PID>`, then restart the TUI to clean up state.

**Logs not updating:**
- **Problem**: Log panel shows old content
- **Solution**: Press 'L' to re-enable auto-scroll. Check that the log file exists and is being written to.

### Graceful Shutdown

When you press `q` to quit, the TUI checks for active runners:

- **Active runners present**: Prompts "N runners active. Stop all and quit? (y/n/c)"
  - `y`: Stop all runners and quit
  - `n`: Quit without stopping (detach runners)
  - `c`: Cancel and return to TUI
- **No active runners**: Quits immediately

On SIGTERM (e.g., `kill <pid>`), the TUI stops all runners automatically and exits.

### Logs

The TUI writes structured JSON logs to `~/.cache/spec-workflow-runner/tui.log` with automatic rotation (10MB max, 3 backups). Use `--debug` for verbose logging including performance metrics.

### Project Discovery Cache

To speed up project discovery, `spec-workflow-run` caches the list of projects found under `repos_root`. The cache:

- **Location**: `~/.cache/spec-workflow-runner/projects.json` (configurable via `cache_dir` in config.json)
- **Auto-refresh**: Cache expires after 7 days by default (configurable via `cache_max_age_days`)
- **Manual refresh**: Use `--refresh-cache` flag to force a fresh scan
- **Auto-invalidation**: Cache invalidates automatically when `repos_root` changes

When using cached results, you'll see:
```bash
Using cached projects (scanned 2 days ago)
```

When the cache is refreshed, you'll see:
```bash
Scanning for projects...
Found 5 project(s). Cache updated.
```

To adjust cache settings in `config.json`:
```json
{
  "cache_dir": "~/.cache/spec-workflow-runner",
  "cache_max_age_days": 7
}
```

### Configuration

If Codex MCP servers take longer than the default 10 seconds to boot or respond,
set `codex_config_overrides` inside `config.json`. Each key maps to a Codex
configuration dotted path:

```json
"codex_config_overrides": {
  "mcp_servers.spec-workflow.tool_timeout_sec": 60,
  "mcp_servers.spec-workflow.startup_timeout_sec": 60
}
```

The runner injects these via `codex -c ...` so every invocation automatically
inherits the longer timeout without editing global Codex settings.

### Task Tracking with MCP

When using **Codex** with the `spec-workflow` MCP server, the AI automatically detects and marks tasks as complete via the MCP tool. No manual task tracking instructions needed in your prompt.

The MCP server provides the AI with:
- Automatic task status detection (pending, in-progress, completed)
- Task completion marking when work is done
- Task list synchronization with `tasks.md`

**For Codex users**: The spec-workflow MCP integration handles task tracking automatically. Your prompt template only needs to focus on work completion and commits.

**For Claude CLI users**: Task tracking is passive (monitors `tasks.md` checkbox changes). The AI would need explicit instructions to manually edit task checkboxes, but this is less reliable than MCP integration.

#### MCP Server Check

The runner automatically verifies that the `spec-workflow` MCP server is configured in the project directory before starting:

```bash
# Example: successful check
✓ spec-workflow MCP server detected for Codex

# Example: missing MCP server (aborts with error)
spec-workflow MCP server not found for Codex.
   The spec-workflow MCP server is required for automatic task tracking.
   Please configure it by running: codex mcp
   Or check your MCP server configuration.
```

**Important**: The MCP server check runs `{provider} mcp list` from the project directory, since MCP servers are configured per-project. Make sure your project has the `spec-workflow` MCP server configured.

The check can be skipped by using `--dry-run` mode.

### Prompt Template

Customize how the AI is prompted via `prompt_template` in `config.json`:

```json
"prompt_template": "Work on the single next task for spec {spec_name}. When you complete a logical unit of work, you MUST run 'git add' followed by 'git commit' with a clear message. DO NOT just stage files - you must actually commit them. DO NOT ask permission - just commit immediately when work is done. Make atomic commits for each semantic group of changes."
```

**Key instructions for reliable commits**:
- ✅ Explicitly mention `git add` and `git commit` commands
- ✅ Emphasize "MUST commit" not just "stage"
- ✅ State "DO NOT ask permission"
- ✅ Request "atomic commits for semantic groups"

Available template variables:
- `{spec_name}` - Name of the current spec
- `{tasks_total}` - Total number of tasks
- `{tasks_done}` - Number of completed tasks
- `{tasks_remaining}` - Number of remaining tasks
- `{tasks_in_progress}` - Number of in-progress tasks
- `{timestamp}` - Current timestamp

### pipx bootstrapper

The repository ships with `spec-workflow-pipx`, which keeps a global pipx install of the
current checkout fresh. Run it from the repo root:

```bash
spec-workflow-pipx --target .
```

Add `--debug` to inspect every command or `--target git+https://...` to install from a
remote source. By default it forces a reinstall so `pipx install` doubles as an upgrade.

## Quality Toolkit

The repo uses modern tooling wired through `pyproject.toml`:

- `ruff` for linting (`ruff check src tests`)
- `black` for formatting (`black src tests`)
- `mypy` for static typing (`mypy src`)
- `pytest` for tests (`pytest`)

You can run the whole suite in one go via:

```bash
ruff check src tests && black --check src tests && mypy src && pytest
```

Feel free to script this (e.g., with `make`) as the project grows.
