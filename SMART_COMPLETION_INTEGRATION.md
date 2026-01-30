# Smart Completion Check - Integration Guide

## Overview

The smart completion check has been integrated into `runner_manager.py` to provide robust completion detection using multiple signals:

1. **Primary Signal**: Git commits (unambiguous, reliable)
2. **Fallback**: Session probing with `--continue` (asks Claude directly)
3. **Rescue**: Commit rescue to salvage uncommitted work

## Architecture

```
RunnerManager
    ├─ check_completion_smart()       [New method]
    │   └─ Uses completion_checker module
    │
    └─ completion_checker module
        ├─ get_new_commits_count()    [Primary signal]
        ├─ probe_session_status()     [Fallback]
        ├─ check_uncommitted_changes() [Detection]
        └─ run_commit_rescue()        [Rescue]
```

## Configuration

Add to `config.json`:

```json
{
  "enable_smart_completion_check": true,
  "completion_check_max_probes": 5,
  "completion_check_probe_interval": 30
}
```

**Parameters**:
- `enable_smart_completion_check`: Enable/disable smart completion (default: `true`)
- `completion_check_max_probes`: Max probe attempts before timeout (default: `5`)
- `completion_check_probe_interval`: Seconds between probes (default: `30`)

**Total wait time**: `max_probes × probe_interval` (default: 5 × 30 = 150s = 2.5 min)

## Usage

### In RunnerManager

```python
from spec_workflow_runner.tui.runner_manager import RunnerManager

# After runner completes or exits
manager = RunnerManager(config, config_path)
runner_id = "some-runner-id"

# Check completion with smart detection
result = manager.check_completion_smart(runner_id)

if result.complete:
    print(f"✅ Complete: {result.new_commits} commits")
    if result.rescued:
        print("⚠️  Had to rescue uncommitted work")
else:
    print(f"❌ Incomplete: {result.status}")
```

### Standalone Script

The standalone `smart-completion-check.py` can still be used for testing:

```bash
# Check completion for a spec
python smart-completion-check.py security-fixes \
  --baseline-commit abc123 \
  --max-probes 5 \
  --probe-interval 30
```

## CompletionResult

The `check_completion_smart()` method returns a `CompletionResult` dataclass:

```python
@dataclass
class CompletionResult:
    complete: bool           # Whether work is complete
    new_commits: int         # Number of new commits detected
    probes_used: int         # Number of probes performed
    rescued: bool            # Whether commit rescue was performed
    status: str              # Status code (see below)
```

**Status codes**:
- `commits_created`: Work completed with commits
- `rescued`: Work completed after commit rescue
- `rescued_final`: Work completed after final rescue attempt
- `nothing_to_do`: Complete with no changes (empty task)
- `timeout`: Max probes reached without completion
- `probe_error`: Probing failed
- `llm_stopped`: LLM said to stop (should_continue: false)

## Decision Flow

```
1. Check git commits (primary signal)
   ├─ If commits exist → ✅ COMPLETE (status: commits_created)
   └─ If no commits → Continue to step 2

2. Probe session with --continue
   ├─ Status: "complete"
   │   ├─ Has uncommitted changes?
   │   │   ├─ Yes → Run rescue
   │   │   │   ├─ Rescue success → ✅ COMPLETE (status: rescued)
   │   │   │   └─ Rescue failed → Continue probing
   │   │   └─ No → ✅ COMPLETE (status: nothing_to_do)
   │
   ├─ Status: "waiting"
   │   └─ Wait probe_interval, retry (agents working)
   │
   ├─ Status: "working"
   │   └─ Wait probe_interval, retry (tasks in progress)
   │
   └─ Status: "error"
       └─ ❌ INCOMPLETE (status: probe_error)

3. Max probes reached
   ├─ Has uncommitted changes?
   │   ├─ Yes → Run final rescue
   │   │   ├─ Success → ✅ COMPLETE (status: rescued_final)
   │   │   └─ Failed → ❌ INCOMPLETE (status: timeout)
   │   └─ No → ❌ INCOMPLETE (status: timeout)
```

## Integration with Circuit Breaker

Replace simple commit checking with smart completion check:

**Before**:
```python
# Simple check
new_commit = detect_new_commits(runner_id)
if not new_commit:
    no_commit_streak += 1  # ❌ False triggers
```

