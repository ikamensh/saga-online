"""The automatic server rollout's steps (.github/workflows/server-rollout.yml).

    resolve   pick the newest published Warband release and decide: deploy it, or the live server already serves it
    host      talk to the restricted server-CI account over pinned SSH: status, backup, install, rollback
    expected  the attestation a prepared archive must serve
    accept    the public checks after activation; a failure makes the workflow roll back
    record    write the machine record of the rollout and, when accepted, the new server baseline

Each subcommand prints JSON. Cloud, DNS and operator credentials are never used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

RELEASE = re.compile(r"[0-9a-f]{64}")
TAG = re.compile(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
OPERATIONS = ("status", "backup", "install", "rollback")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


# --- resolve -----------------------------------------------------------------

def newest_release(api):
    """The newest published Warband release; Warband publishes only verified main builds."""
    for release in api.get("/releases?per_page=20"):
        if not release["draft"] and TAG.fullmatch(release["tag_name"]):
            return release
    raise ValueError("Warband has no published release")


def served_attestation(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Cache-Control": "no-cache"}), timeout=30) as response:
        return json.load(response)


def resolve(api, pins, baseline, catalog, served, *, force=False):
    """Decide what the rollout does and the server pins it deploys with.

    The live server needs nothing when the newest release's contract is the
    recorded baseline's and the server serves exactly that baseline; that is the
    promotion's own test. Anything else deploys, so the two converge.
    """
    from warband_promotion import verify_source
    release = newest_release(api)
    assets = {item["name"]: item for item in api.get(f"/releases/{release['id']}/assets")}
    manifest_item = assets["release.json"]
    require(manifest_item["state"] == "uploaded" and manifest_item["digest"].startswith("sha256:"), "Unverifiable release manifest")
    manifest_sha256 = manifest_item["digest"].removeprefix("sha256:")
    with tempfile.TemporaryDirectory(prefix="rollout-manifest-") as temporary:
        path = Path(temporary) / "release.json"
        api.download(release["tag_name"], {"file": "release.json", "bytes": manifest_item["size"], "sha256": manifest_sha256}, path)
        identity = json.loads(path.read_bytes())["identity"]
    verify_source(api, release, identity, identity["run_id"])
    contract = identity["compatibility"]
    candidate = {"release_id": release["id"], "tag": release["tag_name"], "version": identity["version"],
                 "build_run_id": identity["run_id"], "run_number": identity["run_number"], "manifest_sha256": manifest_sha256,
                 "source_commit": identity["source_commit"], "contract_sha256": contract["sha256"]}
    live = {"deployment_release": baseline["deployment_release"], "source_commit": baseline["warband"]["source_commit"],
            "contract_sha256": baseline["warband"]["compatibility"]["sha256"]}
    plan = {"schema_version": 1, "force": force, "candidate": candidate, "baseline": live, "served_matches_baseline": served == baseline}
    if (identity["source_commit"] == baseline["warband"]["source_commit"]
            and contract == baseline["warband"]["compatibility"] and served == baseline and not force):
        # The downloadable build is already running; only its catalog promotion remains.
        return {**plan, "action": "current", "pins": pins,
                "promote": catalog["games"]["warband"]["source_commit"] != identity["source_commit"]}
    comparison = api.get(f"/compare/{pins['sources']['warband']}...{identity['source_commit']}")
    require(comparison["status"] in ("ahead", "identical"),
            f"Candidate {identity['source_commit']} is {comparison['status']} of the pinned Warband; refusing to move back")
    require(identity["python"] == pins["python"] and identity["uv"] == pins["uv"],
            "The candidate needs another Python or uv on the server; that runtime upgrade is a manual rollout")
    moved = {**pins, "warband_run_id": identity["run_id"], "warband_run_number": identity["run_number"],
             "sources": {**pins["sources"], "warband": identity["source_commit"], "sagaforge": identity["sagaforge_commit"]}}
    return {**plan, "action": "deploy", "pins": moved, "promote": True}


def resolve_command(args):
    from warband_promotion import GitHub
    pins = json.loads(args.pins.read_bytes())
    plan = resolve(GitHub(args.api_url), pins, json.loads(args.baseline.read_bytes()),
                   json.loads(args.catalog.read_bytes()), served_attestation(args.attestation), force=args.force)
    if plan["pins"] != pins:
        args.pins.write_text(json.dumps(plan["pins"], indent=2) + "\n")
    return plan


# --- host --------------------------------------------------------------------

def host_call(args, operation, payload=b""):
    """Run one forced operation on the server-CI account with a pinned host key and no ambient SSH state."""
    require(operation in OPERATIONS, "Unknown server-CI operation")
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", args.host) is not None and 1 <= args.port <= 65535, "Invalid host")
    for path in (args.identity, args.known_hosts):
        require(path.is_file() and path.stat().st_size > 0, f"Missing identity or pinned host-key file: {path}")
    command = ["ssh", "-F", "/dev/null", "-T", "-i", str(args.identity.resolve()), "-p", str(args.port),
               "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none",
               "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={args.known_hosts.resolve()}",
               "-o", "GlobalKnownHostsFile=/dev/null", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=30",
               "-o", "ForwardAgent=no", "-o", "ClearAllForwardings=yes", f"saga2d-server-ci@{args.host}", operation]
    result = subprocess.run(command, input=payload, capture_output=True, timeout=1260)
    sys.stderr.write(result.stderr.decode(errors="replace"))
    require(result.returncode == 0, f"Server {operation} failed (exit {result.returncode})")
    return result.stdout


def request(**fields):
    return json.dumps({"schema_version": 1, **fields}).encode() + b"\n"


def host_command(args):
    if args.operation == "status":
        return json.loads(host_call(args, "status"))
    if args.operation == "backup":
        output = host_call(args, "backup")
        line, data = output.split(b"\n", 1)
        meta = json.loads(line)
        require(re.fullmatch(r"rooms-\d{8}T\d{6}Z\.sqlite3", meta["name"]) is not None, "Unexpected backup name")
        require(len(data) == meta["bytes"] and hashlib.sha256(data).hexdigest() == meta["sha256"], "Backup bytes differ from their header")
        args.output.mkdir(parents=True, exist_ok=True)
        path = args.output / meta["name"]
        with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as file:
            file.write(data)
        return {**meta, "path": str(path)}
    if args.operation == "install":
        archive = args.archive.read_bytes()
        release = hashlib.sha256(archive).hexdigest()
        require(args.archive.name == f"{release}.tar.gz", "Archive name differs from its digest")
        result = json.loads(host_call(args, "install", request(release=release, bytes=len(archive),
                                                               expected_current=args.expected_current) + archive))
        require(result["current"] == release == result["activated"], "The host did not activate the archive")
        return result
    result = json.loads(host_call(args, "rollback", request(**{"from": args.rollback_from})))
    require(result["current"] != args.rollback_from and result["previous"] == args.rollback_from,
            "The host did not return to its previous release")
    return result


# --- expected / accept -------------------------------------------------------

def expected_baseline(archive: Path, endpoint: str) -> dict:
    """What the running archive attests: the same document its preparation verified (check_release.py)."""
    release = hashlib.sha256(archive.read_bytes()).hexdigest()
    with tarfile.open(archive) as bundle:
        inputs = json.load(bundle.extractfile("deploy/server-inputs.json"))
    return {"schema_version": 1, "deployment_release": release, "endpoint": endpoint, "protocol": 1,
            "warband": {"source_commit": inputs["sources"]["warband"], "compatibility": inputs["warband_compatibility"]}}


def http_origin(endpoint):
    """The HTTP origin of a public wss://HOST/play endpoint, or of a loopback ws:// one in tests."""
    match = re.fullmatch(r"(wss)://([a-z0-9.-]+)/play|(ws)://(127\.0\.0\.1:\d+)/play", endpoint)
    require(match is not None, "Expected wss://HOST/play (or a loopback ws:// endpoint)")
    return f"https://{match[2]}" if match[1] else f"http://{match[4]}"


