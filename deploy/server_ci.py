"""Root side of the restricted server-CI account: status, backup, install and rollback.

The operator installs this file, the host tools it runs and its configuration
(`install_server_ci.py`); sudo lets the CI account run exactly
``run status|backup|install|rollback`` and nothing else. Parameters arrive as one
bounded JSON line on stdin, followed by the archive for ``install``. Nothing from
an upload runs as root: the release is staged, compared with these host tools
and prepared by them, and its own code runs only as the service account.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import sys
import tempfile
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
BASE = Path("/opt/saga2d-online")
BACKUPS = Path("/var/backups/saga2d-online")
SITE_PENDING = Path("/srv/saga2d-site/pending.json")
LOCAL = "http://127.0.0.1:8765"
MAX_ARCHIVE = 64 * 1024 * 1024
RELEASE = re.compile(r"[0-9a-f]{64}")
OPERATIONS = ("status", "backup", "install", "rollback")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def header(stream, fields):
    line = stream.readline(4097)
    require(len(line) <= 4096 and line.endswith(b"\n"), "Expected a bounded JSON header line")
    value = json.loads(line)
    require(isinstance(value, dict) and set(value) == {"schema_version", *fields} and value["schema_version"] == 1,
            "Unsupported request header")
    return value


def release_of(link):
    target = os.readlink(link) if link.is_symlink() else None
    return Path(target).name if target else None


def local_json(path):
    with urlopen(LOCAL + path, timeout=10) as response:
        return response.read() if path == "/healthz" else json.load(response)


def status(config):
    active = subprocess.run(["systemctl", "is-active", "saga2d-online"], capture_output=True, text=True).stdout.strip()
    result = {"schema_version": 1, "instance": config["instance"], "tools": HERE.name,
              "current": release_of(BASE / "current"), "previous": release_of(BASE / "previous"),
              "service": active, "site_pending": SITE_PENDING.exists()}
    if active == "active":
        result["health"] = local_json("/healthz").decode().strip()
        result["attestation"] = local_json("/server-compatibility.json")
    return result


def backup(config, out):
    """Take a fresh consistent backup with the installed unit and stream the newest file."""
    subprocess.run(["systemctl", "start", "saga2d-backup.service"], check=True, capture_output=True)
    names = sorted(p.name for p in BACKUPS.iterdir() if re.fullmatch(r"rooms-\d{8}T\d{6}Z\.sqlite3", p.name))
    require(bool(names), "The server holds no room backup")
    path = BACKUPS / names[-1]
    data = path.read_bytes()
    with tempfile.NamedTemporaryFile(suffix=".sqlite3") as copy:
        copy.write(data)
        copy.flush()
        db = sqlite3.connect(f"file:{copy.name}?mode=ro", uri=True)
        try:
            require(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "Backup failed its integrity check")
            rooms = db.execute("SELECT count(*) FROM rooms").fetchone()[0]
        finally:
            db.close()
    meta = {"schema_version": 1, "name": names[-1], "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "rooms": rooms}
    out.write(json.dumps(meta, sort_keys=True).encode() + b"\n" + data)
    return None


def installer(*arguments):
    # install.sh prints its progress; the caller's stdout carries only the JSON result.
    result = subprocess.run(["bash", str(HERE / "install.sh"), *arguments], stdout=sys.stderr, stderr=sys.stderr)
    require(result.returncode == 0, f"install.sh {arguments[0]} failed with exit {result.returncode}")


def install(config, stream):
    request = header(stream, {"release", "bytes", "expected_current"})
    require(bool(RELEASE.fullmatch(request["release"])), "Invalid release identifier")
    require(type(request["bytes"]) is int and 0 < request["bytes"] <= MAX_ARCHIVE, "Archive exceeds its limit")
    current = release_of(BASE / "current")
    require(request["expected_current"] == (current or "none"),
            f"The current release is {current or 'none'}, not the expected {request['expected_current']}")
    with tempfile.TemporaryDirectory(prefix="saga2d-server-upload-") as temporary:
        upload = Path(temporary)
        upload.chmod(0o700)
        archive = upload / "release.tar.gz"
        digest, remaining = hashlib.sha256(), request["bytes"]
        with archive.open("xb") as output:
            while remaining:
                chunk = stream.read(min(1024 * 1024, remaining))
                require(bool(chunk), "Truncated archive")
                digest.update(chunk)
                output.write(chunk)
                remaining -= len(chunk)
        require(not stream.read(1), "Unexpected bytes after the archive")
        require(digest.hexdigest() == request["release"], "Archive differs from its release identifier")
        installer(str(upload), request["release"], config["instance"], config["domain"])
    return {**status(config), "activated": request["release"]}


def rollback(config, stream):
    request = header(stream, {"from"})
    require(bool(RELEASE.fullmatch(request["from"])), "Invalid release identifier")
    require(not stream.read(1), "Rollback does not accept an upload")
    installer("--rollback", request["from"], config["instance"], config["domain"])
    return {**status(config), "rolled_back_from": request["from"]}


def run(operation, stdin, stdout):
    require(operation in OPERATIONS, "Only status, backup, install and rollback are permitted")
    config = json.loads((HERE / "config.json").read_bytes())
    require(set(config) == {"schema_version", "instance", "domain"} and config["schema_version"] == 1,
            "Unsupported installed configuration")
    require((Path("/etc/saga2d-online/managed-instance").read_text().strip() == config["instance"]),
            "Managed instance does not match the installed configuration")
    if operation == "status":
        require(not stdin.read(1), "Status does not accept an upload")
        return status(config)
    if operation == "backup":
        require(not stdin.read(1), "Backup does not accept an upload")
        return backup(config, stdout)
    # One rollout at a time; activation itself also holds the shared publish lock.
    with open("/run/saga2d-server-ci.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return (install if operation == "install" else rollback)(config, stdin)


def expired(signum, frame):
    raise TimeoutError("Server CI command exceeded 1200 seconds")


if __name__ == "__main__":
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(1200)
    require(len(sys.argv) == 2, "Expected exactly one operation")
    result = run(sys.argv[1], sys.stdin.buffer, sys.stdout.buffer)
    if result is not None:
        sys.stdout.buffer.write(json.dumps(result, sort_keys=True).encode() + b"\n")
