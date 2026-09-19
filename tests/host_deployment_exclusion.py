"""Exercise actual deployment entry points on an isolated, root-owned Linux CI host.

This is deliberately not collected by ordinary pytest: it uses the production
host lock and managed-instance marker, and must never run against a live host.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_site_activation import public_site, site


def verify():
    if sys.platform != "linux" or os.geteuid() != 0 or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Run only as root on an isolated GitHub Linux acceptance runner")
    marker = Path("/etc/saga2d-online/managed-instance")
    base = Path("/srv/saga2d-site")
    if marker.exists() or Path("/opt/saga2d-online/current").exists() or base.exists():
        raise RuntimeError("Refusing an already managed host")
    marker.parent.mkdir(exist_ok=True)
    marker.write_text("saga2d-ci\n")
    try:
        with tempfile.TemporaryDirectory(prefix="deployment-exclusion-") as temporary:
            root = Path(temporary)
            source = site(root, "candidate")
            # Deliberately absent input stops the real installer at preparation,
            # before it could change a service, proxy, room store or site.
            installer = ["bash", str(ROOT / "deploy/install.sh"), str(root / "absent-upload"),
                         "a" * 64, "saga2d-ci", "games.example.test"]
            control = subprocess.run(installer, capture_output=True, text=True, timeout=10)
            assert control.returncode != 0 and "absent-upload/release.tar.gz" in control.stderr
            entered, resume = threading.Event(), threading.Event()
            faults = {"block": "/index.html", "entered": entered, "resume": resume}
            with public_site(base, faults) as endpoint:
                publisher_command = [sys.executable, str(ROOT / "deploy/activate_site.py"), "--source", str(source),
                                     "--base", str(base), "--release", "b" * 64, "--generation", "1", "--expected", "none",
                                     "--public-url", endpoint, "--health-url", endpoint + "/healthz", "--mode", "operator"]
                # Neither entry point overrides its production lock path.
                with subprocess.Popen(publisher_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as publisher:
                    try:
                        assert entered.wait(10), "Publisher did not reach public acceptance"
                        with subprocess.Popen(installer, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as server:
                            try:
                                try:
                                    server.wait(timeout=.75)
                                except subprocess.TimeoutExpired:
                                    pass
                                else:
                                    raise AssertionError("Server installer bypassed the site's active host lock")
                            finally:
                                faults.clear()
                                resume.set()
                            _, error = server.communicate(timeout=10)
                            assert server.returncode != 0 and b"absent-upload/release.tar.gz" in error
                        _, error = publisher.communicate(timeout=10)
                        assert publisher.returncode == 0, error
                    finally:
                        faults.clear()
                        resume.set()
                        if publisher.poll() is None:
                            publisher.kill()
                            publisher.communicate(timeout=5)
                assert (base / "current/index.html").read_bytes() == (source / "index.html").read_bytes()
                replacement = site(root, "replacement")
                next_command = publisher_command.copy()
                next_command[next_command.index("--source") + 1] = str(replacement)
                next_command[next_command.index("--release") + 1] = "c" * 64
                next_command[next_command.index("--generation") + 1] = "2"
                next_command[next_command.index("--expected") + 1] = "b" * 64
                entered.clear()
                resume.clear()
                faults.update(block="/index.html", entered=entered, resume=resume, abort=True)
                with subprocess.Popen(next_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as publisher:
                    try:
                        assert entered.wait(10), "Second publisher did not reach public acceptance"
                        assert (base / "pending.json").exists()
                    finally:
                        publisher.kill()
                        publisher.communicate(timeout=5)
                        faults.clear()
                        resume.set()
                refused = subprocess.run(installer, capture_output=True, text=True, timeout=10)
                assert refused.returncode != 0 and "Recover the interrupted site promotion" in refused.stderr
                recovered = subprocess.run(next_command, capture_output=True, text=True, timeout=10)
                assert recovered.returncode == 0, recovered.stderr
                assert not (base / "pending.json").exists()
                assert (base / "previous").resolve().name == "b" * 64
                control = subprocess.run(installer, capture_output=True, text=True, timeout=10)
                assert control.returncode != 0 and "absent-upload/release.tar.gz" in control.stderr
    finally:
        marker.unlink()
        if base.exists():
            shutil.rmtree(base)
    return {"passed": True, "shared_default_lock": "/var/lock/saga2d-online.publish.lock",
            "server_waited_through_site_acceptance": True, "interrupted_site_blocks_server_until_recovery": True,
            "server_activation_performed": False}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True, indent=2))