def deflate(endpoint):
    from websockets.sync.client import connect
    with connect(endpoint, proxy=None) as socket:
        extensions = socket.response.headers.get("Sec-WebSocket-Extensions", "")
    require("permessage-deflate" in extensions, f"The proxy did not negotiate permessage-deflate: {extensions!r}")
    return extensions


def accept(endpoint, expected, backup, *, fail=False, report=None):
    """Public checks in order; stops at the first failure, which the caller answers with a rollback."""
    from deploy.smoke import smoke
    from tools.rehearse_retained import rehearse
    from tools.verify_room_seats import verify as room_seats
    origin = http_origin(endpoint)
    report = {} if report is None else report
    report.update(endpoint=endpoint, passed=False, checks={})

    def check(name, action):
        report["checks"][name] = {"passed": False}
        detail = action()
        report["checks"][name] = {"passed": True, **({"detail": detail} if detail is not None else {})}

    def health():
        with urllib.request.urlopen(origin + "/healthz", timeout=10) as response:
            require(response.status == 200 and response.read() == b"ok\n", "Unexpected public health response")

    def attestation():
        url = origin + "/server-compatibility.json?deployment=" + expected["deployment_release"]
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Cache-Control": "no-cache"}), timeout=10) as response:
            served = json.load(response)
        require(served == expected, "The served attestation differs from the activated candidate")
        return {"deployment_release": served["deployment_release"], "contract_sha256": served["warband"]["compatibility"]["sha256"]}

    def retained():
        # Every Warband seat already resumed on a private copy with this code; live, each
        # resumed room holds a slot for the room TTL, so the newest one stands for all.
        seats = rehearse(backup, endpoint=endpoint, per_game=True, game="warband-v2")
        require(seats["failed"] == 0, f"{seats['failed']} retained seats did not resume on the live server")
        return {key: seats[key] for key in ("rooms", "retained", "failed", "resumed_rooms")} | {"seats": len(seats["seats"])}

    check("health", health)
    check("attestation", attestation)
    check("smoke", lambda: [record["game"] for record in smoke(endpoint, games=("warband-v2",))])
    check("permessage_deflate", lambda: deflate(endpoint))
    check("retained_seats", retained)
    check("three_seat_room", lambda: room_seats(endpoint))
    if fail:
        check("deliberate_failure", lambda: require(False, "Deliberate failure requested to exercise the automatic rollback"))
    report["passed"] = True
    return report


