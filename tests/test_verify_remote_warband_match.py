"""Two-VM acceptance harness: orchestration, cleanup and ranked receipt checks.

The harness is driven through its real CLI against a stub helper executable
standing in for ``tools/remote_warband_ai.py`` at a subprocess boundary; the
stub replays realistic ``status --json`` documents. Public route correlation
is checked against a real local HTTP server. No cloud money is spent.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "verify_remote_warband_match.py"

PUBLIC_SERVER = "wss://games.tachyon-ai.eu/play"

HOST_STATUS = {
    "target": "saga2d-warband-ai-host", "service": "saga2d-warband-ai", "active": True,
    "systemd": {"ActiveState": "active"}, "invocation_id": "HOST-1",
    "room": "MATCH01", "player": 0, "difficulty": "medium",
    "finished": True, "reason": "winner", "winner": 0, "tick": 5400,
    "states_received": 40, "orders_submitted": 120, "reconnects_observed": 0,
    "player_id": "player-host",
    "result": None, "journal_lines": 40, "journal_kept": 12,
}
GUEST_STATUS = {
    "target": "saga2d-warband-ai-guest", "service": "saga2d-warband-ai", "active": True,
    "systemd": {"ActiveState": "active"}, "invocation_id": "GUEST-1",
    "room": "MATCH01", "player": 1, "difficulty": "medium",
    "finished": True, "reason": "winner", "winner": 0, "tick": 5390,
    "states_received": 38, "orders_submitted": 100, "reconnects_observed": 1,
    "player_id": "player-guest",
    "rejoin_continuity": {"player": 1, "before_tick": 100, "tick": 130,
                          "before_units": [11], "units": [11, 12],
                          "before_buildings": [], "buildings": [21]},
    "result": None, "journal_lines": 38, "journal_kept": 11,
}
RATED_RESULT = {
    "match_id": "match-42", "winner": 0,
    "ratings": [
        {"player_id": "player-host", "name": "HostBot", "before": 1000, "after": 1016,
         "delta": 16, "games": 5, "wins": 3, "losses": 2},
        {"player_id": "player-guest", "name": "GuestBot", "before": 1000, "after": 984,
         "delta": -16, "games": 5, "wins": 2, "losses": 3},
    ],
}


def write_stub(path: Path, *, host=None, guest=None, fail_on=(), fail_stop=()) -> Path:
    """A stub helper CLI: create/join record starts, status replays, stop records."""
    helper = path / "stub_helper.py"
    scenario = {"host": host or HOST_STATUS, "guest": guest or GUEST_STATUS,
                "fail_on": list(fail_on), "fail_stop": list(fail_stop)}
    (path / "scenario.json").write_text(json.dumps(scenario))
    helper.write_text("#!/usr/bin/env python3\n" + """\
import json, sys
from pathlib import Path
root = Path(__file__).parent
scenario = json.loads((root / "scenario.json").read_text())
args = sys.argv[1:]
command = args[0] if args else ""
def flag(name):
    return args[args.index(name) + 1] if name in args else ""
side = "guest" if "guest" in (flag("--target") + flag("--player-name")) else "host"
if command in ("create", "join"):
    if side in scenario["fail_on"]:
        print(f"stub: {side} failed to start", file=sys.stderr)
        raise SystemExit(1)
    with (root / "started.log").open("a") as handle:
        handle.write(side + " " + " ".join(args[1:]) + "\\n")
    print(f"stub {side} started")
elif command == "status":
    print(json.dumps(scenario[side]))
elif command == "stop":
    if side in scenario["fail_stop"]:
        print(f"stub: {side} failed to stop", file=sys.stderr)
        raise SystemExit(1)
    with (root / "stopped.log").open("a") as handle:
        handle.write(side + "\\n")
    print(f"stub {side} stopped")
else:
    raise SystemExit(2)
