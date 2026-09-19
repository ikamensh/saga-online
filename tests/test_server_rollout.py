"""The automatic server rollout: its decision, the host protocol, the public checks and its record.

The host side runs for real on a Linux runner (tests/host_server_ci.py); here the
decision runs over real HTTP against a GitHub fixture, the forced command and
root entry point run with stand-ins for sudo and install.sh, and the public
checks run against the real packaged server.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import select
import subprocess
import sys
import tarfile
import threading
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "deploy"))
from tests.test_warband_promotion import REPO, encoded, release_data, sha
from tools import server_rollout
from tools.warband_promotion import GitHub
import server_ci
import install_server_ci

PINS = {"python": "3.13.2", "uv": "0.12.10", "warband_run_id": 100, "warband_run_number": 20,
        "sources": {"sagaforge": "1" * 40, "tribes": "2" * 40, "warband": "3" * 40, "shardbound": "4" * 40}}


@contextmanager
def github(data, releases=None, served=None):
    """GitHub's API, its release downloads and the live attestation, as the rollout reads them."""
    listing = releases if releases is not None else [data["release"]]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            routes = {REPO + "/releases": listing, REPO + "/releases/456/assets": data["release"]["assets"],
                      REPO + f"/actions/runs/{data['run']['id']}": data["run"], REPO + "/actions/workflows/native-packages.yml": {"id": 90},
                      REPO + f"/actions/runs/{data['run']['id']}/attempts/1/jobs": {"jobs": data["jobs"]},
                      REPO + "/git/ref/tags/" + data["release"]["tag_name"]: {"object": {"type": "commit", "sha": data["tag_commit"]}},
                      "/server-compatibility.json": served if served is not None else data["baseline"]}
            if path.startswith(REPO + "/compare/"):
                payload = encoded(data["compare"])
            elif path in routes:
                payload = encoded(routes[path])
            elif path.startswith("/ikamensh/warband/releases/download/"):
                payload = data["assets"][path.rsplit("/", 1)[1]]
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def decide(data, *, pins=PINS, served=None, releases=None, force=False):
    with github(data, releases, served) as url:
        return server_rollout.resolve(GitHub(url), deepcopy(pins), data["baseline"], data["catalog"],
                                      served if served is not None else data["baseline"], force=force)


def changed_contract(data):
    """The live baseline's contract differs from the published candidate's (a rules change)."""
    data["baseline"] = deepcopy(data["baseline"])
    contract = data["baseline"]["warband"]["compatibility"]
    contract["files"]["warband/online/authority.py"] = "9" * 64
    contract["sha256"] = sha(json.dumps({k: v for k, v in contract.items() if k != "sha256"}, sort_keys=True, separators=(",", ":")).encode())


def test_a_build_the_live_server_already_serves_needs_only_its_promotion(tmp_path):
    data = release_data(tmp_path)
    plan = decide(data)
    assert plan["action"] == "current" and plan["pins"] == PINS
    assert plan["promote"] is True, "the catalog still names another source"
    data["catalog"]["games"]["warband"]["source_commit"] = data["manifest"]["identity"]["source_commit"]
    assert decide(data)["promote"] is False, "nothing to do at all: a clean no-op"


@pytest.mark.parametrize("why", ["rules", "served", "force"])
def test_a_new_contract_a_diverged_live_server_or_force_deploys_with_moved_pins(tmp_path, why):
    data = release_data(tmp_path)
    served = None
    if why == "rules":
        changed_contract(data)
    elif why == "served":
        served = {**data["baseline"], "deployment_release": "9" * 64}
    plan = decide(data, served=served, force=why == "force")
    identity = data["manifest"]["identity"]
    assert plan["action"] == "deploy" and plan["promote"] is True
    assert plan["pins"] == {**PINS, "warband_run_id": identity["run_id"], "warband_run_number": identity["run_number"],
                            "sources": {**PINS["sources"], "warband": identity["source_commit"], "sagaforge": identity["sagaforge_commit"]}}
    assert plan["candidate"] == {"release_id": 456, "tag": identity["tag"], "version": identity["version"],
                                 "build_run_id": identity["run_id"], "run_number": identity["run_number"],
                                 "manifest_sha256": sha(data["assets"]["release.json"]),
                                 "source_commit": identity["source_commit"], "contract_sha256": identity["compatibility"]["sha256"]}


