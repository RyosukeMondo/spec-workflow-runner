# Requirements Document

## Introduction

The TUI Unified Runner integrates project discovery, spec browsing, workflow control, and real-time monitoring into a single terminal interface. It replaces the current workflow of switching between `spec-workflow-run` (interactive CLI prompts) and `spec-workflow-monitor` (separate Rich dashboard) with a unified, keyboard-driven TUI that provides instant visibility and control across all projects.

This addresses developer pain points:
- **Context switching overhead**: Currently need to remember project paths, spec names, run monitor separately
- **Limited visibility**: Can't see all project statuses at once, must poll individual monitors
- **Workflow friction**: Starting a spec requires CLI invocation, monitoring requires second terminal window

## Alignment with Product Vision

This feature is the core product evolution outlined in product.md:
- Delivers on "Single interface replaces multiple CLI invocations" objective
- Achieves "Real-time visibility without polling separate monitor instances"
- Enables "Manage multiple concurrent spec executions from one interface"
- Aligns with "Terminal-first" and "SSOT" product principles

## Requirements

### R1: Multi-Project Dashboard

**User Story:** As a developer managing multiple spec-workflow projects, I want to see all my projects and their specs in a hierarchical tree view, so that I can quickly assess status across my entire workspace without navigating directories.

#### Acceptance Criteria

1. WHEN TUI launches THEN system SHALL display a tree view of all projects under `repos_root` (from config.json) containing `.spec-workflow` directories
2. WHEN project is expanded in tree THEN system SHALL list all specs within that project's `.spec-workflow/specs/` directory
3. WHEN spec has tasks.md THEN system SHALL display task completion ratio (e.g., "3/10 tasks") next to spec name
4. IF spec has no unfinished tasks THEN system SHALL display "✓ Complete" badge
5. IF spec has tasks in progress THEN system SHALL display "▶ Active" badge with in-progress count
6. WHEN user types filter text THEN system SHALL fuzzy-match against project/spec names and highlight matches
7. WHEN tree is empty (no projects found) THEN system SHALL display "No projects with .spec-workflow found under {repos_root}"

### R2: Spec Selection and Navigation

**User Story:** As a developer, I want keyboard-driven navigation to quickly select projects and specs, so that I can move between workflows without using a mouse.

#### Acceptance Criteria

1. WHEN user presses arrow keys (↑/↓) THEN system SHALL move selection highlight in tree
2. WHEN user presses Enter on project THEN system SHALL expand/collapse project node
3. WHEN user presses Enter on spec THEN system SHALL load spec details in status panel
4. WHEN user types "/" THEN system SHALL enter filter mode and focus text input
5. WHEN user types text in filter mode THEN system SHALL filter tree to matching items in real-time
6. WHEN user presses Esc in filter mode THEN system SHALL clear filter and return to navigation
7. WHEN user presses "g" THEN system SHALL jump to top of tree
8. WHEN user presses "G" THEN system SHALL jump to bottom of tree
9. WHEN user presses "u" THEN system SHALL filter to show only unfinished specs

### R3: Workflow Runner Control

**User Story:** As a developer, I want to start and stop spec-workflow runners directly from the TUI, so that I can control automation without switching to a terminal and typing CLI commands.

#### Acceptance Criteria

1. WHEN user selects a spec with unfinished tasks AND presses "s" THEN system SHALL prompt for provider selection (Codex/Claude)
2. WHEN user confirms provider selection THEN system SHALL start spec-workflow-run for that spec in background
3. WHEN spec-workflow-run starts THEN system SHALL display "Running" status in tree and status panel
4. IF clean working tree check fails THEN system SHALL display error in status panel and abort start
5. IF MCP server check fails (for Codex) THEN system SHALL display warning and abort start
6. WHEN user presses "x" on running spec THEN system SHALL prompt "Stop runner? (y/n)"
7. WHEN user confirms stop THEN system SHALL send SIGTERM to provider process and mark as "Stopped"
8. IF provider process does not terminate within 5s THEN system SHALL send SIGKILL
9. WHEN runner completes all tasks THEN system SHALL mark spec as "Complete" and stop process
10. WHEN user presses "r" on stopped/completed spec THEN system SHALL restart runner with last-used provider

