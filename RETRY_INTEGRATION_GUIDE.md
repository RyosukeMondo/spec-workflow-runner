# Retry Functionality Integration Guide

**Date**: 2026-01-30
**Status**: ✅ INTEGRATED

---

## Overview

The retry functionality has been successfully integrated into the spec-workflow-runner system. It provides automatic crash recovery with exponential backoff for Claude/Codex subprocess execution.

## What Was Added

### 1. Core Retry Handler (`src/spec_workflow_runner/retry_handler.py`)

- **RetryConfig**: Configuration for retry behavior
- **RetryContext**: Tracks retry attempts across runs
- **RetryHandler**: Implements retry logic with exponential backoff

### 2. Configuration (`config.json`)

New configuration options added:

```json
{
  "retry_max_retries": 3,
  "retry_backoff_seconds": 5,
  "retry_on_crash": true,
  "retry_log_dir": "logs/retries",
  "retry_backoff_multiplier": 2.0,
  "retry_max_backoff_seconds": 300
}
```

### 3. Subprocess Monitoring (`subprocess_helpers.py`)

- **monitor_process_with_timeout()**: Activity monitoring with timeout detection
- **safe_terminate_process()**: Graceful process shutdown with fallback to kill

### 4. RunnerManager Integration (`tui/runner_manager.py`)

- **retry tracking** in RunnerState (retry_count, max_retries, last_retry_at)
- **maybe_retry_runner()**: Automatic retry on crash with backoff
- **State persistence**: Retry state survives TUI restarts

### 5. Utils Updates (`utils.py`)

- **RetryConfig** loaded from config.json
- Integrated into Config dataclass

---

## How It Works

### Automatic Retry Flow

1. **Runner starts** → `retry_count=0`, `max_retries=3` (from config)
2. **Process crashes** → TUI detects via `check_runner_health()`
3. **Retry check** → TUI calls `maybe_retry_runner()`
4. **Backoff applied** → Sleep for 5s (first retry), 10s (second), 20s (third)
5. **Restart process** → New subprocess with fresh log file
6. **Update state** → `retry_count++`, `last_retry_at=now()`
7. **Persist** → State saved to `~/.cache/spec-workflow-runner/runner_state.json`

### Exponential Backoff Formula

```
backoff_seconds = retry_backoff_seconds * (backoff_multiplier ^ retry_count)
backoff_seconds = min(backoff_seconds, max_backoff_seconds)
```

**Examples** (default config):
- Retry 1: 5s * (2.0 ^ 0) = 5s
- Retry 2: 5s * (2.0 ^ 1) = 10s
- Retry 3: 5s * (2.0 ^ 2) = 20s

### When Retry Happens

Automatic retry occurs when:

✅ **retry_on_crash** is `true`
✅ **retry_count** < **max_retries**
✅ **Process exited** with non-zero exit code
✅ **RunnerStatus** is `CRASHED`

### When Retry Stops

Retry is **NOT attempted** when:

❌ **max_retries** reached
❌ **retry_on_crash** is `false`
❌ **Process completed** successfully (exit code 0)
❌ **Manual stop** requested by user

---

## Configuration Options

### `retry_max_retries` (integer, default: 3)

Maximum number of retry attempts before giving up.

**Recommendations:**
- **3**: Good balance (default)
- **5**: For flaky environments
- **0**: Disable retry (set `retry_on_crash: false` instead)

### `retry_backoff_seconds` (integer, default: 5)

Initial backoff delay in seconds before first retry.

**Recommendations:**
- **5s**: Fast recovery (default)
- **10s**: More cautious
- **1s**: Aggressive (for testing)

### `retry_on_crash` (boolean, default: true)

Enable/disable automatic retry on subprocess crash.

**When to disable:**
- Debugging crashes (want immediate failure)
- CI/CD environments (fail fast)
- Development (want to see errors immediately)

### `retry_log_dir` (string, default: "logs/retries")

Directory for retry-specific logs (not yet used).

### `retry_backoff_multiplier` (float, default: 2.0)

Exponential backoff multiplier.

**Recommendations:**
- **2.0**: Standard exponential backoff (default)
- **1.5**: Slower growth
- **3.0**: Aggressive backoff

### `retry_max_backoff_seconds` (integer, default: 300)

Maximum backoff delay cap (prevents infinite wait).

**Recommendations:**
- **300s (5min)**: Default cap
- **600s (10min)**: Patient retry
- **60s (1min)**: Aggressive cap

---

## Usage Examples

### Example 1: Default Configuration

```json
{
  "retry_max_retries": 3,
  "retry_backoff_seconds": 5,
  "retry_on_crash": true
}
```

**Behavior:**
- Retry on crash: ✅
- Max attempts: 4 (1 initial + 3 retries)
- Backoff: 5s, 10s, 20s
- Total retry time: ~35s before final failure

### Example 2: Aggressive Recovery

```json
{
  "retry_max_retries": 5,
  "retry_backoff_seconds": 3,
  "retry_backoff_multiplier": 1.5,
  "retry_on_crash": true
}
```

**Behavior:**
- More retries (5 attempts)
- Faster initial retry (3s)
- Gentler backoff growth (1.5x)
- Backoff: 3s, 4.5s, 6.75s, 10.1s, 15.2s

### Example 3: Disabled Retry (Fail Fast)

```json
{
  "retry_on_crash": false
}
```

**Behavior:**
- No automatic retry
- Immediate failure on crash
- Good for debugging

### Example 4: Patient Retry (Flaky Networks)

