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


def test_site_release_bundles_built_pages_with_its_installer(tmp_path):
    """Publishing needs a finished build; the archive is content-addressed and self-contained."""
    from tools.deploy_online import package_site

    site = tmp_path / "site"
    (site / "warband").mkdir(parents=True)
    with __import__("pytest").raises(FileNotFoundError, match="index.html"):
        package_site(site, tmp_path / "out")
    (site / "index.html").write_text("<h1>Games</h1>")
    (site / "releases.json").write_text("{}")
    (site / "warband" / "index.html").write_text("<h1>Warband</h1>")
    first = package_site(site, tmp_path / "out")
    assert first["files"] == 3 and first["release"] in first["archive"]
    assert package_site(site, tmp_path / "out")["release"] == first["release"]
    unpacked = tmp_path / "unpacked"
    with tarfile.open(first["archive"]) as archive:
        archive.extractall(unpacked, filter="data")
    assert (unpacked / "site/warband/index.html").read_text() == "<h1>Warband</h1>"
    subprocess.run(["bash", "-n", str(unpacked / "deploy/install_site.sh")], check=True)
    (site / "index.html").write_text("<h1>Changed</h1>")
    assert package_site(site, tmp_path / "out")["release"] != first["release"]


def test_proxy_configuration_keeps_play_and_health_on_the_room_server():
    """The static site never shadows the WebSocket endpoint or liveness probe."""
    import shutil
    caddyfile = (ROOT / "deploy/Caddyfile").read_text().replace("__DOMAIN__", "games.example.test")
    assert "@server path /play /healthz" in caddyfile and "reverse_proxy @server 127.0.0.1:8765" in caddyfile
    assert "root * /srv/saga2d-site/current" in caddyfile and "rewrite @invite /join/index.html" in caddyfile
    caddy = shutil.which("caddy")
    if caddy:
        subprocess.run([caddy, "validate", "--adapter", "caddyfile", "--config", "/dev/stdin"],
                       input=caddyfile, text=True, check=True, capture_output=True)


def test_backup_is_a_consistent_copy_with_rotation(tmp_path):
    """The timer's script uses SQLite's backup API on a live WAL database and prunes old files."""
    import sqlite3
    from datetime import datetime, timedelta, timezone
    import runpy

    backup = runpy.run_path(str(ROOT / "deploy/backup.py"))["backup"]
    database = tmp_path / "rooms.sqlite3"
    live = sqlite3.connect(database)
    live.execute("PRAGMA journal_mode=WAL")
    live.execute("CREATE TABLE rooms (code TEXT PRIMARY KEY, game TEXT, tokens TEXT, state TEXT, revision INTEGER, expires_at REAL)")
    live.execute("INSERT INTO rooms VALUES ('abc', 'tribes-v1', '[]', '{}', 1, 9e12)")
    live.commit()
    folder = tmp_path / "backups"
    stale = folder / ("rooms-" + (datetime.now(timezone.utc) - timedelta(days=20)).strftime("%Y%m%dT%H%M%SZ") + ".sqlite3")
    folder.mkdir()
    stale.write_bytes(b"old")
    target = backup(database, folder)
    assert target.stat().st_mode & 0o777 == 0o600 and not stale.exists()
    copy = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    assert copy.execute("SELECT code FROM rooms").fetchall() == [("abc",)]
    live.execute("INSERT INTO rooms VALUES ('def', 'tribes-v1', '[]', '{}', 1, 9e12)")
    live.commit()
    assert copy.execute("SELECT count(*) FROM rooms").fetchone() == (1,)  # A snapshot, not a live view.
    copy.close()
    live.close()
