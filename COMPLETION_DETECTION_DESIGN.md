# Completion Detection System - High-Level Design

## Problem Statement

When Claude works on tasks, it can end in multiple ambiguous states:
1. **Complete**: Work done, commits created
2. **Waiting**: Launched agents/workers running in background
3. **Working**: Still implementing tasks
4. **Stalled**: No progress, genuine failure
5. **Forgot to commit**: Work done but uncommitted

**Challenge**: External monitoring can't distinguish between these states, leading to:
- False circuit breaker triggers (aborting active work)
- Lost work (not rescuing uncommitted changes)
- Wasted resources (waiting for stalled sessions)

## Core Design Principles

### 1. Single Source of Truth: Git Commits

**Primary Signal**: New git commits = work complete

```
if new_commits > 0:
    ✅ COMPLETE - Work is done
```

**Why**:
- Unambiguous: Either commits exist or they don't
- Reliable: Git is the source of truth for code changes
- Simple: One check, no heuristics needed

### 2. Ask, Don't Guess

**When no commits**: Use `claude --continue` to ask Claude directly

```
if new_commits == 0:
    status = probe_session_status()  # Ask Claude
    # Don't guess from logs/heuristics
```

**Why**:
- Claude knows its own state better than external detection
- JSON response is structured and parsable
- Avoids fragile heuristics (parsing log messages, checking file timestamps)

### 3. Rescue Before Abort

**When work exists but no commits**: Salvage before circuit breaking

```
if status == "complete" and has_uncommitted_changes:
    run_commit_rescue()
    # Then re-check commits
```

**Why**:
- Prevents wasted work
- LLM might complete tasks but forget to commit
- Always better to have a commit than lose work

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SMART COMPLETION CHECK                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                ┌─────────────────────────┐
                │  1. CHECK GIT COMMITS   │
                │  (Primary Signal)       │
                └─────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
             new_commits > 0      new_commits == 0
                    │                   │
                    ▼                   ▼
            ┌──────────────┐   ┌─────────────────┐
            │   COMPLETE   │   │  2. PROBE STATUS │
            │   ✅ Done    │   │  (--continue)    │
            └──────────────┘   └─────────────────┘
                                        │
                        ┌───────────────┼───────────────┐
                        │               │               │
                  status:         status:         status:
                 "complete"      "waiting"       "working"
                        │               │               │
                        ▼               ▼               ▼
              ┌──────────────┐  ┌────────────┐  ┌──────────┐
              │3. CHECK CHANGES  │ WAIT FOR   │  │ CONTINUE │
              │   Uncommitted?│  │ AGENTS     │  │ PROBING  │
              └──────────────┘  └────────────┘  └──────────┘
                        │               │               │
                ┌───────┴───────┐       │               │
                │               │       │               │
          has_changes    no_changes    │               │
                │               │       │               │
                ▼               ▼       ▼               ▼
        ┌──────────────┐  ┌─────────┐ │         Loop back
        │4. COMMIT      │  │ DONE    │ │         to step 1
        │   RESCUE      │  │ (empty) │ │         after wait
        └──────────────┘  └─────────┘ │
                │                      │
                ▼                      │
        Re-check commits ──────────────┘