def test_the_newest_published_release_is_the_candidate(tmp_path):
    data = release_data(tmp_path)
    changed_contract(data)
    draft = {**data["release"], "id": 999, "draft": True, "tag_name": "v9.9.9"}
    legacy = {**data["release"], "id": 998, "tag_name": "v0.2.0-preview.3"}
    assert decide(data, releases=[draft, legacy, data["release"]])["candidate"]["release_id"] == 456
    with pytest.raises(ValueError, match="no published release"):
        decide(data, releases=[draft, legacy])


@pytest.mark.parametrize("problem", ["behind", "diverged", "runtime", "failed_native_build", "manifest_digest"])
def test_refuses_to_move_back_change_runtime_or_trust_an_unverified_build(tmp_path, problem):
    data = release_data(tmp_path)
    changed_contract(data)
    pins = PINS
    if problem in ("behind", "diverged"):
        data["compare"] = {"status": problem}
    elif problem == "runtime":
        pins = {**PINS, "python": "3.13.3"}
    elif problem == "failed_native_build":
        data["jobs"][1]["conclusion"] = "failure"
    else:
        data["release"]["assets"] = [{**item, "digest": "sha256:" + "0" * 64} if item["name"] == "release.json" else item
                                     for item in data["release"]["assets"]]
    with pytest.raises(ValueError):
        decide(data, pins=pins)


def test_resolve_command_rewrites_the_pins_only_for_a_deploy(tmp_path):
    data = release_data(tmp_path)
    pins = tmp_path / "pins.json"
    pins.write_text(json.dumps(PINS, indent=2) + "\n")
    before = pins.read_bytes()
    with github(data) as url:
        command = [sys.executable, str(ROOT / "tools/server_rollout.py"), "resolve", "--pins", str(pins),
                   "--baseline", str(tmp_path / "baseline.json"), "--catalog", str(tmp_path / "catalog.json"),
                   "--api-url", url, "--attestation", url + "/server-compatibility.json"]
        current = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
        assert current["action"] == "current" and pins.read_bytes() == before
        forced = json.loads(subprocess.run([*command, "--force"], check=True, capture_output=True, text=True).stdout)
    assert forced["action"] == "deploy" and json.loads(pins.read_bytes()) == forced["pins"] != PINS


# --- the host's forced command and root entry point ---------------------------

def test_forced_command_passes_exactly_four_words_to_sudo(tmp_path):
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "sudo").write_text('#!/bin/sh\nprintf "%s|" "$@"\n')
    (fake / "sudo").chmod(0o755)
    command = tmp_path / "command"
    command.write_text(install_server_ci.COMMAND)
    for original in ("status", "backup", "install", "rollback"):
        result = subprocess.run(["/bin/sh", str(command)], env={"PATH": str(fake), "SSH_ORIGINAL_COMMAND": original},
                                capture_output=True, text=True)
        assert result.returncode == 0 and result.stdout == f"-n|{install_server_ci.TOOLS}/run|{original}|"
    for original in ("", "status ", "status; id", "$(id)", "install x", "run status", "sh"):
        result = subprocess.run(["/bin/sh", str(command)], env={"PATH": str(fake), "SSH_ORIGINAL_COMMAND": original},
                                capture_output=True, text=True)
        assert result.returncode == 64 and result.stdout == "" and "Only status, backup, install and rollback" in result.stderr
    assert install_server_ci.SUDO_RULE.splitlines()[-1] == (
        "saga2d-server-ci ALL=(root) NOPASSWD: " + ", ".join(f"/usr/local/lib/saga2d-server-ci/run {op}"
                                                             for op in ("status", "backup", "install", "rollback")))


def test_every_file_root_runs_ships_in_the_server_ci_package(tmp_path):
    key = tmp_path / "ci.pub"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(tmp_path / "ci")], check=True)
    result = subprocess.run([sys.executable, str(ROOT / "tools/deploy_online.py"), "package-server-ci", "--name", "saga2d-online",
                             "--server-public-key", str(key), "--output", str(tmp_path / "out")], check=True, capture_output=True, text=True)
    with tarfile.open(json.loads(result.stdout)["archive"]) as bundle:
        names = set(bundle.getnames())
    assert names == {"install_server_ci.py", "install_site_ci.py", "server-ci.pub", *install_server_ci.HOST_FILES}
    prepared = (ROOT / "deploy/prepare_release.sh").read_text()
    compared = set(prepared.split("for name in ", 1)[1].split("; do", 1)[0].replace("\\\n", " ").split())
    assert compared == set(install_server_ci.HOST_FILES) - {"server_ci.py"}, "prepare_release.sh compares every host file the archive carries"