""")
    helper.chmod(0o755)
    return helper


def write_targets(path: Path) -> tuple[Path, Path]:
    host = path / "host.json"
    host.write_text(json.dumps({"name": "saga2d-warband-ai-host", "ip": "10.0.0.11",
                                "server_id": "srv-host"}) + "\n")
    guest = path / "guest.json"
    guest.write_text(json.dumps({"name": "saga2d-warband-ai-guest", "ip": "10.0.0.12",
                                 "server_id": "srv-guest"}) + "\n")
    return host, guest


def run_harness(path: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HARNESS), *argv], capture_output=True, text=True,
                          cwd=str(path), timeout=120)


def base_argv(path: Path, helper: Path, host: Path, guest: Path) -> list[str]:
    return ["--host-target", str(host), "--guest-target", str(guest), "--server", PUBLIC_SERVER,
            "--output", str(path / "out"), "--helper", str(helper),
            "--poll-every", "0.05", "--wait-timeout", "10", "--timeout", "30"]


def test_same_vm_rejected_without_starting_anything(tmp_path):
    """Two seats on one VM (same id and IP) cannot host a two-machine match."""
    helper = write_stub(tmp_path)
    host, _ = write_targets(tmp_path)
    twin = tmp_path / "twin.json"
    twin.write_text((tmp_path / "host.json").read_text())
    result = run_harness(tmp_path, *base_argv(tmp_path, helper, host, twin))
    assert result.returncode == 2
    assert not (tmp_path / "started.log").exists()


def test_loopback_server_refused_without_starting_anything(tmp_path):
    """The harness only runs against the public TLS endpoint players use."""
    helper = write_stub(tmp_path)
    host, guest = write_targets(tmp_path)
    argv = base_argv(tmp_path, helper, host, guest)
    argv[argv.index("--server") + 1] = "ws://127.0.0.1:9999/play"
    result = run_harness(tmp_path, *argv)
    assert result.returncode == 2
    assert not (tmp_path / "started.log").exists()


def test_completed_match_with_rejoin_passes_and_cleans_up_owned_services(tmp_path):
    """Winner (not duration), same room, opposite seats, tick/order progress, rejoin."""
    helper = write_stub(tmp_path)
    host, guest = write_targets(tmp_path)
    result = run_harness(tmp_path, *base_argv(tmp_path, helper, host, guest))
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "passed" and report["winner"] == 0
    assert report["room"] == "MATCH01" and sorted(report["seats"]) == [0, 1]
    assert report["guest_rejoined"] is True
    assert "winner 0" in result.stdout
    stopped = (tmp_path / "stopped.log").read_text()
    assert "host" in stopped and "guest" in stopped


def test_duration_without_winner_is_failed_never_complete(tmp_path):
    """A bot that only ran out its clock must not read as a completed match."""
    host = dict(HOST_STATUS, finished=True, reason="duration", winner=None, tick=1800)
    guest = dict(GUEST_STATUS, finished=True, reason="duration", winner=None, tick=1790)
    helper = write_stub(tmp_path, host=host, guest=guest)
    targets = write_targets(tmp_path)
    result = run_harness(tmp_path, *base_argv(tmp_path, helper, *targets))
    assert result.returncode == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "failed" and "winner" not in report
    assert "duration" in report["error"].lower()


def test_timeout_while_waiting_is_failed_and_still_stops_owned_services(tmp_path):
    """A guest that never reaches terminal fails the run but is still stopped."""
    guest = dict(GUEST_STATUS, finished=False, reason=None, winner=None, tick=10,
                 orders_submitted=0, reconnects_observed=0)
    helper = write_stub(tmp_path, guest=guest)
    targets = write_targets(tmp_path)
    argv = base_argv(tmp_path, helper, *targets)
    argv[argv.index("--timeout") + 1] = "1"
    result = run_harness(tmp_path, *argv)
    assert result.returncode == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "failed" and "timed out" in report["error"].lower()
    stopped = (tmp_path / "stopped.log").read_text()
    assert "host" in stopped and "guest" in stopped


def test_start_failure_stops_only_the_service_this_run_started(tmp_path):
    """A guest that never starts leaves the host stopped and the run failed."""
    helper = write_stub(tmp_path, fail_on=("guest",))
    targets = write_targets(tmp_path)
    result = run_harness(tmp_path, *base_argv(tmp_path, helper, *targets))
    assert result.returncode == 1
    stopped = (tmp_path / "stopped.log").read_text()
    assert "host" in stopped and "guest" not in stopped


def write_identity(path: Path, name: str, secret: str = "PRIVATE-IDENTITY-BYTES") -> Path:
    identity = path / name
    identity.write_text(secret + "\n")
    identity.chmod(0o600)
    return identity


@pytest.fixture()
def public_routes(tmp_path):
    """Local file stand-ins for the public status/ratings routes (no sockets needed)."""
    base = tmp_path / "routes"
    (base / "players").mkdir(parents=True)
    (base / "players" / "player-host.json").write_text(json.dumps(
        {"player_id": "player-host", "name": "HostBot", "rating": 1016,
         "games": 5, "wins": 3, "losses": 2}))
    (base / "players" / "player-guest.json").write_text(json.dumps(
        {"player_id": "player-guest", "name": "GuestBot", "rating": 984,
         "games": 5, "wins": 2, "losses": 3}))
    (base / "ratings.json").write_text(json.dumps(
        {"game": "warband-v2",
         "players": [{"player_id": "player-host", "name": "HostBot", "rating": 1016,
                      "games": 5, "wins": 3, "losses": 2},
                     {"player_id": "player-guest", "name": "GuestBot", "rating": 984,
                      "games": 5, "wins": 2, "losses": 3}]}))
    (base / "status.json").write_text(json.dumps(
        {"protocol": "warband-v2", "games": ["warband-v2"], "rooms": 1, "ready_rooms": 0,
         "players": 2, "max_rooms": 100, "max_connections": 200,
         "room_retention": 900, "campaign_retention": 3600, "rated_grace": 60,
         "ratings": {"warband-v2": {"enabled": True, "seats": [2, 3, 4],
                                    "starting_rating": 1500}}}))
    yield f"file://{base}"


def rated_argv(path, helper, host, guest, routes):
    host_id = write_identity(path, "host.identity", "HOST-SECRET-AAA")
    guest_id = write_identity(path, "guest.identity", "GUEST-SECRET-BBB")
    return [*base_argv(path, helper, host, guest), "--rated",
            "--host-player-name", "HostBot", "--guest-player-name", "GuestBot",
            "--host-identity-file", str(host_id), "--guest-identity-file", str(guest_id),
            "--status-base", routes]


def test_rated_run_without_receipt_reports_ignored_ranked_options(tmp_path):
    """A ranked run whose engine ignored the ranked flags fails loudly, not silently."""
    helper = write_stub(tmp_path)
    targets = write_targets(tmp_path)
    argv = [*base_argv(tmp_path, helper, *targets), "--rated",
            "--host-player-name", "HostBot", "--guest-player-name", "GuestBot"]
    result = run_harness(tmp_path, *argv)
    assert result.returncode == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "failed"
    assert "ranked" in report["error"].lower() and "receipt" in report["error"].lower()


def test_rated_run_validates_receipt_deltas_and_public_routes(tmp_path, public_routes):
    """Ranked completion correlates receipt names/deltas with the public player routes."""
    host = dict(HOST_STATUS, result=RATED_RESULT)
    guest = dict(GUEST_STATUS, result=RATED_RESULT)
    helper = write_stub(tmp_path, host=host, guest=guest)
    targets = write_targets(tmp_path)
    result = run_harness(tmp_path, *rated_argv(tmp_path, helper, *targets, public_routes))
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "passed" and report["match_id"] == "match-42"
    assert report["ratings"]["deltas"] == {"HostBot": 16, "GuestBot": -16}
    assert report["public_routes"]["checked"] is True
    assert report["public_routes"]["players"] == {"player-host": 1016, "player-guest": 984}
    started = (tmp_path / "started.log").read_text()
    assert "--rated" in started and "--player-name HostBot" in started
    assert "--player-name GuestBot" in started
    combined = result.stdout + result.stderr + (tmp_path / "out" / "report.json").read_text()
    assert "HOST-SECRET-AAA" not in combined and "GUEST-SECRET-BBB" not in combined


def test_rated_run_rejects_inconsistent_delta_receipt(tmp_path, public_routes):
    """A receipt whose deltas do not net to zero fails the ranked run."""
    bad = dict(RATED_RESULT, ratings=[dict(RATED_RESULT["ratings"][0]),
                                      dict(RATED_RESULT["ratings"][1], after=990, delta=-10)])
    host = dict(HOST_STATUS, result=bad)
    guest = dict(GUEST_STATUS, result=bad)
    helper = write_stub(tmp_path, host=host, guest=guest)
    targets = write_targets(tmp_path)
    result = run_harness(tmp_path, *rated_argv(tmp_path, helper, *targets, public_routes))
    assert result.returncode == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "failed" and "delta" in report["error"].lower()


def crashed_host(error=None, exit_status=0):
    systemd = {"ActiveState": "inactive", "SubState": "dead", "ExecMainStatus": exit_status}
    status = dict(HOST_STATUS, active=False, systemd=systemd, finished=False, reason=None,
                  winner=None, tick=0, orders_submitted=0, states_received=0, result=None,
                  reconnects_observed=0, rejoin_continuity=None)
    if error is not None:
        status["error"] = error
    return status


def test_crashed_bot_fails_promptly_without_waiting_out_timeout(tmp_path):
    """A bot dead on arrival fails on its reported error, not after the timeout."""
    helper = write_stub(tmp_path, host=crashed_host(error="boom went the bot"))
    targets = write_targets(tmp_path)
    argv = base_argv(tmp_path, helper, *targets)
    argv[argv.index("--timeout") + 1] = "30"
    result = run_harness(tmp_path, *argv)
    assert result.returncode == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "failed" and "boom went the bot" in report["error"]
    assert report["elapsed_seconds"] < 10
    assert "host" in (tmp_path / "stopped.log").read_text()


def test_nonzero_exit_without_terminal_event_fails_promptly(tmp_path):
    """A signal death with no finished event fails on its exit status."""
    helper = write_stub(tmp_path, host=crashed_host(exit_status=2))
    targets = write_targets(tmp_path)
    result = run_harness(tmp_path, *base_argv(tmp_path, helper, *targets))
    assert result.returncode == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert "status 2" in report["error"]


def test_pause_resume_counter_without_continuity_is_not_a_rejoin(tmp_path):
    """A pause/resume wobble with no driver rejoined event proves no deliberate rejoin."""
    guest = dict(GUEST_STATUS, rejoin_continuity=None)
    helper = write_stub(tmp_path, guest=guest)
    targets = write_targets(tmp_path)
    result = run_harness(tmp_path, *base_argv(tmp_path, helper, *targets))
    assert result.returncode == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "failed" and "rejoin" in report["error"].lower()


def test_rejoin_continuity_must_match_seat_and_show_later_play(tmp_path):
    """Continuity for another seat, or with no play after it, fails the run."""
    cases = [
        dict(GUEST_STATUS["rejoin_continuity"], player=0),
        dict(GUEST_STATUS["rejoin_continuity"], before_tick=0),
        dict(GUEST_STATUS["rejoin_continuity"], tick=5390),
    ]
    for continuity in cases:
        guest = dict(GUEST_STATUS, rejoin_continuity=continuity)
        helper = write_stub(tmp_path, guest=guest)
        targets = write_targets(tmp_path)
        result = run_harness(tmp_path, *base_argv(tmp_path, helper, *targets))
        assert result.returncode == 1, continuity
        report = json.loads((tmp_path / "out" / "report.json").read_text())
        assert report["status"] == "failed", continuity


def test_cleanup_failure_is_nonzero_and_preserves_the_primary_error(tmp_path):
    """A failed stop fails the run without swallowing the error that got there first."""
    helper = write_stub(tmp_path, fail_on=("guest",), fail_stop=("host",))
    targets = write_targets(tmp_path)
    result = run_harness(tmp_path, *base_argv(tmp_path, helper, *targets))
    assert result.returncode == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "failed"
    assert "helper join failed" in report["error"] and "cleanup failed" in report["error"]


def test_cleanup_failure_turns_a_pass_into_a_failure(tmp_path):
    """Owned units that cannot be stopped fail acceptance even after a clean match."""
    helper = write_stub(tmp_path, fail_stop=("host", "guest"))
    targets = write_targets(tmp_path)
    result = run_harness(tmp_path, *base_argv(tmp_path, helper, *targets))
    assert result.returncode == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "failed" and "cleanup failed" in report["error"]
    assert "winner" not in report


def rated_receipt(**overrides):
    receipt = {"match_id": "match-42", "winner": 0,
               "ratings": [dict(RATED_RESULT["ratings"][0]),
                           dict(RATED_RESULT["ratings"][1])]}
    receipt.update(overrides)
    return receipt


def test_rated_receipt_with_swapped_signs_is_rejected(tmp_path, public_routes):
    """Net-zero deltas with the winner losing rating move the wrong way."""
    receipt = rated_receipt(ratings=[
        dict(RATED_RESULT["ratings"][0], after=984, delta=-16),
        dict(RATED_RESULT["ratings"][1], after=1016, delta=16)])
    helper = write_stub(tmp_path, host=dict(HOST_STATUS, result=receipt),
                        guest=dict(GUEST_STATUS, result=receipt))
    targets = write_targets(tmp_path)
    result = run_harness(tmp_path, *rated_argv(tmp_path, helper, *targets, public_routes))
    assert result.returncode == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "failed" and "wrong way" in report["error"]


def test_rated_fresh_match_with_zero_movement_is_rejected(tmp_path, public_routes):
    """Two fresh 1500 ratings must move; a still receipt is not a ranked result."""
    receipt = rated_receipt(ratings=[
        {"player_id": "player-host", "name": "HostBot", "before": 1500, "after": 1500,
         "delta": 0, "games": 1, "wins": 1, "losses": 0},
        {"player_id": "player-guest", "name": "GuestBot", "before": 1500, "after": 1500,
         "delta": 0, "games": 1, "wins": 0, "losses": 1}])
    helper = write_stub(tmp_path, host=dict(HOST_STATUS, result=receipt),
                        guest=dict(GUEST_STATUS, result=receipt))
    targets = write_targets(tmp_path)
    result = run_harness(tmp_path, *rated_argv(tmp_path, helper, *targets, public_routes))
    assert result.returncode == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "failed" and "must move" in report["error"]


def test_rated_receipt_requires_match_id_winner_and_distinct_ids(tmp_path, public_routes):
    """An empty match id, an out-of-range winner, or a reused player id all fail."""
    base = [dict(RATED_RESULT["ratings"][0]), dict(RATED_RESULT["ratings"][1])]
    cases = [
        (rated_receipt(match_id=""), "match_id"),
        (rated_receipt(winner=5), "winner"),
        (rated_receipt(ratings=[base[0], dict(base[1], player_id="player-host")]), "player_id"),
    ]
    for receipt, keyword in cases:
        helper = write_stub(tmp_path, host=dict(HOST_STATUS, result=receipt),
                            guest=dict(GUEST_STATUS, result=receipt))
        targets = write_targets(tmp_path)
        result = run_harness(tmp_path, *rated_argv(tmp_path, helper, *targets, public_routes))
        assert result.returncode == 1, keyword
        report = json.loads((tmp_path / "out" / "report.json").read_text())
        assert report["status"] == "failed" and keyword in report["error"].lower(), keyword


ENGINE_RECEIPTS = ROOT / "tests" / "data" / "rated_duel_receipts.json"


def seam_from_receipt(base, receipt):
    """Public-route documents consistent with a source-produced receipt."""
    (base / "players").mkdir(parents=True, exist_ok=True)
    profiles = []
    for entry in receipt["ratings"]:
        profile = {"player_id": entry["player_id"], "name": entry["name"],
                   "rating": entry["after"], "games": entry["games"],
                   "wins": entry["wins"], "losses": entry["losses"]}
        (base / "players" / (entry["player_id"] + ".json")).write_text(json.dumps(profile))
        profiles.append(profile)
    (base / "ratings.json").write_text(json.dumps({"game": "warband-v2", "players": profiles}))
    (base / "status.json").write_text(json.dumps(
        {"protocol": "warband-v2", "rooms": 1, "ready_rooms": 0, "players": 2,
         "rated_grace": 60,
         "ratings": {"warband-v2": {"enabled": True, "seats": [2, 3, 4],
                                    "starting_rating": 1500}}}))
    return f"file://{base}"


def rated_statuses_for(receipt, room, host_name, guest_name):
    """Fake helper statuses carrying the receipt's actual public ids per seat."""
    ids = {entry["name"]: entry["player_id"] for entry in receipt["ratings"]}
    host = dict(HOST_STATUS, room=room, result=receipt, player_id=ids[host_name])
    guest = dict(GUEST_STATUS, room=room, result=receipt, player_id=ids[guest_name])
    return host, guest


