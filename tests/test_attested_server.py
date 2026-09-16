"""The deployment process attests its runtime while serving real persistent rooms.

These small game fixtures exercise the deployment interface, not Warband or
the other games' release acceptance. They use the installed released Saga2D.
"""
from contextlib import contextmanager
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from urllib.request import urlopen

import pytest
import saga2d
from saga2d.testing.online import command, first_stdout_line, handshake, receive
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def release(tmp_path):
    root = tmp_path / "release"
    engine = Path(saga2d.__file__).resolve().parent
    for path in engine.rglob("*.py"):
        target = root / "saga2d" / path.relative_to(engine)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    for package, module, game in (("tribes", "multiplayer", "tribes-v1"),
                                  ("warband", "authority", "warband-v2"),
                                  ("eador", "multiplayer", "shardbound-v1")):
        folder = root / package
        folder.mkdir()
        (folder / "__init__.py").write_text("")
        (folder / f"{module}.py").write_text("from saga2d.testing.online import GAMES\n"
                                           f"ONLINE = {{{game!r}: GAMES['counter-realtime-v1']}}\n")
    (root / "sagaforge").mkdir()
    (root / "sagaforge/__init__.py").write_text("")
    (root / "deploy").mkdir()
    for name in ("server.py", "runtime.py"):
        shutil.copyfile(ROOT / "deploy" / name, root / "deploy" / name)
    files = {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in root.rglob("*") if p.is_file()}
    packages = {name: importlib.metadata.version(name) for name in ("pillow", "pyglet", "websockets")}
    packages["saga2d"] = saga2d.__version__
    contract = {"schema_version": 1, "registry": "warband.authority:ONLINE", "python": platform.python_version(),
                "packages": packages, "files": {name: digest for name, digest in files.items() if name.startswith("warband/")}}
    contract["sha256"] = sha(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode())
    inputs = {"schema_version": 1, "sources": dict.fromkeys(("saga-online", "sagaforge", "tribes", "warband", "shardbound"), "a" * 40),
              "python": platform.python_version(), "packages": packages, "files": files, "warband_compatibility": contract}
    (root / "deploy/server-inputs.json").write_bytes(encoded(inputs))
    return root, inputs


def launch(root, state):
    return [sys.executable, "-B", str(root / "deploy/server.py"), "--release-id", "e" * 64,
            "--endpoint", "wss://games.example.test/play", "--port", "0", "--state-dir", str(state)]


@contextmanager
def server(root, state):
    process = subprocess.Popen(launch(root, state), cwd=root.parent, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True,
                               env={**os.environ, "SAGA2D_SILENT": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        line = first_stdout_line(process).strip()
        if not line.startswith("LISTENING ws://"):
            _, error = process.communicate(timeout=5)
            raise AssertionError(f"Server did not start: {line}\n{error}")
        yield line.removeprefix("LISTENING "), process
    finally:
        if process.poll() is None:
            process.terminate()
        _, error = process.communicate(timeout=10)
        assert "Traceback (most recent call last)" not in error, error


def test_running_process_attests_the_verified_runtime_and_serves_all_registered_games(release, tmp_path):
    """Attestation and real game traffic share a process; the HTTP response describes its verified package."""
    root, inputs = release
    with server(root, tmp_path / "state") as (endpoint, process):
        http = endpoint.replace("ws://", "http://")
        with urlopen(http + "/server-compatibility.json?deployment=" + "e" * 64) as response:
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers.get_content_type() == "application/json"
            assert json.load(response) == {"schema_version": 1, "deployment_release": "e" * 64,
                "endpoint": "wss://games.example.test/play", "protocol": 1,
                "warband": {"source_commit": "a" * 40, "compatibility": inputs["warband_compatibility"]}}
        with urlopen(http + "/healthz") as response:
            assert response.read() == b"ok\n"
        for game in ("tribes-v1", "warband-v2", "shardbound-v1"):
            with connect(endpoint + "/play", proxy=None) as host, connect(endpoint + "/play", proxy=None) as guest:
                seat = handshake(host, game=game)
                receive(host)
                handshake(guest, "join", game=game, room=seat["room"])
                receive(guest, predicate=lambda message: message["ready"])
                command(guest, {"action": "add"})
                assert receive(guest, predicate=lambda message: message["state"]["counts"][1] == 1)["ready"]
        assert process.poll() is None


@pytest.mark.parametrize("changed", ["changed_source", "missing_source", "extra_source", "root_source", "python", "dependency", "contract"])
def test_unverified_inputs_refuse_startup_before_opening_the_room_store(release, tmp_path, changed):
    """A process cannot attest desired metadata when its actual code or runtime disagrees."""
    root, inputs = release
    if changed == "changed_source":
        (root / "warband/authority.py").write_text("raise AssertionError('This changed game must not import')\n")
    elif changed == "missing_source":
        (root / "warband/authority.py").unlink()
    elif changed == "extra_source":
        (root / "warband/unrecorded.py").write_text("VALUE = 1\n")
    elif changed == "root_source":
        (root / "unrecorded.py").write_text("VALUE = 1\n")
    elif changed == "python":
        inputs["python"] = "0.0.0"
    elif changed == "dependency":
        inputs["packages"]["websockets"] = "0.0.0"
    else:
        inputs["warband_compatibility"]["sha256"] = "0" * 64
    (root / "deploy/server-inputs.json").write_bytes(encoded(inputs))
    state = tmp_path / "state"
    process = subprocess.Popen(launch(root, state), cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        output, error = process.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.communicate(timeout=10)
        pytest.fail(f"Server accepted {changed} inputs instead of refusing startup")
    assert process.returncode != 0 and "LISTENING" not in output, error
    assert "This changed game must not import" not in error
    assert not state.exists()


@pytest.mark.parametrize("game", ["tribes-v1", "warband-v2", "shardbound-v1"])
def test_sigterm_flushes_the_last_order_and_private_seats_resume_after_restart(release, tmp_path, game):
    """The deployment launcher must preserve the engine's final checkpoint and authenticated rejoin lifecycle."""
    root, _ = release
    state = tmp_path / "state"
    with server(root, state) as (endpoint, process):
        with connect(endpoint + "/play", proxy=None) as host, connect(endpoint + "/play", proxy=None) as guest:
            seat0 = handshake(host, game=game)
            receive(host)
            seat1 = handshake(guest, "join", game=game, room=seat0["room"])
            receive(guest, predicate=lambda message: message["ready"])
            command(guest, {"action": "add"})
            receive(guest, predicate=lambda message: message["state"]["counts"][1] == 1)
            process.terminate()
            process.wait(timeout=10)
            assert process.returncode == 0
    with server(root, state) as (endpoint, _):
        with connect(endpoint + "/play", proxy=None) as host, connect(endpoint + "/play", proxy=None) as guest:
            for socket, seat in ((host, seat0), (guest, seat1)):
                returned = handshake(socket, "resume", game=game, room=seat0["room"], resume_token=seat["resume_token"])
                assert returned["player"] == seat["player"]
            assert receive(guest, predicate=lambda message: message["ready"])["state"]["counts"] == [0, 1]
