# Three-Phase Workflow System

## Problem Statement

Claude was marking tasks complete without actual implementation:
- Tasks marked `[x]` completed but only mocks/tests existed
- No production code implementation
- Claude making excuses ("we can skip this task")
- No validation that work was actually done

## Solution: 3-Phase Validation Loop

Separate **validation**, **implementation**, and **verification** into distinct phases with automated checks.

```
┌─────────────────────────────────────────────────┐
│                                                 │
│  PHASE 1: PRE-SESSION VALIDATION                │
│  ─────────────────────────────────────────      │
│  Script: validation_check.py                    │
│                                                 │
│  ✓ Check completed tasks have real impl        │
│  ✓ Detect mocks-only situations                │
│  ✓ Reset tasks if implementation missing       │
│  ✓ Update tasks.md automatically                │
│  ✓ Output: validation.log                      │
│                                                 │
└─────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│                                                 │
│  PHASE 2: IMPLEMENTATION SESSION                │
│  ──────────────────────────────────────         │
│  Claude: Focus on code only                     │
│  Git Hook: Blocks commits                       │
│                                                 │
│  ✓ Write production code                       │
│  ✓ Write tests                                  │
│  ✓ Meet acceptance criteria                    │
│  ✗ NO git commits (blocked)                     │
│  ✗ NO tasks.md updates                          │
│                                                 │
└─────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│                                                 │
│  PHASE 3: POST-SESSION VERIFICATION             │
│  ─────────────────────────────────────────      │
│  Script: completion_verify.py                   │
│  Claude (optional): Make commits                │
│                                                 │
│  ✓ Check acceptance criteria met               │
│  ✓ Verify files exist (not just mocks)         │
│  ✓ Update tasks.md (only verified work)        │
│  ✓ Make git commits for verified work          │
│  ✓ Output: verification.log                    │
│                                                 │
└─────────────────────────────────────────────────┘
```

## Architecture Components

### 1. validation_check.py
**Purpose**: Pre-session validation script

**What it does**:
- Reads tasks.md and finds completed tasks (`[x]`)
- Extracts file paths from each task
- Checks if implementation files exist
- Detects mock-only or test-only situations
- Resets invalid completions to in-progress (`[-]`)
- Outputs validation report

**Usage**:
```bash
python validation_check.py <spec_name> <spec_path> <project_path>
```

**Output**:
```
✅ All 5 completed tasks verified

OR

🔄 Reset 2/5 tasks with missing implementations

❌ Invalid tasks reset to in-progress:

  VF-2.5: Repository Implementation Unit Tests
    - Only test/mock files exist, no production implementation found
    - Missing implementation: lib/repositories/subscription_repository.dart
```

### 2. completion_verify.py
**Purpose**: Post-session verification script

**What it does**:
- Reads tasks.md and finds in-progress tasks (`[-]`)
- Checks if acceptance criteria checkboxes are met
- Verifies files were created/modified
- Detects production code (not just mocks/tests)
- Updates tasks.md (marks complete only if verified)
- Makes git commits for verified work

**Usage**:
```bash
python completion_verify.py <spec_name> <spec_path> <project_path>
python completion_verify.py <spec_name> <spec_path> <project_path> --no-commit
```

**Output**:
```
✅ 3 tasks completed, ⏸️  2 still in progress

✅ Verified and marked complete:

  VF-2.1: Test Fixtures Foundation
    Files: test/fixtures/subscription_fixtures.dart, test/fixtures/money_fixtures.dart

  VF-2.3: Widget Test Helpers
    Files: test/helpers/widget_test_helpers.dart

⏸️  Still in progress (not ready):

  VF-2.5: Repository Implementation
    - Missing files: lib/repositories/subscription_repository.dart
    - Only test/mock files exist, no production implementation found

📝 Commits created: 1
  a3b4c5d6
```

### 3. git_hooks.py
**Purpose**: Block commits during implementation phase

**What it does**:
- Installs temporary pre-commit hook
- Blocks all commits with helpful message
- Backs up existing hook (if any)
- Removes hook and restores backup after implementation

**Usage**:
```python
from git_hooks import block_commits

# Context manager
with block_commits(project_path):
    run_implementation_session()
    # Commits are blocked here

# Commits allowed again
```

**What user sees when trying to commit**:
```bash
$ git commit -m "some change"
❌ Commits are blocked during implementation phase
   The runner will create commits during post-session verification
   after validating that acceptance criteria are met.
```

### 4. Config Settings

**Enable 3-phase workflow**:
```json
{
  "enable_three_phase_workflow": true,
  "block_commits_during_implementation": true,
  "implementation_prompt": "...",
  "post_session_verification_prompt": "..."
}
```

## How It Works

### Current (Default) Flow
```
1. Pre-validation (Claude checks template compliance)
2. Implementation (Claude writes code + commits)
3. Loop until no more commits or limit reached
```

**Problem**: Claude can mark tasks complete without implementation

### New 3-Phase Flow
```
1. Phase 1: Run validation_check.py (automated)
   - Resets invalid completions
   - Updates tasks.md

2. Phase 2: Run Claude with implementation_prompt
   - Git hook blocks commits
   - Claude focuses on code only
   - No tasks.md updates

3. Phase 3: Run completion_verify.py (automated)
   - Verifies acceptance criteria
   - Updates tasks.md
   - Makes commits for verified work

4. Loop back to Phase 1 if work remains
```

