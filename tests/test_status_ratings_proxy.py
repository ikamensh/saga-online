"""Public engine routes stay on the room server, never the static site fallback."""
from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CADDYFILE = ROOT / "deploy" / "Caddyfile"

ENGINE_PATHS = ("/play", "/healthz", "/server-compatibility.json",
                "/status", "/ratings", "/players/*")


def routes_of(matcher: str) -> list[str]:
    """Split a Caddy path matcher line into its route tokens."""
    return matcher.replace(",", " ").split()


def test_engine_routes_proxy_to_the_room_server():
    """Every engine route (play, health, compat, status, ratings, players) hits upstream."""
    text = CADDYFILE.read_text()
    server = next(line for line in text.splitlines()
                  if line.strip().startswith("@server path"))
    assert set(ENGINE_PATHS) <= set(routes_of(server.split("path", 1)[1])), server
    assert "reverse_proxy @server 127.0.0.1:8765" in text


def test_engine_routes_bypass_static_site_caching_and_fallback():
    """Static cache headers and invitation rewrites must not swallow engine routes."""
    text = CADDYFILE.read_text()
    static = next(line for line in text.splitlines()
                  if line.strip().startswith("@static not path"))
    assert set(ENGINE_PATHS) <= set(routes_of(static.split("path", 1)[1])), static
    assert re.search(r"(?m)^\s*root \* /srv/saga2d-site/current\s*$", text)
    caddy = shutil.which("caddy")
    if caddy is None:
        return
    rendered = text.replace("__DOMAIN__", "games.example.test")
    subprocess.run([caddy, "validate", "--adapter", "caddyfile", "--config", "/dev/stdin"],
                   input=rendered, text=True, check=True, capture_output=True)
