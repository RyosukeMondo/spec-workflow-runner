# TUI Iteration Workflow Guide

## Overview

This guide documents the rapid iteration workflow for TUI development, enabling ultra-fast feedback cycles for identifying issues, fixing bugs, and adding features. The goal is to minimize the time between identifying a problem and verifying the fix.

---

## Fast Feedback Cycle Workflow

### The 7-Step Iteration Process

```
1. Run TUI with debug mode
   ↓
2. Reproduce issue or test feature
   ↓
3. Check logs for errors and debug info
   ↓
4. Write failing test
   ↓
5. Fix code
   ↓
6. Run tests to verify fix
   ↓
7. Collect metrics to check performance
```

### Step-by-Step Details

#### Step 1: Run TUI with Debug Mode

```bash
# Enable verbose logging for detailed diagnostics
spec-workflow-tui --debug

# Or with custom config
spec-workflow-tui --debug --config path/to/config.json
```

**What happens in debug mode:**
- Detailed logging to `~/.cache/spec-workflow-runner/tui.log`
- Poll timing metrics (min/max/avg milliseconds)
- State transition logging
- File system operation tracing

#### Step 2: Reproduce Issue or Test Feature

**For bugs:**
- Follow the exact steps that trigger the issue
- Note any error messages in the footer
- Observe unexpected behavior in the UI

**For features:**
- Exercise the new functionality
- Try edge cases and boundary conditions
- Test with various terminal sizes

**Common test scenarios:**
- Navigate through all specs using arrow keys
- Start multiple runners simultaneously (press `s` multiple times)
- Test with missing files (delete a log file while TUI running)
- Resize terminal to minimum and maximum sizes
- Test filtering with `/` key
- Test with corrupted `runner_state.json`

#### Step 3: Check Logs for Errors and Debug Info

```bash
# View the log file in real-time
tail -f ~/.cache/spec-workflow-runner/tui.log

# Or parse JSON logs for specific events
cat ~/.cache/spec-workflow-runner/tui.log | jq 'select(.event == "error")'

# Find performance metrics
cat ~/.cache/spec-workflow-runner/tui.log | jq 'select(.event == "poll_timing")'

# Find runner events
cat ~/.cache/spec-workflow-runner/tui.log | jq 'select(.event | startswith("runner_"))'
```

**Key log events to check:**
- `tui_start` - TUI initialization
- `runner_start` - Runner subprocess launched
- `runner_stop` - Runner subprocess stopped
- `error` - Any error with stack trace
- `poll_timing` - StatePoller performance (debug mode only)

**Example log analysis:**
```bash
# Find all errors in the last session
jq 'select(.level == "ERROR")' ~/.cache/spec-workflow-runner/tui.log

# Check if poll timing is too slow (> 100ms)
jq 'select(.event == "poll_timing" and .context.avg_ms > 100)' ~/.cache/spec-workflow-runner/tui.log
```

#### Step 4: Write Failing Test

Create a test that reproduces the issue before fixing it (TDD approach).

**Example: Testing a navigation bug**
```python
# tests/tui/test_keybindings.py

def test_arrow_down_wraps_to_first_item(sample_app_state):
    """Test that down arrow wraps from last item to first."""
    handler = KeybindingHandler(sample_app_state, mock_runner_manager)

    # Navigate to last item
    sample_app_state.selected_project = 2
    sample_app_state.selected_spec = 5

    # Press down arrow (should wrap to first)
    handled, message = handler.handle_key("down")

    assert handled is True
    assert sample_app_state.selected_project == 0
    assert sample_app_state.selected_spec == 0
```

**Example: Testing a runner error**
```python
# tests/tui/test_runner_manager.py

def test_start_runner_handles_popen_failure(mock_popen, mock_state_persister):
    """Test that Popen failure is handled gracefully."""
    mock_popen.side_effect = OSError("Permission denied")

    runner_manager = RunnerManager(config, mock_state_persister)

    with pytest.raises(RunnerError) as exc_info:
        runner_manager.start_runner(project, spec, provider)

    assert "Permission denied" in str(exc_info.value)
```

#### Step 5: Fix Code

Make the minimal change needed to fix the issue.

**Debugging tips while fixing:**

```python
# Quick debug output (remove before committing)
from rich import console
console = console.Console()
console.print(f"[yellow]DEBUG: selected_project={app_state.selected_project}")

# Interactive debugging
import pdb; pdb.set_trace()  # Or use breakpoint()

# Structured logging for persistent debugging
logger.debug("navigation_event", extra={
    "context": {
        "key": key,
        "selected_project": app_state.selected_project,
        "selected_spec": app_state.selected_spec
    }
})
```

