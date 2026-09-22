"""Collect a clean, pinned server package and its verifiable runtime inputs."""
from __future__ import annotations

import base64
import fnmatch
import hashlib
import importlib.metadata
import importlib.util
import json
import io
from pathlib import Path
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib

PACKAGES = {"saga2d": ("*.py",), "sagaforge": ("*.py",), "tribes": ("*.py",),
            "warband": ("*.py", "*.wav"), "eador": ("*.py",)}
DISTRIBUTIONS = ("saga2d", "sagaforge", "tribes", "warband", "shardbound")
DEPLOY_FILES = ("install.sh", "prepare_release.sh", "check_release.py", "smoke.py", "backup.py", "server.py", "runtime.py", "stage_release.py", "uv-bootstrap.txt",
                "saga2d-online.service", "saga2d-backup.service", "saga2d-backup.timer", "Caddyfile")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checkout(path, expected=None):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()
    require(Path(git("rev-parse", "--show-toplevel")).resolve() == path, f"Expected repository root: {path}")
    require(not git("status", "--porcelain"), f"Server packaging requires a clean source checkout: {path}")
    commit = git("rev-parse", "HEAD")
    require(expected is None or commit == expected, f"Checkout differs from its server source pin: {path}")
    return commit


def locked_runtime(root):
    lock = tomllib.loads((root / "uv.lock").read_text())
    packages, seen, pending = {}, set(), ["saga-online"]
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        matches = [item for item in lock["package"] if item["name"] == name]
        require(len(matches) == 1, f"Expected one locked runtime entry: {name}")
        item = matches[0]
        pending.extend(dep["name"] for dep in item.get("dependencies", []))
        if "registry" in item["source"]:
            require(item["source"] == {"registry": "https://pypi.org/simple"}, f"Expected a PyPI runtime dependency: {name}")
            require(importlib.metadata.version(name) == item["version"], f"Installed dependency differs from lock: {name}")
            packages[name] = item["version"]
        else:
            require(name in {"saga-online", *DISTRIBUTIONS}, f"Unexpected source dependency: {name}")
    return packages


def tracked_package(root: Path, commit: str, package: str, required: dict[str, str]) -> dict[str, bytes]:
    """Read a package's allowlisted source and declared runtime inputs from its pinned Git tree."""
    tracked = subprocess.check_output(["git", "-C", str(root), "ls-tree", "-r", "--name-only",
                                       commit, "--", package], text=True).splitlines()
    selected = [name for name in tracked if name in required
                or any(fnmatch.fnmatch(name, pattern) for pattern in PACKAGES[package])]
    require(selected, f"No tracked package source: {package}")
    payload = subprocess.check_output(["git", "-C", str(root), "archive", "--format=tar", commit, "--", *selected])
    files = {}
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        for item in archive:
            if item.isdir():
                continue
            require(item.isfile(), f"Linked or special package source: {item.name}")
            files[item.name] = archive.extractfile(item).read()
    return files


def server_files(root: Path) -> dict[str, bytes]:
    """Bind allowlisted source bytes to clean game commits and one exact locked runtime."""
    root = root.resolve()
    pins = json.loads((root / ".github/server-pins.json").read_text())
    require(set(pins) == {"python", "uv", "warband_run_id", "warband_run_number", "sources"}
            and set(pins["sources"]) == {"sagaforge", "tribes", "warband", "shardbound"}
            and all(re.fullmatch(r"[0-9a-f]{40}", commit) for commit in pins["sources"].values()), "Invalid server source pins")
    require(platform.python_version() == pins["python"], "Server packaging requires its pinned Python")
    uv_version = subprocess.check_output(["uv", "--version"], text=True).split()[1]
    require(uv_version == pins["uv"], "Server packaging requires its pinned uv")
    sources = {"saga-online": checkout(root)}
    for name, commit in pins["sources"].items():
        sources[name] = checkout(root.parent / name, commit)
    # --locked checks current project/path metadata as well as the existing lock;
    # --frozen would silently permit the previous games' engine requirements.
    requirements = subprocess.run(["uv", "export", "--locked", "--no-dev", "--no-emit-project", "--no-header",
                                   *(f"--no-emit-package={name}" for name in DISTRIBUTIONS)],
                                  cwd=root, check=True, capture_output=True).stdout
    packages = locked_runtime(root)
    warband = root.parent / "warband"
    with tempfile.TemporaryDirectory(prefix="server-identity-") as temporary:
        path = Path(temporary) / "identity.json"
        # The run number gives the identity its release version; the pinned pair is checked
        # against the actual run where the network is allowed (CI's provenance step, promotion).
        subprocess.run([sys.executable, str(warband / "tools/ci_release.py"), "prepare",
                        "--run-id", str(pins["warband_run_id"]), "--run-number", str(pins["warband_run_number"]),
                        "--output", str(path)], cwd=warband, check=True, capture_output=True)
        identity = json.loads(path.read_bytes())
    require(identity["source_commit"] == sources["warband"] and identity["python"] == pins["python"] and identity["uv"] == pins["uv"]
            and identity["sagaforge_commit"] == sources["sagaforge"] and identity["run_id"] == pins["warband_run_id"]
            and identity["run_number"] == pins["warband_run_number"], "Warband identity differs from the server pins")
    contract = identity["compatibility"]
    require(all(packages[name] == version for name, version in contract["packages"].items()),
            "Server lock differs from Warband's native compatibility runtime")
    files = {}
    for package in PACKAGES:
        if package != "saga2d":
            repository = "shardbound" if package == "eador" else package
            checkout_root = root.parent / repository
            files.update(tracked_package(checkout_root, sources[repository], package, contract["files"]))
        else:
            folder = Path(importlib.util.find_spec(package).origin).resolve().parent
            require(not any(path.is_symlink() for path in folder.rglob("*")), f"Linked package source: {folder}")
            for path in sorted(folder.rglob("*.py")):
                files[f"{package}/{path.relative_to(folder).as_posix()}"] = path.read_bytes()
    # Verify the copied engine against the installed wheel's RECORD, including
    # its inventory. A version string alone must not bless edited engine code.
    distribution = importlib.metadata.distribution("saga2d")
    require(distribution.read_text("direct_url.json") is None, "The engine must be an installed PyPI release")
    records = {str(path): path for path in distribution.files if str(path).startswith("saga2d/") and str(path).endswith(".py")}
    require(set(records) == {name for name in files if name.startswith("saga2d/")}, "Installed engine source inventory differs from its wheel")
    for name, record in records.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(files[name]).digest()).decode().rstrip("=")
        require(record.hash is not None and record.hash.mode == "sha256" and record.hash.value == digest,
                f"Engine source differs from its installed wheel: {name}")
    require(all(hashlib.sha256(files[name]).hexdigest() == digest for name, digest in contract["files"].items()),
            "Packaged authoritative source differs from Warband's native contract")
    for name in DEPLOY_FILES:
        files[f"deploy/{name}"] = subprocess.check_output(["git", "-C", str(root), "show", f"{sources['saga-online']}:deploy/{name}"])
    files["deploy/requirements.txt"] = requirements
    inputs = {"schema_version": 1, "sources": sources, "python": pins["python"], "uv": pins["uv"], "packages": packages,
              "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}, "warband_compatibility": contract}
    files["deploy/server-inputs.json"] = (json.dumps(inputs, sort_keys=True, indent=2) + "\n").encode()
    # The archive must name the same clean inputs that were read at the start.
    for name, commit in sources.items():
        checkout(root if name == "saga-online" else root.parent / name, commit)
    return files