**Benefit**: Automated validation prevents fake completions

## Task Format Requirements

Tasks MUST include:

### 1. Checkbox Format
```markdown
- [ ] 1. Task title (pending)
- [-] 2. Task in progress
- [x] 3. Completed task
```

### 2. File Specifications
```markdown
- **File**: lib/path/to/file.dart
- **Files**:
  - lib/repositories/subscription_repository.dart
  - test/unit/repositories/subscription_repository_test.dart
```

### 3. Acceptance Criteria
```markdown
- **Acceptance**:
  - [ ] Production code exists (not just mocks)
  - [ ] All tests pass
  - [ ] Files created match specification
  - [x] Documentation updated
```

## Validation Logic

### Valid Completion
```markdown
- [x] 2. Implement SubscriptionRepository

- **Files**:
  - lib/repositories/subscription_repository.dart ✓ exists
  - test/unit/repositories/subscription_repository_test.dart ✓ exists

- **Acceptance**:
  - [x] Production code exists
  - [x] All tests pass
  - [x] Repository pattern followed
```

**Result**: ✅ Valid - production code + tests exist

### Invalid Completion (Reset to in-progress)
```markdown
- [x] 2.5 Repository Unit Tests

- **Files**:
  - test/mocks/mock_subscription_repository.dart ✓ exists
  - test/unit/repositories/subscription_repository_test.dart ✓ exists
  - lib/repositories/subscription_repository.dart ✗ MISSING

- **Acceptance**:
  - [ ] Production repository implementation exists
  - [x] Tests written
```

**Result**: ❌ Invalid - only mocks/tests, no production code
**Action**: Reset to `- [-]` in-progress

## Running the Workflow

### Manual Testing

**Phase 1: Validate**
```bash
cd /path/to/project
python /path/to/spec-workflow-runner/src/spec_workflow_runner/validation_check.py \
  verify \
  .spec-workflow/specs/verify \
  .
```

**Phase 2: Implement** (with commit blocking)
```bash
python /path/to/spec-workflow-runner/src/spec_workflow_runner/git_hooks.py install .
codex e "Implement verify spec tasks"
python /path/to/spec-workflow-runner/src/spec_workflow_runner/git_hooks.py remove .
```

**Phase 3: Verify**
```bash
python /path/to/spec-workflow-runner/src/spec_workflow_runner/completion_verify.py \
  verify \
  .spec-workflow/specs/verify \
  .
```

### Automated (via runner)

**Enable in config.json**:
```json
{
  "enable_three_phase_workflow": true
}
```

**Run**:
```bash
spec-workflow-runner --spec verify
```

The runner will automatically:
1. Run validation_check.py before each iteration
2. Block commits during implementation
3. Run completion_verify.py after implementation
4. Loop until spec is complete

## Benefits

### 1. Prevents Fake Completions
- Automated checks for file existence
- Detects mocks-only situations
- Enforces acceptance criteria

### 2. Focus During Implementation
- Claude not distracted by commits
- No premature task updates
- Clean separation of concerns

### 3. Honest Progress Tracking
- Tasks only marked complete if verified
- Clear visibility of what's actually done
- Audit trail in verification.log

### 4. Deterministic Validation
- Scripts don't hallucinate
- Consistent validation logic
- Reproducible results

## Migration Guide

### For Existing Specs

If tasks are already marked complete incorrectly:

```bash
# Run validation to reset invalid completions
python validation_check.py <spec_name> <spec_path> <project_path>

# This will:
# 1. Check all [x] completed tasks
# 2. Reset to [-] if implementation missing
# 3. Update tasks.md automatically
```

### For New Specs

1. Create tasks.md with checkbox format
2. Include **Files**: and **Acceptance**: sections
3. Enable 3-phase workflow in config
4. Let the system validate automatically

## Troubleshooting

### "No files specified in task - cannot verify implementation"
**Fix**: Add `- **Files**: path/to/file.dart` to task

### "Only test/mock files exist, no production implementation found"
**Fix**: Implement actual production code, not just mocks

### "Acceptance criteria not fully met"
**Fix**: Check all acceptance checkboxes before marking complete

### Commits blocked but I need to commit manually
**Fix**: Remove git hook temporarily:
```bash
python git_hooks.py remove /path/to/repo
```

## Future Enhancements

- [ ] Run tests automatically in verification phase
- [ ] Integration with CI/CD for acceptance criteria
- [ ] Auto-detect file paths from codebase structure
- [ ] LLM-based acceptance criteria checking
- [ ] Parallel validation for multiple specs

## Summary

The 3-phase workflow creates a **validation loop** that prevents Claude from marking tasks complete without actual implementation. By separating validation, implementation, and verification, we ensure:

1. **Pre-session**: Invalid completions are detected and reset
2. **Implementation**: Claude focuses on code, not commits
3. **Post-session**: Only verified work is committed and marked complete

This architecture provides **deterministic validation** while allowing **AI autonomy** during implementation.
