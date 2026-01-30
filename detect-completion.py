#!/usr/bin/env python3
"""Detect if work is actually complete or still in progress.

When Claude launches agents, the main session ends ambiguously.
This script uses multiple signals to robustly detect completion.
"""

import re
from pathlib import Path
from typing import Optional


def safe_print(text: str):
    """Print text handling Unicode errors."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', errors='replace').decode('ascii'))


def parse_last_message(log_file: Path) -> str:
    """Extract Claude's last message from log file.

    Returns:
        Last message text, or empty string if not found
    """
    try:
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        # Look for last message before session end
        # Pattern: "[Result: ...]" at the end
        match = re.search(r'\[Result: (.*?)\](?:\s*Saved log:)?', content, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Fallback: last few lines
        lines = content.strip().split('\n')
        return '\n'.join(lines[-10:]) if lines else ""

    except Exception as e:
        safe_print(f"Error reading log: {e}")
        return ""


def is_waiting_for_agents(last_message: str) -> bool:
    """Check if message indicates waiting for agents.

    Args:
        last_message: Claude's last message

    Returns:
        True if waiting for agents, False if complete
    """
    waiting_phrases = [
        "launched",
        "launching",
        "spawned",
        "spawning",
        "agents are working",
        "working in parallel",
        "waiting for",
        "will report back",
        "synthesize their results",
        "concurrent agents",
        "background agents",
        "parallel execution",
    ]

    message_lower = last_message.lower()

    for phrase in waiting_phrases:
        if phrase in message_lower:
            return True

    return False


def is_task_complete(last_message: str) -> bool:
    """Check if message indicates task completion.

    Args:
        last_message: Claude's last message

    Returns:
        True if task is complete, False otherwise
    """
    completion_phrases = [
        "completed task",
        "finished task",
        "task complete",
        "all tasks complete",
        "work complete",
        "successfully completed",
        "committed",
        "all done",
        "tasks.md updated",
        "marked as completed",
    ]

    message_lower = last_message.lower()

    for phrase in completion_phrases:
        if phrase in message_lower:
            return True

    return False


def assess_completion_confidence(
    last_message: str,
    agents_active: bool,
    time_elapsed_minutes: float,
    new_commits_count: int,
) -> dict:
    """Assess confidence that work is complete.

    Args:
        last_message: Claude's last message
        agents_active: Whether agents are currently active
        time_elapsed_minutes: Minutes since session ended
        new_commits_count: Number of new commits since session started

    Returns:
        Dict with:
        {
            "is_complete": bool,
            "confidence": float (0-1),
            "reason": str,
            "should_continue": bool
        }
    """
    # Explicit completion
    if is_task_complete(last_message):
        return {
            "is_complete": True,
            "confidence": 0.95,
            "reason": "Explicit completion message detected",
            "should_continue": False,
        }

    # Explicitly waiting for agents
    if is_waiting_for_agents(last_message):
        if agents_active:
            return {
                "is_complete": False,
                "confidence": 0.90,
                "reason": "Waiting message + agents still active",
                "should_continue": True,
            }
        elif time_elapsed_minutes < 5:
            return {
                "is_complete": False,
                "confidence": 0.70,
                "reason": "Waiting message + agents may still be starting",
                "should_continue": True,
            }
        elif new_commits_count > 0:
            return {
                "is_complete": True,
                "confidence": 0.80,
                "reason": "Waiting message + no active agents + new commits (agents likely finished)",
                "should_continue": False,
            }
        else:
            return {
                "is_complete": False,
                "confidence": 0.60,
                "reason": "Waiting message + no agents + no commits (uncertain, probe needed)",
                "should_continue": True,
            }

    # Ambiguous - use heuristics
    if new_commits_count >= 2:
        return {
            "is_complete": True,
            "confidence": 0.85,
            "reason": f"{new_commits_count} new commits detected",
            "should_continue": False,
        }

    if time_elapsed_minutes > 10 and not agents_active:
        return {
            "is_complete": True,
            "confidence": 0.70,
            "reason": "10+ minutes elapsed, no agents, assuming complete",
            "should_continue": False,
        }

    # Default: uncertain, should probe
    return {
        "is_complete": False,
        "confidence": 0.50,
        "reason": "Uncertain - should probe with --continue",
        "should_continue": True,
    }


def generate_continue_prompt(assessment: dict) -> str:
    """Generate appropriate --continue prompt based on assessment.

    Args:
        assessment: Result from assess_completion_confidence()

    Returns:
        Prompt string for --continue
    """
    if assessment["reason"].startswith("Waiting message"):
        return """STATUS CHECK:

Are the agents you launched still working, or have they completed?

- If agents are STILL WORKING: Report their status and wait
- If agents have COMPLETED: Report their results and mark tasks complete
- If agents FAILED: Report errors and mark tasks accordingly

Provide clear status update."""

    elif "uncertain" in assessment["reason"].lower():
        return """COMPLETION CHECK:

Review the current state:

1. Check if tasks.md has been updated
2. Check if commits were made
3. Check if work is actually complete

If complete:
  - Report what was accomplished
  - Mark tasks as completed
  - Commit tasks.md update

If NOT complete:
  - Report what's still pending
  - Continue working on next task

Provide clear status."""

    else:
        return """CONTINUE:

Keep working on the next pending task from tasks.md.
Make commits as you go."""


def main():
    """Main entry point."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Detect if work is complete")
    parser.add_argument("log_file", type=Path, help="Path to Claude log file")
    parser.add_argument(
        "--agents-active",
        action="store_true",
        help="Whether agents are currently active",
    )
    parser.add_argument(
        "--time-elapsed",
        type=float,
        default=0,
        help="Minutes since session ended",
    )
    parser.add_argument(
        "--new-commits",
        type=int,
        default=0,
        help="Number of new commits since session started",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON format",
    )

    args = parser.parse_args()

    # Parse last message
    last_message = parse_last_message(args.log_file)

    if not last_message:
        safe_print(f"Warning: Could not parse last message from {args.log_file}")

    # Assess completion
    assessment = assess_completion_confidence(
        last_message=last_message,
        agents_active=args.agents_active,
        time_elapsed_minutes=args.time_elapsed,
        new_commits_count=args.new_commits,
    )

    # Generate continue prompt if needed
    if assessment["should_continue"]:
        assessment["continue_prompt"] = generate_continue_prompt(assessment)

    # Output
    if args.json:
        print(json.dumps(assessment, indent=2))
    else:
        safe_print("\n" + "=" * 80)
        safe_print("COMPLETION ASSESSMENT")
        safe_print("=" * 80)
        safe_print(f"Complete: {assessment['is_complete']}")
        safe_print(f"Confidence: {assessment['confidence'] * 100:.0f}%")
        safe_print(f"Reason: {assessment['reason']}")
        safe_print(f"Should continue: {assessment['should_continue']}")

        if assessment["should_continue"]:
            safe_print("\n" + "=" * 80)
            safe_print("RECOMMENDED ACTION: Use --continue")
            safe_print("=" * 80)
            safe_print("\nSuggested prompt:")
            safe_print(assessment.get("continue_prompt", "Keep going"))

        safe_print("\n" + "=" * 80)

    # Exit code: 0 if complete, 1 if should continue
    return 0 if assessment["is_complete"] else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
