# AI Agent Invocation Guide

This document describes how to invoke coding AI agents (Claude CLI and Codex) from other AI agents or automation tools.

## Overview

The spec-workflow-runner supports two providers:
- **Claude CLI** - Anthropic's Claude code assistant
- **Codex** - OpenAI's Codex code assistant

## Command Structure

### Claude CLI Provider

**Basic Command:**
```bash
claude -p "YOUR_PROMPT_HERE" [OPTIONS]
```

**Options:**
- `-p PROMPT` - The prompt/instruction for the agent (required)
- `--model MODEL` - Specify which Claude model to use
- `--dangerously-skip-permissions` - Skip permission prompts for automation

**Supported Models:**
- `sonnet` (default)
- `haiku`
- `opus`

**Example:**
```bash
claude -p "Fix the bug in src/utils.py" --model sonnet --dangerously-skip-permissions
```

**MCP Server List:**
```bash
claude mcp list
```

### Codex Provider

**Basic Command:**
```bash
codex e --dangerously-bypass-approvals-and-sandbox [OPTIONS] "YOUR_PROMPT_HERE"
```

**Options:**
- `e` - Execute mode
- `--dangerously-bypass-approvals-and-sandbox` - Skip approvals for automation
- `--model MODEL` - Specify which Codex model to use
- `-c KEY=VALUE` - Configuration overrides (can be repeated)

**Supported Models:**
- `gpt-5.1-codex-max`
- `gpt-5.1-codex` (recommended)
- `gpt-5.1-codex-mini`
- `gpt-5-codex`

**Example:**
```bash
codex e --dangerously-bypass-approvals-and-sandbox \
  --model gpt-5.1-codex \
  -c max_tokens=4000 \
  -c temperature=0.7 \
  "Refactor the authentication module"
```

**MCP Server List:**
```bash
codex mcp list
```

## Programmatic Usage (Python)

### Using the Provider Abstraction

```python
from pathlib import Path
from spec_workflow_runner.providers import create_provider

# Create a Claude provider
provider = create_provider(
    provider_name="claude",
    base_command=["claude"],
    model="sonnet"
)

# Build command
cmd = provider.build_command(
    prompt="Implement user authentication",
    project_path=Path("/path/to/project"),
    config_overrides=[]
)

# Execute
import subprocess
subprocess.run(cmd.to_list(), cwd=project_path)
```

```python
# Create a Codex provider
provider = create_provider(
    provider_name="codex",
    base_command=["codex", "e", "--dangerously-bypass-approvals-and-sandbox"],
    model="gpt-5.1-codex"
)

# Build command with config overrides
cmd = provider.build_command(
    prompt="Add error handling to API endpoints",
    project_path=Path("/path/to/project"),
    config_overrides=[
        ("max_tokens", "4000"),
        ("temperature", "0.7")
    ]
)

# Execute
import subprocess
subprocess.run(cmd.to_list(), cwd=project_path)
```

## Key Considerations for Agent Invocation

### 1. Automation Mode
Both providers have flags to skip interactive prompts:
- Claude: `--dangerously-skip-permissions`
- Codex: `--dangerously-bypass-approvals-and-sandbox`

**Important:** Only use these flags in trusted, controlled environments.

### 2. Working Directory
Always execute commands from the project root directory to ensure proper context.

### 3. Model Selection
Choose models based on task complexity:
- **Fast/Simple tasks:** `haiku` (Claude) or `gpt-5.1-codex-mini` (Codex)
- **Standard tasks:** `sonnet` (Claude) or `gpt-5.1-codex` (Codex)
- **Complex tasks:** `opus` (Claude) or `gpt-5.1-codex-max` (Codex)

### 4. Prompt Engineering
Structure prompts clearly:
```
[ACTION] [TARGET] [CONTEXT]

Examples:
- "Fix type errors in src/models/user.py"
- "Refactor authentication module to use dependency injection"
- "Add tests for the payment processing service"
```

### 5. Error Handling
Wrap invocations in try-except blocks and check return codes:
```python
result = subprocess.run(
    cmd.to_list(),
    cwd=project_path,
    capture_output=True,
    text=True
)

if result.returncode != 0:
    print(f"Agent failed: {result.stderr}")
```

## Provider Factory Function

```python
def create_provider(
    provider_name: str,
    base_command: Sequence[str],
    model: str | None = None,
) -> Provider:
    """Create a provider instance.

    Args:
        provider_name: "claude" or "codex"
        base_command: Base command parts (e.g., ["claude"] or ["codex", "e"])
        model: Optional model name

    Returns:
        Provider instance

    Raises:
        ValueError: If provider_name is unknown
    """
```

## Getting Available Models

```python
from spec_workflow_runner.providers import get_supported_models

# Get Claude models
claude_models = get_supported_models("claude")
# Returns: ("sonnet", "haiku", "opus")

# Get Codex models
codex_models = get_supported_models("codex")
# Returns: ("gpt-5.1-codex-max", "gpt-5.1-codex", "gpt-5.1-codex-mini", "gpt-5-codex")
```

## Best Practices

1. **Single Responsibility:** One prompt per coding task
2. **Clear Instructions:** Be specific about what needs to be changed
3. **Context Awareness:** Ensure the agent has access to relevant files
4. **Idempotency:** Design prompts to be safely re-runnable
5. **Validation:** Check outputs before proceeding to next steps
6. **Logging:** Capture all commands and outputs for debugging

## Example Workflow

```python
from pathlib import Path
from spec_workflow_runner.providers import create_provider
import subprocess

def invoke_agent(task: str, provider_name: str = "claude", model: str = "sonnet"):
    """Invoke a coding agent with a task."""

    # Create provider
    provider = create_provider(
        provider_name=provider_name,
        base_command=["claude"] if provider_name == "claude" else ["codex", "e"],
        model=model
    )

    # Build command
    cmd = provider.build_command(
        prompt=task,
        project_path=Path.cwd(),
        config_overrides=[]
    )

    # Execute with error handling
    try:
        result = subprocess.run(
            cmd.to_list(),
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode == 0:
            print(f"Task completed: {task}")
            return True
        else:
            print(f"Task failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print(f"Task timed out: {task}")
        return False
    except Exception as e:
        print(f"Error executing task: {e}")
        return False

# Usage
invoke_agent("Add type hints to all functions in src/utils.py")
invoke_agent("Write unit tests for UserService", provider_name="codex", model="gpt-5.1-codex")
```

## Security Considerations

1. **Prompt Injection:** Validate and sanitize prompts from untrusted sources
2. **Code Execution:** Agents execute arbitrary code - only use in sandboxed environments
3. **Secrets:** Never include API keys or credentials in prompts
4. **Approval Bypass:** Only use automation flags in CI/CD or controlled environments
5. **Rate Limiting:** Implement backoff strategies to avoid API throttling

## Troubleshooting

### Command Not Found
Ensure the CLI tool is installed and in PATH:
```bash
which claude  # or which codex
```

### Permission Denied
Check file permissions and ensure the agent has write access to the project.

### Model Not Available
Verify model name against supported models list:
```python
from spec_workflow_runner.providers import get_supported_models
print(get_supported_models("claude"))
```

### Timeout Issues
Increase timeout for complex tasks or split into smaller subtasks.