```json
{
  "retry_max_retries": 3,
  "retry_backoff_seconds": 15,
  "retry_max_backoff_seconds": 120,
  "retry_on_crash": true
}
```

**Behavior:**
- Longer initial wait (15s)
- Capped at 2 minutes
- Backoff: 15s, 30s, 60s
- Good for network-related crashes

---

## TUI Integration

The TUI automatically uses retry functionality when:

1. **Starting a spec** via "s" key
2. **Process crashes** during execution
3. **Health check** detects crash in background

### User Experience

When retry happens:

1. **Status changes** to "RUNNING (retry 1/3)"
2. **Log file updates** with new timestamp
3. **PID changes** to new subprocess
4. **Backoff visible** in status messages

### Manual Retry

Users can manually restart a crashed runner:
- Press "r" key on stopped/crashed spec
- Restarts with last-used provider/model
- Does NOT count towards automatic retry limit

---

## Monitoring Retry Activity

### Check Retry Status in TUI

Look for:
- **Retry count** in status panel: "Retry: 2/3"
- **Last retry timestamp** in status panel
- **Multiple log files** with sequential timestamps

### Check Logs

Retry logs are written to:
```
<project>/.spec-workflow/logs/task_<index>.log
```

With sequential index numbers for retries:
- `task_1.log` - Initial run
- `task_2.log` - First retry
- `task_3.log` - Second retry

### Check Persisted State

Retry state is saved to:
```
~/.cache/spec-workflow-runner/runner_state.json
```

Example entry:
```json
{
  "runner_id": "abc-123",
  "retry_count": 2,
  "max_retries": 3,
  "last_retry_at": "2026-01-30T20:15:30Z",
  "status": "running"
}
```

---

## Debugging Retry Issues

### Problem: Too Many Retries

**Symptom**: Runner retries forever, never succeeds

**Solution**:
1. Check logs for actual error
2. Fix root cause (API keys, permissions, etc.)
3. Consider reducing `retry_max_retries`

### Problem: Not Retrying

**Symptom**: Runner crashes and doesn't retry

**Checks**:
1. ✅ `retry_on_crash: true` in config?
2. ✅ `retry_count` < `max_retries`?
3. ✅ Exit code is non-zero?
4. ✅ TUI calling `maybe_retry_runner()`?

### Problem: Retries Too Fast

**Symptom**: Retries happen too quickly, overwhelming system

**Solution**:
- Increase `retry_backoff_seconds` to 10-15
- Increase `retry_backoff_multiplier` to 2.5-3.0

### Problem: Retries Too Slow

**Symptom**: Long wait between retries

**Solution**:
- Decrease `retry_backoff_seconds` to 3-5
- Decrease `retry_backoff_multiplier` to 1.5
- Decrease `retry_max_backoff_seconds` to 60-120

---

## Testing Retry Functionality

### Manual Test: Simulate Crash

1. Start a spec runner in TUI
2. Kill the process manually: `kill -9 <PID>`
3. Wait for TUI to detect crash
4. Observe automatic retry with backoff

### Manual Test: Disable Retry

```json
{
  "retry_on_crash": false
}
```

1. Start a spec runner
2. Kill the process
3. Verify no automatic retry (stays CRASHED)

### Manual Test: Exhaust Retries

```json
{
  "retry_max_retries": 1,
  "retry_backoff_seconds": 3
}
```

1. Start a spec runner
2. Kill the process twice
3. Observe one retry, then final CRASHED state

---

## Integration with Existing Features

### ✅ Compatible With

- **TUI monitoring** - Retry state visible in status panel
- **State persistence** - Retry survives TUI restart
- **Multiple runners** - Each runner has independent retry state
- **Log files** - Sequential logs for each retry
- **Commit detection** - Works across retries

### ⚠️ Considerations

- **Resource usage**: Retries consume CPU/memory (use `max_retries` wisely)
- **API rate limits**: Retries may trigger rate limits (increase backoff)
- **Long-running tasks**: Retries extend total execution time

---

## Future Enhancements

Potential improvements (not implemented):

1. **Retry reasons** - Track why each retry was needed
2. **Selective retry** - Only retry certain error types
3. **Jitter** - Add random jitter to backoff to prevent thundering herd
4. **Retry budget** - Global retry limit across all runners
5. **Notification** - Alert user when retry exhausted

---

## Files Modified

```
✅ src/spec_workflow_runner/retry_handler.py  [NEW]
✅ src/spec_workflow_runner/subprocess_helpers.py
✅ src/spec_workflow_runner/utils.py
✅ src/spec_workflow_runner/tui/models.py
✅ src/spec_workflow_runner/tui/runner_manager.py
✅ config.json
```

---

## Commits

1. `ebda191` - feat(retry): add retry handler with crash detection and exponential backoff
2. `73b179c` - feat(subprocess): add process monitoring with timeout detection
3. `6991250` - feat(runner): integrate retry logic into RunnerManager

---

## Summary

The retry functionality provides robust crash recovery for spec-workflow-runner:

✅ **Automatic retry** on subprocess crash
✅ **Exponential backoff** to prevent overwhelming system
✅ **Configurable** via `config.json`
✅ **State persistence** across TUI restarts
✅ **TUI integration** with status visibility
✅ **Independent per runner** - doesn't affect other specs

**Default behavior**: 3 retries with 5s, 10s, 20s backoff (~35s total)

---

**Next Steps**: Use the retry functionality in production and monitor effectiveness. Adjust configuration based on real-world crash patterns.
