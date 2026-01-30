#!/usr/bin/env python3
"""Integration test to diagnose Claude subprocess output issue."""

import subprocess
import sys
import time

print("=" * 80)
print("Test 1: Direct subprocess.run (blocking)")
print("=" * 80)

result = subprocess.run(
    ["claude", "--print", "--model", "sonnet", "--dangerously-skip-permissions",
     "--output-format", "stream-json", "--verbose", "Say hello in 3 words"],
    capture_output=True,
    text=True,
    timeout=15
)

print(f"Return code: {result.returncode}")
print(f"Stdout length: {len(result.stdout)}")
print(f"Stderr length: {len(result.stderr)}")
print(f"First 500 chars of stdout:\n{result.stdout[:500]}")

print("\n" + "=" * 80)
print("Test 2: subprocess.Popen with PIPE (non-blocking)")
print("=" * 80)

proc = subprocess.Popen(
    ["claude", "--print", "--model", "sonnet", "--dangerously-skip-permissions",
     "--output-format", "stream-json", "--verbose", "Say hello in 3 words"],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    bufsize=0,
)

print(f"Process PID: {proc.pid}")
print(f"Poll status: {proc.poll()}")
print("Waiting 5 seconds for output...")
time.sleep(5)

# Try to read with timeout
proc.stdout.flush() if hasattr(proc.stdout, 'flush') else None
lines = []
start = time.time()
while time.time() - start < 10:
    line = proc.stdout.readline()
    if not line:
        break
    decoded = line.decode('utf-8', errors='replace').strip()
    lines.append(decoded)
    print(f"Line {len(lines)}: {decoded[:100]}")
    if len(lines) >= 5:  # Get first 5 lines
        break

print(f"\nTotal lines received: {len(lines)}")
print(f"Process poll status after reading: {proc.poll()}")

# Clean up
try:
    proc.terminate()
    proc.wait(timeout=5)
except:
    proc.kill()

print("\n" + "=" * 80)
print("Test 3: subprocess.Popen on Windows with shell=True")
print("=" * 80)

# This mimics what popen_command does on Windows
cmd_str = 'claude --print --model sonnet --dangerously-skip-permissions --output-format stream-json --verbose "Say hello in 3 words"'
proc = subprocess.Popen(
    cmd_str,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    bufsize=0,
    shell=True,
)

print(f"Process PID: {proc.pid}")
print(f"Poll status: {proc.poll()}")
print("Waiting 5 seconds for output...")
time.sleep(5)

lines = []
start = time.time()
while time.time() - start < 10:
    line = proc.stdout.readline()
    if not line:
        break
    decoded = line.decode('utf-8', errors='replace').strip()
    lines.append(decoded)
    print(f"Line {len(lines)}: {decoded[:100]}")
    if len(lines) >= 5:
        break

print(f"\nTotal lines received: {len(lines)}")
print(f"Process poll status after reading: {proc.poll()}")

# Clean up
try:
    proc.terminate()
    proc.wait(timeout=5)
except:
    proc.kill()

print("\nTests complete!")
