"""Rejoin every retained seat of a room backup on a private copy, with the candidate server code.

    uv run python tools/rehearse_retained.py dist/online/backups/rooms-<UTC>.sqlite3
    uv run python tools/rehearse_retained.py BACKUP --endpoint wss://games.tachyon-ai.eu/play   # after activation

Starts the real room server for all three games on a loopback port over a copy of the backup (the
original is never opened for writing), then resumes each seat of each retained room with its own
token and waits for the room's state. Prints one line per seat (stderr) and a JSON summary; exits
non-zero when any retained seat fails to resume. Without --endpoint nothing reaches the live server or store.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

from saga2d.online import OnlineClient
from saga2d.packaging.verify import local_server

GAMES = ("tribes.multiplayer:ONLINE", "warband.online.authority:ONLINE", "eador.multiplayer:ONLINE")


def rooms(path: Path) -> list[dict]:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        suspended = {row[0] for row in db.execute("SELECT code FROM suspended")}
        return [{"code": code, "game": game, "tokens": json.loads(tokens), "revision": revision, "expires_at": expires_at,
                 "suspended": code in suspended}
                for code, game, tokens, revision, expires_at in db.execute("SELECT code, game, tokens, revision, expires_at FROM rooms")]
    finally:
        db.close()


def resume(endpoint: str, room: dict, seat: int, token: str, timeout: float = 20.0) -> dict:
    client = OnlineClient(room["game"], endpoint=endpoint, room=room["code"], resume_token=token)
    started = time.monotonic()
    try:
        while time.monotonic() - started < timeout:
            client.poll()
            if client.error:
                return {"seat": seat, "resumed": False, "error": client.error}
            if client.state is not None:
                return {"seat": seat, "resumed": True, "player": client.player, "tick": client.state.get("world", {}).get("tick"),
                        "revision": client.revision}
            time.sleep(0.02)
        return {"seat": seat, "resumed": False, "error": f"no state within {timeout} s"}
    finally:
        client.close()


def resume_all(endpoint: str, retained: list[dict], report: dict) -> None:
    for room in retained:
        for seat, token in enumerate(room["tokens"]):
            if token is None:
                continue
            outcome = resume(endpoint, room, seat, token)
            report["seats"].append({"room": room["code"], "game": room["game"], "suspended": room["suspended"], **outcome})
            print(f"{room['game']:12s} {room['code']} seat {seat}: {'resumed' if outcome['resumed'] else 'FAILED'}"
                  f" {outcome.get('error', '')} tick {outcome.get('tick')}", file=sys.stderr, flush=True)


def rehearse(backup: Path, endpoint: str | None = None) -> dict:
    """Resume every retained seat: on a private copy with this checkout's server, or on ``endpoint`` itself."""
    retained = [room for room in rooms(backup) if room["expires_at"] > time.time()]
    report = {"backup": backup.name, "rooms": len(rooms(backup)), "retained": len(retained), "seats": [],
              "endpoint": endpoint or "private copy"}
    if endpoint is not None:
        resume_all(endpoint, retained, report)
    else:
        with tempfile.TemporaryDirectory(prefix="saga2d-rehearsal-") as temporary:
            state = Path(temporary) / "state"
            state.mkdir(mode=0o700)
            shutil.copy2(backup, state / "rooms.sqlite3")
            from saga2d.server import RoomServer
            original = RoomServer.__init__

            def with_state(self, games, **kwargs):  # the helper starts a bare server; the rehearsal needs the copied store
                original(self, games, **{**kwargs, "state_dir": state, "room_ttl": 900, "max_rooms": 64, "max_connections": 128})  # the production limits
            RoomServer.__init__ = with_state
            try:
                with local_server(*GAMES) as local:
                    resume_all(local, retained, report)
            finally:
                RoomServer.__init__ = original
    report["failed"] = sum(not seat["resumed"] for seat in report["seats"])
    if retained and not report["seats"]:
        report["failed"] = len(retained)  # retained rooms without a single seat token cannot be resumed
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    parser.add_argument("--endpoint", help="Resume on this server (the live one after activation) instead of a private copy")
    args = parser.parse_args()
    report = rehearse(args.backup, args.endpoint)
    print(json.dumps(report, indent=1))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
