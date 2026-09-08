"""Consistent SQLite backup of the room checkpoints, with age-based rotation.

Run by saga2d-backup.timer as the service user; a raw copy of a live WAL
database is not a backup, so this uses SQLite's online backup API.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys

KEEP_DAYS = 14


def backup(database: Path, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = folder / f"rooms-{stamp}.sqlite3"
    partial = target.with_suffix(".partial")
    source = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        copy = sqlite3.connect(partial)
        try:
            source.backup(copy)
            if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup failed its integrity check")
            rooms = copy.execute("SELECT count(*) FROM rooms").fetchone()[0]
        finally:
            copy.close()
    finally:
        source.close()
    partial.chmod(0o600)
    partial.replace(target)
    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    for old in folder.glob("rooms-*.sqlite3"):
        if datetime.strptime(old.name[6:22], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc) < cutoff:
            old.unlink()
    print(f"{target} ({rooms} rooms)", flush=True)
    return target


if __name__ == "__main__":
    backup(Path(sys.argv[1]), Path(sys.argv[2]))
