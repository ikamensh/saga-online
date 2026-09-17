"""Exercise the installed site publisher over real SSH on a disposable Linux host.

Run only inside a new test container or an isolated GitHub runner as root. This
uses production paths and refuses an already managed host. It is not a pytest
test and must never run on the production server.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_site_activation import public_site, site, promotion_receipt
from tests.test_site_receiver import upload


def run(command, **kwargs):
    result = subprocess.run(command, capture_output=True, timeout=30, **kwargs)
    assert result.returncode == 0, (command, result.stdout, result.stderr)
    return result


def verify():
    disposable = os.environ.get("GITHUB_ACTIONS") == "true" or Path("/.dockerenv").is_file()
    if sys.platform != "linux" or os.geteuid() != 0 or not disposable:
        raise RuntimeError("Run only as root on a disposable Linux acceptance host")
    marker = Path("/etc/saga2d-online/managed-instance")
    base = Path("/srv/saga2d-site")
    tools = Path("/usr/local/lib/saga2d-site-ci")
    if marker.exists() or base.exists() or tools.exists() or Path("/opt/saga2d-online/current").exists():
        raise RuntimeError("Refusing an already managed host")
    marker.parent.mkdir(exist_ok=True)
    marker.parent.chmod(0o755)
    marker.write_text("saga2d-ci\n")
    Path("/run/sshd").mkdir(exist_ok=True)
    # Installation/publication must remain readable by SSH/Caddy even when
    # the trusted operator uses a restrictive umask for private material.
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix="site-ssh-acceptance-") as temporary:
        folder = Path(temporary)
        key, host_key = folder / "client", folder / "host"
        for path in (key, host_key):
            run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path)])
        source = site(folder, "candidate")
        private = Path("/var/lib/saga2d-online")
        private.mkdir(mode=0o700)
        checkpoint = private / "checkpoint.json"
        checkpoint.write_text("private checkpoint must survive unchanged")
        # Even executable-looking website content is inert upload data.
        (source / "install_site.sh").write_text(f"#!/bin/sh\nprintf compromised > {checkpoint}\n")
        baseline = {"schema_version": 1, "deployment_release": "d" * 64}
        payload, release = upload(source, promotion_receipt(source, baseline))
        faults = {"baseline": baseline}
        with public_site(base, faults) as endpoint:
            package = json.loads(run([sys.executable, str(ROOT / "tools/deploy_online.py"), "package-site-ci", "--name", "saga2d-ci",
                                      "--site-public-key", str(key.with_suffix(".pub")), "--output", str(folder / "packages")]).stdout)
            uploaded_tools = folder / "uploaded-tools"
            with tarfile.open(package["archive"]) as bundle:
                bundle.extractall(uploaded_tools, filter="data")
            setup = [sys.executable, str(uploaded_tools / "install_site_ci.py"), "--instance", "saga2d-ci",
                     "--public-key", str(uploaded_tools / "site-ci.pub"), "--public-url", endpoint]
            installed = json.loads(run(setup).stdout)
            assert json.loads(run(setup).stdout) == installed, "Setup must be repeatable"
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            config = folder / "sshd_config"
            config.write_text(f"Port {port}\nListenAddress 127.0.0.1\nHostKey {host_key}\n"
                              f"PidFile {folder / 'sshd.pid'}\nUsePAM yes\nPasswordAuthentication no\n"
                              "PermitRootLogin no\nStrictModes yes\nLogLevel VERBOSE\n"
                              "Subsystem sftp internal-sftp\nInclude /etc/ssh/sshd_config.d/00-saga-site-ci.conf\n")
            known_hosts = folder / "known_hosts"
            known_hosts.write_text(f"[127.0.0.1]:{port} {host_key.with_suffix('.pub').read_text()}")
            ssh = ["ssh", "-F", "/dev/null", "-T", "-i", str(key), "-p", str(port), "-o", "BatchMode=yes",
                   "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=5",
                   "-o", f"UserKnownHostsFile={known_hosts}", "-o", "GlobalKnownHostsFile=/dev/null"]
            target = "saga2d-site-ci@127.0.0.1"
            client = [sys.executable, str(ROOT / "tools/site_publish.py"), "--host", "127.0.0.1", "--port", str(port),
                      "--identity", str(key), "--known-hosts", str(known_hosts)]
            archive = folder / "site.tar.gz"
            archive.write_bytes(payload.split(b"\n", 1)[1])
            publish = [*client, "publish", "--archive", str(archive), "--generation", "1", "--expected", "none"]
            with (folder / "sshd.log").open("w+") as log:
                with subprocess.Popen(["/usr/sbin/sshd", "-D", "-e", "-f", str(config)], stdout=log, stderr=log) as daemon:
                    try:
                        deadline = time.monotonic() + 10
                        while True:
                            assert daemon.poll() is None, (folder / "sshd.log").read_text()
                            try:
                                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                                    break
                            except ConnectionRefusedError:
                                assert time.monotonic() < deadline, "SSH daemon did not listen"
                                time.sleep(.05)
                        initial = json.loads(run([*client, "status"]).stdout)
                        assert initial == {"schema_version": 1, "accepted": {"release": "none", "generation": 0}, "pending": False}
                        first = json.loads(run(publish).stdout)
                        assert first["release"] == release and first["generation"] == 1
                        assert json.loads(run(publish).stdout) == first
                        assert json.loads(run([*ssh, target, "status"], input=b"").stdout)["accepted"] == first
                        public_bytes = run(["runuser", "-u", "nobody", "--", "cat", str(base / "current/warband/index.html")]).stdout
                        assert public_bytes == (source / "warband/index.html").read_bytes()
                        for original in ("", "sh", "status; touch /tmp/ci-command-escape", "publish extra", "cat /etc/shadow"):
                            rejected = subprocess.run([*ssh, target, original], input=b"", capture_output=True, timeout=10)
                            assert rejected.returncode != 0 and b"Only status and publish" in rejected.stderr, (original, rejected.returncode, rejected.stdout, rejected.stderr)
                        assert not Path("/tmp/ci-command-escape").exists()
                        # A real SFTP INIT must not receive a protocol response.
                        rejected = subprocess.run([*ssh, "-s", target, "sftp"], input=b"\x00\x00\x00\x05\x01\x00\x00\x00\x03",
                                                  capture_output=True, timeout=10)
                        assert rejected.returncode != 0 and rejected.stdout == b"", (rejected.returncode, rejected.stdout, rejected.stderr)
                        for forwarding in (["-N", "-R", "0:127.0.0.1:80", "-o", "ExitOnForwardFailure=yes"],
                                           ["-W", "127.0.0.1:80"]):
                            rejected = subprocess.run([*ssh, *forwarding, target], input=b"", capture_output=True, timeout=10)
                            assert rejected.returncode != 0 and (b"forwarding failed" in rejected.stderr or b"administratively prohibited" in rejected.stderr)
                        wrong_hosts = folder / "wrong_hosts"
                        wrong_hosts.write_text(f"[127.0.0.1]:{port} {key.with_suffix('.pub').read_text()}")
                        wrong_client = [str(wrong_hosts) if part == str(known_hosts) else part for part in client]
                        rejected = subprocess.run([*wrong_client, "status"], capture_output=True, timeout=10)
                        assert rejected.returncode != 0 and b"Host key verification failed" in rejected.stderr
                        for protected in (tools, tools / "current/site_receiver.py", Path("/etc/saga2d-online/site-ci-authorized-keys"),
                                          Path("/var/lib/saga2d-site-ci"), checkpoint):
                            assert subprocess.run(["runuser", "-u", "saga2d-site-ci", "--", "test", "-w", str(protected)]).returncode != 0
                        assert subprocess.run(["runuser", "-u", "saga2d-site-ci", "--", "test", "-r", str(checkpoint)]).returncode != 0
                        assert subprocess.run(["runuser", "-u", "saga2d-site-ci", "--", "sudo", "-n", "true"], capture_output=True).returncode != 0
                        rejected = subprocess.run([*ssh, target, "publish"], input=b"invalid header\n", capture_output=True, timeout=10)
                        assert rejected.returncode != 0
                        replacement = site(folder, "replacement")
                        replacement_payload, replacement_release = upload(replacement, promotion_receipt(replacement, baseline),
                                                                          generation=2, expected=release)
                        archive.write_bytes(replacement_payload.split(b"\n", 1)[1])
                        next_publish = [*client, "publish", "--archive", str(archive), "--generation", "2", "--expected", release]
                        faults["baseline"] = {**baseline, "deployment_release": "e" * 64}
                        rejected = subprocess.run(next_publish, capture_output=True, timeout=15)
                        assert rejected.returncode != 0 and b"Live server differs" in rejected.stderr
                        faults["baseline"] = baseline
                        faults["health"] = True
                        rejected = subprocess.run(next_publish, capture_output=True, timeout=15)
                        assert rejected.returncode != 0 and b"Room server health check failed" in rejected.stderr
                        assert json.loads(run([*client, "status"]).stdout) == {"schema_version": 1, "accepted": first, "pending": False}
                        assert (base / "current/index.html").read_bytes() == (source / "index.html").read_bytes()
                        del faults["health"]
                        assert json.loads(run(next_publish).stdout)["release"] == replacement_release
                        assert (base / "previous").resolve().name == release
                        assert checkpoint.read_text() == "private checkpoint must survive unchanged"
                    finally:
                        daemon.terminate()
                        daemon.wait(timeout=10)
    return {"passed": True, "real_ssh_publish_retry": True, "separate_public_reader": True,
            "host_setup_repeatable": True, "command_subsystem_forwarding_refused": True,
            "wrong_host_key_refused": True, "server_files_private_and_unchanged": True,
            "compatibility_failure_preserves_site": True, "public_failure_rolls_back": True}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True, indent=2))