```

## Component Breakdown

### Component 1: Git Commit Checker

**Purpose**: Primary completion signal

**Function**: `get_new_commits_count(project_path, baseline_commit) -> int`

**Input**:
- Project path
- Baseline commit (snapshot before work started)

**Output**: Number of new commits

**Logic**:
```bash
git rev-list {baseline}..HEAD --count
```

**Robustness**:
- ✅ No parsing required (just count)
- ✅ Works regardless of LLM behavior
- ✅ Atomic check (either commits exist or not)
- ✅ No race conditions

---

### Component 2: Session Status Prober

**Purpose**: Ask Claude about current state when no commits detected

**Function**: `probe_session_status(project_path) -> dict`

**Input**: Project path

**Output**: JSON status dict:
```json
{
  "status": "complete|waiting|working",
  "message": "Brief description",
  "agents_active": true/false,
  "agents_details": "What agents are doing",
  "tasks_completed": ["Task 1.1"],
  "tasks_pending": ["Task 1.2"],
  "commits_made": 0,
  "should_continue": true/false,
  "next_action": "What should happen next"
}
```

**Implementation**:
```bash
claude --continue --print --model sonnet << EOF
STATUS PROBE - Respond in JSON only:
{...}
EOF
```

**Robustness**:
- ✅ Structured JSON response (no heuristic parsing)
- ✅ Claude knows its own state
- ✅ Includes agent information
- ✅ Provides actionable next steps
- ❌ **Fragile point**: JSON parsing can fail if LLM doesn't follow format
  - **Mitigation**: Regex extraction handles markdown-wrapped JSON
  - **Mitigation**: Fallback to error status on parse failure
  - **Mitigation**: Timeout prevents hanging

---

### Component 3: Uncommitted Changes Checker

**Purpose**: Detect work that exists but wasn't committed

**Function**: `check_uncommitted_changes(project_path) -> dict`

**Input**: Project path

**Output**: Dict with changed files info

**Logic**:
```bash
git status --porcelain
```

**Robustness**:
- ✅ Standard git command
- ✅ Porcelain format (stable output)
- ✅ Distinguishes staged vs unstaged
- ✅ Works regardless of LLM state

---

### Component 4: Commit Rescue

**Purpose**: Salvage uncommitted work before aborting

**Function**: `run_commit_rescue(project_path, spec_name) -> bool`

**Input**:
- Project path
- Spec name

**Output**: Success/failure boolean

**Implementation**:
- Calls existing `commit-rescue.py` script
- Analyzes changes and creates atomic commits
- Updates tasks.md based on actual work done

**Robustness**:
- ✅ Reuses battle-tested commit-rescue.py
- ✅ LLM analyzes actual changes (not assumptions)
- ✅ Creates proper conventional commits
- ❌ **Fragile point**: commit-rescue.py might not exist
  - **Mitigation**: Check file existence first
  - **Mitigation**: Return False if missing (graceful degradation)

---

### Component 5: Smart Completion Check (Orchestrator)

**Purpose**: Coordinate all components with retry logic

**Function**: `smart_completion_check(...) -> dict`

**Input**:
- Project path
- Spec name
- Baseline commit
- Max probes
- Probe interval

**Output**: Result dict with completion status

**Decision Tree**:

```python
for probe in range(max_probes):

    # Step 1: Check commits (PRIMARY)
    new_commits = get_new_commits_count()
    if new_commits > 0:
        return COMPLETE  # ✅ Done

    # Step 2: Probe status (FALLBACK)
    status = probe_session_status()

    if status == "complete":
        # Check for uncommitted work
        changes = check_uncommitted_changes()
        if changes:
            # Step 3: Rescue
            if commit_rescue():
                new_commits = get_new_commits_count()
                if new_commits > 0:
                    return COMPLETE  # ✅ Rescued
        else:
            return COMPLETE  # ✅ Nothing to do

    elif status == "waiting":
        # Agents working, wait and retry
        wait(probe_interval)
        continue

    elif status == "working":
        # Still implementing, wait and retry
        wait(probe_interval)
        continue

    elif status == "error":
        return ERROR  # ❌ Probe failed

# Max probes reached
changes = check_uncommitted_changes()
if changes:
    commit_rescue()  # Final attempt

return TIMEOUT  # ⏱️ Gave up
```

**Robustness**:
- ✅ Multiple retry attempts (default: 5)
- ✅ Configurable intervals (default: 30s)
- ✅ Final rescue attempt even on timeout
- ✅ Clear status codes for caller
- ✅ No silent failures

## Integration Points

### With Circuit Breaker

**Old behavior**:
```python
if no_commits_detected:
    no_commit_streak += 1
    if no_commit_streak >= 3:
        ABORT  # ❌ Might abort active work
```

**New behavior**:
```python
result = smart_completion_check(...)

if result["complete"]:
    no_commit_streak = 0  # Reset
elif result["status"] == "timeout":
    no_commit_streak += 1  # Only increment on genuine timeout
    if no_commit_streak >= 3:
        ABORT  # ✅ Only abort after multiple timeouts
```

**Why better**:
- Distinguishes "waiting for agents" from "stalled"
- Rescues work before aborting
- More sophisticated than simple commit counting

### With Iteration Loop

**Usage**:
```python
# Before iteration
baseline = get_current_commit()

# Run Claude session
run_claude_session(...)

# After session ends
result = smart_completion_check(
    project_path=project_path,
    spec_name=spec_name,
    baseline_commit=baseline,
    max_probes=5,
    probe_interval=30,
)

if result["complete"]:
    print(f"✅ Iteration complete: {result['new_commits']} commits")
    if result["rescued"]:
        print("⚠️  Had to rescue uncommitted work")
else:
    print(f"❌ Iteration failed: {result['status']}")
