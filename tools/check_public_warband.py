"""Run a downloaded Warband client against the public server.

    check_public_warband.py --version 0.2.67 --output DIR
        the anonymously downloaded public catalog release, against the accepted baseline
    check_public_warband.py --candidate-tag v0.2.70 --manifest-sha256 SHA --expected-baseline FILE --output DIR
        a rollout's candidate, from its immutable GitHub release, against the server just activated for it
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

from saga2d.packaging.verify import executable_smoke, sha256

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://games.tachyon-ai.eu"
DOWNLOADS = "https://github.com/ikamensh/warband/releases/download"
REQUIRED = {"create_join", "authoritative_movement", "foreign_order_rejected", "private_seat_rejoin",
            "global_production", "automatic_plan_builder", "cancel_plans", "assembly_point"}


def public_json(path: str) -> dict:
    with urllib.request.urlopen(SITE + path, timeout=30) as response:
        return json.load(response)


def target():
    return {("Windows", "amd64"): ("windows", "x64", "portable-zip"),
            ("Darwin", "arm64"): ("macos", "arm64", "app-zip")}[platform.system(), platform.machine().lower()]


def exercise(package: dict, url: str, game: dict, endpoint: str, output: Path, *, native: bool = False) -> dict:
    """Download exact bytes, unpack the frozen client and run its online acceptance against ``endpoint``.

    ``native`` also plays the rendered journey (a real window, input and frames in ``output``); on
    macOS only, since Windows runners draw through a separately installed Mesa.
    """
    assert Path(package["file"]).name == package["file"]
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="public-warband-") as temporary:
        root = Path(temporary)
        archive = root / package["file"]
        with urllib.request.urlopen(url, timeout=60) as response, archive.open("wb") as destination:
            shutil.copyfileobj(response, destination)
        assert archive.stat().st_size == package["bytes"] and sha256(archive) == package["sha256"], "Downloaded archive bytes differ"
        if target()[0] == "windows":
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(root / "extracted")
            executable = root / "extracted/Warband/Warband.exe"
        else:
            subprocess.run(["ditto", "-x", "-k", str(archive), str(root / "extracted")], check=True)
            app = root / "extracted/Warband.app"
            subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
            executable = app / "Contents/MacOS/Warband"
        receipt = executable_smoke(executable, endpoint, output / "client.json", game)
        if native:
            receipt["native"] = executable_smoke(executable, endpoint, output / "native.json", game, native=True)
    assert receipt["frozen"] is True and receipt["bundled_fonts"] is True
    assert all(receipt["online"][name] is True for name in REQUIRED), "Incomplete public online acceptance"
    return receipt


def public(args):
    catalog = public_json("/releases.json")
    assert catalog == json.loads((ROOT / "releases/catalog.json").read_text()), "Public catalog differs from this checkout"
    game = catalog["games"]["warband"]
    assert game["version"] == args.version, "Public Warband version differs from the requested version"
    baseline = json.loads((ROOT / "releases/server-baseline.json").read_text())
    assert public_json("/server-compatibility.json") == baseline, "Live runtime differs from the accepted baseline"
    assert game["source_commit"] == baseline["warband"]["source_commit"], "The download and server run different Warband builds"
    assert catalog["server"]["endpoint"] == baseline["endpoint"] == SITE.replace("https:", "wss:") + "/play"
    package, = [item for item in game["packages"] if (item["os"], item["arch"], item["kind"]) == target()]
    assert package["url"] == f"{DOWNLOADS}/v{args.version}/{package['file']}"
    receipt = exercise(package, package["url"], game, baseline["endpoint"], args.output.resolve())
    assert public_json("/server-compatibility.json") == baseline, "Live runtime changed during acceptance"
    assert public_json("/releases.json") == catalog, "Public catalog changed during acceptance"
    print(f"{args.version}: public {target()[0]} download and packaged online checks passed")
    return {"passed": True, "version": args.version, "source_commit": game["source_commit"],
            "package": package, "server_release": baseline["deployment_release"], "client": receipt}


def candidate(args):
    """The rollout's own client, before its promotion: the new rules on both ends of the wire."""
    expected = json.loads(args.expected_baseline.read_bytes())
    with urllib.request.urlopen(f"{DOWNLOADS}/{args.candidate_tag}/release.json", timeout=60) as response:
        manifest_bytes = response.read()
    assert hashlib.sha256(manifest_bytes).hexdigest() == args.manifest_sha256, "Candidate manifest differs from the resolved one"
    manifest = json.loads(manifest_bytes)
    identity = manifest["identity"]
    assert identity["tag"] == args.candidate_tag and identity["source_commit"] == expected["warband"]["source_commit"]
    assert identity["compatibility"] == expected["warband"]["compatibility"], "Candidate client and server contracts differ"
    platform_target = "windows-x64" if target()[0] == "windows" else "darwin-arm64"
    suffix = "-portable.zip" if target()[0] == "windows" else "-app.zip"
    package, = [item for item in manifest["targets"][platform_target]["artifacts"] if item["file"].endswith(suffix)]
    assert public_json("/server-compatibility.json") == expected, "The public server does not serve the candidate"
    receipt = exercise(package, f"{DOWNLOADS}/{args.candidate_tag}/{package['file']}",
                       {"source_commit": identity["source_commit"], "version": identity["version"]},
                       expected["endpoint"], args.output.resolve(), native=target()[0] == "macos")
    assert public_json("/server-compatibility.json") == expected, "Live runtime changed during acceptance"
    print(f"{identity['version']}: candidate {target()[0]} client passed its online checks against the activated server")
    return {"passed": True, "version": identity["version"], "source_commit": identity["source_commit"],
            "package": package["file"], "server_release": expected["deployment_release"],
            "online": {name: receipt["online"][name] for name in sorted(REQUIRED)},
            **({"native": {key: value for key, value in receipt["native"].items() if isinstance(value, bool)}}
               if "native" in receipt else {})}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", help="Exact Warband version in the public catalog")
    parser.add_argument("--candidate-tag", help="Tag of a rollout candidate's immutable release")
    parser.add_argument("--manifest-sha256", help="SHA-256 of the candidate's release.json")
    parser.add_argument("--expected-baseline", type=Path, help="Attestation the activated server must serve")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (args.version is None) == (args.candidate_tag is None):
        parser.error("Pass exactly one of --version and --candidate-tag")
    if args.candidate_tag is not None and (args.manifest_sha256 is None or args.expected_baseline is None):
        parser.error("--candidate-tag needs --manifest-sha256 and --expected-baseline")
    result = public(args) if args.version else candidate(args)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "acceptance.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