### R4: Real-time Status Monitoring

**User Story:** As a developer, I want to see real-time status of running specs including task progress, execution time, and logs, so that I can monitor workflows without opening separate terminals.

#### Acceptance Criteria

1. WHEN spec is selected THEN system SHALL display status panel showing:
   - Project path
   - Spec name
   - Total tasks, completed, in-progress, pending counts
   - Progress bar (completed/total)
2. WHEN spec runner is active THEN system SHALL additionally display:
   - Running duration (HH:MM:SS, updated every second)
   - Provider name and model (e.g., "Codex - claude-sonnet-4.5")
   - Process ID (PID)
   - Last commit hash and message (if any commits since start)
3. WHEN tasks.md file is modified THEN system SHALL refresh task counts within 2 seconds
4. WHEN log file is updated THEN system SHALL refresh log panel within 1 second
5. IF log file does not exist THEN system SHALL display "Waiting for logs..."
6. WHEN log file exists THEN system SHALL display last 200 lines in scrollable panel
7. WHEN user presses "l" THEN system SHALL toggle log panel visibility
8. WHEN user scrolls log panel THEN system SHALL disable auto-scroll to tail
9. WHEN user presses "L" (shift+l) THEN system SHALL re-enable auto-scroll to tail

### R5: Multi-Spec Concurrency

**User Story:** As a developer, I want to run multiple specs concurrently across different projects, so that I can parallelize work and maximize throughput.

#### Acceptance Criteria

1. WHEN user starts a spec runner THEN system SHALL allow starting additional runners in other specs
2. WHEN multiple runners are active THEN system SHALL display count in footer (e.g., "2 runners active")
3. WHEN switching between specs THEN system SHALL preserve individual runner states and logs
4. WHEN user presses "a" THEN system SHALL display "All Active Runners" view listing all running specs
5. IF more than 5 runners are active THEN system SHALL display performance warning (soft limit)
6. WHEN runner completes THEN system SHALL decrement active count and update footer

### R6: Persistent State Management

**User Story:** As a developer, I want the TUI to remember runner states across crashes or restarts, so that I can recover running workflows without losing progress.

#### Acceptance Criteria

1. WHEN runner starts THEN system SHALL persist state to `~/.cache/spec-workflow-runner/runner_state.json` including:
   - Project path
   - Spec name
   - Provider name and model
   - PID
   - Start timestamp
   - Config hash (to detect config changes)
2. WHEN TUI launches THEN system SHALL read persisted state and check if PIDs are still running
3. IF PID is running AND matches config THEN system SHALL restore runner as "Running"
4. IF PID is not running OR config changed THEN system SHALL mark runner as "Stopped" and clean up state
5. WHEN runner stops normally THEN system SHALL remove entry from state file
6. WHEN TUI exits (SIGINT/SIGTERM) THEN system SHALL flush state to disk before terminating

### R7: Configuration and Customization

**User Story:** As a developer, I want to customize TUI behavior (refresh rates, log lines, keybindings), so that I can optimize the interface for my workflow preferences.

#### Acceptance Criteria

1. WHEN TUI launches THEN system SHALL read configuration from `config.json` including:
   - `tui_refresh_seconds`: UI refresh interval (default: 2)
   - `tui_log_tail_lines`: Log panel line count (default: 200)
   - `tui_min_terminal_size`: Minimum cols x rows (default: 80x24)
2. IF terminal size < min_terminal_size THEN system SHALL display warning and suggest resizing
3. WHEN user presses "?" THEN system SHALL display help panel with all keybindings
4. WHEN user presses "c" THEN system SHALL display config panel showing current settings
5. WHEN user presses "q" THEN system SHALL exit TUI gracefully (after confirming if runners active)

### R8: Error Handling and Feedback

**User Story:** As a developer, I want clear error messages and status feedback when operations fail, so that I can understand and resolve issues quickly.

#### Acceptance Criteria

