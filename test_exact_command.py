#!/usr/bin/env python3
"""Test the exact command that spec-workflow-run uses."""

import subprocess
import time
import threading
from pathlib import Path

# Exact command from spec-workflow-run
command_list = [
    "claude",
    "--print",
    "--model", "sonnet",
    "--dangerously-skip-permissions",
    "--output-format", "stream-json",
    "--verbose",
    "[!] IMPORTANT: Test prompt"
]

# Format as string using Windows method
command_str = subprocess.list2cmdline(command_list)
print(f"Command string: {command_str}\n")

# Create subprocess exactly as popen_command does
proc = subprocess.Popen(
    command_str,
    cwd=Path.cwd(),
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    bufsize=0,
    shell=True,
)

print(f"Process PID: {proc.pid}")
print(f"Poll status: {proc.poll()}")
print(f"stdout: {proc.stdout}")

# Exact read logic from run_tasks.py WITH file writing
log_file = Path("test_output.log")

def read_output():
    with log_file.open("w", encoding="utf-8") as handle:
        print("[DEBUG] Reader thread started")
        line_count = 0
        while True:
            print(f"[DEBUG] Calling readline() for line {line_count + 1}...")
            line = proc.stdout.readline()
            if not line:
                break

            # Write to file like in run_tasks.py
            decoded = line.decode("utf-8", errors="replace").strip()
            handle.write(decoded + "\n")
            handle.flush()

            print(f"[DEBUG] Got line {line_count + 1}: {decoded[:100]}")
            line_count += 1
            if line_count >= 3:
                break
        print(f"[DEBUG] Reader finished. Got {line_count} lines")

# Start reader thread
thread = threading.Thread(target=read_output, daemon=True)
thread.start()

# Wait for thread
thread.join(timeout=10)

if thread.is_alive():
    print("\n[ERROR] Thread is still blocked after 10 seconds!")
    print("readline() is hanging!")
else:
    print("\n[SUCCESS] Thread completed!")

# Cleanup
try:
    proc.terminate()
    proc.wait(timeout=5)
except:
    proc.kill()