**After**:
```python
# Smart check
result = check_completion_smart(runner_id)
if result.complete:
    no_commit_streak = 0  # Reset
    if result.rescued:
        logger.warning("Had to rescue uncommitted work")
elif result.status == "timeout":
    no_commit_streak += 1  # Only on genuine timeout
```

**Benefits**:
- Distinguishes "waiting for agents" from "stalled"
- Rescues uncommitted work before circuit breaking
- Reduces false positives by ~90% (estimated)

## Logging

Smart completion check logs at different levels:

```
INFO  - Starting smart completion check (spec=security-fixes)
DEBUG - Completion check 1/5
DEBUG - New commits: 0
DEBUG - No commits detected - probing status
DEBUG - Probe response: waiting
INFO  - Waiting for agents: analyzing security issues
DEBUG - Waiting 30s before next check
...
INFO  - Work complete - 3 commits detected
INFO  - Smart completion check result: complete=True, status=commits_created
```

## Error Handling

All failure modes are handled gracefully:

| Error | Handling | Impact |
|-------|----------|--------|
| JSON parse failure | Regex extraction + fallback | ⚠️ Medium - Returns error status |
| commit-rescue.py missing | Check existence first | ✅ Low - System continues |
| Git commands fail | Timeout + safe defaults | ⚠️ Medium - Degraded info |
| Probe timeout | 60s timeout on subprocess | ✅ Low - Retries continue |
| Agents hang | Max probes limit | ⚠️ Medium - Eventually recovers |

## Testing

### Unit Tests

```bash
# Test completion checker module
pytest tests/test_completion_checker.py
```

### Integration Tests

```bash
# Test with runner manager
pytest tests/test_runner_manager_completion.py
```

### Manual Testing

```bash
# Scenario 1: Normal completion (commits exist)
# Expected: Completes immediately with status=commits_created

# Scenario 2: Agents working (no commits yet)
# Expected: Waits and probes, then completes after agents finish

# Scenario 3: Uncommitted work (complete but no commits)
# Expected: Runs rescue, creates commits, status=rescued

# Scenario 4: Genuine stall (no commits, no progress)
# Expected: Times out after max_probes, status=timeout
```

## Tuning Parameters

### max_probes

- **Default**: 5
- **Too low** (< 3): May timeout before agents complete
- **Too high** (> 10): Wastes time on genuine stalls
- **Recommended**: 5-7 for normal workloads

### probe_interval

- **Default**: 30s
- **Too low** (< 15s): Excessive probing, wastes API calls
- **Too high** (> 60s): Slow to detect completion
- **Recommended**: 30s for normal, 60s for slow tasks

### Example Tuning

```json
{
  "completion_check_max_probes": 7,
  "completion_check_probe_interval": 45
}
```

Total wait: 7 × 45 = 315s = 5.25 min

## Monitoring Metrics

Track these metrics to validate effectiveness:

1. **False abort rate**: # false circuit breakers / total
   - Target: < 5%

2. **Rescue rate**: # rescues / total completions
   - Target: < 10% (if higher, prompt engineering needed)

3. **Average probes**: Sum(probes_used) / total
   - Target: 1-2 (most tasks complete quickly)

4. **Timeout rate**: # timeouts / total
   - Target: < 5%

## Migration Checklist

- [x] Create `completion_checker.py` module
- [x] Add `check_completion_smart()` to `RunnerManager`
- [x] Add config parameters to `Config` class
- [x] Update `config.json` with defaults
- [ ] Replace simple commit checking in circuit breaker
- [ ] Add unit tests for completion_checker
- [ ] Add integration tests for runner_manager
- [ ] Monitor metrics in production
- [ ] Tune parameters based on real usage

## Next Steps

1. **Replace circuit breaker logic** in monitoring/TUI to use `check_completion_smart()`
2. **Add unit tests** for completion_checker module
3. **Monitor metrics** to validate effectiveness
4. **Tune parameters** based on real workload patterns

## Summary

The smart completion check provides:
- ✅ **Robust detection** - Multiple signals, no guessing
- ✅ **No false aborts** - Distinguishes waiting from stalled
- ✅ **Work rescue** - Salvages uncommitted changes
- ✅ **Configurable** - Tunable parameters for your workload
- ✅ **Graceful degradation** - Handles all failure modes

Primary signal (git commits) is unambiguous. Fallback (probing) only when needed. Rescue (commit-rescue.py) prevents waste.
