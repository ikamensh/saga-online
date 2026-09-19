"""Promotion protocol fixtures over real HTTP and ZIPs, not native execution evidence."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import tarfile
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools/warband_promotion.py"
REPO = "/repos/ikamensh/warband"


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def archive(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
    return out.getvalue()


def release_data(tmp_path, *, run_id=123, run_number=26):
    contract = {"schema_version": 1, "registry": "warband.online.authority:ONLINE", "python": "3.13.2",
                "packages": {"saga2d": "0.3.2", "pillow": "12.3.0", "pyglet": "2.1.16", "websockets": "17.1"},
                "files": {"warband/online/authority.py": sha(b"A reviewed simulation input fixture")}}
    contract["sha256"] = sha(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode())
    version = f"0.2.{run_number - 25}"
    identity = {"schema_version": 2, "game": "warband", "source_commit": "a" * 40,
                "version": version, "tag": "v" + version, "run_id": run_id,
                "base_version": "0.2.0", "run_number": run_number, "version_run_base": 25,
                "saga2d_version": "0.3.2", "lock_sha256": "c" * 64, "sagaforge_commit": "d" * 40,
                "python": "3.13.2", "uv": "0.12.10", "inno_setup": "6.7.1", "compatibility": contract}
    baseline = {"schema_version": 1, "deployment_release": "e" * 64,
                "endpoint": "wss://games.tachyon-ai.eu/play", "protocol": 1,
                "warband": {"source_commit": "b" * 40, "compatibility": contract}}
    (tmp_path / "baseline.json").write_bytes(encoded(baseline))
    catalog = json.loads((ROOT / "releases/catalog.json").read_text())
    # Keep the transition fixture independent of whichever version is live today.
    old = catalog["games"]["warband"]
    catalog["games"]["warband"] = json.loads(json.dumps(old).replace(old["version"], "0.2.0-preview.122"))
    catalog["games"]["warband"]["source_commit"] = "b" * 40
    (tmp_path / "catalog.json").write_bytes(encoded(catalog))
    assets, targets = {}, {}
    for target in ("windows-x64", "darwin-arm64"):
        windows = target.startswith("windows")
        executable = ("A deliberately non-executable " + target + " fixture").encode()
        prefix = f"Warband-{identity['version']}-{target}"
        portable = prefix + "-portable.zip"
        installed = prefix + ("-setup.exe" if windows else "-app.zip")
        assets[portable] = archive({"Warband/Warband.exe" if windows else "Warband/Warband": executable})
        assets[installed] = b"Installer format fixture" if windows else archive({"Warband.app/Contents/MacOS/Warband": executable})
        artifacts = [{"file": name, "bytes": len(assets[name]), "sha256": sha(assets[name])} for name in (portable, installed)]
        packages = {"saga2d": "0.3.2", "sagaforge": "0.1.0", "Pillow": "12.3.0", "pyglet": "2.1.16",
                    "websockets": "17.1", "numpy": "2.5.3", "pyinstaller": "6.22.2", "pyinstaller-hooks-contrib": "2026.7"}
        inputs = {"identity": identity, "target": target, "packages": packages}
        if windows:
            inputs.update(inno_setup=identity["inno_setup"], inno_setup_sha256="f" * 64)
        manifest = {"product": "Warband", "game": "warband", "source_commit": identity["source_commit"],
                    "version": identity["version"], "working_tree_dirty": False, "python": identity["python"],
                    "platform": "Windows-10" if windows else "macOS-15", "architecture": "AMD64" if windows else "arm64",
                    "packages": {k: v for k, v in packages.items() if k not in ("saga2d", "sagaforge")}, "artifacts": artifacts}
        common = {"passed": True, "source_commit": identity["source_commit"], "version": identity["version"],
                  "executable_sha256": sha(executable)}
        socket = {**common, "frozen": True, "bundled_fonts": True,
                  "online": dict.fromkeys(("create_join", "authoritative_movement", "foreign_order_rejected",
                                            "private_seat_rejoin", "global_production", "automatic_plan_builder",
                                            "cancel_plans", "assembly_point"), True)}
        native = {**common, "backend": "pyglet", "images": ["native.png"], "live_match_menu": True,
                  "native_clipboard_join": True, "native_multiplayer_input": True, "native_settlement_planning": True,
                  "start_after_resize": True}
        report = {"passed": True, "source_commit": identity["source_commit"], "version": identity["version"],
                  "portable": socket, "installed": socket, "native": native}
        report.update({"install_shortcut_uninstall": True} if windows else {"app_native": native})
        log = b"901 passed, 12 skipped\n"
        evidence = {"build-inputs.json": encoded(inputs), "build-manifest.json": encoded(manifest),
                    "verification.json": encoded(report), "regression.log": log,
                    "regression.json": encoded({"identity": identity, "exit_code": 0, "command": ["-m", "pytest", "-q", "--slow"], "log_sha256": sha(log)}),
                    "SHA256SUMS": "".join(f"{x['sha256']}  {x['file']}\n" for x in artifacts).encode(),
                    "verification/native.png": b"\x89PNG\r\n\x1a\nFixture"}
        assets[f"evidence-{target}.zip"] = archive(evidence)
        targets[target] = {"schema_version": 1, "identity": identity, "target": target, "artifacts": artifacts,
                           "evidence": {name: sha(content) for name, content in evidence.items()}}
    manifest = {"schema_version": 1, "identity": identity, "targets": targets,
                "assets": [{"file": name, "bytes": len(data), "sha256": sha(data)} for name, data in assets.items()]}
    assets["release.json"] = encoded(manifest)
    records = [{"id": i + 1, "name": name, "state": "uploaded", "size": len(data), "digest": "sha256:" + sha(data)}
               for i, (name, data) in enumerate(assets.items())]
    data = {"root": tmp_path, "assets": assets, "manifest": manifest, "catalog": catalog, "baseline": baseline,
            "release": {"id": 456, "tag_name": identity["tag"], "target_commitish": identity["source_commit"],
                        "draft": False, "immutable": True, "prerelease": True, "published_at": "2026-09-16T10:00:00Z",
                        "assets": records},
            "run": {"id": run_id, "run_number": run_number, "head_sha": identity["source_commit"], "head_branch": "main", "event": "push",
                    "path": ".github/workflows/native-packages.yml", "workflow_id": 90, "run_attempt": 1,
                    "status": "completed", "conclusion": "success", "repository": {"full_name": "ikamensh/warband"},
                    "head_repository": {"full_name": "ikamensh/warband"}},
            "jobs": [{"name": name, "status": "completed", "conclusion": "success"} for name in
                     ("inputs", "native (windows-2025, windows-x64)", "native (macos-15, darwin-arm64)", "validate")],
            "tag_commit": identity["source_commit"], "compare": {"status": "ahead"}, "requests": []}
    return data


@pytest.fixture
def release(tmp_path):
    return release_data(tmp_path)


@contextmanager
def service(data):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            data["requests"].append(path)
            if "on_request" in data:
                data["on_request"](path)
            routes = {REPO + "/releases/456": data["release"], REPO + "/releases/456/assets": data["release"]["assets"],
                      REPO + f"/actions/runs/{data['run']['id']}": data["run"], REPO + "/actions/workflows/native-packages.yml": {"id": 90},
                      REPO + f"/actions/runs/{data['run']['id']}/attempts/1/jobs": {"jobs": data["jobs"]},
                      REPO + "/git/ref/tags/" + data["release"]["tag_name"]: {"object": {"type": "commit", "sha": data["tag_commit"]}},
                      "/server-compatibility.json": data["baseline"]}
            if path.startswith(REPO + "/compare/"):
                payload = encoded(data["compare"])
            elif path in routes:
                payload = encoded(routes[path])
            elif path.startswith("/ikamensh/warband/releases/download/"):
                payload = data["assets"][path.rsplit("/", 1)[1]]
            else:
                self.send_error(404); return
            self.send_response(200); self.send_header("Content-Length", str(len(payload))); self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown(); server.server_close(); thread.join()


def prepare(data, *, output="prepared", previous=None):
    root = data["root"]
    with service(data) as url:
        return subprocess.run([sys.executable, str(CLI), "--build-run-id", str(data["manifest"]["identity"]["run_id"]), "--release-id", "456",
                               "--manifest-sha256", sha(data["assets"]["release.json"]),
                               "--catalog", str(root / "catalog.json"), "--baseline", str(root / "baseline.json"),
                               "--api-url", url, "--server-attestation", url + "/server-compatibility.json",
                               "--output", str(root / output),
                               *(["--previous-promotion", str(previous)] if previous else [])], capture_output=True, text=True)


def reseal(data):
    """Re-sign format fixtures so rejection must inspect their meaning, not a stale outer digest."""
    data["manifest"]["assets"] = [{"file": name, "bytes": len(content), "sha256": sha(content)}
                                  for name, content in data["assets"].items() if name != "release.json"]
    data["assets"]["release.json"] = encoded(data["manifest"])
    data["release"]["assets"] = [{"id": i + 1, "name": name, "state": "uploaded", "size": len(content), "digest": "sha256:" + sha(content)}
                                 for i, (name, content) in enumerate(data["assets"].items())]


def test_prepare_accepts_exact_downloads_and_preserves_the_rest_of_the_catalog(release):
    """Successful independent preparation creates a reviewable catalog without modifying accepted inputs."""
    before = (release["root"] / "catalog.json").read_bytes()
    result = prepare(release)
    assert result.returncode == 0, result.stderr
    out = release["root"] / "prepared"
    catalog = json.loads((out / "catalog.json").read_text())
    game = catalog["games"]["warband"]
    assert game["version"] == "0.2.1" and game["source_commit"] == "a" * 40
    assert len(game["packages"]) == 4
    for package in game["packages"]:
        assert sha((out / "downloads" / package["file"]).read_bytes()) == package["sha256"]
    catalog["games"]["warband"] = release["catalog"]["games"]["warband"]
    assert catalog == release["catalog"]
    assert (release["root"] / "catalog.json").read_bytes() == before
    receipt = json.loads((out / "promotion.json").read_text())
    assert receipt["release_id"] == 456 and receipt["build_run_id"] == 123
    assert receipt["manifest_sha256"] == sha(release["assets"]["release.json"])
    assert receipt["baseline"] == json.loads((release["root"] / "baseline.json").read_text())


def test_verified_promotion_builds_packages_and_activates_with_the_same_catalog_and_receipt(release):
    """The independent consumer's output must pass the real website/upload/activation path without weakening its digest binding."""
    from tests.test_site_activation import public_site
    root = release["root"]
    result = prepare(release)
    assert result.returncode == 0, result.stderr
    prepared, site = root / "prepared", root / "website"
    subprocess.run([sys.executable, str(ROOT / "tools/build_site.py"), "--catalog", str(prepared / "catalog.json"),
                    "--output", str(site)], check=True, capture_output=True)
    packaged = subprocess.run([sys.executable, str(ROOT / "tools/deploy_online.py"), "package-site", "--name", "saga2d-ci",
                               "--site-dir", str(site), "--output", str(root / "artifacts"),
                               "--promotion-receipt", str(prepared / "promotion.json")], capture_output=True, text=True)
    assert packaged.returncode == 0, packaged.stderr
    package = json.loads(packaged.stdout)
    assert package["mode"] == "warband-promotion"
    uploaded, host = root / "uploaded", root / "host"
    with tarfile.open(package["archive"]) as bundle:
        bundle.extractall(uploaded, filter="data")
    assert (uploaded / "promotion.json").read_bytes() == (prepared / "promotion.json").read_bytes()
    assert not (uploaded / "site/promotion.json").exists()
    with public_site(host, {"baseline": release["baseline"]}) as endpoint:
        result = subprocess.run([sys.executable, str(ROOT / "deploy/activate_site.py"), "--source", str(uploaded / "site"),
                                 "--base", str(host), "--release", package["release"], "--generation", "1", "--expected", "none",
                                 "--public-url", endpoint, "--health-url", endpoint + "/healthz",
                                 "--deployment-lock", str(root / "deployment.lock"), "--mode", "warband-promotion",
                                 "--promotion-receipt", str(uploaded / "promotion.json")], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    assert (host / "current/releases.json").read_bytes() == (prepared / "catalog.json").read_bytes()


@pytest.mark.parametrize("problem", ["draft", "mutable", "wrong_release", "branch", "fork", "failed_run",
                                    "wrong_workflow", "wrong_commit", "failed_job", "missing_job", "changed_tag"])
def test_untrusted_or_incomplete_github_provenance_cannot_prepare_a_catalog(release, problem):
    """A supplied manifest or dispatch cannot overrule GitHub's independent provenance."""
    if problem == "draft":
        release["release"]["draft"] = True
    elif problem == "mutable":
        release["release"]["immutable"] = False
    elif problem == "wrong_release":
        release["release"]["id"] = 789
    elif problem == "branch":
        release["run"]["head_branch"] = "feature"
    elif problem == "fork":
        release["run"]["head_repository"]["full_name"] = "another/warband"
    elif problem == "failed_run":
        release["run"]["conclusion"] = "failure"
    elif problem == "wrong_workflow":
        release["run"]["workflow_id"] = 91
    elif problem == "wrong_commit":
        release["run"]["head_sha"] = "f" * 40
    elif problem == "failed_job":
        release["jobs"][1]["conclusion"] = "skipped"
    elif problem == "missing_job":
        release["jobs"].pop()
    else:
        release["tag_commit"] = "f" * 40
    result = prepare(release)
    assert result.returncode != 0, problem
    assert not (release["root"] / "prepared").exists()


@pytest.mark.parametrize("problem", ["changed_rules", "changed_runtime", "different_live_deployment", "wrong_endpoint", "missing_baseline"])
def test_promotion_requires_the_reviewed_and_live_server_to_match_the_candidate(release, problem):
    """A live service on the right game ID is insufficient when its rules, runtime or deployment differ."""
    path = release["root"] / "baseline.json"
    baseline = json.loads(path.read_text())
    if problem == "changed_rules":
        baseline["warband"]["compatibility"]["files"]["warband/online/authority.py"] = "9" * 64
    elif problem == "changed_runtime":
        baseline["warband"]["compatibility"]["python"] = "3.12.9"
    elif problem == "different_live_deployment":
        release["baseline"] = {**baseline, "deployment_release": "9" * 64}
    elif problem == "wrong_endpoint":
        baseline["endpoint"] = "wss://another.example/play"
    else:
        path.unlink()
    if problem in ("changed_rules", "changed_runtime", "wrong_endpoint"):
        contract = baseline["warband"]["compatibility"]
        contract["sha256"] = sha(json.dumps({k: v for k, v in contract.items() if k != "sha256"}, sort_keys=True, separators=(",", ":")).encode())
        path.write_bytes(encoded(baseline))
        release["baseline"] = baseline
    result = prepare(release)
    assert result.returncode != 0, problem
    assert not (release["root"] / "prepared").exists()


@pytest.mark.parametrize("problem", ["failed_native", "failed_socket", "missing_app", "stale_receipt",
                                    "failed_regression", "fast_tier_only", "dirty_build", "changed_runtime", "changed_executable",
                                    "extra_evidence"])
def test_valid_outer_digests_cannot_hide_invalid_native_evidence(release, problem):
    """The consumer reads native receipts and the archived executable even after all outer hashes are refreshed."""
    target = release["manifest"]["targets"]["darwin-arm64"]
    archive_name = "evidence-darwin-arm64.zip"
    with zipfile.ZipFile(io.BytesIO(release["assets"][archive_name])) as bundle:
        evidence = {name: bundle.read(name) for name in bundle.namelist()}
    report = json.loads(evidence["verification.json"])
    build = json.loads(evidence["build-manifest.json"])
    if problem == "failed_native":
        report["native"]["native_multiplayer_input"] = False
    elif problem == "failed_socket":
        report["installed"]["online"]["authoritative_movement"] = False
    elif problem == "missing_app":
        del report["app_native"]
    elif problem == "stale_receipt":
        report["installed"]["source_commit"] = "f" * 40
    elif problem == "failed_regression":
        regression = json.loads(evidence["regression.json"])
        regression["exit_code"] = 1
        evidence["regression.json"] = encoded(regression)
    elif problem == "fast_tier_only":
        regression = json.loads(evidence["regression.json"])
        regression["command"] = ["-m", "pytest", "-q"]
        evidence["regression.json"] = encoded(regression)
    elif problem == "dirty_build":
        build["working_tree_dirty"] = True
    elif problem == "changed_runtime":
        inputs = json.loads(evidence["build-inputs.json"])
        inputs["packages"]["websockets"] = build["packages"]["websockets"] = "99.0"
        evidence["build-inputs.json"] = encoded(inputs)
    elif problem == "changed_executable":
        artifact = target["artifacts"][1]
        content = archive({"Warband.app/Contents/MacOS/Warband": b"An unverified different executable"})
        release["assets"][artifact["file"]] = content
        artifact.update(bytes=len(content), sha256=sha(content))
        build["artifacts"] = target["artifacts"]
        evidence["SHA256SUMS"] = "".join(f"{x['sha256']}  {x['file']}\n" for x in target["artifacts"]).encode()
    evidence["verification.json"] = encoded(report)
    evidence["build-manifest.json"] = encoded(build)
    target["evidence"] = {name: sha(content) for name, content in evidence.items()}
    if problem == "extra_evidence":
        evidence["unaccounted-file"] = b"Not accepted in the producer manifest"
    release["assets"][archive_name] = archive(evidence)
    reseal(release)
    result = prepare(release)
    assert result.returncode != 0, problem
    assert not (release["root"] / "prepared").exists()


@pytest.mark.parametrize("problem", ["missing_asset", "duplicate_asset", "asset_not_uploaded", "wrong_asset_digest", "corrupt_download"])
def test_public_asset_metadata_and_downloads_must_both_match(release, problem):
    """An immutable release must contain exactly the accepted public bytes, not just an accepting manifest."""
    records = release["release"]["assets"]
    if problem == "missing_asset":
        records.pop(0)
    elif problem == "duplicate_asset":
        records.append(deepcopy(records[0]))
    elif problem == "asset_not_uploaded":
        records[0]["state"] = "starter"
    elif problem == "wrong_asset_digest":
        records[0]["digest"] = "sha256:" + "0" * 64
    else:
        name = records[0]["name"]
        release["assets"][name] += b"changed after acceptance"
    result = prepare(release)
    assert result.returncode != 0, problem
    assert not (release["root"] / "prepared").exists()


@pytest.mark.parametrize("order", ["behind", "diverged"])
def test_an_older_or_divergent_source_cannot_replace_current_downloads(release, order):
    """Queue order does not confer source freshness; Git ancestry must show a forward promotion."""
    release["compare"]["status"] = order
    result = prepare(release)
    assert result.returncode != 0 and "source" in result.stderr
    assert not (release["root"] / "prepared").exists()


def test_repeating_preparation_preserves_the_exact_existing_candidate(release):
    """Publication retry may download accepted bytes again but cannot overwrite a prepared version."""
    assert prepare(release).returncode == 0
    root = release["root"] / "prepared"
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = prepare(release)
    assert result.returncode == 0, result.stderr
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()} == before
    (root / "downloads/release.json").write_bytes(b"Changed locally after acceptance")
    result = prepare(release)
    assert result.returncode != 0 and "overwrit" in result.stderr
    assert (root / "downloads/release.json").read_bytes() == b"Changed locally after acceptance"


