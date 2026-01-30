# Claude-Flow Integration Plan

## Goal
Leverage claude-flow's swarm capabilities with spec-workflow-runner's progress tracking for autonomous task completion.

## Current State

### spec-workflow-runner Strengths:
- ✅ Spec/task discovery and selection
- ✅ Progress tracking with visual indicators
- ✅ Circuit breaker for stuck sessions
- ✅ Multi-spec orchestration (--spec all)
- ✅ Activity timeout monitoring

### claude-flow Strengths:
- ✅ Swarm orchestration and coordination
- ✅ Model routing (haiku for simple, sonnet for complex)
- ✅ Background workers (map, audit, optimize, consolidate)
- ✅ Parallel task execution
- ✅ Metrics and analytics

## Integration Strategy

### 1. Monitor claude-flow Workers

Add monitoring for claude-flow daemon state:

```python
def monitor_claude_flow_workers(project_path: Path) -> dict:
    """Monitor claude-flow worker status."""
    daemon_state = project_path / ".claude-flow" / "daemon-state.json"
    if daemon_state.exists():
        with open(daemon_state) as f:
            return json.load(f)["workers"]
    return {}

def wait_for_claude_flow_completion(project_path: Path, timeout: int = 600):
    """Wait for claude-flow workers to complete."""
    start = time.time()
    while time.time() - start < timeout:
        workers = monitor_claude_flow_workers(project_path)
        running = any(w.get("isRunning") for w in workers.values())
        if not running:
            return True
        time.sleep(5)
    return False
```

### 2. Update Prompt Template

Remove anti-agent constraints, embrace swarm:

```
Continue work on spec '{spec_name}':

## Current Progress
{progress_summary}

## Your Approach

You have FULL AUTONOMY to:
- Use Task tool to spawn specialized agents
- Use claude-flow for parallel execution
- Coordinate swarm workers for efficiency
- Split complex tasks across multiple agents

## Requirements

1. **Read tasks.md** to understand remaining work
2. **Choose optimal strategy**:
   - Simple fixes: Direct implementation
   - Complex work: Spawn agents with clear objectives
   - Testing: Parallel test execution
3. **Make commits** after each logical change
4. **Update tasks.md** to reflect progress

## claude-flow Workers Available

- map: Fast codebase analysis
- audit: Security and quality checks
- optimize: Performance improvements
- consolidate: Deduplication and cleanup

Use these workers intelligently for parallel work!
```

### 3. Enhanced Completion Detection

Don't just check git commits - monitor multiple signals:

```python
class ProgressSignals:
    git_commits: int = 0
    file_modifications: int = 0
    claude_flow_runs: int = 0
    tasks_completed: int = 0
    worker_activity: bool = False

    def has_progress(self) -> bool:
        return any([
            self.git_commits > 0,
            self.file_modifications > 5,
            self.claude_flow_runs > 0,
            self.tasks_completed > 0,
            self.worker_activity
        ])
```

### 4. Add MCP Server Configuration

Enable claude-flow MCP server in spec-workflow runs:

```json
{
  "mcp_servers": {
    "claude-flow": {
      "command": "npx",
      "args": ["@pimzino/claude-flow-mcp@latest"],
      "env": {}
    }
  }
}
```

### 5. Real-time Worker Monitoring

Display claude-flow activity during execution:

```
================================================================================
SPEC: security-fixes (Progress: 3/15 tasks)
================================================================================

Claude Activity:
  [AGENT] Spawned 3 task agents
  [WORKER] audit: Running security scan...
  [WORKER] optimize: Analyzing performance...
  [FILE] 12 files modified
  [COMMIT] fix(security): Add input validation (c67ed84)

claude-flow Workers:
  ✅ map: 325/325 successful
  ⚙️ audit: Running... (avg 54s)
  ⏳ optimize: Queued

Last activity: 2s ago
```

## Implementation Steps

1. ✅ **Phase 1: Monitoring** (30 min)
   - Add claude-flow worker monitoring
   - Display worker status in progress view
   - Track worker runs as progress signals

2. **Phase 2: Integration** (1 hour)
   - Update prompt to encourage agent usage
   - Add MCP server configuration
   - Implement multi-signal completion detection

3. **Phase 3: Optimization** (1 hour)
   - Add worker-specific task routing
   - Implement parallel spec execution
   - Add worker failure recovery

## Benefits

- **10x faster**: Parallel execution across multiple agents
- **Higher quality**: Specialized workers for specific tasks
- **Better resource usage**: Model routing (haiku for simple, sonnet for complex)
- **Continuous operation**: Background workers handle maintenance
- **Better visibility**: Real-time worker status and progress

## Example Workflow

```bash
# User runs spec-workflow-runner
spec-workflow-run --provider claude --model sonnet --project ~/keyrx --spec all

# spec-workflow-runner:
1. Picks next spec: "security-fixes"
2. Displays progress: 0/15 tasks
3. Spawns Claude with enhanced prompt

# Claude + claude-flow:
1. Reads tasks.md and requirements.md
2. Spawns 3 Task agents for parallel work:
   - Agent 1: Input validation (tasks 1-5)
   - Agent 2: Path validation (tasks 6-10)
   - Agent 3: Tests (tasks 11-15)
3. Uses claude-flow workers:
   - audit: Security scan
   - map: Track dependencies

# spec-workflow-runner monitors:
- File modifications: ✅ Detected
- Git commits: ✅ 3 new commits
- claude-flow runs: ✅ audit completed
- Tasks updated: ✅ 5/15 → 15/15

# Result: All tasks completed in parallel!
```

## Next Steps

1. Implement worker monitoring functions
2. Update prompt template
3. Add multi-signal progress detection
4. Test with a single spec
5. Roll out to --spec all mode

This transforms spec-workflow-runner from a sequential executor into a **parallel orchestration platform**!