**Example fix: Wrapping navigation**
```python
# src/spec_workflow_runner/tui/keybindings.py

def _handle_arrow_down(self) -> tuple[bool, str | None]:
    """Handle down arrow key."""
    total_items = len(self.app_state.projects)
    if total_items == 0:
        return True, None

    # Increment and wrap around
    current = self.app_state.selected_project
    self.app_state.selected_project = (current + 1) % total_items
    self.app_state.selected_spec = 0  # Reset spec selection

    return True, None
```

#### Step 6: Run Tests to Verify Fix

```bash
# Run just the TUI tests
pytest tests/tui/ -v

# Run a specific test file
pytest tests/tui/test_keybindings.py -v

# Run a specific test
pytest tests/tui/test_keybindings.py::test_arrow_down_wraps_to_first_item -v

# Run with coverage to see what's tested
pytest tests/tui/ --cov=src/spec_workflow_runner/tui --cov-report=term-missing

# Run fast tests only (exclude slow integration tests)
pytest tests/tui/ -k "not slow" -v
```

**Interpreting results:**
- All tests pass → Ready to commit
- Some tests fail → Fix is incomplete or broke something else
- Coverage dropped → Add tests for new code paths

#### Step 7: Collect Metrics to Check Performance

```bash
# Run the metrics collection script
python scripts/collect_metrics.py

# Or if integrated into pytest
pytest tests/tui/test_performance.py --benchmark-only
```

**Expected output:**
```json
{
  "timestamp": "2025-12-18T01:00:00Z",
  "startup_ms": 234,
  "memory_mb": 28,
  "poll_latency_ms": 12,
  "cpu_percent_idle": 2.3
}
```

**Performance thresholds (from tech.md):**
- Startup time: < 500ms
- Memory usage: < 50MB
- Poll latency: < 100ms
- CPU idle: < 5%

**If metrics exceed thresholds:**
```bash
# Profile the code to find bottlenecks
python -m cProfile -o profile.stats scripts/collect_metrics.py
python -c "import pstats; p = pstats.Stats('profile.stats'); p.sort_stats('cumulative').print_stats(20)"

# Check for memory leaks
python -m memory_profiler src/spec_workflow_runner/tui/app.py
```

---

## Debugging Tips

### Using Debug Mode Effectively

**Enable debug mode for development:**
```bash
# Always run with --debug during development
alias tui-dev='spec-workflow-tui --debug'
```

**Watch logs in real-time:**
```bash
# Terminal 1: Run TUI
spec-workflow-tui --debug

# Terminal 2: Watch logs
tail -f ~/.cache/spec-workflow-runner/tui.log | jq '.'
```

### Quick Debug Output

**Temporary console printing:**
```python
from rich.console import Console
console = Console()

# In any TUI code
console.print(f"[red]DEBUG:[/red] {variable_name}")
console.print_exception()  # Print current exception with traceback
```

**Note:** Remove all `console.print()` debug statements before committing.

### Interactive Debugging

**Using Python debugger:**
```python
# Set breakpoint
breakpoint()  # Python 3.7+
# Or: import pdb; pdb.set_trace()

# Common pdb commands:
# n - next line
# s - step into function
# c - continue execution
# p variable - print variable
# ll - list current function code
# q - quit debugger
```

**Debugging with pytest:**
```bash
# Drop into debugger on test failure
pytest tests/tui/test_keybindings.py --pdb

# Drop into debugger at specific point
pytest tests/tui/test_keybindings.py -k "test_name" --pdb -s
```

### Checking Poll Timings

**Debug mode logs poll timing:**
```bash
# Find slow poll cycles (> 50ms)
jq 'select(.event == "poll_timing" and .context.avg_ms > 50)' \
  ~/.cache/spec-workflow-runner/tui.log
```

**Optimize polling:**
- Use mtime-based change detection (already implemented)
- Avoid reading entire files on every poll
- Batch file checks in a single cycle

### Terminal State Issues

**If terminal state is corrupted after crash:**
```bash
# Reset terminal
reset

# Or restore with stty
stty sane
```

**If Rich Layout doesn't restore properly:**
- Check that `Live` context manager exits cleanly
- Ensure signal handlers call cleanup methods
- Test with `try/finally` blocks

---

## Common Pitfalls and Solutions

### 1. Blocking I/O in Main Thread

**Symptom:** TUI freezes or becomes unresponsive

**Problem:**
```python
# BAD: Reading file in main thread
def render_status_panel(spec):
    log_content = Path(spec.log_path).read_text()  # BLOCKING!
    return Panel(log_content)
```

**Solution:**
```python
# GOOD: Read file in background thread
class StatePoller:
    def poll_cycle(self):
        # This runs in background thread
        log_content = Path(log_path).read_text()
        self.queue.put(StateUpdate("log_update", log_content))

# Main thread just reads from queue (non-blocking)
def update_from_queue(self):
    while not self.state_queue.empty():
        update = self.state_queue.get_nowait()
        self.app_state.apply_update(update)
```

