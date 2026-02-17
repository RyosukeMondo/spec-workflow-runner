#!/usr/bin/env python3
"""Test the exact command that's failing."""

import subprocess
import threading
from pathlib import Path

# EXACT command from last_command.txt
command_str = (
    r'claude --print --model sonnet --dangerously-skip-permissions --output-format stream-json --verbose --mcp-config C:\Users\ryosu\repos\keyrx\.claude\mcp-only.json "[!] IMPORTANT: NO launch swarms on this session - Do not invoke agents or use multiple threading to prevent hang-ups from thread management failures.'
    + "\n\n"
    + r"You have the spec-workflow MCP server available. Use the manage-tasks tool IMMEDIATELY to list all tasks for spec "
    "'"
    "bug-remediation-sweep"
    "'"
    ", find the first pending task, and work on it. You may work on multiple tasks at once if they are similar, related, or beneficial to complete together."
    + "\n\n"
    + r"Before starting work, mark the task as in-progress. When you complete the work, you MUST run "
    "'"
    "git add"
    "'"
    " followed by "
    "'"
    "git commit"
    "'"
    ' with a clear message, then mark the task as completed using manage-tasks. DO NOT just stage files - you must actually commit them. DO NOT ask permission - just start working immediately. Make atomic commits for each semantic group of changes."'
)

print(f"Command: {command_str[:200]}...\n")

proc = subprocess.Popen(
    command_str,
    cwd=Path(r"C:\Users\ryosu\repos\keyrx"),
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    bufsize=0,
    shell=True,
)

print(f"Process PID: {proc.pid}")
print(f"Poll status: {proc.poll()}")
print("Waiting for output...")


def read_output():
    print("[Thread] Starting to read...")
    line_count = 0
    while True:
        print(f"[Thread] Calling readline() for line {line_count + 1}...")
        line = proc.stdout.readline()
        if not line:
            print("[Thread] Got empty line, breaking")
            break
        decoded = line.decode("utf-8", errors="replace").strip()
        print(f"[Thread] Line {line_count + 1}: {decoded[:100]}")
        line_count += 1
        if line_count >= 3:
            break
    print(f"[Thread] Finished. Got {line_count} lines")


thread = threading.Thread(target=read_output, daemon=True)
thread.start()

thread.join(timeout=15)

if thread.is_alive():
    print("\n[ERROR] Thread blocked after 15 seconds!")
    print("This reproduces the bug!")
else:
    print("\n[SUCCESS] Thread completed!")

try:
    proc.terminate()
    proc.wait(timeout=5)
except:
    proc.kill()
