# Claude-Flow Configuration for spec-workflow-runner

This directory contains claude-flow configuration for agent-based development.

## Files

- **agents.json**: Agent profiles with roles, specializations, and model preferences
- **domains.json**: Domain mappings to codebase modules
- **workflows.json**: Predefined workflows for common tasks
- **metrics/**: Agent performance tracking (auto-generated)
- **patterns/**: Reusable code patterns (auto-generated)

## Usage

Claude automatically uses these configurations when the MCP server is active.

### Invoke a Workflow

```
Claude, start the "implement-spec-task" workflow for the next
pending task in .spec-workflow/specs/task-auto-fix/tasks.md
```

### Spawn Specific Agents

```
Claude, spawn the architect agent to review the provider
abstraction pattern in src/spec_workflow_runner/providers.py
```

### Check Swarm Status

```
Claude, show swarm status and agent progress
```

## Customization

Edit JSON files to:
- Add new agent profiles
- Define custom workflows
- Map new domains to modules
- Adjust agent model preferences (haiku/sonnet/opus)
