"""Inspect or publish the static site through the dedicated, host-key-pinned CI SSH account.

The server installs the trusted transaction separately. This client sends only
archive bytes and ordering preconditions; it cannot select a remote path or
command. Cloud and operator credentials are not used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("status")
    publish = commands.add_parser("publish")
    publish.add_argument("--archive", type=Path, required=True)
    publish.add_argument("--generation", type=int, required=True)
    publish.add_argument("--expected", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", args.host) or not 1 <= args.port <= 65535:
        parser.error("Expected a hostname/IPv4 address and a valid SSH port")
    for path in (args.identity, args.known_hosts):
        if not path.is_file() or not path.stat().st_size:
            parser.error(f"Missing identity or pinned host-key file: {path}")
    payload = b""
    if args.operation == "publish":
        if args.generation <= 0 or not re.fullmatch(r"none|[a-f0-9]{64}", args.expected):
            parser.error("Expected a positive generation and a current release SHA-256 (or none)")
        with args.archive.open("rb") as source:
            archive = source.read(64 * 1024 * 1024 + 1)
        if not 0 < len(archive) <= 64 * 1024 * 1024:
            parser.error("Site archive must be nonempty and at most 64 MiB")
        header = {"schema_version": 1, "release": hashlib.sha256(archive).hexdigest(), "bytes": len(archive),
                  "generation": args.generation, "expected": args.expected}
        payload = json.dumps(header).encode() + b"\n" + archive
    command = ["ssh", "-F", "/dev/null", "-T", "-i", str(args.identity.resolve()), "-p", str(args.port),
               "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none",
               "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={args.known_hosts.resolve()}",
               "-o", "GlobalKnownHostsFile=/dev/null", "-o", "ConnectTimeout=10",
               "-o", "ForwardAgent=no", "-o", "ClearAllForwardings=yes",
               f"saga2d-site-ci@{args.host}", args.operation]
    result = subprocess.run(command, input=payload, capture_output=True, timeout=330)
    if result.returncode:
        raise RuntimeError(f"Site {args.operation} failed: {result.stderr.decode(errors='replace').strip()}")
    print(json.dumps(json.loads(result.stdout), sort_keys=True))


if __name__ == "__main__":
    main()
