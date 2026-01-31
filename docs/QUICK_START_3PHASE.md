# Quick Start: 3-Phase Workflow

## Enable the 3-Phase Workflow

**Edit `config.json`:**

```json
{
  "enable_three_phase_workflow": true,
  "block_commits_during_implementation": true
}
```

That's it! The runner will now use the 3-phase workflow.

## What Changes

### Before (Legacy Workflow)
```
1. Pre-validation (Claude checks template)
2. Implementation (Claude codes + commits)
3. Loop
```

### After (3-Phase Workflow)
```
1. PHASE 1: validation_check.py (script validates)
   - Checks completed tasks have real implementations
   - Resets invalid completions

2. PHASE 2: Claude implements (commits BLOCKED)
   - Focus on code only
   - No git commits allowed

3. PHASE 3: completion_verify.py (script verifies)
   - Verifies acceptance criteria
   - Updates tasks.md
   - Makes git commits for verified work

4. Loop back to Phase 1
```

## Run the Workflow

```bash
# Standard run
spec-workflow-runner --spec verify

# Or use TUI
spec-workflow-tui
```

## Output

You'll see clear phase separators:

```
================================================================================
PHASE 1: PRE-SESSION VALIDATION
================================================================================

✅ All 5 completed tasks verified

================================================================================
PHASE 2: IMPLEMENTATION SESSION
================================================================================

🔒 Git commits blocked during implementation

[Claude implements...]

🔓 Git commits allowed again

================================================================================
PHASE 3: POST-SESSION VERIFICATION
================================================================================

✅ 3 tasks completed, ⏸️ 2 still in progress

✅ Verified and marked complete:
  VF-2.1: Test Fixtures Foundation
  VF-2.3: Widget Test Helpers

⏸️ Still in progress (not ready):
  VF-2.5: Repository Implementation
    - Missing files: lib/repositories/subscription_repository.dart

📝 Created 1 commit(s)
   Check logs/verify/verification_1.log for details
```

## Logs

Each iteration creates logs:

```
logs/verify/
├── validation_1.log      # Phase 1 results
├── task_1.log             # Phase 2 Claude session
├── verification_1.log     # Phase 3 results
├── validation_2.log       # Next iteration
├── task_2.log
└── verification_2.log
```

## Manual Testing (Scripts Only)

Test individual phases without the runner:

```bash
cd /path/to/project

# Phase 1: Validate
PYTHONPATH=/path/to/spec-workflow-runner/src python3 \
  /path/to/spec-workflow-runner/src/spec_workflow_runner/validation_check.py \
  verify \
  .spec-workflow/specs/verify \
  .

# Phase 2: Implement (with blocking)
PYTHONPATH=/path/to/spec-workflow-runner/src python3 \
  /path/to/spec-workflow-runner/src/spec_workflow_runner/git_hooks.py \
  install .

codex e "Implement verify spec"

PYTHONPATH=/path/to/spec-workflow-runner/src python3 \
  /path/to/spec-workflow-runner/src/spec_workflow_runner/git_hooks.py \
  remove .

# Phase 3: Verify
PYTHONPATH=/path/to/spec-workflow-runner/src python3 \
  /path/to/spec-workflow-runner/src/spec_workflow_runner/completion_verify.py \
  verify \
  .spec-workflow/specs/verify \
  .
```

## Troubleshooting

### "Git hook not removed after crash"

```bash
# Manually remove hook
PYTHONPATH=src python3 src/spec_workflow_runner/git_hooks.py remove /path/to/project
```

### "Verification script fails"

Check the logs:
```bash
cat logs/verify/verification_1.log
```

### "Tasks not being marked complete"

This is working as designed! Tasks are only marked complete if:
1. All acceptance criteria checkboxes are checked
2. Production code exists (not just mocks/tests)
3. Required files are present

Fix the implementation and run again.

### "Want to disable 3-phase workflow"

```json
{
  "enable_three_phase_workflow": false
}
```

Runner will revert to legacy workflow.

## Benefits

✅ **Prevents fake completions** - automated file checks
✅ **Focused implementation** - no commit distractions
✅ **Honest progress** - tasks only complete if verified
✅ **Audit trail** - validation/verification logs

## Next Steps

- Read `docs/THREE_PHASE_WORKFLOW.md` for complete details
- Check `docs/CHECKBOX_FORMAT.md` for task format requirements
- See `docs/IMPLEMENTATION_SUMMARY.md` for architecture overview