def rated_names(receipt):
    names = [entry["name"] for entry in receipt["ratings"]]
    return names[0], names[1]


def test_engine_captured_float_receipts_pass_harness(tmp_path):
    """Source-produced float receipts (equal then fractional) verify end to end."""
    if not ENGINE_RECEIPTS.is_file():
        pytest.skip("engine-produced receipt fixture not captured")
    captured = json.loads(ENGINE_RECEIPTS.read_text())
    for key, room in (("duel_equal", "FLOAT01"), ("duel_unequal", "FLOAT02")):
        duel = captured[key]
        receipt = duel["result"]
        for entry in receipt["ratings"]:
            assert isinstance(entry["before"], float), "engine emits float ratings"
            assert isinstance(entry["delta"], float)
        host_name, guest_name = rated_names(receipt)
        host, guest = rated_statuses_for(receipt, room, host_name, guest_name)
        helper = write_stub(tmp_path, host=host, guest=guest)
        targets = write_targets(tmp_path)
        routes = seam_from_receipt(tmp_path / f"routes-{key}", receipt)
        argv = [*base_argv(tmp_path, helper, *targets), "--rated",
                "--host-player-name", host_name, "--guest-player-name", guest_name,
                "--status-base", routes]
        result = run_harness(tmp_path, *argv)
        assert result.returncode == 0, result.stderr + result.stdout
        report = json.loads((tmp_path / "out" / "report.json").read_text())
        assert report["status"] == "passed" and report["match_id"] == receipt["match_id"]