def accept_command(args):
    expected = json.loads(args.expected.read_bytes())
    report = {}
    try:
        return accept(expected["endpoint"], expected, args.backup, fail=args.fail, report=report)
    finally:
        args.report.write_bytes(encoded(report))


# --- record ------------------------------------------------------------------

def outcome(fragments):
    deploy = fragments.get("deploy", {})
    natives = [value for key, value in fragments.items() if key.startswith("native-")]
    if "install_failed" in deploy:
        return "activation_failed_installer_restored_previous"
    if "install" not in deploy:
        return "stopped_before_activation"
    if "rollback" in fragments or "rollback" in deploy:
        return "rolled_back"
    if deploy.get("acceptance", {}).get("passed") and natives and all(item.get("passed") for item in natives):
        return "accepted"
    return "failed_without_rollback"


def record(plan, fragments, run_url, now=None):
    now = now or datetime.now(timezone.utc)
    result = outcome(fragments)
    deploy = fragments.get("deploy", {})
    entry = {"schema_version": 1, "run": run_url, "finished": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "outcome": result,
             "force": plan["force"], "candidate": plan["candidate"], "previous": plan["baseline"],
             "pins": plan["pins"], **{key: value for key, value in deploy.items() if key != "expected"},
             "native": {key.removeprefix("native-"): value for key, value in fragments.items() if key.startswith("native-")}}
    if "rollback" in fragments:
        entry["rollback"] = fragments["rollback"]
    if result == "accepted":
        entry["deployment_release"] = deploy["expected"]["deployment_release"]
    name = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{plan['candidate']['source_commit'][:8]}.json"
    return name, entry, deploy["expected"] if result == "accepted" else None


