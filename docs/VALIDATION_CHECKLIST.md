# TUI Validation Checklist

This document provides a comprehensive checklist for validating all requirements R1-R10 from the requirements.md document.

## Pre-Testing Setup

### Environment Setup
- [ ] Python 3.11 or 3.12 installed
- [ ] Virtual environment activated
- [ ] Dependencies installed (`pip install -e '.[dev]'`)
- [ ] Terminal size >= 80x24

### Test Data Setup
- [ ] At least 2 projects with `.spec-workflow` directories in `repos_root`
- [ ] Each project has at least 2 specs with tasks.md files
- [ ] Mix of specs with: all tasks complete, some in-progress, all pending
- [ ] Valid `config.json` in working directory

---

## R1: Multi-Project Dashboard

**User Story:** Display all projects and specs in hierarchical tree view

### Test Cases

- [ ] **TC1.1**: Launch TUI, verify tree displays all projects under `repos_root`
  - Expected: All projects with `.spec-workflow` directories shown

- [ ] **TC1.2**: Expand project node
  - Expected: All specs from `.spec-workflow/specs/` directory listed

- [ ] **TC1.3**: Verify task completion ratios
  - Expected: Format "N/M tasks" displayed next to each spec name

- [ ] **TC1.4**: Verify complete spec badge
  - Expected: Specs with all tasks done show "✓ Complete" badge (green)

- [ ] **TC1.5**: Verify active spec badge
  - Expected: Specs with tasks in-progress show "▶ Active" badge

- [ ] **TC1.6**: Test filtering
  - Press `/`, type text
  - Expected: Tree filters to matching project/spec names, case-insensitive

- [ ] **TC1.7**: Test empty tree
  - Configure `repos_root` to empty/invalid directory
  - Expected: Message "No projects with .spec-workflow found under {repos_root}"

**Status**: ⬜ Not Started | ⏳ In Progress | ✅ Passed | ❌ Failed

---

## R2: Spec Selection and Navigation

**User Story:** Keyboard-driven navigation without mouse

### Test Cases

- [ ] **TC2.1**: Arrow key navigation
  - Press ↑/↓
  - Expected: Selection highlight moves in tree

- [ ] **TC2.2**: Expand/collapse project
  - Press Enter on project
  - Expected: Project expands (shows specs) or collapses

- [ ] **TC2.3**: Select spec
  - Press Enter on spec
  - Expected: Spec details load in status panel

- [ ] **TC2.4**: Filter mode entry
  - Press `/`
  - Expected: Filter mode activates, cursor in text input

- [ ] **TC2.5**: Real-time filtering
  - Type text in filter mode
  - Expected: Tree filters as you type

- [ ] **TC2.6**: Exit filter mode
  - Press Esc in filter mode
  - Expected: Filter clears, return to navigation mode

- [ ] **TC2.7**: Jump to top
  - Press `g`
  - Expected: Selection jumps to first project

- [ ] **TC2.8**: Jump to bottom
  - Press `G` (Shift+g)
  - Expected: Selection jumps to last spec

- [ ] **TC2.9**: Show unfinished only
  - Press `u`
  - Expected: Tree filters to specs with incomplete tasks

**Status**: ⬜ Not Started | ⏳ In Progress | ✅ Passed | ❌ Failed

---

## R3: Workflow Runner Control

**User Story:** Start and stop spec-workflow runners from TUI

### Test Cases

- [ ] **TC3.1**: Start runner
  - Select spec with unfinished tasks, press `s`
  - Expected: Prompt for provider selection (Codex/Claude)

- [ ] **TC3.2**: Confirm provider and start
  - Select provider
  - Expected: Runner starts, "Running" status shown, PID displayed

