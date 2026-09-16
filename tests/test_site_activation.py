"""Exercise atomic site publication through a real CLI, filesystem and HTTP server."""
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "deploy/activate_site.py"


@contextmanager
def public_site(base, faults=None):
    faults = {} if faults is None else faults
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if urlsplit(self.path).path == faults.get("block"):
                entered, resume, abort = faults["entered"], faults["resume"], faults.get("abort", False)
                entered.set()
                resume.wait(20)
                if abort:
                    return
            if self.path == "/healthz":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"failed\n" if faults.get("health") else b"ok\n")
            elif urlsplit(self.path).path == faults.get("corrupt"):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Incorrect public bytes")
            else:
                super().do_GET()

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(base / "current")))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def site(root, name):
    directory = root / name
    directory.mkdir()
    (directory / "index.html").write_text(f"<h1>{name}</h1>\n")
    (directory / "releases.json").write_text(json.dumps({"fixture_release": name}))
    (directory / "warband").mkdir()
    (directory / "warband/index.html").write_text(f"<h1>Warband {name}</h1>\n")
    return directory


def command(source, base, endpoint, release, generation, expected="none"):
    return [sys.executable, str(CLI), "--source", str(source), "--base", str(base),
            "--release", release, "--generation", str(generation), "--expected", expected,
            "--public-url", endpoint, "--health-url", endpoint + "/healthz"]


def activate(*args):
    return subprocess.run(command(*args), capture_output=True, text=True, timeout=30)


def test_a_verified_site_activates_once_and_retains_the_previous_release(tmp_path):
    """Public bytes match the candidate; retry preserves the current and rollback targets."""
    base = tmp_path / "host"
    first, second = site(tmp_path, "first"), site(tmp_path, "second")
    with public_site(base) as endpoint:
        result = activate(first, base, endpoint, "a" * 64, 1)
        assert result.returncode == 0, result.stderr
        result = activate(second, base, endpoint, "b" * 64, 2, "a" * 64)
        assert result.returncode == 0, result.stderr
        assert (base / "current/index.html").read_bytes() == (second / "index.html").read_bytes()
        assert (base / "previous/index.html").read_bytes() == (first / "index.html").read_bytes()
        original = (base / "state.json").read_bytes()
        result = activate(second, base, endpoint, "b" * 64, 2, "a" * 64)
        assert result.returncode == 0, result.stderr
        assert (base / "state.json").read_bytes() == original
        assert (base / "previous").resolve().name == "a" * 64


def test_retry_recovers_an_activation_interrupted_after_the_pointer_swap(tmp_path):
    """Killing the publisher during its public check leaves recoverable state, not a wedged deployment."""
    base = tmp_path / "host"
    first, second = site(tmp_path, "first"), site(tmp_path, "second")
    faults = {}
    entered, resume = threading.Event(), threading.Event()
    with public_site(base, faults) as endpoint:
        assert activate(first, base, endpoint, "a" * 64, 1).returncode == 0
        faults.update(block="/index.html", entered=entered, resume=resume, abort=True)
        with subprocess.Popen(command(second, base, endpoint, "b" * 64, 2, "a" * 64),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            try:
                assert entered.wait(10), "Publisher did not reach the public check"
                assert (base / "current").resolve().name == "b" * 64
            finally:
                process.kill()
                process.communicate(timeout=5)
                resume.set()
                faults.clear()
        result = activate(second, base, endpoint, "b" * 64, 2, "a" * 64)
        assert result.returncode == 0, result.stderr
        assert (base / "current").resolve().name == "b" * 64
        assert (base / "previous").resolve().name == "a" * 64


@pytest.mark.parametrize("failure", ["public_bytes", "server_health"])
def test_failed_public_acceptance_rolls_back_and_the_same_candidate_can_retry(tmp_path, failure):
    """A bad public page or unhealthy server leaves every prior download/catalog byte available."""
    base = tmp_path / "host"
    first, second = site(tmp_path, "first"), site(tmp_path, "second")
    faults = {}
    with public_site(base, faults) as endpoint:
        assert activate(first, base, endpoint, "a" * 64, 1).returncode == 0
        original = (base / "state.json").read_bytes()
        faults.update({"corrupt": "/warband/index.html"} if failure == "public_bytes" else {"health": True})
        result = activate(second, base, endpoint, "b" * 64, 2, "a" * 64)
        assert result.returncode != 0
        assert (base / "current").resolve().name == "a" * 64
        assert (base / "current/releases.json").read_bytes() == (first / "releases.json").read_bytes()
        assert (base / "state.json").read_bytes() == original
        faults.clear()
        result = activate(second, base, endpoint, "b" * 64, 2, "a" * 64)
        assert result.returncode == 0, result.stderr


def test_stale_or_rebound_promotions_cannot_replace_a_newer_site(tmp_path):
    """Both compare-and-swap and generation checks protect the current site; versioned bytes cannot change."""
    base = tmp_path / "host"
    first, second, stale = (site(tmp_path, name) for name in ("first", "second", "stale"))
    with public_site(base) as endpoint:
        assert activate(first, base, endpoint, "a" * 64, 10).returncode == 0
        assert activate(second, base, endpoint, "b" * 64, 12, "a" * 64).returncode == 0
        original = (base / "state.json").read_bytes()
        for expected in ("a" * 64, "b" * 64):
            result = activate(stale, base, endpoint, "c" * 64, 11, expected)
            assert result.returncode != 0
            assert (base / "current").resolve().name == "b" * 64
            assert (base / "state.json").read_bytes() == original
        (second / "index.html").write_text("Changed after publication")
        result = activate(second, base, endpoint, "b" * 64, 12, "a" * 64)
        assert result.returncode != 0 and "cannot be overwritten" in result.stderr
        assert (base / "current/index.html").read_text() == "<h1>second</h1>\n"


def test_a_second_publisher_waits_until_public_verification_commits(tmp_path):
    """Concurrent publishers cannot interrupt each other's public check or both accept the same old head."""
    base = tmp_path / "host"
    first, second, third = (site(tmp_path, name) for name in ("first", "second", "third"))
    faults = {}
    entered, resume = threading.Event(), threading.Event()
    with public_site(base, faults) as endpoint:
        assert activate(first, base, endpoint, "a" * 64, 1).returncode == 0
        faults.update(block="/index.html", entered=entered, resume=resume)
        with subprocess.Popen(command(second, base, endpoint, "b" * 64, 2, "a" * 64),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) as publisher:
            try:
                assert entered.wait(10)
                with subprocess.Popen(command(third, base, endpoint, "c" * 64, 3, "a" * 64),
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE) as competitor:
                    try:
                        with pytest.raises(subprocess.TimeoutExpired):
                            competitor.wait(timeout=0.5)
                    finally:
                        faults.clear()
                        resume.set()
                    _, error = competitor.communicate(timeout=10)
                    assert competitor.returncode != 0 and b"Current site changed" in error
                _, error = publisher.communicate(timeout=10)
                assert publisher.returncode == 0, error
            finally:
                faults.clear()
                resume.set()
        assert (base / "current").resolve().name == "b" * 64