def record_command(args):
    plan = json.loads(args.plan.read_bytes())
    fragments = {path.stem: json.loads(path.read_bytes()) for path in sorted(args.fragments.glob("*.json"))}
    name, entry, baseline = record(plan, fragments, args.run_url)
    args.records.mkdir(parents=True, exist_ok=True)
    (args.records / name).write_bytes(encoded(entry))
    if baseline is not None:
        args.baseline.write_bytes(encoded(baseline))
    return {"record": str(args.records / name), "outcome": entry["outcome"], "baseline_updated": baseline is not None}


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    resolve_parser = commands.add_parser("resolve")
    resolve_parser.add_argument("--pins", type=Path, default=ROOT / ".github/server-pins.json")
    resolve_parser.add_argument("--baseline", type=Path, default=ROOT / "releases/server-baseline.json")
    resolve_parser.add_argument("--catalog", type=Path, default=ROOT / "releases/catalog.json")
    resolve_parser.add_argument("--api-url", default="https://api.github.com")
    resolve_parser.add_argument("--attestation", default="https://games.tachyon-ai.eu/server-compatibility.json")
    resolve_parser.add_argument("--force", action="store_true", help="Deploy even when the live server serves the candidate's contract")
    host = commands.add_parser("host")
    host.add_argument("--host", required=True)
    host.add_argument("--port", type=int, default=22)
    host.add_argument("--identity", type=Path, required=True)
    host.add_argument("--known-hosts", type=Path, required=True)
    operations = host.add_subparsers(dest="operation", required=True)
    operations.add_parser("status")
    operations.add_parser("backup").add_argument("--output", type=Path, required=True)
    install = operations.add_parser("install")
    install.add_argument("--archive", type=Path, required=True)
    install.add_argument("--expected-current", required=True, help="Release the host must be running now, or none")
    operations.add_parser("rollback").add_argument("--from", dest="rollback_from", required=True)
    expected = commands.add_parser("expected")
    expected.add_argument("--archive", type=Path, required=True)
    expected.add_argument("--endpoint", default="wss://games.tachyon-ai.eu/play")
    accept_parser = commands.add_parser("accept")
    accept_parser.add_argument("--expected", type=Path, required=True)
    accept_parser.add_argument("--backup", type=Path, required=True, help="Backup taken before activation: its seats must resume live")
    accept_parser.add_argument("--report", type=Path, required=True)
    accept_parser.add_argument("--fail", action="store_true", help="Fail after the checks, to exercise the automatic rollback")
    record_parser = commands.add_parser("record")
    record_parser.add_argument("--plan", type=Path, required=True)
    record_parser.add_argument("--fragments", type=Path, required=True)
    record_parser.add_argument("--run-url", required=True)
    record_parser.add_argument("--records", type=Path, default=ROOT / "releases/rollouts")
    record_parser.add_argument("--baseline", type=Path, default=ROOT / "releases/server-baseline.json")
    args = parser.parse_args(argv)
    if args.command == "host" and args.operation == "install":
        require(args.expected_current == "none" or RELEASE.fullmatch(args.expected_current), "Invalid --expected-current")
    if args.command == "host" and args.operation == "rollback":
        require(RELEASE.fullmatch(args.rollback_from) is not None, "Invalid --from")
    return args


def main(argv=None):
    args = arguments(argv)
    if args.command == "resolve":
        result = resolve_command(args)
    elif args.command == "host":
        result = host_command(args)
    elif args.command == "expected":
        result = expected_baseline(args.archive, args.endpoint)
    elif args.command == "accept":
        result = accept_command(args)
    else:
        result = record_command(args)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
