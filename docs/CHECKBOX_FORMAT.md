# Checkbox Format Specification

## Overview

The spec-workflow-runner uses **checkbox format** for all tasks.md files. This enables:
- Accurate programmatic progress counting
- TUI task tracking and visualization
- Simple text-based task status updates
- Fast pre-session validation

## Required Format

All tasks MUST use this format:

```markdown
## Tasks

- [ ] 1. Task title (pending)
- [-] 2. Task in progress (in progress)
- [x] 3. Completed task (completed)
- [ ] 4.1 Subtask (pending)
```

## Status Indicators

| Checkbox | Status | Meaning |
|----------|--------|---------|
| `[ ]` | Pending | Task not started |
| `[-]` | In Progress | Task currently being worked on |
| `[x]` | Completed | Task finished |

## Validation

### Automated Validation

Use `progress_count.py` to validate format:

```bash
# Validate format
python src/spec_workflow_runner/progress_count.py --validate path/to/tasks.md

# Count progress
python src/spec_workflow_runner/progress_count.py path/to/tasks.md
```

### Pre-Session Validation

The runner automatically validates tasks.md format before each session using the script above.

## Invalid Formats

### ❌ Heading-Based Format

**DO NOT USE:**

```markdown
#### Task VF-1.1: Create Test Directory Structure
- **ID**: VF-1.1
- **Status**: Pending
- **Priority**: P0
```

This format is **NOT supported** and will fail validation.

### Why Checkbox Format?

1. **Simple**: Easy to read and edit manually
2. **Standard**: Uses standard markdown checkbox syntax
3. **Parseable**: Regex-based counting is fast and reliable
4. **Tool-friendly**: Works with TUI, scripts, and text editors
5. **No dependencies**: No need for MCP tools for basic operations

## Tools

### progress_count.py

Dedicated script for checkbox counting and validation:

```python
from spec_workflow_runner.progress_count import count_tasks, validate_format
from pathlib import Path

# Count tasks
progress = count_tasks(Path("tasks.md"))
print(f"{progress.completed}/{progress.total} completed")

# Validate format
errors = validate_format(Path("tasks.md"))
if errors:
    for error in errors:
        print(f"Error: {error}")
```

### CLI Usage

```bash
# JSON output with counts
python src/spec_workflow_runner/progress_count.py tasks.md
# {
#   "pending": 5,
#   "in_progress": 2,
#   "completed": 3,
#   "total": 10,
#   "percentage": 30.0
# }

# Validation only
python src/spec_workflow_runner/progress_count.py --validate tasks.md
# ✅ Format valid: tasks.md uses checkbox format
```

## Migration Guide

If you have existing heading-based tasks.md files:

1. Extract task titles from headings
2. Convert to checkbox format with sequential numbering
3. Remove metadata fields (Status, Priority, etc.)
4. Keep only essential information in task descriptions
5. Validate with `progress_count.py --validate`

### Example Migration

**Before (heading format):**
```markdown
#### Task VF-1.1: Create Test Directory Structure
- **ID**: VF-1.1
- **Status**: Completed
- **Priority**: P0
- **Description**: Set up test directory structure
```

**After (checkbox format):**
```markdown
- [x] 1.1 Create test directory structure
  - Set up test directory structure
```

## Template

See `.spec-workflow/templates/tasks-template.md` for the official format template with examples.

## Troubleshooting

### "No checkbox tasks found"

- Ensure tasks are in `## Tasks` section
- Check checkbox syntax: `- [ ]` with space inside brackets
- Verify tasks have format: `- [ ] N. Title`

### "Invalid format detected: Heading-based tasks"

- Remove `#### Task XX-N:` headings
- Convert to checkbox format `- [ ] N. Task title`
- Run validation after conversion

### TUI not showing tasks

- Verify checkbox format with `progress_count.py --validate`
- Check that tasks.md exists in spec directory
- Ensure `## Tasks` section header exists
