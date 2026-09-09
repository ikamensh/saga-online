"""Run every game's create/join path before activating an unpacked release."""
import os
from pathlib import Path
import subprocess
import sys
import select


release = Path(sys.argv[1]).resolve()
python = str(release / ".venv/bin/python")
with subprocess.Popen(
    ["runuser", "-u", "saga2d-online", "--", python,
     "-m", "saga2d.server", "--host", "127.0.0.1", "--port", "0", "--games", *"tribes.multiplayer:ONLINE warband.multiplayer:ONLINE eador.multiplayer:ONLINE".split()],
    cwd=release, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    stdout=subprocess.PIPE, text=True,
) as process:
    try:
        readable, _, _ = select.select([process.stdout], [], [], 15)
        if not readable:
            raise RuntimeError("Candidate server did not start within 15 seconds")
        line = process.stdout.readline().strip()
        if not line.startswith("LISTENING ws://127.0.0.1:"):
            raise RuntimeError(f"Candidate server did not announce a loopback endpoint: {line}")
        endpoint = line.removeprefix("LISTENING ") + "/play"
        subprocess.run([python, str(release / "deploy/smoke.py"), endpoint], check=True, timeout=60)
    finally:
        process.terminate()
        process.wait(timeout=25)
