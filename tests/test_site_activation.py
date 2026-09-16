"""Exercise atomic site publication through a real CLI, filesystem and HTTP server."""
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import hashlib
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
            if urlsplit(self.path).path == "/server-compatibility.json" and "baseline" in faults:
                self.send_response(200)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(json.dumps(faults["baseline"]).encode())
            elif self.path == "/healthz":
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


def command(source, base, endpoint, release, generation, expected="none", *, promotion=None):
    return [sys.executable, str(CLI), "--source", str(source), "--base", str(base),
            "--release", release, "--generation", str(generation), "--expected", expected,
            "--public-url", endpoint, "--health-url", endpoint + "/healthz",
            "--deployment-lock", str(base.parent / "deployment.lock"),
            *(["--mode", "warband-promotion", "--promotion-receipt", str(promotion)] if promotion
              else ["--mode", "operator"])]


def activate(*args, **kwargs):
    return subprocess.run(command(*args, **kwargs), capture_output=True, text=True, timeout=30)


def promotion_receipt(source, baseline):
    """Only the accepted catalog digest and baseline cross the deployment seam; producer verification has its own suite."""
    receipt = source.parent / (source.name + "-promotion.json")
    receipt.write_text(json.dumps({"schema_version": 1, "baseline": baseline,
                                  "catalog_sha256": hashlib.sha256((source / "releases.json").read_bytes()).hexdigest()}))
    return receipt


def test_promoted_downloads_and_same_generation_retries_require_the_reviewed_live_baseline(tmp_path):
    """An accepted receipt binds site bytes to the running server, even when that site is already current."""
    base = tmp_path / "site-host"
    source = site(tmp_path, "candidate")
    baseline = {"schema_version": 1, "deployment_release": "d" * 64, "endpoint": "wss://games.example.test/play",
                "protocol": 1, "warband": {"source_commit": "e" * 40, "compatibility": {"sha256": "f" * 64}}}
    receipt = promotion_receipt(source, baseline)
    faults = {"baseline": baseline}
    with public_site(base, faults) as endpoint:
        result = activate(source, base, endpoint, "a" * 64, 1, promotion=receipt)
        assert result.returncode == 0, result.stderr
        before = (base / "state.json").read_bytes()
        faults["baseline"] = {**baseline, "deployment_release": "b" * 64}
        result = activate(source, base, endpoint, "a" * 64, 1, promotion=receipt)
        assert result.returncode != 0 and "Live server differs" in result.stderr
        assert (base / "state.json").read_bytes() == before
        assert (base / "current/releases.json").read_bytes() == (source / "releases.json").read_bytes()