@pytest.fixture
def host(tmp_path, monkeypatch):
    base = tmp_path / "opt"
    (base / "releases" / ("a" * 64)).mkdir(parents=True)
    (base / "current").symlink_to(base / "releases" / ("a" * 64))
    calls = []

    def installer(*arguments):
        upload = Path(arguments[0])
        calls.append((arguments, (upload / "release.tar.gz").read_bytes() if upload.is_dir() else None))
    monkeypatch.setattr(server_ci, "BASE", base)
    monkeypatch.setattr(server_ci, "installer", installer)
    monkeypatch.setattr(server_ci, "status", lambda config: {"current": server_ci.release_of(base / "current")})
    return SimpleNamespace(config={"instance": "saga2d-online", "domain": "games.example.test"}, calls=calls)


def upload(archive, expected_current="a" * 64, **overrides):
    fields = {"release": hashlib.sha256(archive).hexdigest(), "bytes": len(archive), "expected_current": expected_current, **overrides}
    return io.BytesIO(server_rollout.request(**fields) + archive)


def test_install_hands_the_exact_verified_bytes_to_the_installed_installer(host):
    archive = b"archive bytes"
    result = server_ci.install(host.config, upload(archive))
    (arguments, staged), = host.calls
    assert arguments[1:] == (hashlib.sha256(archive).hexdigest(), "saga2d-online", "games.example.test") and staged == archive
    assert result["activated"] == hashlib.sha256(archive).hexdigest()


@pytest.mark.parametrize("fault", ["stale_current", "checksum", "truncated", "trailing", "oversized", "extra_field", "bad_release"])
def test_install_refuses_before_the_installer_runs(host, fault):
    archive = b"archive bytes"
    stream = {"stale_current": lambda: upload(archive, expected_current="b" * 64),
              "checksum": lambda: upload(archive, release="c" * 64),
              "truncated": lambda: upload(archive, bytes=len(archive) + 5),
              "trailing": lambda: io.BytesIO(upload(archive).getvalue() + b"x"),
              "oversized": lambda: upload(archive, bytes=server_ci.MAX_ARCHIVE + 1),
              "extra_field": lambda: upload(archive, command="sh"),
              "bad_release": lambda: upload(archive, release="../../etc")}[fault]()
    with pytest.raises(ValueError):
        server_ci.install(host.config, stream)
    assert host.calls == []


def test_rollback_names_the_release_it_leaves(host):
    server_ci.rollback(host.config, io.BytesIO(server_rollout.request(**{"from": "a" * 64})))
    assert host.calls == [(("--rollback", "a" * 64, "saga2d-online", "games.example.test"), None)]
    for stream in (io.BytesIO(server_rollout.request(**{"from": "a" * 64}) + b"x"),
                   io.BytesIO(server_rollout.request(**{"from": "a" * 64, "to": "b" * 64}))):
        with pytest.raises(ValueError):
            server_ci.rollback(host.config, stream)


# --- the record ----------------------------------------------------------------

PLAN = {"schema_version": 1, "force": False, "pins": PINS, "baseline": {"deployment_release": "e" * 64},
        "candidate": {"source_commit": "a" * 40, "tag": "v0.2.70"}}
EXPECTED = {"schema_version": 1, "deployment_release": "f" * 64, "warband": {}}


@pytest.mark.parametrize("fragments, outcome", [
    ({"deploy": {"expected": EXPECTED, "install": {}, "acceptance": {"passed": True}},
      "native-windows": {"passed": True}, "native-macos": {"passed": True}}, "accepted"),
    ({"deploy": {"expected": EXPECTED, "install": {}, "acceptance": {"passed": True}},
      "native-windows": {"passed": False}, "native-macos": {"passed": True}, "rollback": {"current": "e" * 64}}, "rolled_back"),
    ({"deploy": {"expected": EXPECTED, "install": {}, "acceptance": {"passed": False}, "rollback": {}}}, "rolled_back"),
    ({"deploy": {"expected": EXPECTED, "install_failed": {"passed": False}}}, "activation_failed_installer_restored_previous"),
    ({"deploy": {"expected": EXPECTED, "rehearsal": {"failed": 2}}}, "stopped_before_activation"),
    ({"deploy": {"expected": EXPECTED, "install": {}, "acceptance": {"passed": True}}}, "failed_without_rollback"),
])
def test_record_names_the_outcome_and_only_acceptance_moves_the_baseline(tmp_path, fragments, outcome):
    (tmp_path / "fragments").mkdir()
    for name, value in fragments.items():
        (tmp_path / "fragments" / f"{name}.json").write_text(json.dumps(value))
    (tmp_path / "plan.json").write_text(json.dumps(PLAN))
    records, baseline = tmp_path / "records", tmp_path / "baseline.json"
    baseline.write_text("previous")
    result = subprocess.run([sys.executable, str(ROOT / "tools/server_rollout.py"), "record", "--plan", str(tmp_path / "plan.json"),
                             "--fragments", str(tmp_path / "fragments"), "--run-url", "https://example.test/run/1", "--records", str(records),
                             "--baseline", str(baseline)], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout)["outcome"] == outcome
    entry, = [json.loads(path.read_text()) for path in records.glob("*-aaaaaaaa.json")]
    assert entry["outcome"] == outcome and entry["candidate"] == PLAN["candidate"] and entry["run"] == "https://example.test/run/1"
    assert json.loads(baseline.read_text()) == EXPECTED if outcome == "accepted" else baseline.read_text() == "previous"


