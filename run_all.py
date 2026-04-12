"""
MoodWave - Run All Servers
Starts both Spotify (port 5000) and YouTube (port 5001) together.

Run:
    python run_all.py
"""

import subprocess
import sys
import os
import threading
import time

SPOTIFY_DIR = os.path.dirname(os.path.abspath(__file__))
YOUTUBE_DIR = os.path.join(os.path.dirname(SPOTIFY_DIR), "rm project")

# The rm project uses 'rm app.py' as its script name
YOUTUBE_SCRIPT = "rm app.py"


def stream(proc, label):
    for line in iter(proc.stdout.readline, b""):
        try:
            print(f"[{label}] " + line.decode("utf-8", errors="replace"), end="")
        except Exception:
            pass


def launch(script_dir, script_name, label):
    script_path = os.path.join(script_dir, script_name)
    if not os.path.isfile(script_path):
        print(f"[ERROR] Script not found: {script_path}")
        return None
    proc = subprocess.Popen(
        [sys.executable, script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=script_dir,
    )
    t = threading.Thread(target=stream, args=(proc, label), daemon=True)
    t.start()
    return proc


if __name__ == "__main__":
    print("=" * 52)
    print("  MoodWave - Starting Both Servers")
    print("=" * 52)
    print("  Spotify  ->  http://localhost:5000")
    print("  YouTube  ->  http://localhost:5001")
    print("=" * 52)
    print()

    if not os.path.isdir(YOUTUBE_DIR):
        print(f"[ERROR] YouTube project not found at: {YOUTUBE_DIR}")
        print("        Make sure 'rm project' folder exists next to 'music project'.")
        sys.exit(1)

    procs = []

    sp = launch(SPOTIFY_DIR, "app.py", "Spotify:5000")
    if sp:
        procs.append(sp)
    time.sleep(1.5)

    yt = launch(YOUTUBE_DIR, YOUTUBE_SCRIPT, "YouTube:5001")
    if yt:
        procs.append(yt)

    if not procs:
        print("[ERROR] No servers started. Check the script paths above.")
        sys.exit(1)

    print("[MoodWave] Servers running. Press Ctrl+C to stop.\n")

    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("\n[MoodWave] Stopping all servers...")
        for p in procs:
            p.terminate()
        print("[MoodWave] Stopped. Bye!")