def test_live_ranked_duels_settle_float_receipts(tmp_path):
    """Real wire duels, fresh then reused identities: floats verify end to end."""
    import importlib.util
    if importlib.util.find_spec("websockets") is None \
            or importlib.util.find_spec("saga2d.testing.online") is None \
            or importlib.util.find_spec("warband.online.authority") is None:
        pytest.skip("live duel needs websockets, saga2d.testing.online and the warband engine")
    from websockets.sync.client import connect
    from saga2d.testing.online import command, handshake, receive, running_server
    import warband.online.authority  # noqa: F401

    def duel(url, token_a, token_b, seed):
        with connect(url, proxy=None) as host, connect(url, proxy=None) as guest:
            fields = {} if token_a is None else {"player_token": token_a}
            join_fields = {} if token_b is None else {"player_token": token_b}
            welcome = handshake(host, game="warband-v2",
                                options={"seed": seed, "width": 48, "height": 40},
                                rated=True, player_name="DuelA", **fields)
            guest_welcome = handshake(guest, "join", game="warband-v2", room=welcome["room"],
                                      player_name="DuelB", **join_fields)
            receive(host, predicate=lambda message: message["ready"])
            receive(guest, predicate=lambda message: message["ready"])
            command(guest, {"action": "resign", "args": [1]})
            decided = receive(host, predicate=lambda message: message["result"] is not None)
            assert receive(guest, predicate=lambda message: message["result"] is not None)[
                "result"] == decided["result"]
            return welcome, guest_welcome, decided["result"]

    with running_server("warband.online.authority:ONLINE") as (url, _process):
        first = duel(url, None, None, 3)
        second = duel(url, first[0]["player_token"], first[1]["player_token"], 7)
    assert first[0]["player_id"] == second[0]["player_id"], "identities are reused"
    assert first[2]["match_id"] != second[2]["match_id"], "two distinct rooms were settled"
    for entry, replayed in zip(sorted(second[2]["ratings"], key=lambda e: e["name"]),
                               sorted(first[2]["ratings"], key=lambda e: e["name"])):
        assert entry["before"] == replayed["after"], "second duel continues the first"
    for welcome, guest_welcome, receipt in (first, second):
        assert receipt["match_id"] == welcome["match_id"] and receipt["winner"] == 0
        for entry in receipt["ratings"]:
            assert isinstance(entry["before"], float) and isinstance(entry["delta"], float)
    fractional = [entry["delta"] for entry in second[2]["ratings"]]
    assert any(delta != int(delta) for delta in fractional), fractional
    for (welcome, _guest_welcome, receipt), room in zip(
            (first, second), ("LIVE01", "LIVE02")):
        host, guest = rated_statuses_for(receipt, room, "DuelA", "DuelB")
        helper = write_stub(tmp_path, host=host, guest=guest)
        targets = write_targets(tmp_path)
        routes = seam_from_receipt(tmp_path / f"routes-{room}", receipt)
        argv = [*base_argv(tmp_path, helper, *targets), "--rated",
                "--host-player-name", "DuelA", "--guest-player-name", "DuelB",
                "--status-base", routes]
        result = run_harness(tmp_path, *argv)
        assert result.returncode == 0, result.stderr + result.stdout