def current_release(data):
    """Record a prepared desired catalog as the previous accepted Git promotion."""
    assert prepare(data).returncode == 0
    root = data["root"]
    (root / "catalog.json").write_bytes((root / "prepared/catalog.json").read_bytes())
    previous = root / "previous.json"
    previous.write_bytes((root / "prepared/promotion.json").read_bytes())
    data["compare"]["status"] = "identical"
    return previous


def test_current_release_retry_preserves_unrelated_catalog_updates(release):
    """A site retry revalidates the same release while keeping another game's newer catalog changes."""
    previous = current_release(release)
    path = release["root"] / "catalog.json"
    catalog = json.loads(path.read_text())
    catalog["games"]["tribes"]["released"] = "2026-09-17"
    path.write_bytes(encoded(catalog))
    result = prepare(release, output="retry", previous=previous)
    assert result.returncode == 0, result.stderr
    assert json.loads((release["root"] / "retry/catalog.json").read_text()) == catalog
    receipt = json.loads((release["root"] / "retry/promotion.json").read_text())
    assert receipt["already_current"] is True


@pytest.mark.parametrize("changed", ["catalog.json", "baseline.json", "previous.json"])
def test_concurrent_input_edits_cannot_be_labeled_as_the_prepared_catalog(release, changed):
    """Downloads cannot turn an older input into a candidate authorized against newly edited local state."""
    previous = current_release(release)
    path = release["root"] / changed
    edited = path.read_bytes() + b"\n"

    def edit_during_download(request):
        if request.endswith("/release.json"):
            path.write_bytes(edited)

    release["on_request"] = edit_during_download
    result = prepare(release, output="retry", previous=previous)
    assert result.returncode != 0 and "changed during preparation" in result.stderr, result.stderr
    assert not (release["root"] / "retry").exists()
    assert path.read_bytes() == edited