```

## Failure Modes and Mitigations

### 1. JSON Parsing Failure

**Scenario**: LLM doesn't return valid JSON

**Mitigation**:
- Regex extraction for markdown-wrapped JSON
- Try multiple JSON patterns
- Return error status on parse failure
- Timeout prevents infinite waiting

**Impact**: ⚠️ Medium - Falls back to error, won't break system

---

### 2. commit-rescue.py Missing

**Scenario**: Script doesn't exist in project

**Mitigation**:
- Check file existence before calling
- Return False if missing (graceful degradation)
- Log warning but continue

**Impact**: ✅ Low - System continues, just won't rescue

---

### 3. Git Commands Fail

**Scenario**: Git repo corrupted or commands timeout

**Mitigation**:
- All git commands have timeouts (10s)
- Return safe defaults (0 commits, no changes)
- Catch subprocess exceptions

**Impact**: ⚠️ Medium - System continues with degraded info

---

### 4. LLM Says "complete" But Actually Stalled

**Scenario**: LLM incorrectly reports completion

**Mitigation**:
- **Primary check**: Git commits (can't be fooled)
- If no commits: Check for uncommitted changes
- If no changes: Return "nothing to do" (still considered complete)
- Circuit breaker still increments if repeated

**Impact**: ✅ Low - Git commits are source of truth

---

### 5. Agents Hang Forever

**Scenario**: Agents launched but never complete

**Mitigation**:
- Max probes limit (default: 5 × 30s = 2.5 min)
- After timeout: Final rescue attempt
- Then return timeout status
- Circuit breaker will eventually trigger

**Impact**: ⚠️ Medium - Wastes 2.5 min but eventually recovers

---

### 6. Probe Timeout

**Scenario**: `claude --continue` hangs

**Mitigation**:
- 60s timeout on subprocess
- Return error status
- System continues to next probe

**Impact**: ✅ Low - Just one failed probe, retries continue

## Configuration

**Tunable Parameters**:

```json
{
  "completion_check": {
    "max_probes": 5,
    "probe_interval_seconds": 30,
    "probe_timeout_seconds": 60,
    "final_rescue_attempt": true
  }
}
```

**Defaults**:
- `max_probes`: 5 (total wait: 2.5 min with 30s interval)
- `probe_interval`: 30s (balance between responsiveness and spam)
- `probe_timeout`: 60s (enough for LLM to respond)
- `final_rescue_attempt`: true (always try to rescue)

## Success Metrics

**Primary metric**: False abort rate
- Target: <5% (down from 30-50% without detection)
- Measure: # aborts while agents active / total aborts

**Secondary metrics**:
- Rescue success rate: % of rescues that create commits
- Average probes per iteration: Should be 1-2 for normal cases
- Timeout rate: % of iterations that hit max probes

## Testing Strategy

### Unit Tests

1. **Test git commit counting**
   - Multiple commits
   - No commits
   - Invalid baseline

2. **Test uncommitted changes detection**
   - Staged changes
   - Unstaged changes
   - No changes

3. **Test JSON parsing**
   - Valid JSON
   - Markdown-wrapped JSON
   - Invalid JSON (should handle gracefully)

### Integration Tests

1. **Test complete workflow**
   - Work with commits → Completes immediately
   - Work without commits → Rescues
   - Agents working → Waits then completes
   - Genuine stall → Times out

2. **Test edge cases**
   - commit-rescue.py missing
   - Git commands fail
   - LLM returns bad JSON
   - Multiple probe rounds

### Manual Testing

1. **Real agent scenario**
   ```bash
   # Launch agents manually
   # Run smart-completion-check
   # Verify it detects waiting status
   ```

2. **Uncommitted work scenario**
   ```bash
   # Make changes but don't commit
   # Run smart-completion-check
   # Verify rescue creates commits
   ```

## Migration Path

### Phase 1: Standalone Testing (Current)
- Use `smart-completion-check.py` standalone
- Test with real specs
- Verify all scenarios work

### Phase 2: Integration
- Add to runner_manager.py
- Replace simple commit checking
- Keep old behavior as fallback

### Phase 3: Refinement
- Tune parameters based on metrics
- Add more sophisticated error handling
- Optimize probe intervals

## Summary

**Key Insights**:

1. **Git commits are the source of truth** - Everything else is supporting evidence

2. **Ask, don't guess** - Use `--continue` to probe status instead of fragile heuristics

3. **Rescue before abort** - Always try to salvage work before giving up

4. **Timeouts prevent hangs** - Every subprocess has a timeout

5. **Graceful degradation** - System continues even if components fail

**Robustness guarantees**:
- ✅ No infinite loops (max probes limit)
- ✅ No silent failures (all errors logged)
- ✅ No lost work (rescue before abort)
- ✅ No false aborts (distinguishes waiting from stalled)

**Why this design works**:
- Simple components with clear responsibilities
- Primary signal (commits) is unambiguous
- Fallback mechanism (probing) only when needed
- Final safety net (rescue) prevents waste
- Multiple layers of defense against false triggers
