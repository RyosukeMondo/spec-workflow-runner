# Technology Stack

## Project Type
Terminal User Interface (TUI) application - interactive CLI tool with Rich-based dashboard for managing spec-workflow automation across multiple projects.

## Core Technologies

### Primary Language(s)
- **Language**: Python 3.11+
- **Runtime**: CPython 3.11+ (required for modern typing features)
- **Language-specific tools**:
  - pip (package manager)
  - hatchling (build backend, already used)
  - Type hints with runtime validation

### Key Dependencies/Libraries
- **Rich 13.7.0+**: Terminal rendering, layout management, live updates, theming
  - `rich.layout.Layout`: Multi-panel dashboard layout
  - `rich.live.Live`: Real-time refresh without flickering
  - `rich.tree.Tree`: Hierarchical project/spec navigation
  - `rich.panel.Panel`: Bordered containers for status sections
  - `rich.progress.Progress`: Task progress bars
  - `rich.table.Table`: Structured data display
  - `rich.console.Console`: Output management and styling
  - `rich.text.Text`: Styled text rendering
- **Standard Library**:
  - `subprocess`: Provider process management (Popen for background execution)
  - `threading`: Background polling for file changes, process monitoring
  - `pathlib`: File system navigation
  - `dataclasses`: State models (RunnerState, ProjectState, SpecState)
  - `enum`: Status enums (RunnerStatus, ProviderType)
  - `queue`: Thread-safe communication between poller and UI
  - `signal`: Graceful shutdown handling (SIGINT, SIGTERM)

### Application Architecture
- **Event-driven TUI**: Main event loop with background pollers feeding state updates
- **SSOT Pattern**: File system as single source of truth
  - `tasks.md`: Task status (polling with mtime checks)
  - Log files: Provider output (tail following)
  - Git repo: Commit detection (git log polling)
  - Process table: Runner liveness (psutil or /proc)
- **Three-layer architecture**:
  1. **State Layer**: Models and file system readers (SSOT)
  2. **Controller Layer**: Event handlers, runner lifecycle management
  3. **View Layer**: Rich components and layout rendering
- **Modular components**:
  - `tui_app.py`: Main application loop and layout orchestration
  - `state.py`: State models and file system polling logic
  - `runner_manager.py`: Provider subprocess lifecycle management
  - `views/`: Rich component builders (tree_view, status_panel, log_viewer)
  - Reuse existing: `utils.py`, `providers.py`, `config.py`

### Data Storage (if applicable)
- **Primary storage**: File system (no database)
  - `~/.cache/spec-workflow-runner/runner_state.json`: Persistent runner state (PIDs, start times)
  - In-memory: Current UI state (selected project/spec, scroll position)
- **Caching**: Extend existing project cache (`projects.json`) with spec metadata
- **Data formats**: JSON for cache/state, markdown for specs/tasks, plain text for logs

### External Integrations (if applicable)
- **Provider processes**: Subprocess integration with Codex/Claude CLI
  - Protocols: stdin/stdout/stderr pipes, non-blocking reads
  - Lifecycle: Spawn, monitor (psutil), graceful shutdown (SIGTERM → SIGKILL)
- **Git**: Read-only git commands for commit detection
  - `git log --oneline -n 1`: Latest commit hash/message
  - `git status --porcelain`: Working tree status
- **MCP servers**: Validation only (via existing `check_mcp_server_exists`)

### Monitoring & Dashboard Technologies
- **Dashboard Framework**: Rich TUI (terminal-native, no web framework)
- **Real-time Communication**: File system polling + threading
  - Polling interval: 2s for tasks.md, 0.5s for logs (configurable)
  - `watchdog` library: Consider for inotify-based file watching (Linux) - future optimization
- **Visualization**: Rich built-in components
  - `Progress`: Task completion bars
  - `Tree`: Nested project/spec navigation
  - `Live`: Flicker-free updates
  - `Syntax`: Log syntax highlighting (detect ANSI codes)
- **State Management**: File system as SSOT + in-memory cache
  - Cache invalidation: mtime comparison, config change detection
  - State sync: Periodic file system reads (polling), no write-back

## Development Environment

### Build & Development Tools
- **Build System**: hatchling (existing, continue using)
- **Package Management**: pip with `pyproject.toml` (existing)
- **Development workflow**:
  - Editable install: `pip install -e '.[dev]'`
  - Hot reload: Not applicable (TUI needs restart for code changes)
  - Manual testing: `spec-workflow-tui` in test project directories

### Code Quality Tools
- **Static Analysis**:
  - ruff (existing): Linting + import sorting
  - mypy (existing): Type checking with strict mode
- **Formatting**: black (existing)
- **Testing Framework**:
  - pytest (existing): Unit tests for state logic, runner manager
  - Manual testing: TUI requires interactive testing (no GUI automation)
  - Integration tests: Spawn TUI in test mode, mock file system
- **Documentation**: Docstrings (Google style), inline comments for complex logic