@pytest.mark.parametrize("problem", ["no_receipt", "different_manifest", "different_release", "older_build", "rebound_source"])
def test_same_source_retries_cannot_rebind_an_accepted_version(release, problem):
    """One published version stays bound to its exact release, manifest and source; same-source run order is monotonic."""
    previous = current_release(release)
    if problem == "no_receipt":
        previous = None
    elif problem in ("different_manifest", "different_release"):
        value = json.loads(previous.read_text())
        value["manifest_sha256" if problem == "different_manifest" else "release_id"] = "f" * 64 if problem == "different_manifest" else 999
        previous.write_bytes(encoded(value))
    elif problem == "older_build":
        path = release["root"] / "catalog.json"
        path.write_text(path.read_text().replace("0.2.1", "0.2.2"))
        previous = None
    else:
        path = release["root"] / "catalog.json"
        value = json.loads(path.read_text())
        value["games"]["warband"]["source_commit"] = "b" * 40
        path.write_bytes(encoded(value))
        release["compare"]["status"] = "ahead"
        previous = None
    result = prepare(release, output="retry", previous=previous)
    assert result.returncode != 0, problem
    assert not (release["root"] / "retry").exists()


@pytest.mark.parametrize("counter", [0, -1, True, 27])
def test_manifest_counter_must_match_independent_github_run(release, counter):
    """An archive cannot choose another run's short version even with valid outer hashes."""
    release["run"]["run_number"] = counter
    result = prepare(release)
    assert result.returncode != 0
    assert not (release["root"] / "prepared").exists()


