"""Verify a packaged server's actual inputs before its game registries are imported."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
from urllib.parse import urlsplit

SOURCE_ROOTS = ("saga2d", "sagaforge", "tribes", "warband", "eador", "deploy")
REGISTRIES = ("tribes.multiplayer:ONLINE", "warband.authority:ONLINE", "eador.multiplayer:ONLINE")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inventory(root):
    require({path.name for path in root.iterdir()} <= set(SOURCE_ROOTS) | {".venv", ".ready"},
            "Unrecorded files at the package root")
    files = {}
    for name in SOURCE_ROOTS:
        directory = root / name
        require(directory.is_dir() and not directory.is_symlink(), f"Missing or linked source directory: {name}")
        for path in sorted(directory.rglob("*")):
            require(not path.is_symlink(), f"Linked package input: {path}")
            if path.is_dir():
                continue
            require(path.is_file(), f"Unsupported package input: {path}")
            relative = path.relative_to(root).as_posix()
            if relative != "deploy/server-inputs.json":
                files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def attestation(root: Path, release_id: str, endpoint: str) -> dict:
    """Return the public baseline only after every recorded input agrees with this process."""
    require(re.fullmatch(r"[0-9a-f]{64}", release_id), "Expected the verified archive's SHA-256 release ID")
    url = urlsplit(endpoint)
    require(url.scheme == "wss" and url.hostname and url.path == "/play" and not url.query and not url.fragment
            and url.username is None and url.password is None, "Expected a public wss /play endpoint")
    inputs = json.loads((root / "deploy/server-inputs.json").read_bytes())
    require(set(inputs) == {"schema_version", "sources", "python", "packages", "files", "warband_compatibility"}
            and inputs["schema_version"] == 1, "Unsupported server input manifest")
    require(set(inputs["sources"]) == {"saga-online", "sagaforge", "tribes", "warband", "shardbound"}
            and all(re.fullmatch(r"[0-9a-f]{40}", commit) for commit in inputs["sources"].values()), "Invalid server source commits")
    files = inventory(root)
    require(files == inputs["files"], "Packaged source inventory differs from its recorded inputs")
    require(platform.python_version() == inputs["python"], "Server Python differs from its recorded runtime")
    # Saga2D ships as verified source; the remaining distributions are installed
    # from hashed requirements in this release's own environment.
    import saga2d
    require(Path(saga2d.__file__).resolve() == root / "saga2d/__init__.py", "Server imported Saga2D outside its verified release")
    packages = {name: saga2d.__version__ if name == "saga2d" else importlib.metadata.version(name)
                for name in inputs["packages"]}
    require(packages == inputs["packages"], "Server dependencies differ from the recorded runtime")
    contract = inputs["warband_compatibility"]
    require(set(contract) == {"schema_version", "registry", "python", "packages", "files", "sha256"}
            and contract["schema_version"] == 1 and contract["registry"] == "warband.authority:ONLINE",
            "Unsupported Warband compatibility contract")
    body = {key: value for key, value in contract.items() if key != "sha256"}
    require(hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest() == contract["sha256"],
            "Invalid Warband compatibility digest")
    require(contract["python"] == platform.python_version()
            and all(packages[name] == version for name, version in contract["packages"].items())
            and contract["files"] and all(name.startswith("warband/") and files[name] == digest
                                            for name, digest in contract["files"].items()),
            "Warband compatibility contract differs from the actual server inputs")
    from saga2d.server import PROTOCOL
    return {"schema_version": 1, "deployment_release": release_id, "endpoint": endpoint, "protocol": PROTOCOL,
            "warband": {"source_commit": inputs["sources"]["warband"], "compatibility": contract}}
