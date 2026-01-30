# Claude Process Crash Analysis

**Date**: 2026-01-30 19:46:14
**Project**: spec-workflow-runner
**Issue**: Claude process unexpected termination

## What Happened

The Claude process was running with:
- `--output-format stream-json`
- `--verbose`
- Activity timeout: 300s (5 minutes)
- Working on spec: `text-selection-annotations`

Process terminated unexpectedly at **19:46:14** during an Edit tool call.

## Root Cause Analysis

### Primary Issue: Spec Doesn't Exist

The command specified working on `text-selection-annotations` spec, but this spec **does not exist** in this project.

Available specs in `spec-workflow-runner`:
- task-auto-fix
- test-streaming
- tui-unified-runner

The `text-selection-annotations` spec likely exists in a different project (possibly a C# PDF viewer project based on the file paths shown in the output).

### Secondary Issues

1. **Wrong working directory**: Claude was in the wrong project
2. **Missing validation**: No check if spec exists before starting
3. **Stream JSON parsing**: Possible issue with output format under error conditions
4. **No crash logs**: Exit was silent without error messages

## Why This Caused a Crash

When Claude tried to:
1. Read `.spec-workflow/specs/text-selection-annotations/tasks.md` → File not found
2. Make edits to ViewModels that don't exist in this project → Failed
3. Stream JSON output may have corrupted on errors → Parser crash

## Differences from Worker Timeout Issue

This is **NOT** the same as your previous worker timeout issue:

| Worker Timeout Issue | This Crash |
|---------------------|------------|
| Workers running too long (>5 min) | Process crashed mid-execution |
| Predictable timeout pattern | Sudden unexpected termination |
| Log shows "Process exited with code null" | No error message at all |
| Fixed by increasing timeout | Different root cause |

## How to Prevent This

### 1. Validate Spec Exists

Before running Claude on a spec, verify:
```bash
# Check spec exists
ls .spec-workflow/specs/YOUR_SPEC_NAME/tasks.md

# Or use validation
if [ ! -f ".spec-workflow/specs/YOUR_SPEC_NAME/tasks.md" ]; then
    echo "Error: Spec 'YOUR_SPEC_NAME' not found"
    exit 1
fi
```

### 2. Use Correct Working Directory

Make sure you're in the right project:
```bash
# For spec-workflow-runner specs:
cd C:\Users\ryosu\repos\spec-workflow-runner

# For PDF viewer specs (text-selection-annotations):
cd <path-to-pdf-viewer-project>
```

### 3. Add Error Handling to Runner

Wrap Claude execution with:
- Pre-flight checks (spec exists, git clean, etc.)
- Better error capture (stderr, exit codes)
- Crash recovery (save partial progress)
- Detailed logging

### 4. Use Safer Output Format

Consider using `--output-format text` instead of `stream-json` for more resilient output handling:
```bash
claude --print --model sonnet --output-format text
```

## Retry Instructions

### Option A: Retry in Correct Project (PDF Viewer)

If you meant to work on the PDF viewer text-selection-annotations spec:

```bash
# Navigate to the PDF viewer project
cd <path-to-pdf-viewer-project>

# Verify spec exists
ls .spec-workflow/specs/text-selection-annotations/tasks.md

# Retry with the retry script
python path/to/retry-with-logging.py text-selection-annotations
```

### Option B: Work on This Project's Specs

If you want to work on specs in `spec-workflow-runner`:

```bash
# Available specs:
# - task-auto-fix
# - test-streaming
# - tui-unified-runner

# Example:
python retry-with-logging.py test-streaming
```

### Option C: Simple Direct Retry

For quick retry without the wrapper:

```bash
claude --print --model sonnet --dangerously-skip-permissions \
  "Work on the test-streaming spec. Read .spec-workflow/specs/test-streaming/tasks.md and continue implementation."
```

## Enhanced Retry Script

I created `retry-with-logging.py` which includes:

✅ **Crash detection**: Monitors for unexpected termination
✅ **Activity timeout**: Warns if no output for 5 minutes
✅ **Full logging**: Saves stdout/stderr to timestamped files
✅ **Unicode handling**: Prevents encoding crashes
✅ **Exit code reporting**: Clear success/failure indication

Usage:
```bash
# Make sure you're in the correct project first!
cd <correct-project-path>

# Then run:
python retry-with-logging.py <spec-name>
```

## Recommended Next Steps

1. **Identify the correct project** for `text-selection-annotations`
2. **Navigate to that project**
3. **Verify the spec exists**:
   ```bash
   ls .spec-workflow/specs/text-selection-annotations/
   ```
4. **Use the retry script**:
   ```bash
   python C:\Users\ryosu\repos\spec-workflow-runner\retry-with-logging.py text-selection-annotations
   ```
5. **Monitor the logs** in `logs/claude-runs/`

## System Checks

Before retrying, verify:

- [ ] Correct working directory (where the spec actually lives)
- [ ] Spec files exist: `tasks.md`, `requirements.md`, `design.md`
- [ ] Git status clean or changes are intentional
- [ ] Enough disk space for logs
- [ ] No antivirus blocking Claude process
- [ ] System resources available (memory, CPU)

## Debugging Future Crashes

If crashes continue:

1. **Check Windows Event Viewer**: Application logs for crash details
2. **Monitor Task Manager**: Watch memory usage during Claude run
3. **Test with simpler prompts**: See if specific operations trigger crashes
4. **Try different output formats**: `text` vs `stream-json`
5. **Update Claude**: `npm install -g @anthropic-ai/claude-code@latest`

---

**Next Action**: Determine which project contains `text-selection-annotations` and retry there.