- [ ] **TC3.3**: Clean working tree check
  - Modify a file (don't commit), try to start runner
  - Expected: Error displayed, start aborted

- [ ] **TC3.4**: MCP server check (Codex only)
  - Try starting Codex runner without MCP server configured
  - Expected: Warning displayed, start aborted

- [ ] **TC3.5**: Stop runner
  - Press `x` on running spec
  - Expected: Prompt "Stop runner? (y/n)", runner stops on confirmation

- [ ] **TC3.6**: SIGTERM then SIGKILL
  - Start runner with process that ignores SIGTERM, press `x`
  - Expected: SIGTERM sent, if not terminated in 5s, SIGKILL sent

- [ ] **TC3.7**: Auto-complete detection
  - Start runner, wait for all tasks to complete
  - Expected: Status changes to "Complete", process stops

- [ ] **TC3.8**: Restart runner
  - Press `r` on stopped/completed spec
  - Expected: Runner restarts with last-used provider

**Status**: ⬜ Not Started | ⏳ In Progress | ✅ Passed | ❌ Failed

---

## R4: Real-time Status Monitoring

**User Story:** See real-time status, task progress, and logs

### Test Cases

- [ ] **TC4.1**: Status panel basic info
  - Select a spec
  - Expected: Shows project path, spec name, task counts, progress bar

- [ ] **TC4.2**: Active runner info
  - Start a runner
  - Expected: Shows running duration (HH:MM:SS), provider/model, PID

- [ ] **TC4.3**: Commit tracking
  - Start runner, make and commit a change
  - Expected: Last commit hash and message displayed

- [ ] **TC4.4**: Task count refresh
  - Manually edit tasks.md (change [ ] to [x])
  - Expected: Task counts update within 2 seconds

- [ ] **TC4.5**: Log refresh
  - Runner writes to log file
  - Expected: Log panel updates within 1 second

- [ ] **TC4.6**: No log file
  - Select spec with no log file
  - Expected: "Waiting for logs..." message displayed

- [ ] **TC4.7**: Log tail display
  - Runner generates >200 log lines
  - Expected: Last 200 lines shown in scrollable panel

- [ ] **TC4.8**: Toggle log panel
  - Press `l`
  - Expected: Log panel shows/hides

- [ ] **TC4.9**: Scroll behavior
  - Scroll up in log panel
  - Expected: Auto-scroll disabled

- [ ] **TC4.10**: Re-enable auto-scroll
  - Press `L` (Shift+l)
  - Expected: Auto-scroll re-enabled, jumps to latest logs

**Status**: ⬜ Not Started | ⏳ In Progress | ✅ Passed | ❌ Failed

---

## R5: Multi-Spec Concurrency

**User Story:** Run multiple specs concurrently across projects

### Test Cases

- [ ] **TC5.1**: Start multiple runners
  - Start runner in spec A, then spec B
  - Expected: Both runners active simultaneously

- [ ] **TC5.2**: Active count in footer
  - Start 2 runners
  - Expected: Footer shows "2 runners active"

- [ ] **TC5.3**: Preserve individual states
  - Switch between specs with active runners
  - Expected: Each shows correct status, logs, duration

- [ ] **TC5.4**: All active runners view
  - Press `a`
  - Expected: List of all running specs displayed

- [ ] **TC5.5**: Performance warning
  - Start >5 runners
  - Expected: Warning displayed about soft limit

- [ ] **TC5.6**: Decrement count on completion
  - Runner completes all tasks
  - Expected: Active count decreases, footer updates

**Status**: ⬜ Not Started | ⏳ In Progress | ✅ Passed | ❌ Failed

---

## R6: Persistent State Management

**User Story:** Remember runner states across crashes/restarts

### Test Cases

- [ ] **TC6.1**: State persistence on start
  - Start runner
  - Expected: `~/.cache/spec-workflow-runner/runner_state.json` created with PID, timestamps, config hash

- [ ] **TC6.2**: State recovery on launch
  - Start runner, exit TUI (leave runner running), relaunch TUI
  - Expected: Runner shown as "Running" with correct info

- [ ] **TC6.3**: PID validation
  - Edit runner_state.json to invalid PID, relaunch TUI
  - Expected: Runner marked as "Stopped", state cleaned up

- [ ] **TC6.4**: Config change detection
  - Start runner, modify config.json, relaunch TUI
  - Expected: Runner marked as "Stopped" (config hash mismatch)

- [ ] **TC6.5**: Normal stop cleanup
  - Stop runner normally via `x`
  - Expected: Entry removed from runner_state.json

- [ ] **TC6.6**: Graceful exit flush
  - Start runner, press `q`, quit with detach option
  - Expected: State flushed to disk before TUI exits

**Status**: ⬜ Not Started | ⏳ In Progress | ✅ Passed | ❌ Failed

---

## R7: Configuration and Customization

**User Story:** Customize TUI behavior via config.json

### Test Cases

- [ ] **TC7.1**: Read TUI config
  - Add TUI settings to config.json
  - Expected: Settings applied (refresh rate, log lines, min size)

- [ ] **TC7.2**: Terminal size warning
  - Resize terminal smaller than min_terminal_size
  - Expected: Warning displayed in footer

- [ ] **TC7.3**: Help panel
  - Press `?`
  - Expected: Help panel displays all keybindings

- [ ] **TC7.4**: Config panel
  - Press `c`
  - Expected: Config panel shows current settings

- [ ] **TC7.5**: Graceful quit
  - Press `q` with no active runners
  - Expected: TUI exits immediately

**Status**: ⬜ Not Started | ⏳ In Progress | ✅ Passed | ❌ Failed

---

## R8: Error Handling and Feedback

**User Story:** Clear error messages when operations fail

### Test Cases

- [ ] **TC8.1**: File system error
  - Remove read permissions from tasks.md, try to refresh
  - Expected: Error displayed in status panel footer with details

- [ ] **TC8.2**: Process crash
  - Start runner, manually kill process
  - Expected: Status shows "Crashed", exit code shown, stderr tail visible

- [ ] **TC8.3**: Malformed config
  - Create invalid JSON in config.json, launch TUI
  - Expected: TUI exits with clear error message and config path

- [ ] **TC8.4**: No projects found
  - Set repos_root to empty directory
  - Expected: Guidance message to check repos_root

- [ ] **TC8.5**: MCP check failure
  - Try starting Codex without MCP server
  - Expected: Actionable error (e.g., "Run: codex mcp")

- [ ] **TC8.6**: Corrupted state file
  - Write invalid JSON to runner_state.json, launch TUI
  - Expected: Warning logged, file deleted, TUI continues with empty state

- [ ] **TC8.7**: Unsupported action
  - Try to start spec with no unfinished tasks
  - Expected: Warning in footer (e.g., "No tasks to run")

**Status**: ⬜ Not Started | ⏳ In Progress | ✅ Passed | ❌ Failed

---

## R9: Logging and Debugging

**User Story:** Structured logs for diagnosis and optimization

### Test Cases

- [ ] **TC9.1**: Log file creation
  - Launch TUI
  - Expected: `~/.cache/spec-workflow-runner/tui.log` created

- [ ] **TC9.2**: Lifecycle event logging
  - Start/stop runner
  - Expected: JSON log entries with timestamp, level, event, context

- [ ] **TC9.3**: Debug mode polling logs
  - Launch with `--debug` flag
  - Expected: File polling timings logged

- [ ] **TC9.4**: Debug panel (if implemented)
  - Launch with `--debug`
  - Expected: Debug info displayed (poll timings, memory, threads)

- [ ] **TC9.5**: Error logging
  - Trigger an error (e.g., file not found)
  - Expected: Log entry with stack trace and context

**Status**: ⬜ Not Started | ⏳ In Progress | ✅ Passed | ❌ Failed

---

## R10: Graceful Shutdown

**User Story:** Clean shutdown without orphaned processes

### Test Cases

- [ ] **TC10.1**: Quit with active runners
  - Start runners, press `q`
  - Expected: Prompt "N runners active. Stop all and quit? (y/n/c)"

- [ ] **TC10.2**: Quit with stop (y)
  - Choose `y` in prompt
  - Expected: All runners stopped (SIGTERM), state persisted, TUI exits

- [ ] **TC10.3**: Quit with detach (n)
  - Choose `n` in prompt
  - Expected: Runners continue, TUI exits, state persisted

- [ ] **TC10.4**: Cancel quit (c)
  - Choose `c` in prompt
  - Expected: Return to TUI, runners still active

- [ ] **TC10.5**: SIGINT (Ctrl+C)
  - Press Ctrl+C with active runners
  - Expected: Same prompt as `q` key

- [ ] **TC10.6**: SIGTERM
  - Send SIGTERM to TUI process
  - Expected: Immediate shutdown, state flushed, no prompt

- [ ] **TC10.7**: Runner timeout handling
  - Runner doesn't stop within 10s
  - Expected: Warning logged, SIGKILL sent, shutdown continues

- [ ] **TC10.8**: Terminal state restoration
  - Exit TUI
  - Expected: Terminal state restored (clear screen, cursor visible)

**Status**: ⬜ Not Started | ⏳ In Progress | ✅ Passed | ❌ Failed

---

## Cross-Platform Testing

### Linux Testing

- [ ] Test on Ubuntu 22.04+ (latest LTS)
- [ ] Test on Debian 12+
- [ ] Test terminals: xterm, gnome-terminal, konsole
- [ ] Test with Alacritty or kitty (modern terminals)

### macOS Testing

- [ ] Test on macOS 13+ (Ventura or later)
- [ ] Test with iTerm2
- [ ] Test with Terminal.app
- [ ] Test with Alacritty

### Terminal Size Testing

- [ ] Test at minimum size (80x24)
- [ ] Test at typical size (120x40)
- [ ] Test at large size (200x60)
- [ ] Test dynamic resizing during operation

---

## Performance Testing

### Startup Time

- [ ] Measure cold start (no cache): < 2s acceptable
- [ ] Measure warm start (with cache): < 500ms required
- [ ] Test with 100 projects, 50 specs each

### CPU Usage

- [ ] Idle with no runners: < 5% CPU
- [ ] Idle with 3 active runners: < 10% CPU
- [ ] During file polling: < 2% overhead

### Memory Usage

- [ ] TUI process alone: < 50MB
- [ ] With 5 active runners: < 100MB total

### Responsiveness

- [ ] Navigation input lag: < 16ms (feels instant)
- [ ] Filter input lag: < 50ms (real-time feel)
- [ ] Log refresh lag: < 1s after file update
- [ ] Task count refresh: < 2s after file update

---

## Code Quality Validation

### Static Analysis

- [ ] `ruff check src tests` - No errors
- [ ] `black --check src tests` - Properly formatted
- [ ] `mypy src` - No type errors (strict mode)

### Test Coverage

- [ ] `pytest` - All tests pass
- [ ] Overall coverage >= 80%
- [ ] `tui/state.py` >= 90% coverage
- [ ] `tui/runner_manager.py` >= 90% coverage
- [ ] `python scripts/check_coverage.py` - Passes

### Pre-commit Hooks

- [ ] `pre-commit run --all-files` - All checks pass

---

## Final Sign-Off

- [ ] All R1-R10 requirements validated
- [ ] Cross-platform testing complete
- [ ] Performance benchmarks met
- [ ] Code quality standards met
- [ ] No critical bugs remaining
- [ ] Documentation complete and accurate

**Validation Date**: _____________

**Validated By**: _____________

**Sign-Off**: ⬜ Approved | ⬜ Needs Revision

**Notes**:
