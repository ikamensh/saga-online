"""Exercise both public websites through the production Caddy routing template."""
from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATHS = ("/play", "/healthz", "/server-compatibility.json", "/status",
                "/ratings", "/leaderboard", "/players/player-1", "/activity")


@contextmanager
def public_sites(tmp_path):
    """Run the shipped proxy with two local hosts and a real upstream HTTP server."""
    caddy = shutil.which("caddy")
    if caddy is None:
        pytest.skip("Native Caddy executable is required")

    class RoomServer(BaseHTTPRequestHandler):
        def do_GET(self):
            body = ("room server: " + self.path).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    website = tmp_path / "site"
    for name, body in {"index.html": "Games home", "warband-online/index.html": "Warband multiplayer",
                       "join/index.html": "Join a room", "static/warband.css": "Warband styles",
                       "images/warband.webp": "Warband art", "fonts/warband.woff2": "Warband font",
                       "status": "static impostor", "activity": "static impostor"}.items():
        path = website / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    with socket.socket() as games_port, socket.socket() as warband_port:
        games_port.bind(("127.0.0.1", 0))
        warband_port.bind(("127.0.0.1", 0))
        games = f"http://127.0.0.1:{games_port.getsockname()[1]}"
        warband = f"http://127.0.0.1:{warband_port.getsockname()[1]}"
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), RoomServer)
    worker = threading.Thread(target=upstream.serve_forever, kwargs={"poll_interval": .01})
    worker.start()
    config = tmp_path / "Caddyfile"
    config.write_text("{\n admin off\n auto_https off\n}\n" + (ROOT / "deploy/Caddyfile").read_text()
                      .replace("__DOMAIN__", games).replace("__WARBAND_DOMAIN__", warband)
                      .replace("127.0.0.1:8765", f"127.0.0.1:{upstream.server_port}")
                      .replace("/srv/saga2d-site/current", str(website)))
    environment = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "config"), "XDG_DATA_HOME": str(tmp_path / "data")}
    try:
        subprocess.run([caddy, "validate", "--adapter", "caddyfile", "--config", str(config)],
                       check=True, capture_output=True, env=environment)
        with (tmp_path / "caddy.log").open("w+") as log:
            process = subprocess.Popen([caddy, "run", "--adapter", "caddyfile", "--config", str(config)],
                                       stdout=log, stderr=log, env=environment)
            try:
                deadline = time.monotonic() + 5
                for host in (games, warband):
                    while True:
                        try:
                            with urlopen(host + "/healthz", timeout=.2) as response:
                                assert response.status == 200
                            break
                        except URLError:
                            if process.poll() is not None or time.monotonic() >= deadline:
                                log.seek(0)
                                pytest.fail("Public proxy did not start: " + log.read())
                            time.sleep(.02)
                yield games, warband
            finally:
                process.terminate()
                process.wait(timeout=5)
    finally:
        upstream.shutdown()
        worker.join(timeout=5)
        upstream.server_close()


def test_warband_home_and_assets_share_the_release_without_changing_games_home(tmp_path):
    """The dedicated hostname lands on multiplayer while the games catalog and shared assets still load."""
    with public_sites(tmp_path) as (games, warband):
        for host, path, body in ((games, "/", b"Games home"),
                                 (warband, "/", b"Warband multiplayer"),
                                 (games, "/join/warband-v2/ABC", b"Join a room"),
                                 (warband, "/static/warband.css", b"Warband styles"),
                                 (warband, "/images/warband.webp", b"Warband art"),
                                 (warband, "/fonts/warband.woff2", b"Warband font")):
            with urlopen(host + path, timeout=2) as response:
                if path == "/":
                    assert response.geturl() == host + path
                assert response.read() == body
                assert response.headers["Cache-Control"] == "public, max-age=300"


def test_live_routes_reach_the_running_server_on_both_hosts_without_static_caching(tmp_path):
    """MMR, player records and activity come from the live process even when static files shadow their names."""
    with public_sites(tmp_path) as hosts:
        for host in hosts:
            for path in ENGINE_PATHS:
                query = path + "?game=warband-v2&limit=100"
                with urlopen(host + query, timeout=2) as response:
                    assert response.read() == ("room server: " + query).encode()
                    assert response.headers["Cache-Control"] == "no-store"