def test_numeric_version_order_accepts_ten_after_nine(tmp_path):
    """Version order is numeric, so 0.2.10 is newer than 0.2.9."""
    data = release_data(tmp_path, run_number=35)
    path = tmp_path / "catalog.json"
    path.write_text(path.read_text().replace("0.2.0-preview.122", "0.2.9"))
    result = prepare(data)
    assert result.returncode == 0, result.stderr
    assert json.loads((tmp_path / "prepared/catalog.json").read_text())["games"]["warband"]["version"] == "0.2.10"


def test_newer_source_cannot_roll_back_the_public_version(release):
    """A changed counter anchor must not permit version rollback even on a descendant commit."""
    path = release["root"] / "catalog.json"
    path.write_text(path.read_text().replace("0.2.0-preview.122", "0.2.2"))
    result = prepare(release)
    assert result.returncode != 0 and "older version" in result.stderr
    assert not (release["root"] / "prepared").exists()


def test_new_build_of_same_source_gets_new_version_without_rebinding_old_release(release):
    """A later native run can replace the download while preserving the previous immutable identity."""
    previous = current_release(release)
    catalog_bytes = (release["root"] / "catalog.json").read_bytes()
    later = release_data(release["root"], run_id=124, run_number=27)
    (release["root"] / "catalog.json").write_bytes(catalog_bytes)
    later["compare"]["status"] = "identical"
    result = prepare(later, output="next", previous=previous)
    assert result.returncode == 0, result.stderr
    assert json.loads((release["root"] / "next/catalog.json").read_text())["games"]["warband"]["version"] == "0.2.2"
