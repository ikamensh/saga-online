"""Run the anonymously downloaded Warband client against the accepted public server."""
from __future__ import annotations

import argparse
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


def public_json(path: str) -> dict:
    with urllib.request.urlopen(SITE + path, timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    catalog = public_json("/releases.json")
    assert catalog == json.loads((ROOT / "releases/catalog.json").read_text()), "Public catalog differs from this checkout"
    game = catalog["games"]["warband"]
    assert game["version"] == args.version, "Public Warband version differs from the requested version"
    baseline = json.loads((ROOT / "releases/server-baseline.json").read_text())
    assert public_json("/server-compatibility.json") == baseline, "Live runtime differs from the accepted baseline"
    assert catalog["server"]["endpoint"] == baseline["endpoint"] == SITE.replace("https:", "wss:") + "/play"
    target = {("Windows", "amd64"): ("windows", "x64", "portable-zip"),
              ("Darwin", "arm64"): ("macos", "arm64", "app-zip")}[platform.system(), platform.machine().lower()]
    package, = [item for item in game["packages"] if (item["os"], item["arch"], item["kind"]) == target]
    assert Path(package["file"]).name == package["file"]
    assert package["url"] == f"https://github.com/ikamensh/warband/releases/download/v{args.version}/{package['file']}"
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="public-warband-") as temporary:
        root = Path(temporary)
        archive = root / package["file"]
        with urllib.request.urlopen(package["url"], timeout=60) as response, archive.open("wb") as destination:
            shutil.copyfileobj(response, destination)
        assert archive.stat().st_size == package["bytes"] and sha256(archive) == package["sha256"], "Public archive bytes differ"
        if target[0] == "windows":
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(root / "extracted")
            executable = root / "extracted/Warband/Warband.exe"
        else:
            subprocess.run(["ditto", "-x", "-k", str(archive), str(root / "extracted")], check=True)
            app = root / "extracted/Warband.app"
            subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
            executable = app / "Contents/MacOS/Warband"
        receipt = executable_smoke(executable, baseline["endpoint"], output / "client.json", game)
        required = {"create_join", "authoritative_movement", "foreign_order_rejected", "private_seat_rejoin",
                    "global_production", "automatic_plan_builder", "cancel_plans", "assembly_point"}
        assert receipt["frozen"] is True and receipt["bundled_fonts"] is True
        assert all(receipt["online"][name] is True for name in required), "Incomplete public online acceptance"
    assert public_json("/server-compatibility.json") == baseline, "Live runtime changed during acceptance"
    assert public_json("/releases.json") == catalog, "Public catalog changed during acceptance"
    result = {"passed": True, "version": args.version, "source_commit": game["source_commit"],
              "package": package, "server_release": baseline["deployment_release"], "client": receipt}
    (output / "acceptance.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"{args.version}: public {target[0]} download and packaged online checks passed")


if __name__ == "__main__":
    main()
