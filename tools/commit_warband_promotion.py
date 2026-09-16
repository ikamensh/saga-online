"""Commit a verified desired Warband catalog; site activation remains a separate operation."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess

from release_catalog import validate
from warband_promotion import encoded, require, sha

CATALOG = "releases/catalog.json"
RECEIPT = "releases/warband-promotion.json"


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"Git {args[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def commit(args):
    root = args.repository.resolve()
    require(re.fullmatch(r"[0-9a-f]{40}", args.expected_head), "Expected a full catalog checkout commit")
    require(Path(git(root, "rev-parse", "--show-toplevel")).resolve() == root, "Use the repository root")
    require(git(root, "rev-parse", "HEAD") == args.expected_head, "Catalog checkout changed after preparation")
    require(not git(root, "status", "--porcelain"), "Catalog checkout must be clean")
    if args.push:
        remote = git(root, "ls-remote", "--exit-code", "origin", "refs/heads/main")
        require(remote.split() == [args.expected_head, "refs/heads/main"], "Remote main changed; prepare again from its current head")

    def result(changed):
        head = git(root, "rev-parse", "HEAD")
        if args.push:
            git(root, "push", "origin", f"{head}:refs/heads/main")
        return {"commit": head, "changed": changed, "pushed": args.push}

    candidate_bytes = (args.prepared / "catalog.json").read_bytes()
    receipt_bytes = (args.prepared / "promotion.json").read_bytes()
    candidate = validate(json.loads(candidate_bytes))
    receipt = json.loads(receipt_bytes)
    before_bytes = (root / CATALOG).read_bytes()
    before = validate(json.loads(before_bytes))
    require(receipt["schema_version"] == 1 and receipt["before_catalog_sha256"] == sha(before_bytes)
            and receipt["catalog_sha256"] == sha(candidate_bytes)
            and receipt["game_sha256"] == sha(encoded(candidate["games"]["warband"])), "Prepared catalog digest differs")
    manifest_bytes = (args.prepared / "downloads/release.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    identity = manifest["identity"]
    game = candidate["games"]["warband"]
    require(sha(manifest_bytes) == receipt["manifest_sha256"] and manifest["schema_version"] == 1
            and identity["game"] == "warband" and identity["run_id"] == receipt["build_run_id"]
            and game["version"] == identity["version"]
            and game["source_commit"] == identity["source_commit"] == receipt["source_commit"],
            "Prepared catalog differs from its verified release identity")
    unchanged = deepcopy(candidate)
    unchanged["games"]["warband"] = before["games"]["warband"]
    require(unchanged == before, "A promotion cannot change catalog facts outside Warband")
    if receipt["already_current"] is True:
        require(candidate == before, "An already-current promotion cannot change the catalog")
        previous = json.loads((root / RECEIPT).read_bytes())
        fields = ("schema_version", "source_commit", "build_run_id", "release_id", "manifest_sha256", "game_sha256")
        require(all(previous[key] == receipt[key] for key in fields), "Current release differs from the original receipt")
        return result(False)
    require(receipt["already_current"] is False and candidate != before, "Expected a new desired release")
    (root / CATALOG).write_bytes(candidate_bytes)
    (root / RECEIPT).write_bytes(receipt_bytes)
    git(root, "add", "--", CATALOG, RECEIPT)
    git(root, "commit", "--only", "-m", f"Publish Warband {candidate['games']['warband']['version']} catalog", "--", CATALOG, RECEIPT)
    return result(True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--push", action="store_true", help="Push the desired commit to existing origin/main; never activates the site")
    print(json.dumps(commit(parser.parse_args()), sort_keys=True))