def test_engine_fractional_delta_is_not_an_integer(tmp_path):
    """The reused-identity duel settles a genuinely fractional exchange."""
    if not ENGINE_RECEIPTS.is_file():
        pytest.skip("engine-produced receipt fixture not captured")
    receipt = json.loads(ENGINE_RECEIPTS.read_text())["duel_unequal"]["result"]
    deltas = [entry["delta"] for entry in receipt["ratings"]]
    assert any(delta != int(delta) for delta in deltas), deltas


def test_nonfinite_and_bool_ratings_are_rejected(tmp_path, public_routes):
    """NaN, Infinity and bools are never valid ratings, however they arrive."""
    poisoned = [
        ("nan", "delta", float("nan"), "non-numeric"),
        ("inf", "delta", float("inf"), "non-numeric"),
        ("bool-delta", "delta", True, "non-numeric"),
        ("bool-games", "games", True, "non-integer"),
    ]
    for label, field, value, keyword in poisoned:
        entries = [dict(RATED_RESULT["ratings"][0]), dict(RATED_RESULT["ratings"][1])]
        entries[0][field] = value
        receipt = {"match_id": "match-42", "winner": 0, "ratings": entries}
        helper = write_stub(tmp_path, host=dict(HOST_STATUS, result=receipt),
                            guest=dict(GUEST_STATUS, result=receipt))
        targets = write_targets(tmp_path)
        argv = [*base_argv(tmp_path, helper, *targets), "--rated",
                "--host-player-name", "HostBot", "--guest-player-name", "GuestBot",
                "--status-base", public_routes]
        result = run_harness(tmp_path, *argv)
        assert result.returncode == 1, label
        report = json.loads((tmp_path / "out" / "report.json").read_text())
        assert report["status"] == "failed" and keyword in report["error"].lower(), label