**Prevention:**
- Never call file I/O in view renderers
- Use `StatePoller` for all file operations
- Keep main event loop non-blocking

### 2. Forgetting to Update AppState

**Symptom:** UI doesn't reflect changes after keypress

**Problem:**
```python
# BAD: Modifying local variable
def handle_key(self, key):
    selected_project = self.app_state.selected_project
    selected_project += 1  # Local change only!
    return True, None
```

**Solution:**
```python
# GOOD: Update AppState fields directly
def handle_key(self, key):
    self.app_state.selected_project += 1  # Modifies state
    return True, None
```

**Verification in tests:**
```python
def test_key_handler_updates_state():
    handler.handle_key("down")
    assert app_state.selected_project == 1  # Verify state changed
```

### 3. Race Conditions in Polling

**Symptom:** Inconsistent state or crashes during updates

**Problem:**
```python
# BAD: No synchronization
class StatePoller:
    def poll_cycle(self):
        self.state.runners = load_runner_state()  # Thread 1

# Meanwhile in main thread:
def render():
    for runner in state.runners:  # Thread 2 reading
        # Race condition! List might be modified during iteration
```

**Solution:**
```python
# GOOD: Use queue for cross-thread communication
class StatePoller:
    def poll_cycle(self):
        runners = load_runner_state()
        self.queue.put(StateUpdate("runners", runners))  # Thread-safe

# Main thread updates state from queue
def update_from_queue(self):
    while not self.queue.empty():
        update = self.queue.get_nowait()
        self.state.runners = update.data  # Single-threaded
```

**Use locks for shared mutable state:**
```python
from threading import Lock

class RunnerManager:
    def __init__(self):
        self._lock = Lock()
        self._runners = []

    def start_runner(self, ...):
        with self._lock:
            self._runners.append(runner)
```

### 4. Terminal State Not Restored

**Symptom:** Terminal shows no cursor or garbled output after TUI exits

**Problem:**
```python
# BAD: No cleanup on exit
def run(self):
    live = Live(layout)
    live.start()
    while True:
        key = get_key()
        if key == "q":
            sys.exit(0)  # Doesn't cleanup!
```

**Solution:**
```python
# GOOD: Use context manager and cleanup
def run(self):
    try:
        with Live(layout, screen=True) as live:
            while True:
                key = get_key()
                if key == "q":
                    break  # Exits context, restores terminal
    finally:
        self.cleanup()  # Additional cleanup if needed
```

**Test cleanup:**
```bash
# After running TUI, check cursor is visible
echo "Cursor should be visible"

# If not, TUI didn't restore terminal state properly
```

### 5. Not Handling Missing Files

**Symptom:** TUI crashes when log files or tasks.md are missing

**Problem:**
```python
# BAD: Assumes file exists
def poll_cycle(self):
    content = Path(log_path).read_text()  # FileNotFoundError!
    self.queue.put(StateUpdate("log", content))
```

**Solution:**
```python
# GOOD: Handle missing files gracefully
def poll_cycle(self):
    try:
        if Path(log_path).exists():
            content = Path(log_path).read_text()
            self.queue.put(StateUpdate("log", content))
        else:
            # Show "Waiting for logs..." in UI
            self.queue.put(StateUpdate("log", None))
    except (FileNotFoundError, PermissionError) as e:
        logger.warning("log_read_error", extra={"error": str(e)})
        # Continue polling, don't crash
```

**Graceful degradation:**
- Show cached data if file read fails
- Display helpful messages ("No logs yet")
- Log warnings but continue operation

### 6. Incorrect PID Validation

**Symptom:** Stale runner entries shown as active or false "runner stopped" messages

**Problem:**
```python
# BAD: Assumes PID exists means process is ours
def is_running(self, pid):
    return psutil.pid_exists(pid)  # Could be a different process!
```

**Solution:**
```python
# GOOD: Validate PID is our process
def is_running(self, pid, expected_cmdline):
    try:
        process = psutil.Process(pid)
        # Check command line to ensure it's our runner
        cmdline = " ".join(process.cmdline())
        return expected_cmdline in cmdline
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
```

**Or use os.kill for basic check:**
```python
import os, errno

def is_running(self, pid):
    try:
        os.kill(pid, 0)  # Signal 0 checks if process exists
        return True
    except OSError as e:
        if e.errno == errno.ESRCH:  # No such process
            return False
        elif e.errno == errno.EPERM:  # Permission denied (exists)
            return True
        raise
```

### 7. Not Mocking External Dependencies in Tests

**Symptom:** Tests fail when run without project files or git repo

**Problem:**
```python
# BAD: Test depends on real file system
def test_load_tasks():
    tasks = read_task_stats("tasks.md")  # Reads real file!
    assert len(tasks) > 0
```