def test_waiting_promotion_rechecks_the_server_after_another_deployment_finishes(tmp_path):
    """A baseline accepted during preparation cannot survive a different server activation while waiting for the host lock."""
    base = tmp_path / "site-host"
    first, second = site(tmp_path, "first"), site(tmp_path, "second")
    baseline = {"schema_version": 1, "deployment_release": "d" * 64}
    receipt = promotion_receipt(second, baseline)
    faults = {"baseline": baseline}
    with public_site(base, faults) as endpoint:
        assert activate(first, base, endpoint, "a" * 64, 1).returncode == 0
        before = (base / "state.json").read_bytes()
        with deployment_operation(tmp_path / "deployment.lock"):
            process = subprocess.Popen(command(second, base, endpoint, "b" * 64, 2, "a" * 64, promotion=receipt),
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with pytest.raises(subprocess.TimeoutExpired):
                process.wait(timeout=.5)
            faults["baseline"] = {**baseline, "deployment_release": "e" * 64}
        _, error = process.communicate(timeout=10)
        assert process.returncode != 0 and b"Live server differs" in error
        assert (base / "state.json").read_bytes() == before
        assert (base / "current").resolve().name == "a" * 64


def test_baseline_change_during_public_verification_restores_downloads_and_retry_succeeds(tmp_path):
    """A process change after the pointer swap rolls back the entire promotion without consuming its generation."""
    base = tmp_path / "site-host"
    first, second = site(tmp_path, "first"), site(tmp_path, "second")
    baseline = {"schema_version": 1, "deployment_release": "d" * 64}
    receipt = promotion_receipt(second, baseline)
    faults = {"baseline": baseline}
    entered, resume = threading.Event(), threading.Event()
    with public_site(base, faults) as endpoint:
        assert activate(first, base, endpoint, "a" * 64, 1).returncode == 0
        before = (base / "state.json").read_bytes()
        faults.update(block="/index.html", entered=entered, resume=resume)
        with subprocess.Popen(command(second, base, endpoint, "b" * 64, 2, "a" * 64, promotion=receipt),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            try:
                assert entered.wait(10)
                assert (base / "current").resolve().name == "b" * 64
                faults["baseline"] = {**baseline, "deployment_release": "e" * 64}
            finally:
                del faults["block"]
                resume.set()
            _, error = process.communicate(timeout=10)
            assert process.returncode != 0 and b"Live server differs" in error
        assert (base / "current").resolve().name == "a" * 64
        assert (base / "state.json").read_bytes() == before
        assert not (base / "previous").exists() and not (base / "pending.json").exists()
        faults["baseline"] = baseline
        result = activate(second, base, endpoint, "b" * 64, 2, "a" * 64, promotion=receipt)
        assert result.returncode == 0, result.stderr
        assert (base / "current").resolve().name == "b" * 64
        assert (base / "previous").resolve().name == "a" * 64


@pytest.mark.parametrize("fault", ["changed_catalog", "missing_receipt", "operator_receipt", "null_baseline"])
def test_promotion_cannot_change_the_verified_catalog_or_omit_its_receipt(tmp_path, fault):
    """Explicit operation modes and the receipt's catalog digest prevent silently publishing unchecked promotion bytes."""
    base = tmp_path / "host"
    first, second = site(tmp_path, "first"), site(tmp_path, "second")
    baseline = {"schema_version": 1, "deployment_release": "d" * 64}
    receipt = promotion_receipt(second, baseline)
    with public_site(base, {"baseline": baseline}) as endpoint:
        assert activate(first, base, endpoint, "a" * 64, 1).returncode == 0
        before = (base / "state.json").read_bytes()
        args = command(second, base, endpoint, "b" * 64, 2, "a" * 64, promotion=receipt)
        if fault == "changed_catalog":
            (second / "releases.json").write_text('{"different_downloads": true}')
        elif fault == "missing_receipt":
            position = args.index("--promotion-receipt")
            del args[position:position + 2]
        elif fault == "null_baseline":
            contents = json.loads(receipt.read_text())
            contents["baseline"] = None
            receipt.write_text(json.dumps(contents))
        else:
            args[args.index("--mode") + 1] = "operator"
        result = subprocess.run(args, capture_output=True, text=True, timeout=10)
        assert result.returncode != 0 and "receipt" in result.stderr
        assert (base / "state.json").read_bytes() == before
        assert (base / "current").resolve().name == "a" * 64


@contextmanager
def deployment_operation(path):
    """Hold the host's actual OS lock in another process until the caller releases it."""
    script = """
import fcntl, sys
with open(sys.argv[1], 'a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    print('LOCKED', flush=True)
    sys.stdin.read(1)
"""
    with subprocess.Popen([sys.executable, "-c", script, str(path)], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
        try:
            assert process.stdout.readline().strip() == "LOCKED"
            yield
        finally:
            process.stdin.write("\n")
            process.stdin.flush()
            _, error = process.communicate(timeout=10)
            assert process.returncode == 0, error


def test_site_waits_for_a_separate_host_deployment_before_changing_downloads(tmp_path):
    """Server-side work and site publication must contend on a shared lock outside either release tree."""
    base = tmp_path / "site-host"
    source = site(tmp_path, "candidate")
    with public_site(base) as endpoint:
        with deployment_operation(tmp_path / "deployment.lock"):
            process = subprocess.Popen(command(source, base, endpoint, "a" * 64, 1),
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with pytest.raises(subprocess.TimeoutExpired):
                process.wait(timeout=.5)
            assert not (base / "current").exists()
        _, error = process.communicate(timeout=10)
        assert process.returncode == 0, error
    assert (base / "current/index.html").read_bytes() == (source / "index.html").read_bytes()


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


def test_new_generation_of_current_site_preserves_the_distinct_rollback_target(tmp_path):
    """A fresh CI attempt may verify current bytes without making them their own rollback release."""
    base = tmp_path / "host"
    first, second = site(tmp_path, "first"), site(tmp_path, "second")
    faults = {}
    with public_site(base, faults) as endpoint:
        assert activate(first, base, endpoint, "a" * 64, 1).returncode == 0
        assert activate(second, base, endpoint, "b" * 64, 2, "a" * 64).returncode == 0
        result = activate(second, base, endpoint, "b" * 64, 3, "b" * 64)
        assert result.returncode == 0, result.stderr
        state = json.loads((base / "state.json").read_text())
        assert state == {"release": "b" * 64, "generation": 3, "previous": "a" * 64}
        assert (base / "previous").resolve().name == "a" * 64
        faults["health"] = True
        result = activate(second, base, endpoint, "b" * 64, 4, "b" * 64)
        assert result.returncode != 0 and "health" in result.stderr
        assert json.loads((base / "state.json").read_text()) == state
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
