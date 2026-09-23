"""Verify the attested package and three-game orders/rejoin before activation.

Run as the intended service user. Test rooms and private seat credentials remain
in this process and its private temporary directory, never the live store.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stdout
import json
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
from urllib.request import urlopen

from backup import backup
from smoke import smoke, resume


@contextmanager
def running(release, release_id, endpoint, state):
    python = str(release / ".venv/bin/python")
    process = subprocess.Popen([python, "-B", str(release / "deploy/server.py"), "--host", "127.0.0.1", "--port", "0",
                                "--release-id", release_id, "--endpoint", endpoint, "--state-dir", str(state)],
                               cwd=state.parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        readable, _, _ = select.select([process.stdout], [], [], 15)
        if not readable:
            raise RuntimeError("Candidate server did not start within 15 seconds")
        line = process.stdout.readline().strip()
        if not line.startswith("LISTENING ws://127.0.0.1:"):
            raise RuntimeError(f"Candidate server did not announce a loopback endpoint: {line}")
        yield line.removeprefix("LISTENING ")
    finally:
        if process.poll() is None:
            process.terminate()
        _, error = process.communicate(timeout=25)
        if process.returncode != 0:
            raise RuntimeError(f"Candidate server exited with {process.returncode}: {error}")


def verify(release, release_id, endpoint):
    release = release.resolve()
    inputs = json.loads((release / "deploy/server-inputs.json").read_bytes())
    expected = {"schema_version": 1, "deployment_release": release_id, "endpoint": endpoint, "protocol": 1,
                "warband": {"source_commit": inputs["sources"]["warband"], "compatibility": inputs["warband_compatibility"]}}
    with tempfile.TemporaryDirectory(prefix="saga2d-check-") as temporary:
        state = Path(temporary) / "rooms"
        restored = Path(temporary) / "restored"
        for restart in (False, True):
            with running(release, release_id, endpoint, state) as local:
                with urlopen(local.replace("ws://", "http://") + "/server-compatibility.json", timeout=10) as response:
                    actual = json.load(response)
                if actual != expected:
                    raise RuntimeError("Running candidate differs from its expected compatibility baseline")
                if restart:
                    resume(local + "/play", records)
                else:
                    records = smoke(local + "/play", games=("warband-v2",))
            if not restart:
                # Capture this exact paused checkpoint before rejoining both
                # players lets the RTS advance during the restart check.
                with redirect_stdout(sys.stderr):
                    saved = backup(state / "rooms.sqlite3", Path(temporary) / "backups")
                restored.mkdir(mode=0o700)
                shutil.copy2(saved, restored / "rooms.sqlite3")
        # Use only the backup, without borrowing the original database or WAL.
        with running(release, release_id, endpoint, restored) as local:
            resume(local + "/play", records)
    return {"passed": True, "baseline": expected, "games": [record["game"] for record in records],
            "restart_rejoin": True, "backup_restore": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--endpoint", required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.release, args.release_id, args.endpoint), sort_keys=True, indent=2))
