"""Push a verified desired Warband catalog and publish its prepared site through restricted SSH.

Retries start with freshly verified preparation from current main. An already
committed catalog still reaches the host transaction; an already accepted site
keeps its generation and distinct previous release while rechecking public bytes.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace

from commit_warband_promotion import commit, git
from prepare_warband_site import FIELDS, rendering_inputs
from warband_promotion import encoded, require, sha
from deploy.site_receiver import MAX_ARCHIVE, unpack

ROOT = Path(__file__).resolve().parents[1]


def host(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=350)
    require(result.returncode == 0, result.stderr.strip())
    return json.loads(result.stdout)


def apply(args):
    plan = json.loads((args.site / "site-plan.json").read_bytes())
    require(plan["schema_version"] == 1 and re.fullmatch(r"[a-f0-9]{64}", plan["release"])
            and plan["archive"] == f"site-{plan['release']}.tar.gz",
            "Invalid prepared site archive identity")
    archive = args.site / plan["archive"]
    require(not archive.is_symlink() and 0 < plan["bytes"] <= MAX_ARCHIVE, "Invalid prepared archive size/type")
    with archive.open("rb") as source:
        payload = source.read(MAX_ARCHIVE + 1)
    require(len(payload) == plan["bytes"] and sha(payload) == plan["release"], "Prepared archive bytes changed")
    catalog_bytes = (args.prepared / "catalog.json").read_bytes()
    receipt = json.loads((args.prepared / "promotion.json").read_bytes())
    require(plan["catalog_sha256"] == sha(catalog_bytes) == receipt["catalog_sha256"], "Prepared site catalog differs")
    require(plan["build_date"] == json.loads(catalog_bytes)["games"]["warband"]["released"]
            and plan["rendering_inputs"] == rendering_inputs(), "Rendering inputs differ from the prepared site")
    expected_receipt = {key: receipt[key] for key in FIELDS}
    expected_receipt["site_build"] = {"date": plan["build_date"], "inputs_sha256": sha(encoded(plan["rendering_inputs"]))}
    client = [sys.executable, str(ROOT / "tools/site_publish.py"), "--host", args.host, "--port", str(args.port),
              "--identity", str(args.identity), "--known-hosts", str(args.known_hosts)]
    status = host([*client, "status"])
    require(status["schema_version"] == 1, "Unsupported host publication state")
    accepted = status["accepted"]
    generation = accepted["generation"]
    if accepted["release"] != plan["release"] or generation == 0:
        generation += 1
    header = {"schema_version": 1, "release": plan["release"], "bytes": plan["bytes"],
              "generation": generation, "expected": accepted["release"]}
    # Validate the actual protocol/archive before the Git write and retain its
    # private verified copy through publication, avoiding changed input bytes.
    with tempfile.TemporaryDirectory(prefix="warband-apply-") as temporary:
        folder = Path(temporary)
        _, extracted = unpack(io.BytesIO(json.dumps(header).encode() + b"\n" + payload), folder)
        uploaded_receipt = (extracted / "promotion.json").read_bytes()
        require(uploaded_receipt == encoded(expected_receipt) and sha(uploaded_receipt) == plan["promotion_sha256"]
                and (extracted / "site/releases.json").read_bytes() == catalog_bytes,
                "Upload differs from the verified promotion")
        committed = commit(SimpleNamespace(repository=args.repository, prepared=args.prepared,
                                           expected_head=args.expected_head, push=True))
        remote = git(args.repository, "ls-remote", "--exit-code", "origin", "refs/heads/main")
        require(remote.split() == [committed["commit"], "refs/heads/main"], "Remote catalog changed before site publication; prepare again")
        activation = host([*client, "publish", "--archive", str(folder / "archive.gz"),
                           "--generation", str(generation), "--expected", accepted["release"]])
        require(activation["release"] == plan["release"] and activation["generation"] == generation,
                "Host did not accept the prepared site")
    return {"catalog_commit": committed["commit"], "activation": activation}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    print(json.dumps(apply(parser.parse_args()), sort_keys=True))
