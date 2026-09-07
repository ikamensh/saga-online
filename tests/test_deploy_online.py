"""Deployment preparation must run offline without opening cloud credentials."""
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import select

from tools.deploy_online import load_scaleway_key, firewall_ports


ROOT = Path(__file__).resolve().parents[2]


def test_plan_is_reviewable_without_credentials(tmp_path):
    """Operators can inspect the precise target without provisioning anything."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/deploy_online.py"), "plan",
         "--name", "saga2d-online", "--secrets-file", str(tmp_path / "absent")],
        check=True, capture_output=True, text=True,
    )
    plan = json.loads(result.stdout)
    assert plan["endpoint"] == "wss://games.tachyon-ai.eu/play"
    assert plan["instance"]["name"] == "saga2d-online"
    assert plan["instance"]["type"] == "DEV1-S"
    assert plan["secrets_on_server"] is False
    assert not list(tmp_path.iterdir())


def test_packaged_release_runs_server_entrypoint(tmp_path):
    """The artifact contains all game modules and runs away from the checkout."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/deploy_online.py"), "package",
         "--name", "saga2d-online", "--output", str(tmp_path)],
        check=True, capture_output=True, text=True,
    )
    package = json.loads(result.stdout)
    unpacked = tmp_path / "unpacked"
    with tarfile.open(package["archive"]) as archive:
        archive.extractall(unpacked, filter="data")
    subprocess.run([sys.executable, "-m", "online_server", "--help"],
                   cwd=unpacked, check=True, capture_output=True)
    subprocess.run(["bash", "-n", str(unpacked / "deploy/install.sh")], check=True)
    assert all((unpacked / game / "multiplayer.py").exists()
               for game in ["tribes", "warband", "eador"])
    assert not list(unpacked.rglob("*.md"))  # No local secret stores in artifacts.
    assert (unpacked / "deploy/requirements.txt").read_text().find("websockets==") >= 0
    with subprocess.Popen([sys.executable, "-m", "online_server", "--port", "0"],
                          cwd=unpacked, stdout=subprocess.PIPE, text=True) as process:
        try:
            readable, _, _ = select.select([process.stdout], [], [], 15)
            assert readable, "Packaged server failed to start"
            endpoint = process.stdout.readline().strip().removeprefix("LISTENING ") + "/play"
            subprocess.run([sys.executable, str(unpacked / "deploy/smoke.py"), endpoint],
                           cwd=unpacked, check=True, timeout=60, capture_output=True)
        finally:
            process.terminate()
            process.wait(timeout=10)


def test_credentials_selected_by_heading_not_file_order(tmp_path):
    """Adding unrelated keys cannot silently grant a deployment wider access."""
    path = tmp_path / "scaleway.md"
    path.write_text("## Personal admin key — laptop only\nKey ID: ADMIN\nSecret Key: top-secret\n"
                    "## saga2d-deploy\nProject ID: project-one\nKey ID: APP\nSecret Key: scoped-secret\n")
    key = load_scaleway_key(path, "saga2d-deploy")
    assert key.access_key == "APP"
    assert key.secret_key == "scoped-secret"
    assert key.project_id == "project-one"
    assert "scoped-secret" not in repr(key)


def test_provider_smtp_blocks_survive_game_firewall_setup():
    """New Scaleway groups contain immutable egress rules that aren't game ingress."""
    provider_rules = [dict(editable=False, action="drop", direction="outbound", protocol="TCP",
                           ip_range=address, dest_port_from=port, dest_port_to=None)
                      for address in ["0.0.0.0/0", "::/0"] for port in [25, 465, 587]]
    game_rule = dict(editable=True, action="accept", direction="inbound", protocol="TCP",
                     ip_range="0.0.0.0/0", dest_port_from=443, dest_port_to=None)
    assert firewall_ports(provider_rules + [game_rule]) == {443}