### Version Control & Collaboration
- **VCS**: Git (existing)
- **Branching Strategy**: GitHub Flow (feature branches)
- **Code Review Process**: PR-based, linting/type checks in CI

### Dashboard Development (if applicable)
- **Live Reload**: Not applicable - TUI restart required
- **Port Management**: N/A (terminal-based, no network ports)
- **Multi-Instance Support**: Yes - each terminal can run independent TUI instance
  - Coordination: Via file system locks (`~/.cache/spec-workflow-runner/tui.lock`) if needed
  - Conflict handling: Warn if multiple TUIs try to start same spec runner

## Deployment & Distribution (if applicable)
- **Target Platform(s)**: Linux, macOS (terminal emulator required)
  - Tested on: xterm, iTerm2, Alacritty, tmux, screen
  - Windows: WSL or native (Rich supports Windows terminal)
- **Distribution Method**: pipx (existing installer)
  - `pipx install spec-workflow-runner`
  - Entry point: `spec-workflow-tui` (new CLI command)
- **Installation Requirements**:
  - Python 3.11+
  - UTF-8 terminal emulator
  - 256-color support (minimum), truecolor preferred
  - Codex and/or Claude CLI installed (for runner functionality)
- **Update Mechanism**: `pipx upgrade spec-workflow-runner`

## Technical Requirements & Constraints

### Performance Requirements
- **UI responsiveness**: <16ms frame time for 60fps interaction feel
  - Keyboard input handling: <10ms latency
  - Filtering/search: <50ms for 1000+ specs
- **Startup time**:
  - Cold start: <500ms (with cache)
  - Warm start: <200ms (cache hit)
- **Refresh overhead**: <5% CPU during idle polling
- **Memory usage**: <50MB for TUI (excluding provider subprocesses which may use 200MB+)

### Compatibility Requirements
- **Platform Support**: Linux (primary), macOS (secondary), Windows/WSL (best-effort)
- **Terminal Emulators**: xterm-compatible, 256-color minimum
- **Python Versions**: 3.11+ (strict, due to typing features)
- **Provider CLIs**: Codex 1.x, Claude Code 0.x (version detection not critical)

### Security & Compliance
- **Security Requirements**:
  - No credentials in TUI (providers handle auth)
  - Log sanitization: Don't display API keys if leaked to logs
  - Process isolation: Provider subprocesses inherit user permissions
- **Threat Model**: Local user compromise only (no network attack surface)

### Scalability & Reliability
- **Expected Load**:
  - Projects: 10-100 under `~/repos`
  - Specs per project: 5-50
  - Concurrent runners: 1-5 (user limitation, not technical)
- **Availability Requirements**: Best-effort (local tool, no SLA)
- **Failure handling**:
  - Provider crash: Detect and surface error, allow restart
  - File system errors: Graceful degradation (show cached state)
  - TUI crash: Clean up runner subprocesses on exit (signal handlers)

## Technical Decisions & Rationale

### Decision Log
1. **Rich over alternatives (urwid, textual)**:
   - Already dependency in project (monitor uses Rich)
   - Rich 13.7+ has `Live` API for flicker-free updates
   - Simpler than urwid, more stable than textual (as of 2024)
   - Trade-off: Less interactive than textual (no async event loop), but simpler mental model
2. **File system polling over inotify/watchdog**:
   - Cross-platform (inotify is Linux-only)
   - Simpler implementation (no event handling complexity)
   - Sufficient for 2s refresh rate (not real-time requirement)
   - Trade-off: Higher CPU overhead, but <5% acceptable for local tool
   - Future: Add watchdog as optional optimization for Linux
3. **Separate TUI CLI vs merge into existing runner**:
   - Separate command (`spec-workflow-tui`) preserves scriptability of `spec-workflow-run`
   - Clean separation: TUI is superset feature, doesn't complicate existing CLI
   - User choice: TUI for interactive, CLI for automation/CI
   - Trade-off: More entry points, but clearer user intent
4. **Threads over asyncio**:
   - File system polling and subprocess management fit thread model
   - Rich `Live` API is synchronous (simpler with threads)
   - Avoid asyncio complexity for I/O-bound file reads
   - Trade-off: GIL contention possible, but workload is I/O-bound (acceptable)

## Known Limitations
- **No remote TUI sharing**: Unlike tmux attach, can't share TUI state across SSH sessions
  - Impact: Each user runs own TUI instance
  - Future: WebSocket broadcast mode for read-only remote viewers
- **Log scrolling performance**: Large logs (>100K lines) may cause stuttering
  - Mitigation: Tail-only display (last 200 lines), configurable
  - Future: Lazy loading with virtual scrolling
- **Terminal resize handling**: Layout may break on extreme resize (e.g., 40x10)
  - Mitigation: Minimum terminal size warning (80x24)
- **Provider output parsing**: No structured logging from providers (plain text logs)
  - Impact: Can't extract structured metrics easily
  - Mitigation: Regex parsing for key events (commit detection)
