#!/usr/bin/env python3
"""Probe Claude session status using --continue with JSON output.

Much simpler than external detection: just ask Claude directly!
"""

import json
import subprocess
import sys
from pathlib import Path


def safe_print(text: str):
    """Print text handling Unicode errors."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', errors='replace').decode('ascii'))


def probe_session_status(project_path: Path) -> dict:
    """Probe Claude session status with --continue.

    Returns:
        Dict with:
        {
            "status": "complete" | "waiting" | "working",
            "message": str,
            "agents_active": bool,
            "tasks_completed": list[str],
            "tasks_pending": list[str],
            "commits_made": int,
            "should_continue": bool
        }
    """
    probe_prompt = """STATUS PROBE - Respond in JSON only:

Analyze current state and respond with JSON:

```json
{
  "status": "complete|waiting|working",
  "message": "Brief status description",
  "agents_active": true/false,
  "agents_details": "What agents are doing (if any)",
  "tasks_completed": ["Task X.Y completed"],
  "tasks_pending": ["Task X.Y still pending"],
  "commits_made": 0,
  "should_continue": true/false,
  "next_action": "What should happen next"
}
```

Status values:
- "complete": All work done, tasks committed, ready for next iteration
- "waiting": Agents/workers running in background, need to wait
- "working": Currently implementing tasks, need more time

RESPOND WITH ONLY THE JSON OBJECT. No other text."""

    try:
        result = subprocess.run(
            [
                "claude",
                "--print",
                "--model", "sonnet",
                "--dangerously-skip-permissions",
                "--continue",  # KEY: Resume session
                probe_prompt,
            ],
            cwd=project_path,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=60,  # Quick probe
        )

        # Parse JSON from output
        output = result.stdout

        # Extract JSON (might be wrapped in markdown)
        import re
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', output, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON
            json_match = re.search(r'(\{[^{}]*"status"[^{}]*\})', output, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Fallback: parse whole output
                json_str = output

        status = json.loads(json_str)
        return status

    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "message": "Probe timeout",
            "should_continue": False,
        }
    except json.JSONDecodeError as e:
        safe_print(f"Error parsing JSON: {e}")
        safe_print(f"Output was: {output[:500]}")
        return {
            "status": "error",
            "message": f"Could not parse JSON response: {e}",
            "should_continue": False,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Probe failed: {e}",
            "should_continue": False,
        }


def continuation_loop_with_probing(
    project_path: Path,
    spec_name: str,
    max_probes: int = 10,
    probe_interval_seconds: int = 30,
) -> dict:
    """Run continuation loop with status probing.

    Args:
        project_path: Path to project
        spec_name: Name of spec
        max_probes: Maximum probes before giving up
        probe_interval_seconds: Seconds between probes

    Returns:
        Final status dict
    """
    import time

    safe_print("\n" + "=" * 80)
    safe_print("SMART CONTINUATION LOOP WITH PROBING")
    safe_print("=" * 80)
    safe_print(f"Spec: {spec_name}")
    safe_print(f"Max probes: {max_probes}")
    safe_print(f"Interval: {probe_interval_seconds}s")
    safe_print("=" * 80 + "\n")

    for probe_num in range(1, max_probes + 1):
        safe_print(f"\n{'=' * 80}")
        safe_print(f"PROBE {probe_num}/{max_probes}")
        safe_print(f"{'=' * 80}\n")

        # Probe status
        status = probe_session_status(project_path)

        # Display status
        safe_print(json.dumps(status, indent=2))

        # Check completion
        if status.get("status") == "complete":
            safe_print("\n✅ COMPLETE - Work done!")
            return status

        if status.get("status") == "error":
            safe_print("\n❌ ERROR - Probe failed")
            return status

        if status.get("status") == "waiting":
            safe_print(f"\n⏳ WAITING - {status.get('message', 'Agents working')}")
            safe_print(f"   Agents: {status.get('agents_details', 'Unknown')}")

        if status.get("status") == "working":
            safe_print(f"\n🔨 WORKING - {status.get('message', 'Tasks in progress')}")

        # Check if should continue
        if not status.get("should_continue", True):
            safe_print("\n🛑 Stopped - LLM says no need to continue")
            return status

        # Wait before next probe
        if probe_num < max_probes:
            safe_print(f"\nWaiting {probe_interval_seconds}s before next probe...")
            time.sleep(probe_interval_seconds)

    safe_print(f"\n⚠️  Max probes ({max_probes}) reached")
    return {
        "status": "timeout",
        "message": f"Reached max probes ({max_probes})",
        "should_continue": False,
    }


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Probe session status")
    parser.add_argument(
        "spec_name",
        nargs="?",
        default="security-fixes",
        help="Name of spec",
    )
    parser.add_argument(
        "--project-path",
        type=Path,
        default=Path.cwd(),
        help="Path to project",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Probe once and exit (no loop)",
    )
    parser.add_argument(
        "--max-probes",
        type=int,
        default=10,
        help="Maximum probes in loop mode",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Seconds between probes",
    )

    args = parser.parse_args()

    if args.once:
        # Single probe
        safe_print("Probing session status...")
        status = probe_session_status(args.project_path)
        print(json.dumps(status, indent=2))
        sys.exit(0 if status.get("status") == "complete" else 1)
    else:
        # Loop until complete
        final_status = continuation_loop_with_probing(
            project_path=args.project_path,
            spec_name=args.spec_name,
            max_probes=args.max_probes,
            probe_interval_seconds=args.interval,
        )

        safe_print("\n" + "=" * 80)
        safe_print("FINAL STATUS")
        safe_print("=" * 80)
        print(json.dumps(final_status, indent=2))

        sys.exit(0 if final_status.get("status") == "complete" else 1)


if __name__ == "__main__":
    main()
