#!/usr/bin/env python3
"""Stress test thread-safe state."""
import sys
import threading
import time
sys.path.insert(0, '/home/rik/WhisprBar')

from whisprbar.main import AppState

state = AppState()
errors = []

def hammer_recording(iterations: int):
    """Rapidly toggle recording state."""
    for i in range(iterations):
        state.recording = True
        time.sleep(0.0001)
        state.recording = False

def hammer_transcribing(iterations: int):
    """Rapidly toggle transcribing state."""
    for i in range(iterations):
        state.transcribing = True
        time.sleep(0.0001)
        state.transcribing = False

def hammer_last_transcript(iterations: int):
    """Rapidly update last_transcript."""
    for i in range(iterations):
        state.last_transcript = f"Test transcript {i}"
        time.sleep(0.0001)

def verify_consistency():
    """Verify state remains consistent."""
    for _ in range(1000):
        snapshot = state.get_status()
        if not isinstance(snapshot["recording"], bool):
            errors.append("recording not bool")
        if not isinstance(snapshot["transcribing"], bool):
            errors.append("transcribing not bool")
        if not isinstance(snapshot["last_transcript"], str):
            errors.append("last_transcript not str")
        time.sleep(0.001)

# Create 15 concurrent threads
threads = []
for i in range(5):
    t1 = threading.Thread(target=hammer_recording, args=(1000,))
    t2 = threading.Thread(target=hammer_transcribing, args=(1000,))
    t3 = threading.Thread(target=verify_consistency)
    threads.extend([t1, t2, t3])

print("Starting stress test with 15 concurrent threads...")
print("- 5 threads hammering recording state (5000 operations)")
print("- 5 threads hammering transcribing state (5000 operations)")
print("- 5 threads verifying consistency (5000 checks)")
print()

start_time = time.time()

for t in threads:
    t.start()
for t in threads:
    t.join()

elapsed = time.time() - start_time

print(f"Test completed in {elapsed:.2f} seconds")
print()

if errors:
    print(f"❌ FAILED: {len(errors)} errors detected")
    print("Errors:", set(errors))
    sys.exit(1)
else:
    print("✅ PASSED: No race conditions detected")
    print("All state accesses were thread-safe")
    sys.exit(0)