def test_swapped_public_ids_are_refused_despite_right_names(tmp_path, public_routes):
    """Seats reporting each other's public ids fail even with correct receipt names."""
    host = dict(HOST_STATUS, result=RATED_RESULT, player_id="player-guest")
    guest = dict(GUEST_STATUS, result=RATED_RESULT, player_id="player-host")
    helper = write_stub(tmp_path, host=host, guest=guest)
    targets = write_targets(tmp_path)
    argv = [*base_argv(tmp_path, helper, *targets), "--rated",
            "--host-player-name", "HostBot", "--guest-player-name", "GuestBot",
            "--status-base", public_routes]
    result = run_harness(tmp_path, *argv)
    assert result.returncode == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "failed" and "row for seat host" in report["error"]


def test_missing_seat_public_id_is_refused(tmp_path, public_routes):
    """A rated seat with no finished public id cannot be correlated by id."""
    guest = dict(GUEST_STATUS, result=RATED_RESULT, player_id=None)
    helper = write_stub(tmp_path, host=dict(HOST_STATUS, result=RATED_RESULT), guest=guest)
    targets = write_targets(tmp_path)
    argv = [*base_argv(tmp_path, helper, *targets), "--rated",
            "--host-player-name", "HostBot", "--guest-player-name", "GuestBot",
            "--status-base", public_routes]
    result = run_harness(tmp_path, *argv)
    assert result.returncode == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "failed" and "public player id" in report["error"].lower()


