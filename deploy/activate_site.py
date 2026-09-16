"""Activate a prepared static site without touching the room server.

The caller supplies the expected current release and a monotonically increasing
promotion generation. Production uses HTTPS; loopback HTTP is for integration
tests. This script does not create cloud resources or install credentials.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import quote, urlsplit
from urllib.request import urlopen


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def contents(directory: Path) -> dict[str, str]:
    result = {}
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), f"Site releases cannot contain symlinks: {path}")
        if path.is_file():
            with path.open("rb") as stream:
                result[path.relative_to(directory).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
        else:
            require(path.is_dir(), f"Unsupported site entry: {path}")
    require("index.html" in result and "releases.json" in result, "Build the site before activating it")
    return result


def write_json(path: Path, value: dict) -> None:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(stream.name, path)
    sync_directory(path.parent)


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def current(base: Path) -> str:
    path = base / "current"
    if not path.is_symlink():
        require(not path.exists(), "The current site must be a release symlink")
        return "none"
    target = path.resolve(strict=True)
    require(target.parent == base / "releases" and bool(re.fullmatch(r"[0-9a-f]{64}", target.name)),
            "The current site points outside the managed releases")
    return target.name


def point(base: Path, name: str, release: str) -> None:
    require(release == "none" or bool(re.fullmatch(r"[0-9a-f]{64}", release)), "Invalid stored release identifier")
    path = base / name
    if release == "none":
        path.unlink(missing_ok=True)
        sync_directory(base)
        return
    # The lock serializes both publishers and recovery; replace is atomic to readers.
    temporary = base / (name + ".next")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(Path("releases") / release)
    temporary.replace(path)
    sync_directory(base)


def recover(base: Path) -> None:
    """Resolve an interrupted transaction under the same publication lock."""
    pending = base / "pending.json"
    if not pending.exists():
        return
    transaction = json.loads(pending.read_text())
    before, after = transaction["before"], transaction["after"]
    state_path = base / "state.json"
    stored = json.loads(state_path.read_text()) if state_path.exists() else before
    pointer = current(base)
    if stored == after:
        require(pointer == after["release"], "Committed activation has an unexpected site pointer")
    else:
        require(stored == before and pointer in (before["release"], after["release"]),
                "Interrupted activation conflicts with externally changed publication state")
        point(base, "current", before["release"])
        point(base, "previous", before.get("previous", "none"))
    pending.unlink()
    sync_directory(base)


def verify_public(files: dict[str, str], public_url: str, health_url: str, release: str) -> None:
    for url in (public_url, health_url):
        parsed = urlsplit(url)
        require(parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "::1", "localhost")),
                "Public verification requires HTTPS (or loopback HTTP for tests)")
    for name, expected in files.items():
        url = public_url.rstrip("/") + "/" + quote(name) + "?release=" + release
        with urlopen(url, timeout=10) as response:
            require(response.status == 200 and hashlib.sha256(response.read()).hexdigest() == expected,
                    f"Public site differs from candidate: {name}")
    with urlopen(health_url, timeout=10) as response:
        require(response.status == 200 and response.read() == b"ok\n", "Room server health check failed")


def activate(source: Path, base: Path, release: str, generation: int, expected: str,
             public_url: str, health_url: str) -> dict:
    require(bool(re.fullmatch(r"[0-9a-f]{64}", release)), "Release must be a SHA-256 identifier")
    require(expected == "none" or bool(re.fullmatch(r"[0-9a-f]{64}", expected)), "Expected release must be a SHA-256 identifier or none")
    require(generation > 0, "Promotion generation must be positive")
    source, base = source.resolve(), base.resolve()
    require(not base.is_relative_to(source), "The destination must not be inside the source site")
    files = contents(source)
    base.mkdir(parents=True, exist_ok=True)
    with (base / ".publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        recover(base)
        previous = current(base)
        state_path = base / "state.json"
        state = json.loads(state_path.read_text()) if state_path.exists() else {"release": previous, "generation": 0}
        require(state["release"] == previous, "Site pointer differs from publication state")
        retry = previous == release and state["generation"] == generation
        if not retry:
            require(previous == expected, "Current site changed since this promotion was prepared")
            require(generation > state["generation"], "An older promotion cannot replace the current site")
        destination = base / "releases" / release
        if destination.exists():
            require(not destination.is_symlink() and contents(destination) == files, "A versioned site release cannot be overwritten")
        else:
            destination.parent.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="site-", dir=destination.parent) as temporary:
                staged = Path(temporary) / "site"
                shutil.copytree(source, staged)
                require(contents(staged) == files, "Site bytes changed during staging")
                staged.rename(destination)
        if retry:
            verify_public(files, public_url, health_url, release)
            return state
        after = {"release": release, "generation": generation, "previous": previous}
        pending = base / "pending.json"
        write_json(pending, {"before": state, "after": after})
        point(base, "current", release)
        try:
            verify_public(files, public_url, health_url, release)
        except BaseException:
            point(base, "current", previous)
            pending.unlink()
            sync_directory(base)
            raise
        point(base, "previous", previous)
        write_json(state_path, after)
        pending.unlink()
        sync_directory(base)
        return after


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--expected", required=True)
    parser.add_argument("--public-url", required=True)
    parser.add_argument("--health-url", required=True)
    args = parser.parse_args()
    result = activate(args.source, args.base, args.release, args.generation, args.expected, args.public_url, args.health_url)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
