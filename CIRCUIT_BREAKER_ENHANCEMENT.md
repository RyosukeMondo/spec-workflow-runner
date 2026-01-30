# Circuit Breaker Enhancement: Intelligent Commit Rescue

## Problem

Current circuit breaker triggers after 3 iterations with no commits, even if good work was done:

```
Iteration 1: No commits (streak: 1/3)
Iteration 2: No commits (streak: 2/3)
Iteration 3: No commits (streak: 3/3) → CIRCUIT BREAKER TRIGGERS ❌
Result: Abort even if Tasks 3.2 and 3.3 were implemented correctly
```

**Issue**: LLM may do good work but forget to commit, causing circuit breaker to waste the work.

## Solution: Commit Rescue Mode

Before triggering circuit breaker, check for uncommitted changes and attempt rescue:

```python
def check_circuit_breaker(no_commit_streak, project_path, spec_name):
    """Enhanced circuit breaker with commit rescue."""

    if no_commit_streak >= NO_COMMIT_LIMIT:
        # Instead of immediate failure, check for uncommitted work
        if has_uncommitted_changes():
            print("⚠️  Circuit breaker triggered, but uncommitted changes detected")
            print("🚑 Attempting commit rescue...")

            # Run rescue prompt
            rescue_success = run_commit_rescue(spec_name, project_path)

            if rescue_success:
                print("✅ Rescue successful! Resetting circuit breaker.")
                return 0  # Reset streak
            else:
                print("❌ Rescue failed. Work may be lost.")
                raise CircuitBreakerError("Rescue failed")
        else:
            # No uncommitted changes, genuine stall
            raise CircuitBreakerError("3 iterations with no progress")

    return no_commit_streak
```

## Implementation

### 1. Detection Logic

```python
def has_uncommitted_changes() -> bool:
    """Check if uncommitted changes exist."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
    )
    return len(result.stdout.strip()) > 0
```

### 2. Rescue Prompt

The rescue prompt should:
1. Show `git status` and `git diff` output
2. Instruct Claude to analyze what was implemented
3. Create atomic commits for each logical change
4. Update tasks.md based on actual code changes
5. Commit tasks.md separately

Example rescue prompt:
```
COMMIT RESCUE TASK

You implemented work on spec 'security-fixes' but forgot to commit.

Changed files (5):
- src/Infrastructure/Linux/LinuxKeyringManager.cs
- src/Infrastructure/Security/ApiKeyManager.cs
- tests/Security/ApiKeyManagerTests.cs
- .spec-workflow/specs/security-fixes/tasks.md
- src/Infrastructure/DependencyInjection/PlatformServiceRegistration.cs

Your task:
1. Run: git status && git diff --stat
2. Read: .spec-workflow/specs/security-fixes/tasks.md
3. Analyze which tasks were completed based on code changes
4. Create atomic commits:
   - git add src/Infrastructure/Linux/LinuxKeyringManager.cs
   - git commit -m "feat(security): implement LinuxKeyringManager"
   - git add src/Infrastructure/Security/ApiKeyManager.cs tests/...
   - git commit -m "refactor(security): use ISecureStorage in ApiKeyManager"
5. Update tasks.md: Mark Tasks 3.2, 3.3 as Completed
6. Commit: git add tasks.md && git commit -m "chore(spec): update task status"

DO NOT ASK QUESTIONS. Commit the work NOW.
```

### 3. Integration Points

**In `run_tasks.py` (or monitoring script)**:

```python
# After detecting no new commit
if last_commit == baseline_commit:
    no_commit_streak += 1

    if no_commit_streak >= NO_COMMIT_LIMIT:
        # Check for uncommitted changes
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=project_path,
        )

        if result.stdout.strip():
            # Uncommitted changes detected - attempt rescue
            print(f"[!]  Circuit breaker: {no_commit_streak}/{NO_COMMIT_LIMIT}")
            print("     Uncommitted changes detected - attempting rescue...")

            rescue_script = Path(__file__).parent / "commit-rescue.py"
            rescue_result = subprocess.run(
                ["python", str(rescue_script), spec_name, "--project-path", project_path],
                capture_output=False,  # Show output
            )

            if rescue_result.returncode == 0:
                print("✅ Rescue successful - resetting circuit breaker")
                no_commit_streak = 0
                continue
            else:
                print("❌ Rescue failed - circuit breaker triggered")
                raise CircuitBreakerError("Rescue attempt failed")
        else:
            # No changes - genuine stall
            raise CircuitBreakerError(f"No commits for {no_commit_streak} iterations")
```

## Benefits

### Before (Current Behavior)
```
Iteration 3: Implements Tasks 3.2, 3.3 ✅
             Forgets to commit ❌
             Circuit breaker triggers 🔴
             Work lost
```

### After (With Rescue)
```
Iteration 3: Implements Tasks 3.2, 3.3 ✅
             Forgets to commit ❌
             Circuit breaker detects changes 🟡
             Rescue mode activated 🚑
             Creates 2 commits ✅
             Updates tasks.md ✅
             Resets circuit breaker 🟢
             Work saved! Continue iteration 4
```

## Configuration

Add to `config.json`:

```json
{
  "circuit_breaker": {
    "no_commit_limit": 3,
    "enable_rescue": true,
    "rescue_timeout_seconds": 300,
    "rescue_max_attempts": 1
  }
}
```

## Edge Cases

### Case 1: Rescue Also Fails to Commit
- Allow ONE rescue attempt per circuit breaker trigger
- If rescue fails, trigger circuit breaker normally
- Log rescue failure for debugging

### Case 2: Partial Commits
- Rescue creates some commits but not all
- Check `git status` after rescue
- If still has changes, consider rescue failed

### Case 3: Invalid Changes
- Rescue finds changes that break build
- Should still commit (with proper message indicating WIP)
- Better to have committed WIP than lose all work

### Case 4: tasks.md Not Updated
- Rescue should ALWAYS update tasks.md as final step
- Even if uncertain, make best guess based on code changes

## Testing

```bash
# Test rescue mechanism
cd test-project

# Create changes without committing
echo "new file" > test.txt

# Trigger rescue
python commit-rescue.py test-spec

# Verify
git log -1  # Should show new commit
git status  # Should be clean
```

## Rollback

If rescue causes issues:

```json
{
  "circuit_breaker": {
    "enable_rescue": false
  }
}
```

Fallback to original immediate circuit breaker trigger.

## Success Metrics

Track rescue effectiveness:
- **Rescue success rate**: % of rescues that successfully commit all changes
- **Work saved**: # of iterations saved from abort
- **False positives**: # of rescues that created bad commits

Target: >80% rescue success rate

## Future Enhancements

1. **Smart commit grouping**: Use AI to group related files into logical commits
2. **Conflict resolution**: Handle merge conflicts during rescue
3. **Partial rescue**: Save what can be saved, mark rest as WIP
4. **Rescue history**: Track rescue attempts for debugging

## Summary

**Before**: Circuit breaker = immediate abort = wasted work
**After**: Circuit breaker = rescue attempt = saved work + continue

This enhancement makes the system much more robust to LLM forgetfulness while maintaining circuit breaker safety.