def test_duplicate_rated_names_are_refused_before_ssh(tmp_path):
    """One alias for both seats cannot resolve roles, so it is rejected up front."""
    helper = write_stub(tmp_path)
    targets = write_targets(tmp_path)
    argv = [*base_argv(tmp_path, helper, *targets), "--rated",
            "--host-player-name", "SameBot", "--guest-player-name", "SameBot"]
    result = run_harness(tmp_path, *argv)
    assert result.returncode == 2
    assert "differ" in result.stderr
    assert not (tmp_path / "started.log").exists()


def test_rated_start_forwards_a_single_rated_flag(tmp_path, public_routes):
    """The helper create line carries one --rated alongside the ranked names."""
    host = dict(HOST_STATUS, result=RATED_RESULT)
    guest = dict(GUEST_STATUS, result=RATED_RESULT)
    helper = write_stub(tmp_path, host=host, guest=guest)
    targets = write_targets(tmp_path)
    result = run_harness(tmp_path, *rated_argv(tmp_path, helper, *targets, public_routes))
    assert result.returncode == 0, result.stderr + result.stdout
    started = (tmp_path / "started.log").read_text()
    assert "--rated --rated" not in started
    assert started.count("--rated") == 1


def board_leaders(*, size=20, top=2000, step=10):
    """Valid public leaderboard rows, sorted by rating descending."""
    return [{"player_id": f"leader-{index:02d}", "name": f"Leader {index:02d}",
             "rating": top - index * step, "games": 50, "wins": 30, "losses": 20}
            for index in range(size)]


def board_with(index, **overrides):
    """A full valid board with one row replaced, still sorted unless overrides break it."""
    leaders = board_leaders()
    leaders[index] = {**leaders[index], **overrides}
    return leaders


def seam_with_full_leaderboard(base, receipt, *, board_size=20, top_rating=2000):
    """Individual profiles exact; leaderboard holds only higher-rated strangers."""
    (base / "players").mkdir(parents=True, exist_ok=True)
    for entry in receipt["ratings"]:
        profile = {"player_id": entry["player_id"], "name": entry["name"],
                   "rating": entry["after"], "games": entry["games"],
                   "wins": entry["wins"], "losses": entry["losses"]}
        (base / "players" / (entry["player_id"] + ".json")).write_text(json.dumps(profile))
    leaders = board_leaders(size=board_size, top=top_rating)
    (base / "ratings.json").write_text(json.dumps({"game": "warband-v2", "players": leaders}))
    (base / "status.json").write_text(json.dumps(
        {"protocol": "warband-v2", "rooms": 1, "ready_rooms": 0, "players": 22,
         "rated_grace": 60,
         "ratings": {"warband-v2": {"enabled": True, "seats": [2, 3, 4],
                                    "starting_rating": 1500}}}))
    return f"file://{base}"


def test_rated_seats_below_full_leaderboard_pass_on_exact_profiles(tmp_path):
    """Lower-ranked seats outside a full top-20 still pass when profiles match."""
    receipt = rated_receipt()
    routes = seam_with_full_leaderboard(tmp_path / "routes-full20", receipt)
    result = run_rated_against(tmp_path, receipt, routes)
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "passed" and report["match_id"] == "match-42"


def run_rated_against(tmp_path, receipt, routes):
    """Drive the real CLI with both seats carrying one authoritative receipt."""
    host = dict(HOST_STATUS, result=receipt)
    guest = dict(GUEST_STATUS, result=receipt)
    helper = write_stub(tmp_path, host=host, guest=guest)
    targets = write_targets(tmp_path)
    argv = [*base_argv(tmp_path, helper, *targets), "--rated",
            "--host-player-name", "HostBot", "--guest-player-name", "GuestBot",
            "--status-base", routes]
    return run_harness(tmp_path, *argv)


def rewrite_board(base, leaders):
    (base / "ratings.json").write_text(json.dumps({"game": "warband-v2", "players": leaders}))


def test_rated_absent_seat_with_room_on_board_fails(tmp_path):
    """A 19-row leaderboard has room, so an absent seat is not excused."""
    receipt = rated_receipt()
    base = tmp_path / "routes-room"
    routes = seam_with_full_leaderboard(base, receipt, board_size=19)
    result = run_rated_against(tmp_path, receipt, routes)
    assert result.returncode == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "failed" and "/ratings" in report["error"]