# --- the public checks, against the real packaged server ------------------------

@pytest.fixture(scope="module")
def packaged(tmp_path_factory):
    folder = tmp_path_factory.mktemp("packaged")
    package = json.loads(subprocess.run([sys.executable, str(ROOT / "tools/deploy_online.py"), "package", "--name", "saga2d-online",
                                         "--output", str(folder)], check=True, capture_output=True, text=True).stdout)
    unpacked = folder / "release"
    with tarfile.open(package["archive"]) as bundle:
        bundle.extractall(unpacked, filter="data")
    inputs = json.loads((unpacked / "deploy/server-inputs.json").read_text())
    subprocess.run(["uv", "venv", "--python", inputs["python"], str(unpacked / ".venv")], check=True, capture_output=True)
    subprocess.run(["uv", "pip", "install", "--python", str(unpacked / ".venv/bin/python"), "--require-hashes",
                    "-r", str(unpacked / "deploy/requirements.txt")], check=True, capture_output=True)
    return SimpleNamespace(archive=Path(package["archive"]), release=package["release"], root=unpacked, folder=folder)


@contextmanager
def running(packaged, state):
    with subprocess.Popen([str(packaged.root / ".venv/bin/python"), "-B", str(packaged.root / "deploy/server.py"), "--port", "0",
                           "--release-id", packaged.release, "--endpoint", "wss://games.tachyon-ai.eu/play", "--state-dir", str(state)],
                          cwd=packaged.folder, stdout=subprocess.PIPE, text=True) as process:
        try:
            assert select.select([process.stdout], [], [], 15)[0], "Packaged server failed to start"
            yield process.stdout.readline().strip().removeprefix("LISTENING ") + "/play"
        finally:
            process.terminate()
            process.wait(timeout=20)


def test_public_checks_pass_on_the_activated_release_and_a_deliberate_failure_follows_them(packaged, tmp_path):
    from deploy.backup import backup
    from deploy.smoke import smoke
    expected = server_rollout.expected_baseline(packaged.archive, "wss://games.tachyon-ai.eu/play")
    state = tmp_path / "state"
    with running(packaged, state) as endpoint:
        seeded = smoke(endpoint)  # three paused rooms with private seats, retained across the restart
    saved = backup(state / "rooms.sqlite3", tmp_path / "backups")
    with running(packaged, state) as endpoint:  # a fresh process: its room-creation budget is its own
        wrong = {**expected, "deployment_release": "0" * 64}
        with pytest.raises(ValueError, match="served attestation"):
            server_rollout.accept(endpoint, wrong, saved)
        report = {}
        with pytest.raises(ValueError, match="Deliberate failure"):
            server_rollout.accept(endpoint, expected, saved, fail=True, report=report)
    checks = report["checks"]
    assert [name for name, check in checks.items() if check["passed"]] == [
        "health", "attestation", "smoke", "permessage_deflate", "retained_seats", "three_seat_room"]
    assert checks["deliberate_failure"] == {"passed": False} and report["passed"] is False
    newest_of_each_game = [record["room"] for record in sorted(seeded, key=lambda record: record["game"])]
    assert checks["retained_seats"]["detail"] == {"rooms": 3, "retained": 3, "failed": 0, "seats": 6,
                                                  "resumed_rooms": newest_of_each_game}


def test_a_live_check_samples_the_newest_retained_room_of_each_game():
    from tools.rehearse_retained import newest_per_game
    rooms = [{"code": code, "game": game, "expires_at": expires} for code, game, expires in
             [("a", "tribes-v1", 5), ("b", "tribes-v1", 9), ("c", "shardbound-v1", 1), ("d", "shardbound-v1", 3), ("e", "warband-v2", 2)]]
    assert [room["code"] for room in newest_per_game(rooms)] == ["d", "b", "e"]
