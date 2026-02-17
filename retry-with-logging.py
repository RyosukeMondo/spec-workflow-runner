#!/usr/bin/env python3
"""
Retry Claude spec work with enhanced logging and crash recovery.

Usage:
    python retry-with-logging.py [spec-name]
"""

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def safe_print(text: str):
    """Print text, handling Unicode encoding errors."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))


def run_with_logging(spec_name: str = "text-selection-annotations"):
    """Run Claude with enhanced logging and crash detection."""

    # Create log directory
    log_dir = Path("logs/claude-runs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Generate log file names
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{spec_name}_{timestamp}.log"
    error_file = log_dir / f"{spec_name}_{timestamp}_error.log"

    safe_print(f"Starting Claude work on spec: {spec_name}")
    safe_print(f"Logs: {log_file}")
    safe_print(f"Errors: {error_file}")
    safe_print("-" * 80)

    # Build command with safer options
    cmd = [
        "claude",
        "--print",
        "--model",
        "sonnet",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--verbose",
        f"""Continue work on spec '{spec_name}':

## Current Progress
Check and update task status in .spec-workflow/specs/{spec_name}/tasks.md

## Your Approach - Work Incrementally

1. **Read tasks.md**: Review current status
2. **Pick 2-3 related tasks**: Work on small batches
3. **Make changes**: Use Edit/Write tools directly
4. **Test**: Run any relevant tests
5. **Commit**: Create atomic commits as you go
6. **Update tasks.md**: Mark tasks completed

## Safety Guidelines

- Work incrementally (2-3 tasks at a time)
- Commit frequently (after each logical change)
- Test before committing
- Update tasks.md status after completion

## Requirements

1. Read the tasks.md file first
2. Make small, focused changes
3. Commit with format: 'fix(component): description'
4. Update task status: Pending → Completed
5. Report progress clearly

Work carefully and methodically!""",
    ]

    # Run with subprocess
    start_time = time.time()
    safe_print("Launching Claude...\n")

    try:
        with (
            open(log_file, "w", encoding="utf-8") as log_f,
            open(error_file, "w", encoding="utf-8") as err_f,
        ):
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            # Monitor output
            last_activity = time.time()
            activity_timeout = 300  # 5 minutes

            while True:
                # Check if process is still running
                if process.poll() is not None:
                    break

                # Read stdout
                line = process.stdout.readline()
                if line:
                    safe_print(line.rstrip())
                    log_f.write(line)
                    log_f.flush()
                    last_activity = time.time()

                # Check for timeout
                if time.time() - last_activity > activity_timeout:
                    safe_print(f"\n⚠️  WARNING: No activity for {activity_timeout}s")
                    safe_print("Process may be hung. Waiting another 60s...")
                    activity_timeout = 60

                time.sleep(0.1)

            # Get return code
            return_code = process.returncode

            # Capture any remaining output
            remaining_out, remaining_err = process.communicate()
            if remaining_out:
                safe_print(remaining_out)
                log_f.write(remaining_out)
            if remaining_err:
                safe_print(f"\nSTDERR:\n{remaining_err}")
                err_f.write(remaining_err)

            # Report results
            elapsed = time.time() - start_time
            safe_print("\n" + "=" * 80)
            safe_print(f"Process exited with code: {return_code}")
            safe_print(f"Elapsed time: {elapsed:.1f}s ({elapsed / 60:.1f} minutes)")

            if return_code == 0:
                safe_print("✅ SUCCESS")
            else:
                safe_print(f"❌ FAILED with exit code {return_code}")
                safe_print(f"Check error log: {error_file}")

            return return_code

    except KeyboardInterrupt:
        safe_print("\n⚠️  Interrupted by user")
        if process:
            process.terminate()
            safe_print("Process terminated")
        return 130

    except Exception as e:
        safe_print(f"\n❌ EXCEPTION: {e}")
        import traceback

        traceback.print_exc()
        if process:
            process.terminate()
        return 1


if __name__ == "__main__":
    spec_name = sys.argv[1] if len(sys.argv) > 1 else "text-selection-annotations"
    exit_code = run_with_logging(spec_name)
    sys.exit(exit_code)
