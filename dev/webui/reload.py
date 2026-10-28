"""Restart the sandbox server when Python source changes."""
from pathlib import Path
import signal
import subprocess
import sys
import time


ROOTS = ("webui", "Buttons", "commands", "helpers", "listeners", "setup", "dev")


def source_times():
    paths = [Path("config.py")]
    for root in ROOTS:
        paths.extend(Path(root).rglob("*.py"))
    return {str(path): path.stat().st_mtime_ns for path in paths if path.is_file()}


def main():
    process = None

    def stop(signum, frame):
        if process is not None:
            process.terminate()
            process.wait()
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    previous = source_times()
    process = subprocess.Popen([sys.executable, "-m", "webui.server"])
    try:
        while True:
            time.sleep(1)
            current = source_times()
            if current != previous:
                print("Python source changed; restarting web UI", flush=True)
                process.terminate()
                process.wait()
                process = subprocess.Popen([sys.executable, "-m", "webui.server"])
                previous = current
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()


if __name__ == "__main__":
    main()
