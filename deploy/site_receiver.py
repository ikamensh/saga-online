"""Trusted, unprivileged receiver for the forced SSH status/publish operations.

Configuration and this module are installed by the operator, never supplied in
an upload. Publication uses only the adjacent trusted activation implementation.
"""
from __future__ import annotations

import argparse
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import sys
import tarfile
import tempfile

# Isolated Python (-I) excludes the working directory and environment imports.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from activate_site import accepted_state, activate, require

MAX_ARCHIVE = 64 * 1024 * 1024
MAX_EXPANDED = 256 * 1024 * 1024
MAX_FILES = 2048


def status(base, lock_path):
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return {"schema_version": 1, "accepted": accepted_state(base), "pending": (base / "pending.json").exists()}


def unpack(stream, folder):
    line = stream.readline(4097)
    require(len(line) <= 4096 and line.endswith(b"\n"), "Expected a bounded JSON upload header")
    header = json.loads(line)
    require(set(header) == {"schema_version", "release", "bytes", "generation", "expected"}
            and header["schema_version"] == 1, "Unsupported upload header")
    require(type(header["bytes"]) is int and 0 < header["bytes"] <= MAX_ARCHIVE, "Upload exceeds the archive limit")
    require(type(header["generation"]) is int and header["generation"] > 0, "Expected a positive promotion generation")
    require(re.fullmatch(r"[a-f0-9]{64}", header["release"])
            and re.fullmatch(r"none|[a-f0-9]{64}", header["expected"]), "Invalid upload release identifier")
    compressed = folder / "archive.gz"
    remaining = header["bytes"]
    with compressed.open("xb") as output:
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            require(bool(chunk), "Truncated upload")
            output.write(chunk)
            remaining -= len(chunk)
    require(not stream.read(1), "Unexpected bytes after upload")
    with compressed.open("rb") as source:
        require(hashlib.file_digest(source, "sha256").hexdigest() == header["release"], "Upload checksum differs")
    # Bound the complete decompressed stream, including tar/PAX metadata,
    # before parsing member headers or allocating member-sized buffers.
    expanded = folder / "archive.tar"
    total = 0
    with gzip.open(compressed, "rb") as source, expanded.open("xb") as output:
        while chunk := source.read(1024 * 1024):
            total += len(chunk)
            require(total <= MAX_EXPANDED, "Upload exceeds the expanded limit")
            output.write(chunk)
    extracted = folder / "content"
    extracted.mkdir()
    seen = set()
    with tarfile.open(expanded, "r:") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            require(member.isfile() and member.sparse is None and not member.pax_headers
                    and str(path) == member.name and not path.is_absolute()
                    and all(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", part) and part not in (".", "..") for part in path.parts),
                    "Unsafe upload entry")
            require(member.name == "promotion.json" or (len(path.parts) > 1 and path.parts[0] == "site"), "Unrelated upload entry")
            require(member.name not in seen and len(seen) < MAX_FILES, "Duplicate entry or too many upload files")
            seen.add(member.name)
            target = extracted / path
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            target.chmod(0o644)
    require({"promotion.json", "site/index.html", "site/releases.json"} <= seen, "Upload requires a complete site and promotion receipt")
    return header, extracted


def receive(config, operation, stream):
    require(operation in ("status", "publish"), "Only status and publish are permitted")
    require(set(config) == {"schema_version", "base", "lock", "public_url"} and config["schema_version"] == 1,
            "Unsupported installed receiver configuration")
    base, lock = Path(config["base"]).resolve(), Path(config["lock"]).resolve()
    if operation == "status":
        require(not stream.read(1), "Status does not accept an upload")
        return status(base, lock)
    with tempfile.TemporaryDirectory(prefix="saga2d-site-upload-") as temporary:
        header, extracted = unpack(stream, Path(temporary))
        promotion = json.loads((extracted / "promotion.json").read_bytes())
        require(isinstance(promotion, dict), "Expected a promotion receipt")
        return activate(extracted / "site", base, header["release"], header["generation"], header["expected"],
                        config["public_url"], config["public_url"].rstrip("/") + "/healthz", lock, promotion)


def expired(signum, frame):
    raise TimeoutError("Site command exceeded 300 seconds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Operator-installed configuration, never an upload path")
    args = parser.parse_args()
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(300)
    result = receive(json.loads(args.config.read_bytes()), os.environ.get("SSH_ORIGINAL_COMMAND", ""), sys.stdin.buffer)
    print(json.dumps(result, sort_keys=True))
