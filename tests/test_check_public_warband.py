"""The rollout's public-server check outlasts a runner that briefly cannot resolve the site, and nothing else."""

import io
import json
import socket
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import check_public_warband  # noqa: E402


def lookups(monkeypatch, failures):
    """The site answers after *failures*, each raised in turn; returns the waits slept between tries."""
    pending = list(failures)
    waits = []

    def urlopen(url, timeout):
        if pending:
            raise pending.pop(0)
        return io.BytesIO(json.dumps({"url": url}).encode())

    monkeypatch.setattr(check_public_warband.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(check_public_warband.time, "sleep", waits.append)
    return waits


def test_a_name_the_runner_cannot_resolve_yet_is_asked_again(monkeypatch):
    """Rollouts 36940296319 (Windows), 36942292736, 36991524222 and 36995987201 (macOS) were rolled back because
    the runner's first lookup of the site failed, though its DNS answered everywhere else."""
    unresolved = urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided, or not known"))
    waits = lookups(monkeypatch, [unresolved, unresolved])
    path = "/server-compatibility.json"
    assert check_public_warband.public_json(path) == {"url": check_public_warband.SITE + path}
    assert len(waits) == 2


def test_a_site_that_never_resolves_still_fails_and_other_failures_fail_at_once(monkeypatch):
    unresolved = urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))
    lookups(monkeypatch, [unresolved] * 20)
    with pytest.raises(urllib.error.URLError):
        check_public_warband.public_json("/releases.json")
    waits = lookups(monkeypatch, [urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))])
    with pytest.raises(urllib.error.URLError):
        check_public_warband.public_json("/releases.json")
    assert waits == []
