"""Exercise the restricted server-CI account over real SSH and sudo on a disposable Linux host.

    sudo env GITHUB_ACTIONS=true .venv/bin/python -B tests/host_server_ci.py RELEASE.json PROBE.json HOST_CHANGE.json

Each argument is the JSON ``deploy_online.py package`` printed: the release the
Tests workflow already prepared, another release of the same sources, and one
whose proxy configuration differs. Installs the account with the operator's
setup program, then through the CI client alone: activates both releases on the
runner's systemd, rolls back to the first, refuses the host change, stale
expectations and every command outside the four. Uses production paths; run
only as root on an isolated GitHub runner after host_site_ssh.py, never on the
production server. Not collected by pytest.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
from types import SimpleNamespace
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import server_rollout

INSTANCE, DOMAIN = "saga2d-ci", "games.example.test"
TOOLS = Path("/usr/local/lib/saga2d-server-ci")
BASE = Path("/opt/saga2d-online")


def run(command, **kwargs):
    result = subprocess.run(command, capture_output=True, timeout=600, **kwargs)
    assert result.returncode == 0, (command, result.stdout, result.stderr)
    return result


def served():
    with urlopen("http://127.0.0.1:8765/server-compatibility.json", timeout=10) as response:
        return json.load(response)["deployment_release"]


def refused(action, text):
    try:
        action()
    except ValueError:
        pass
    else:
        raise AssertionError(f"Expected a refusal: {text}")


@contextmanager
def sshd(folder, host_key):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    config = folder / "sshd_config"
    config.write_text(f"Port {port}\nListenAddress 127.0.0.1\nHostKey {host_key}\nPidFile {folder / 'sshd.pid'}\n"
                      "UsePAM yes\nPasswordAuthentication no\nPermitRootLogin no\nStrictModes yes\nLogLevel VERBOSE\n"
                      "Include /etc/ssh/sshd_config.d/00-saga-server-ci.conf\n")
    Path("/run/sshd").mkdir(exist_ok=True)
    with (folder / "sshd.log").open("w+") as log, \
            subprocess.Popen(["/usr/sbin/sshd", "-D", "-e", "-f", str(config)], stdout=log, stderr=log) as daemon:
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
            yield port
        finally:
            daemon.terminate()
            daemon.wait(timeout=10)


def verify(release, probe, host_change):
    if sys.platform != "linux" or os.geteuid() != 0 or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Run only as root on an isolated GitHub Linux acceptance runner")
    marker = Path("/etc/saga2d-online/managed-instance")
    if (marker.exists() and marker.read_text().strip() != INSTANCE) or (BASE / "current").exists() or TOOLS.exists():
        raise RuntimeError("Refusing an already managed host")
    marker.parent.mkdir(exist_ok=True)
    marker.write_text(INSTANCE + "\n")
    first, second, changed = (json.loads(Path(path).read_bytes()) for path in (release, probe, host_change))
    assert len({first["release"], second["release"], changed["release"]}) == 3
    with tempfile.TemporaryDirectory(prefix="server-ci-acceptance-") as temporary:
        folder = Path(temporary)
        folder.chmod(0o755)
        key, host_key = folder / "client", folder / "host"
        for path in (key, host_key):
            run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path)])
        package = json.loads(run([sys.executable, str(ROOT / "tools/deploy_online.py"), "package-server-ci", "--name", INSTANCE,
                                  "--server-public-key", str(key.with_suffix(".pub")), "--output", str(folder / "packages")]).stdout)
        uploaded = folder / "uploaded-tools"
        with tarfile.open(package["archive"]) as bundle:
            bundle.extractall(uploaded, filter="data")
        setup = [sys.executable, str(uploaded / "install_server_ci.py"), "--instance", INSTANCE, "--domain", DOMAIN,
                 "--public-key", str(uploaded / "server-ci.pub")]
        installed = json.loads(run(setup).stdout)
        assert json.loads(run(setup).stdout) == installed, "Setup must be repeatable"
        with sshd(folder, host_key) as port:
            known_hosts = folder / "known_hosts"
            known_hosts.write_text(f"[127.0.0.1]:{port} {host_key.with_suffix('.pub').read_text()}")
            client = SimpleNamespace(host="127.0.0.1", port=port, identity=key, known_hosts=known_hosts)

            def host(operation, **fields):
                return server_rollout.host_command(SimpleNamespace(**vars(client), operation=operation, **fields))

            before = host("status")
            assert before["current"] is None and before["service"] != "active", before
            archive = lambda package: Path(package["archive"])
            activated = host("install", archive=archive(first), expected_current="none")
            assert activated["current"] == served() == first["release"] and activated["health"] == "ok"
            refused(lambda: host("install", archive=archive(second), expected_current="0" * 64), "stale expected release")
            assert served() == first["release"]
            activated = host("install", archive=archive(second), expected_current=first["release"])
            assert (activated["current"], activated["previous"]) == (second["release"], first["release"]) == (served(), first["release"])
            backup = host("backup", output=folder / "backups")
            assert backup["rooms"] >= 0 and Path(backup["path"]).stat().st_mode & 0o777 == 0o600
            refused(lambda: host("rollback", rollback_from=first["release"]), "rollback from a release that is not current")
            restored = host("rollback", rollback_from=second["release"])
            assert (restored["current"], restored["previous"]) == (first["release"], second["release"]), restored
            assert served() == first["release"] and restored["attestation"]["deployment_release"] == first["release"]
            refused(lambda: host("install", archive=archive(changed), expected_current=first["release"]), "host change")
            assert served() == first["release"] and not (BASE / "releases" / changed["release"] / ".ready").exists()
            # Re-activating the running release keeps the distinct one behind it for rollback.
            again = host("install", archive=archive(first), expected_current=first["release"])
            assert (again["current"], again["previous"]) == (first["release"], second["release"])

            ssh = ["ssh", "-F", "/dev/null", "-T", "-i", str(key), "-p", str(port), "-o", "BatchMode=yes",
                   "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known_hosts}",
                   "-o", "GlobalKnownHostsFile=/dev/null", "saga2d-server-ci@127.0.0.1"]
            for original in ("", "sh", "status; touch /tmp/server-ci-escape", "install extra", "run status", "cat /etc/shadow"):
                rejected = subprocess.run([*ssh, original], input=b"", capture_output=True, timeout=30)
                assert rejected.returncode != 0 and b"Only status, backup, install and rollback" in rejected.stderr, (original, rejected)
            assert not Path("/tmp/server-ci-escape").exists()
            for forwarding in (["-N", "-R", "0:127.0.0.1:80", "-o", "ExitOnForwardFailure=yes"], ["-W", "127.0.0.1:80"]):
                rejected = subprocess.run([*ssh[:-1], *forwarding, ssh[-1]], input=b"", capture_output=True, timeout=30)
                assert rejected.returncode != 0
            as_ci = ["runuser", "-u", "saga2d-server-ci", "--"]
            for command in (["sudo", "-n", "true"], ["sudo", "-n", str(TOOLS / "run"), "shell"],
                            ["sudo", "-n", str(TOOLS / "run")], ["sudo", "-n", "bash", str(TOOLS / "current/install.sh")]):
                assert subprocess.run([*as_ci, *command], capture_output=True, timeout=30).returncode != 0, command
            for protected in (TOOLS, TOOLS / "run", TOOLS / "current/server_ci.py", TOOLS / "current/install.sh",
                              Path("/etc/sudoers.d/saga2d-server-ci"), Path("/etc/saga2d-online/server-ci-authorized-keys"),
                              BASE / "current", Path("/var/lib/saga2d-server-ci")):
                assert subprocess.run([*as_ci, "test", "-w", str(protected)]).returncode != 0, protected
            for private in ("/var/lib/saga2d-online", "/var/backups/saga2d-online"):
                assert subprocess.run([*as_ci, "ls", private], capture_output=True).returncode != 0, private
    return {"passed": True, "sudo": installed["sudo"], "setup_repeatable": True, "install_over_ssh": True,
            "stale_expectation_refused": True, "backup_streamed": True, "rollback_restored_previous": True,
            "host_change_refused_before_preparation": True, "reactivation_keeps_previous": True,
            "commands_outside_four_refused": True, "no_general_sudo": True, "tools_not_writable": True}


if __name__ == "__main__":
    print(json.dumps(verify(*sys.argv[1:4]), sort_keys=True, indent=2))