def test_rated_listed_seat_mismatch_fails_despite_full_board(tmp_path):
    """A listed seat whose rating disagrees fails even with a full 20."""
    receipt = rated_receipt()
    base = tmp_path / "routes-mismatch"
    routes = seam_with_full_leaderboard(base, receipt)
    leaders = board_with(0, player_id="player-host", name="HostBot", rating=1015,
                         games=5, wins=3, losses=2)
    leaders.sort(key=lambda row: row["rating"], reverse=True)
    rewrite_board(base, leaders)
    result = run_rated_against(tmp_path, receipt, routes)
    assert result.returncode == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "failed" and "disagrees" in report["error"]


@pytest.mark.parametrize("label,overrides", [
    ("wrong-name", {"name": "Impostor"}),
    ("wrong-count", {"games": 6}),
])
def test_rated_listed_seat_profile_mismatch_fails(tmp_path, label, overrides):
    """A listed seat matching on rating but not its full profile still fails."""
    receipt = rated_receipt()
    base = tmp_path / f"routes-{label}"
    routes = seam_with_full_leaderboard(base, receipt)
    leaders = board_leaders(size=19)
    leaders.append({"player_id": "player-host", "name": "HostBot", "rating": 1016,
                    "games": 5, "wins": 3, "losses": 2, **overrides})
    rewrite_board(base, leaders)
    result = run_rated_against(tmp_path, receipt, routes)
    assert result.returncode == 1, label
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "failed" and "disagrees" in report["error"], label


def test_rated_overlong_leaderboard_fails_despite_listed_seats(tmp_path):
    """A board longer than the requested 20 is malformed even with both seats listed."""
    receipt = rated_receipt()
    base = tmp_path / "routes-overlong"
    routes = seam_with_full_leaderboard(base, receipt)
    leaders = board_leaders(size=19)
    leaders.append({"player_id": "player-host", "name": "HostBot", "rating": 1016,
                    "games": 5, "wins": 3, "losses": 2})
    leaders.append({"player_id": "player-guest", "name": "GuestBot", "rating": 984,
                    "games": 5, "wins": 2, "losses": 3})
    leaders.sort(key=lambda row: row["rating"], reverse=True)
    rewrite_board(base, leaders)
    result = run_rated_against(tmp_path, receipt, routes)
    assert result.returncode == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "failed" and "/ratings" in report["error"]


def test_rated_absent_seat_above_board_cutoff_fails(tmp_path):
    """An absent seat outranking part of a full board should be listed, not excused."""
    receipt = rated_receipt()
    base = tmp_path / "routes-cutoff"
    routes = seam_with_full_leaderboard(base, receipt)
    rewrite_board(base, board_leaders(top=1100))
    result = run_rated_against(tmp_path, receipt, routes)
    assert result.returncode == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "failed" and "/ratings" in report["error"]


def test_rated_listed_seat_with_absent_seat_below_cutoff_passes(tmp_path):
    """One listed seat matching plus one absent seat below the cutoff still passes."""
    receipt = rated_receipt()
    base = tmp_path / "routes-mixed"
    routes = seam_with_full_leaderboard(base, receipt)
    leaders = board_leaders(size=18)
    leaders.append({"player_id": "player-host", "name": "HostBot", "rating": 1016,
                    "games": 5, "wins": 3, "losses": 2})
    leaders.append({"player_id": "leader-tail", "name": "Leader Tail", "rating": 1000,
                    "games": 50, "wins": 30, "losses": 20})
    rewrite_board(base, leaders)
    result = run_rated_against(tmp_path, receipt, routes)
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "passed" and report["match_id"] == "match-42"


@pytest.mark.parametrize("label,leaders", [
    ("empty", []),
    ("malformed", [{"player_id": "leader-00", "name": "Leader 00",
                    "games": 50, "wins": 30, "losses": 20}]),
    ("duplicate", [{"player_id": "leader-00", "name": "Leader 00", "rating": 2000,
                    "games": 50, "wins": 30, "losses": 20} for _ in range(20)]),
    ("unordered", board_with(19, rating=1830)),
    ("nonfinite", board_with(0, rating=float("inf"))),
    ("bool", board_with(0, rating=True)),
])
def test_rated_broken_leaderboard_never_silently_passes(tmp_path, label, leaders):
    """Empty, malformed, duplicate, unordered or non-numeric boards always fail."""
    receipt = rated_receipt()
    base = tmp_path / f"routes-{label}"
    routes = seam_with_full_leaderboard(base, receipt)
    rewrite_board(base, leaders)
    result = run_rated_against(tmp_path, receipt, routes)
    assert result.returncode == 1, label
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "failed" and "/ratings" in report["error"], label
