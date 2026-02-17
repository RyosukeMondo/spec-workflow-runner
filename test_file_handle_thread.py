#!/usr/bin/env python3
"""Test passing file handle from main thread to worker thread."""

import subprocess
import threading
from pathlib import Path

command_list = [
    "claude",
    "--print",
    "--model",
    "sonnet",
    "--dangerously-skip-permissions",
    "--output-format",
    "stream-json",
    "--verbose",
    "Say hello in 3 words",
]

command_str = subprocess.list2cmdline(command_list)
print(f"Command: {command_str}\n")

log_file = Path("test_handle.log")

# EXACT pattern from run_tasks.py
output_lines = []


def read_output(proc, handle, output_lines):
    """Exact function from run_tasks.py"""
    print("[DEBUG] Reader thread started", flush=True)
    print(f"[DEBUG] proc.stdout: {proc.stdout}", flush=True)
    print("[DEBUG] About to start reading loop...", flush=True)

    line_count = 0
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        print(f"[DEBUG] Got line {line_count + 1}, length: {len(line)}", flush=True)
        decoded = line.decode("utf-8", errors="replace").strip()

        # Write to log file
        handle.write(decoded + "\n")
        handle.flush()
        output_lines.append(decoded)

        line_count += 1
        if line_count >= 3:
            break

    print(f"[DEBUG] Reader finished. Got {line_count} lines", flush=True)


# Open file in main thread, pass handle to worker thread
with log_file.open("w", encoding="utf-8") as handle:
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

    # Start reader thread - EXACTLY like run_tasks.py
    reader_thread = threading.Thread(
        target=read_output, args=(proc, handle, output_lines), daemon=True
    )
    reader_thread.start()
    print("[DEBUG] Reader thread started from main")

    # Wait for thread
    reader_thread.join(timeout=10)

    if reader_thread.is_alive():
        print("\n[ERROR] Thread is still blocked!")
    else:
        print("\n[SUCCESS] Thread completed!")
        print(f"Got {len(output_lines)} lines")

    # Cleanup
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except:
        proc.kill()
