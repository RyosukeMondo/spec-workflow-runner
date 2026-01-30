# Agent Detection for Circuit Breaker

## Problem

When Claude launches agents (via Task tool or claude-flow workers), the main session ends without commits. The circuit breaker sees "no commits" and increments the streak, even though agents are actively working in background.

```
Iteration 1:
  Main: "Launching 6 agents..."  [Task tool calls]
  Main: Session ends (no commits)

  Monitor: "No commits" → Streak: 1/3 ❌

  Reality: 6 agents working! ✅
```

**Result**: False circuit breaker triggers, aborting work that's actually in progress.

## Solution: Detect Active Agents

Before incrementing circuit breaker, check if agents are working:

```python
if no_commits_detected:
    # Check for active agents
    activity = check_agent_activity(project_path)

    if activity["has_activity"]:
        print("✅ Agents working - NOT incrementing circuit breaker")
        no_commit_streak = 0  # Reset
    else:
        no_commit_streak += 1  # Increment as normal
```

## Detection Methods

### 1. Check claude-flow Daemon State

```python
# Read .claude-flow/daemon-state.json
{
  "workers": {
    "optimize": {"status": "running", ...},
    "audit": {"status": "running", ...}
  }
}
```

**Pros**: Direct source of truth
**Cons**: Requires claude-flow to be set up

### 2. Check Recent Agent Logs

```python
# Check .claude-flow/logs/headless/*_result.log
# If modified in last 5 minutes → agents active
```

**Pros**: Works even if daemon state is stale
**Cons**: Time-based heuristic (less reliable)

### 3. Check for Task Tool Agent Files

```python
# Check for files indicating spawned agents
# Look for temp files, lock files, etc.
```

**Pros**: Catches all agent types
**Cons**: Implementation-dependent

## Implementation

### Core Detection Function

```python
def check_agent_activity(project_path: Path) -> dict:
    """Check for active agent activity.

    Returns:
        {
            "has_activity": bool,
            "active_workers": list,
            "recent_logs": list,
            "daemon_running": bool
        }
    """
    # 1. Check daemon state
    daemon_running = check_claude_flow_daemon(project_path)

    # 2. Get active workers
    active_workers = get_active_workers(project_path)

    # 3. Check recent logs (last 5 minutes)
    recent_logs = get_recent_agent_logs(project_path, minutes=5)

    # Activity if: workers active OR recent logs exist
    has_activity = bool(active_workers or recent_logs)

    return {
        "has_activity": has_activity,
        "active_workers": active_workers,
        "recent_logs": recent_logs,
        "daemon_running": daemon_running,
    }
```

### Integration with Circuit Breaker

```python
# In your monitoring loop:

if last_commit == baseline_commit:
    # No new commit detected

    # Check for active agents BEFORE incrementing streak
    activity = check_agent_activity(project_path)

    if activity["has_activity"]:
        print("🔍 AGENTS WORKING - Skipping circuit breaker increment")
        print(f"  Active workers: {len(activity['active_workers'])}")
        print(f"  Recent logs: {len(activity['recent_logs'])}")

        # Don't increment streak
        no_commit_streak = 0  # Reset

        # Optional: Wait for agents to complete
        if args.wait_for_agents:
            wait_for_agents_completion(project_path, max_wait=300)

    else:
        # No agents - genuine lack of progress
        no_commit_streak += 1
        print(f"[!]  No commit detected. Streak: {no_commit_streak}/{NO_COMMIT_LIMIT}")
```

### Wait for Agent Completion

```python
def wait_for_agents_completion(
    project_path: Path,
    max_wait_seconds: int = 300,
) -> bool:
    """Wait for active agents to complete."""

    start = time.time()

    while time.time() - start < max_wait_seconds:
        activity = check_agent_activity(project_path)

        if not activity["has_activity"]:
            print("✅ All agents completed")
            return True

        print(f"⏳ Waiting for {len(activity['active_workers'])} agents...")
        time.sleep(10)

    print("⏱️ Timeout waiting for agents")
    return False
```

## Usage

### Check Agent Activity

