"""Thirty days of minute samples, containing only per-game counts and UTC times.

Samples are instantaneous connected seats and observers. Missing samples mean
collection was interrupted, never that the server had zero players. Nothing is
backfilled before this collector first ran.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import time

SAMPLE_INTERVAL_SECONDS = 60
RETENTION_DAYS = 30
COUNTS = ("players", "observers", "rooms", "ready_rooms")


def utc(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def current_counts(rooms, games):
    """Count connected seats and watchers separately for every registered game."""
    counts = {game: dict.fromkeys(COUNTS, 0) for game in games}
    for room in rooms:
        current = counts[room.game]
        current["players"] += room.present
        current["observers"] += room.observer_count
        current["rooms"] += 1
        current["ready_rooms"] += int(room.ready)
    return counts


class ActivityHistory:
    """Persist observed counts; reports combine bounded history with fresh counts."""

    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory / "activity.sqlite3"
        path.touch(mode=0o600, exist_ok=True)
        path.chmod(0o600)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        with self.db:
            self.db.execute("""CREATE TABLE IF NOT EXISTS samples (
                game TEXT NOT NULL, timestamp INTEGER NOT NULL,
                players INTEGER NOT NULL, observers INTEGER NOT NULL,
                rooms INTEGER NOT NULL, ready_rooms INTEGER NOT NULL,
                PRIMARY KEY (game, timestamp)
            )""")

    def record(self, counts, *, now=None):
        """Write one observation per game and remove samples older than thirty days."""
        timestamp = int(time.time() if now is None else now)
        with self.db:
            self.db.executemany("INSERT OR IGNORE INTO samples VALUES (?, ?, ?, ?, ?, ?)",
                                [(game, timestamp, *(values[name] for name in COUNTS))
                                 for game, values in counts.items()])
            self.db.execute("DELETE FROM samples WHERE timestamp < ?",
                            (timestamp - RETENTION_DAYS * 86400,))

    def report(self, game, hours, *, current, now=None):
        """Return observed samples only; no interpolation across collection gaps."""
        timestamp = int(time.time() if now is None else now)
        since = self.db.execute("SELECT MIN(timestamp) FROM samples WHERE game = ?", (game,)).fetchone()[0]
        samples = [{"timestamp": utc(observed), **dict(zip(COUNTS, values))}
                   for observed, *values in self.db.execute(
                       "SELECT timestamp, players, observers, rooms, ready_rooms FROM samples "
                       "WHERE game = ? AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp",
                       (game, timestamp - hours * 3600, timestamp))]
        return {"game": game, "hours": hours, "server_time": utc(timestamp),
                "collected_since": None if since is None else utc(since),
                "sample_interval_seconds": SAMPLE_INTERVAL_SECONDS, "retention_days": RETENTION_DAYS,
                "current": current, "samples": samples}

    def close(self):
        self.db.close()
