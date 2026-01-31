#!/usr/bin/env python3
"""Fix claude-flow worker timeout configuration in both projects."""

import json
from pathlib import Path
from typing import Any


def fix_timeout_config(project_path: Path, new_timeout_ms: int = 1800000) -> bool:
    """Update workerTimeoutMs in daemon-state.json."""
    daemon_state = project_path / ".claude-flow" / "daemon-state.json"

    if not daemon_state.exists():
        print(f"[!] {project_path.name}: No daemon-state.json found")
        return False

    try:
        # Read current config
        with open(daemon_state, encoding="utf-8") as f:
            data = json.load(f)

        old_timeout = data.get("config", {}).get("workerTimeoutMs", 0)

        if old_timeout == new_timeout_ms:
            print(f"[=] {project_path.name}: Already configured with {new_timeout_ms}ms timeout")
            return True

        # Update timeout
        if "config" not in data:
            data["config"] = {}

        data["config"]["workerTimeoutMs"] = new_timeout_ms

        # Backup original
        backup_path = daemon_state.with_suffix(".json.backup")
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # Write updated config
        with open(daemon_state, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(f"[+] {project_path.name}: Updated timeout from {old_timeout}ms to {new_timeout_ms}ms")
        print(f"    Backup saved to: {backup_path}")
        return True

    except (json.JSONDecodeError, OSError) as e:
        print(f"[!] {project_path.name}: Error updating config - {e}")
        return False


def main():
    """Fix timeout configuration in both projects."""
    projects = [
        Path(r"C:\Users\ryosu\repos\kids-guard2"),
        Path(r"C:\Users\ryosu\repos\keyrx"),
    ]

    new_timeout_ms = 1800000  # 30 minutes

    print("\n" + "=" * 100)
    print("CLAUDE-FLOW WORKER TIMEOUT FIX")
    print("=" * 100)
    print(f"\nChanging workerTimeoutMs from 300000ms (5 min) to {new_timeout_ms}ms (30 min)")
    print("\nThis will allow optimize and testgaps workers sufficient time to analyze large codebases.")
    print("\n" + "=" * 100)
    print()

    success_count = 0
    for project_path in projects:
        if not project_path.exists():
            print(f"[!] Project not found: {project_path}")
            continue

        if fix_timeout_config(project_path, new_timeout_ms):
            success_count += 1
        print()

    print("=" * 100)
    print("NEXT STEPS")
    print("=" * 100)
    print()

    if success_count > 0:
        print("1. Restart claude-flow daemons:")
        print()
        for project_path in projects:
            if project_path.exists():
                print(f"   cd {project_path}")
                print(f"   npx @claude-flow/cli@latest daemon stop")
                print(f"   npx @claude-flow/cli@latest daemon start")
                print()

        print("2. Monitor worker success rates:")
        print(f"   python {Path(__file__).parent / 'diagnose-workers.py'}")
        print()

        print("3. Check next optimize/testgaps run (within 15-20 minutes)")
        print("   - Should complete successfully")
        print("   - Duration should be 5-15 minutes")
        print("   - Success rate should improve to >90%")
        print()

        print("4. If still failing:")
        print("   - Check logs in .claude-flow/logs/headless/")
        print("   - Consider increasing timeout to 3600000ms (60 minutes)")
        print("   - May need to optimize worker implementation")
        print()
    else:
        print("[!] No configurations were updated successfully.")
        print("    Please check error messages above.")
        print()

    print("=" * 100)


if __name__ == "__main__":
    main()