```bash
# Check if agents are working
python detect-active-agents.py --project-path ~/repos/kids-guard2

# Output:
# ================================================================================
# AGENT ACTIVITY CHECK
# ================================================================================
# Project: /home/user/repos/kids-guard2
# Daemon running: True
# Active workers: 2
# Recent logs: 3
# Has activity: True
#
# Active workers:
#   - optimize: running
#   - audit: running
```

### Wait for Agents to Complete

```bash
# Wait up to 5 minutes for agents to finish
python detect-active-agents.py \
  --project-path ~/repos/kids-guard2 \
  --wait \
  --wait-timeout 300

# Output:
# ================================================================================
# AGENTS DETECTED - Waiting for completion...
# ================================================================================
# ⏳ Waiting... (2 workers active, elapsed: 10s)
# ⏳ Waiting... (2 workers active, elapsed: 20s)
# ⏳ Waiting... (1 worker active, elapsed: 30s)
# ✅ All agents completed (waited 35s)
```

### Integration in Monitoring Script

```python
from detect_active_agents import check_agent_activity, wait_for_agents_completion

# In your monitoring loop
if no_commits_detected:
    activity = check_agent_activity(project_path)

    if activity["has_activity"]:
        # Agents working - wait for them
        print("Agents detected - waiting for completion...")
        wait_for_agents_completion(project_path, max_wait_seconds=300)

        # Check for commits after agents complete
        # ...
    else:
        # No agents - increment circuit breaker
        no_commit_streak += 1
```

## Configuration

Add to `config.json`:

```json
{
  "circuit_breaker": {
    "check_agents": true,
    "agent_wait_timeout": 300,
    "agent_check_interval": 10
  }
}
```

## Behavior Comparison

### Before (No Agent Detection)

```
Iteration 1: Launch 6 agents
             Main session ends, no commits
             Monitor: Streak 1/3 ❌

Iteration 2: Agents still working...
             No commits yet
             Monitor: Streak 2/3 ❌

Iteration 3: Agents finishing up...
             No commits yet
             Monitor: Streak 3/3 → ABORT! ❌❌❌

Result: Work aborted while agents were actively working
```

### After (With Agent Detection)

```
Iteration 1: Launch 6 agents
             Main session ends, no commits
             Monitor: "2 agents active - NOT incrementing" ✅
             Wait for agents...

After 2min: Agents complete, 3 commits created ✅
            Monitor: "Commits detected, streak reset" ✅

Iteration 2: Continue with next tasks
```

## Edge Cases

### Case 1: Agents Hang

```python
# If agents take too long:
if wait_for_agents_completion(project_path, max_wait=300):
    # Completed successfully
    continue
else:
    # Timeout - consider it a genuine stall
    no_commit_streak += 1
```

### Case 2: Agents Crash

```python
# Check agent logs for errors
for log_file in activity["recent_logs"]:
    if "error" in log_file.read_text().lower():
        print("⚠️ Agent errors detected")
        # Still count as activity (rescue will handle commits)
```

### Case 3: False Positives

```python
# Old logs from previous run might still exist
# Solution: Only consider logs from last 5 minutes
recent_logs = get_recent_agent_logs(project_path, minutes=5)
```

## Testing

```bash
# Simulate agent launch
cd ~/repos/kids-guard2

# Start a worker manually
npx @claude-flow/cli@latest worker run optimize

# In another terminal, check detection
python detect-active-agents.py --project-path .

# Should show: "Has activity: True"
```

## Success Metrics

Track agent detection effectiveness:

- **False triggers prevented**: # of times agent detection prevented false circuit breaker
- **Wait time**: Average time waiting for agents to complete
- **Timeout rate**: % of agent waits that timeout

Target: <5% false circuit breaker triggers with agent detection

## Summary

**Problem**: Circuit breaker triggers while agents work in background

**Solution**: Detect active agents before incrementing circuit breaker

**Detection methods**:
1. Check daemon state for running workers
2. Check recent agent logs (last 5 min)
3. Both methods = high confidence

**Benefits**:
- No false circuit breaker triggers during agent work
- Wait for agents to complete naturally
- Works with commit rescue
- Supports parallel agent execution

**Integration**: 3 lines of code in monitoring loop