**Solution:**
```python
# GOOD: Mock file system
@patch("pathlib.Path.read_text")
def test_load_tasks(mock_read_text):
    mock_read_text.return_value = "- [x] Task 1\n- [ ] Task 2"
    tasks = read_task_stats("tasks.md")
    assert tasks.completed == 1
    assert tasks.pending == 1
```

**Mock subprocess for runner tests:**
```python
@patch("subprocess.Popen")
def test_start_runner(mock_popen):
    mock_process = MagicMock()
    mock_process.pid = 12345
    mock_popen.return_value = mock_process

    runner = runner_manager.start_runner(...)
    assert runner.pid == 12345
```

---

## Example Iteration Session

Here's a complete example of using the workflow to fix a bug:

### Problem: Arrow key navigation doesn't wrap around

**Step 1: Run with debug**
```bash
spec-workflow-tui --debug
```

**Step 2: Reproduce**
- Navigate to last spec in tree using down arrow
- Press down arrow again
- Expected: Jump to first spec
- Actual: Nothing happens (stuck at last)

**Step 3: Check logs**
```bash
tail ~/.cache/spec-workflow-runner/tui.log | jq 'select(.event == "navigation")'
# No navigation event logged - might not have logging here
```

**Step 4: Write failing test**
```python
# tests/tui/test_keybindings.py
def test_down_arrow_wraps_from_last_to_first():
    app_state = AppState(
        projects=[
            ProjectState("proj1", [SpecState("spec1")]),
            ProjectState("proj2", [SpecState("spec2")])
        ],
        selected_project=1,  # Last project
        selected_spec=0
    )
    handler = KeybindingHandler(app_state, mock_runner_manager)

    handled, msg = handler.handle_key("down")

    assert handled is True
    assert app_state.selected_project == 0  # Wrapped to first
```

Run test:
```bash
pytest tests/tui/test_keybindings.py::test_down_arrow_wraps_from_last_to_first -v
# FAILS: AssertionError: assert 1 == 0
```

**Step 5: Fix code**
```python
# src/spec_workflow_runner/tui/keybindings.py
def _handle_arrow_down(self) -> tuple[bool, str | None]:
    total = len(self.app_state.projects)
    if total == 0:
        return True, None

    # Add wrapping logic
    current = self.app_state.selected_project
    self.app_state.selected_project = (current + 1) % total  # Wrap!
    self.app_state.selected_spec = 0
    return True, None
```

**Step 6: Verify fix**
```bash
pytest tests/tui/test_keybindings.py::test_down_arrow_wraps_from_last_to_first -v
# PASSED

# Run all tests to check for regressions
pytest tests/tui/ -v
# All pass
```

**Step 7: Check metrics**
```bash
python scripts/collect_metrics.py
# All metrics within thresholds
```

**Commit:**
```bash
git add src/spec_workflow_runner/tui/keybindings.py tests/tui/test_keybindings.py
git commit -m "fix(tui): add wrapping to arrow key navigation

Arrow keys now wrap from last item to first (down) and from
first item to last (up) for better navigation UX."
```

---

## Performance Optimization Tips

### Profiling TUI Performance

```bash
# Profile startup time
python -m cProfile -o startup.prof -c "from spec_workflow_runner.tui.app import TUIApp; app = TUIApp(config); app.initialize()"

# Analyze profile
python -m pstats startup.prof
> sort cumulative
> stats 20
```

### Reducing Render Overhead

**Avoid re-rendering everything:**
```python
# BAD: Re-render on every loop iteration
def run(self):
    while True:
        live.update(self.render_layout())  # Always renders!
        time.sleep(0.1)
```

**GOOD: Only render on state change:**
```python
def run(self):
    needs_render = True
    while True:
        if needs_render:
            live.update(self.render_layout())
            needs_render = False

        # Check for updates
        if self.state_queue.has_updates():
            self.process_updates()
            needs_render = True
```

### Optimizing File Polling

**Use mtime to skip unchanged files:**
```python
class StatePoller:
    def __init__(self):
        self._last_mtimes = {}

    def poll_cycle(self):
        for file_path in self.watch_paths:
            current_mtime = file_path.stat().st_mtime
            if current_mtime != self._last_mtimes.get(file_path):
                # File changed, read it
                self._read_and_publish(file_path)
                self._last_mtimes[file_path] = current_mtime
```

---

## Conclusion

This workflow enables rapid iteration by providing:
- Fast feedback through debug logging
- Test-driven approach to prevent regressions
- Performance monitoring to maintain speed
- Common pitfall awareness to avoid mistakes

**Remember the key principle: Identify → Test → Fix → Verify → Commit**

For more information:
- [TUI Guide](TUI_GUIDE.md) - User-facing documentation
- [README](../README.md) - Installation and basic usage
- Project CLAUDE.md - Code quality standards