1. WHEN any file system operation fails THEN system SHALL display error in status panel footer with details
2. WHEN provider process crashes THEN system SHALL mark runner as "Crashed", display exit code, and show stderr tail
3. WHEN config.json is malformed THEN system SHALL exit with error message and config path
4. WHEN no projects are found THEN system SHALL display guidance to check `repos_root` in config
5. WHEN MCP check fails THEN system SHALL display actionable error (e.g., "Run: codex mcp")
6. IF runner_state.json is corrupted THEN system SHALL log warning, delete file, and continue with empty state
7. WHEN user attempts unsupported action (e.g., start spec with no tasks) THEN system SHALL display warning in footer

### R9: Logging and Debugging

**User Story:** As a developer debugging the TUI or workflows, I want structured logs of TUI operations, so that I can diagnose issues and optimize performance.

#### Acceptance Criteria

1. WHEN TUI starts THEN system SHALL initialize logger writing to `~/.cache/spec-workflow-runner/tui.log`
2. WHEN runner lifecycle events occur THEN system SHALL log JSON entries:
   ```json
   {"timestamp": "2025-01-15T10:30:00Z", "level": "info", "event": "runner_start", "project": "/path", "spec": "my-spec", "provider": "codex", "pid": 12345}
   ```
3. WHEN file polling occurs THEN system SHALL log in debug mode (disabled by default, enable with `--debug` flag)
4. IF `--debug` flag is provided THEN system SHALL display debug panel showing:
   - File polling timings (min/max/avg ms)
   - Memory usage (MB)
   - Active threads count
5. WHEN error occurs THEN system SHALL log with stack trace and context (project, spec, operation)

### R10: Graceful Shutdown

**User Story:** As a developer, I want the TUI to cleanly shut down and handle active runners safely, so that I don't lose work or orphan processes.

#### Acceptance Criteria

1. WHEN user presses "q" THEN system SHALL check for active runners
2. IF active runners exist THEN system SHALL prompt "2 runners active. Stop all and quit? (y/n/c)"
   - y: Stop all runners (SIGTERM), wait up to 10s, then quit
   - n: Leave runners running (detached), quit TUI only
   - c: Cancel, return to TUI
3. WHEN user confirms quit with active runners THEN system SHALL stop all runners and persist state
4. WHEN SIGINT (Ctrl+C) is received THEN system SHALL execute same shutdown flow as "q"
5. WHEN SIGTERM is received THEN system SHALL immediately flush state and terminate (no prompt)
6. IF runner does not stop within 10s THEN system SHALL log warning, send SIGKILL, and continue shutdown
7. WHEN shutdown completes THEN system SHALL restore terminal state (clear screen, show cursor)

## Non-Functional Requirements

### Code Architecture and Modularity
- **Single Responsibility Principle**: Separate modules for:
  - `tui_app.py`: Main loop and layout (entry point)
  - `state.py`: State models (ProjectState, SpecState, RunnerState) and file system readers
  - `runner_manager.py`: Subprocess lifecycle (start, stop, monitor)
  - `views/tree_view.py`: Project/spec tree rendering
  - `views/status_panel.py`: Spec status rendering
  - `views/log_viewer.py`: Log tail rendering
  - `keybindings.py`: Keyboard event handlers
- **Modular Design**: Reuse existing code:
  - `utils.py`: `discover_projects`, `discover_specs`, `read_task_stats`, `load_config`
  - `providers.py`: `Provider` interface, `CodexProvider`, `ClaudeProvider`
- **Dependency Injection**: Pass `Config` and `Provider` instances, not globals
- **Clear Interfaces**: Define protocols for state readers (`StateReader`), view renderers (`ViewRenderer`)

### Performance
- UI refresh: <16ms frame time (60fps feel)
- Startup: <500ms with cache
- File polling: <5% CPU overhead during idle
- Memory: <50MB for TUI process

### Security
- No credential storage (providers handle auth)
- Log sanitization: Redact patterns like `api_key=...` or `token=...`
- Process isolation: Runners inherit user permissions only

### Reliability
- Crash recovery: Restore runner states from persisted JSON
- Graceful degradation: Show cached data if file system errors occur
- Clean shutdown: No orphaned processes, terminal state restored

### Usability
- Keyboard-driven: All features accessible without mouse
- Discoverable: "?" help panel with keybinding reference
- Responsive: Instant feedback for navigation, filtering
- Clear status: Visual indicators (badges, colors) for runner states
- Error clarity: Actionable error messages with next steps
