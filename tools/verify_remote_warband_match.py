"""Verify one authoritative AI-vs-AI match on two disposable VMs through public TLS.

    uv run python tools/verify_remote_warband_match.py \\
        --host-target dist/online-ai/host.json --guest-target dist/online-ai/guest.json \\
        --server wss://games.tachyon-ai.eu/play --output /tmp/remote-match \\
        --rated --host-player-name HostBot --guest-player-name GuestBot \\
        --host-identity-file ~/.warband/host.identity \\
        --guest-identity-file ~/.warband/guest.identity

The host creates the room, the guest joins it and deliberately rejoins
mid-match; the run passes only on an authoritative winner (never a bare
duration expiry) with both seats reporting the same room, opposite seats,
tick/order progress and a consistent winner. A rated run additionally
requires the server result receipt on both sides, validates its rating
deltas and name correlation, and checks the public /status, /players/ and
/ratings routes. Identity files must already be owner-only mode 0600; their
bytes are never read into the report. Only services started by this run are
stopped, always, and a compact sanitized report is written on success or
failure. No account profiles or private tokens appear in the output.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import math
import os
import re
import stat as statmod
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
GAME_ID = "warband-v2"
PUBLIC_SERVER = "wss://games.tachyon-ai.eu/play"
TARGET_PATTERN = re.compile(r"saga2d-warband-ai(?:-[a-z0-9-]{1,40})?\Z")
PRODUCTION = "saga2d-online"
DIFFICULTIES = ("easy", "medium", "hard", "master")
THEMES = ("summer", "winter", "wasteland")
RACES = ("human", "orc", "elf", "dwarf")
PLAYER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,31}\Z")
HELPER_TIMEOUT = 60


def arguments(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host-target", type=Path, required=True)
    parser.add_argument("--guest-target", type=Path, required=True)
    parser.add_argument("--server", default=PUBLIC_SERVER)
    parser.add_argument("--status-base", default=None,
                        help="origin for /status, /players/ and /ratings "
                             "(default: derived from --server; file:// is a local seam)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=2400)
    parser.add_argument("--timeout", type=float, default=None,
                        help="overall harness deadline (default: duration + 300)")
    parser.add_argument("--wait-timeout", type=float, default=300)
    parser.add_argument("--poll-every", type=float, default=5)
    parser.add_argument("--host-difficulty", choices=DIFFICULTIES, default="medium")
    parser.add_argument("--guest-difficulty", choices=DIFFICULTIES, default="medium")
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument("--width", type=int, default=48)
    parser.add_argument("--height", type=int, default=40)
    parser.add_argument("--theme", choices=THEMES, default="summer")
    parser.add_argument("--race", choices=RACES, default=None)
    parser.add_argument("--reconnect-after", type=float, default=15)
    parser.add_argument("--disconnect-for", type=float, default=5)
    parser.add_argument("--rated", action="store_true")
    parser.add_argument("--host-player-name", default=None)
    parser.add_argument("--guest-player-name", default=None)
    parser.add_argument("--host-identity-file", type=Path, default=None)
    parser.add_argument("--guest-identity-file", type=Path, default=None)
    parser.add_argument("--helper", type=Path, default=ROOT / "tools" / "remote_warband_ai.py")
    parser.add_argument("--ssh-key", type=Path, default=Path.home() / ".ssh/id_ed25519.pub")
    args = parser.parse_args(argv)
    validate(args, parser)
    return args


def public_host(value: str, parser: argparse.ArgumentParser, name: str) -> str:
    try:
        parsed = urllib.parse.urlparse(value)
    except ValueError:
        parsed = None
    if parsed is None or parsed.scheme != "wss" or not parsed.hostname:
        parser.error(f"{name} must be the public wss:// endpoint")
    host = parsed.hostname
    try:
        if ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback \
                or ipaddress.ip_address(host).is_link_local:
            parser.error(f"{name} must be the public server, not {host}")
    except ValueError:
        if host == "localhost" or "." not in host:
            parser.error(f"{name} must be the public server, not {host}")
    return host


def check_identity(path: Path | None, parser: argparse.ArgumentParser, name: str) -> None:
    if path is None:
        return
    if not path.is_file():
        parser.error(f"{name} does not exist: {path}")
    if statmod.S_IMODE(os.stat(path).st_mode) & 0o077:
        parser.error(f"{name} must be a private mode 0600 file")


def validate(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    public_host(args.server, parser, "--server")
    if args.status_base is not None:
        if args.status_base.startswith("file://"):
            pass
        elif args.status_base.startswith("https://"):
            host = urllib.parse.urlparse(args.status_base).hostname or ""
            try:
                barred = ipaddress.ip_address(host).is_private \
                    or ipaddress.ip_address(host).is_loopback
            except ValueError:
                barred = host == "localhost" or "." not in host
            if barred:
                parser.error("--status-base must be the public https:// origin")
        else:
            parser.error("--status-base must be https:// or file://")
    for name in ("duration", "wait-timeout", "poll-every", "reconnect-after", "disconnect-for"):
        value = getattr(args, name.replace("-", "_"))
        if not math.isfinite(value) or value <= 0:
            parser.error(f"--{name} must be positive and finite")
    if args.timeout is not None and (not math.isfinite(args.timeout) or args.timeout <= 0):
        parser.error("--timeout must be positive and finite")
    if not 48 <= args.width <= 80:
        parser.error("--width must be 48-80")
    if not 40 <= args.height <= 64:
        parser.error("--height must be 40-64")
    if args.rated and not (args.host_player_name and args.guest_player_name):
        parser.error("--rated requires --host-player-name and --guest-player-name")
    if args.rated and args.host_player_name == args.guest_player_name:
        parser.error("--host-player-name and --guest-player-name must differ")
    for name in ("host-player-name", "guest-player-name"):
        value = getattr(args, name.replace("-", "_"))
        if value is not None and not PLAYER_PATTERN.fullmatch(value):
            parser.error(f"--{name} must be 1-32 letters, digits, spaces, _ or -")
    if args.host_identity_file is not None and not args.host_player_name:
        parser.error("--host-identity-file requires --host-player-name")
    if args.guest_identity_file is not None and not args.guest_player_name:
        parser.error("--guest-identity-file requires --guest-player-name")
    check_identity(args.host_identity_file, parser, "--host-identity-file")
    check_identity(args.guest_identity_file, parser, "--guest-identity-file")
    if not args.helper.is_file():
        parser.error(f"--helper does not exist: {args.helper}")
    try:
        host = load_target(args.host_target, "host")
        guest = load_target(args.guest_target, "guest")
        check_targets(host, guest)
    except ValueError as exc:
        parser.error(str(exc))


def load_target(path: Path, role: str) -> dict:
    try:
        target = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"{role} target unreadable: {path}: {exc}")
    name = target.get("name") if isinstance(target, dict) else None
    if name == PRODUCTION:
        raise ValueError(f"{role} target refuses the {PRODUCTION} production instance")
    if not isinstance(name, str) or not TARGET_PATTERN.fullmatch(name):
        raise ValueError(f"{role} target must name saga2d-warband-ai[-slug]: {path}")
    if not target.get("server_id") or not target.get("ip"):
        raise ValueError(f"{role} target must carry server_id and ip: {path}")
    return target


def check_targets(host: dict, guest: dict) -> None:
    if host["name"] == guest["name"]:
        raise ValueError("Host and guest must be distinct VMs, not one target twice")
    if host["server_id"] == guest["server_id"] or host["ip"] == guest["ip"]:
        raise ValueError("Host and guest share a server id or IP: two separate VMs required")


def status_base(args: argparse.Namespace) -> str:
    if args.status_base:
        return args.status_base
    return "https://" + (urllib.parse.urlparse(args.server).hostname or "")


def helper_run(args: argparse.Namespace, *argv: object) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(args.helper), *[str(item) for item in argv]],
                          capture_output=True, text=True, timeout=HELPER_TIMEOUT)


def helper_status(args: argparse.Namespace, target: Path, side: str) -> dict:
    result = helper_run(args, "status", "--target", target, "--ssh-key", args.ssh_key, "--json")
    if result.returncode != 0:
        tail = (result.stderr.strip() or result.stdout.strip()).splitlines()
        raise RuntimeError(f"helper status failed for {side}: "
                           + ("; ".join(tail[-3:]) if tail else f"exit {result.returncode}"))
    try:
        status = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"helper status for {side} returned non-JSON output")
    if not isinstance(status, dict):
        raise RuntimeError(f"helper status for {side} returned a non-object")
    return status


def helper_stop(args: argparse.Namespace, target: Path, side: str) -> None:
    result = helper_run(args, "stop", "--target", target, "--ssh-key", args.ssh_key)
    if result.returncode != 0:
        tail = (result.stderr.strip() or result.stdout.strip()).splitlines()
        raise RuntimeError(f"helper stop failed for {side}: "
                           + ("; ".join(tail[-3:]) if tail else f"exit {result.returncode}"))


def base_bot_argv(args: argparse.Namespace, target: Path, difficulty: str) -> list:
    return ["--target", target, "--ssh-key", args.ssh_key, "--server", args.server,
            "--difficulty", difficulty, "--duration", str(args.duration),
            "--require-completion"]


def named_argv(args: argparse.Namespace, player: str | None, identity: Path | None) -> list:
    argv: list = []
    if player is not None:
        argv += ["--player-name", player]
    if identity is not None:
        argv += ["--identity-file", str(identity)]
    return argv


def flag_argv(flag: str, value: object) -> list:
    return [flag, value] if value is not None else []


def start_host(args: argparse.Namespace) -> None:
    argv = ["create", *base_bot_argv(args, args.host_target, args.host_difficulty),
            *named_argv(args, args.host_player_name, args.host_identity_file),
            "--seed", str(args.seed), "--width", str(args.width),
            "--height", str(args.height), "--theme", args.theme,
            *flag_argv("--race", args.race)]
    if args.rated:
        argv.append("--rated")
    result = helper_run(args, *argv)
    if result.returncode != 0:
        tail = (result.stderr.strip() or result.stdout.strip()).splitlines()
        raise RuntimeError("helper create failed for host: "
                           + ("; ".join(tail[-3:]) if tail else "exit 1"))


def start_guest(args: argparse.Namespace, room: str) -> None:
    argv = ["join", *base_bot_argv(args, args.guest_target, args.guest_difficulty),
            "--room", room,
            *named_argv(args, args.guest_player_name, args.guest_identity_file),
            "--reconnect-after", str(args.reconnect_after),
            "--disconnect-for", str(args.disconnect_for),
            *flag_argv("--race", args.race)]
    result = helper_run(args, *argv)
    if result.returncode != 0:
        tail = (result.stderr.strip() or result.stdout.strip()).splitlines()
        raise RuntimeError("helper join failed for guest: "
                           + ("; ".join(tail[-3:]) if tail else "exit 1"))


def fresh_accumulator() -> dict:
    return {"room": None, "player": None, "invocation": None, "tick": 0, "orders": 0,
            "states": 0, "reconnects": 0, "continuity": None, "finished": False,
            "reason": None, "winner": None, "result": None, "player_id": None}


def accumulate(seen: dict, status: dict, side: str) -> None:
    """Fold one status poll into running evidence; the journal tail alone forgets."""
    room, player = status.get("room"), status.get("player")
    if room is not None:
        if seen["room"] is None:
            seen["room"] = room
        elif seen["room"] != room:
            raise RuntimeError(f"{side} changed rooms mid-run: {seen['room']} -> {room}")
    if player is not None:
        if seen["player"] is None:
            seen["player"] = player
        elif seen["player"] != player:
            raise RuntimeError(f"{side} changed seats mid-run: {seen['player']} -> {player}")
    invocation = status.get("invocation_id")
    if invocation is not None:
        if seen["invocation"] is None:
            seen["invocation"] = invocation
        elif seen["invocation"] != invocation:
            raise RuntimeError(f"{side} restarted mid-run: {seen['invocation']} -> {invocation}")
    public_id = status.get("player_id")
    if public_id is not None:
        if seen["player_id"] is None:
            seen["player_id"] = public_id
        elif seen["player_id"] != public_id:
            raise RuntimeError(f"{side} public id changed mid-run")
    for key, field in (("tick", "tick"), ("orders", "orders_submitted"),
                       ("states", "states_received"), ("reconnects", "reconnects_observed")):
        value = status.get(field)
        if isinstance(value, int) and value > seen[key]:
            seen[key] = value
    if status.get("rejoin_continuity") is not None:
        seen["continuity"] = status["rejoin_continuity"]
    if status.get("finished"):
        seen["finished"] = True
        seen["reason"] = status.get("reason")
        seen["winner"] = status.get("winner")
        seen["result"] = status.get("result")


def check_terminal_error(status: dict, side: str) -> None:
    """Fail promptly on a crashed bot instead of waiting out the whole timeout."""
    if status.get("finished") or status.get("active"):
        return
    # The helper reports the bot's terminal `error` event here; `interrupted`
    # and signal deaths surface as a nonzero main-process exit status.
    error = status.get("error")
    if error:
        raise RuntimeError(f"{side} bot failed: {error}")
    try:
        code = int(str(status.get("systemd", {}).get("ExecMainStatus", 0)))
    except (TypeError, ValueError):
        code = 0
    if code != 0:
        raise RuntimeError(f"{side} bot exited with status {code} and no terminal event")


def poll(args: argparse.Namespace, target: Path, side: str, seen: dict) -> dict:
    status = helper_status(args, target, side)
    accumulate(seen, status, side)
    check_terminal_error(status, side)
    return status


def wait_for_room(args: argparse.Namespace, seen: dict, deadline: float) -> str:
    while True:
        poll(args, args.host_target, "host", seen)
        if seen["room"] is not None:
            return seen["room"]
        if time.monotonic() >= deadline:
            raise TimeoutError("timed out waiting for the host to publish a room")
        time.sleep(args.poll_every)


def wait_for_finished(args: argparse.Namespace, host_seen: dict, guest_seen: dict,
                      deadline: float) -> None:
    while True:
        poll(args, args.host_target, "host", host_seen)
        poll(args, args.guest_target, "guest", guest_seen)
        if host_seen["finished"] and guest_seen["finished"]:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("timed out waiting for both bots to reach terminal finished")
        time.sleep(args.poll_every)


def check_match(host_seen: dict, guest_seen: dict) -> dict:
    if host_seen["room"] is None or guest_seen["room"] is None:
        raise RuntimeError("no room was ever published by both seats")
    if host_seen["room"] != guest_seen["room"]:
        raise RuntimeError(f"seats played different rooms: {host_seen['room']} "
                           f"vs {guest_seen['room']}")
    if {host_seen["player"], guest_seen["player"]} != {0, 1}:
        raise RuntimeError(f"seats are not opposite: {host_seen['player']} vs "
                           f"{guest_seen['player']}")
    for side, seen in (("host", host_seen), ("guest", guest_seen)):
        if seen["tick"] < 1 or seen["orders"] < 1:
            raise RuntimeError(f"{side} shows no authoritative tick/order progress")
        if seen["reason"] != "winner" or seen["winner"] is None:
            raise RuntimeError(f"{side} ended by {seen['reason'] or 'unknown'} without a winner; "
                               "a duration expiry is not a completed match")
    if host_seen["winner"] != guest_seen["winner"]:
        raise RuntimeError(f"seats disagree on the winner: {host_seen['winner']} "
                           f"vs {guest_seen['winner']}")
    check_rejoin(guest_seen)
    return {"room": host_seen["room"], "winner": host_seen["winner"],
            "seats": [host_seen["player"], guest_seen["player"]]}


def check_rejoin(guest_seen: dict) -> None:
    """Require the driver's actual rejoined continuity, not a pause/resume wobble."""
    continuity = guest_seen["continuity"]
    if not isinstance(continuity, dict):
        raise RuntimeError("guest shows no deliberate rejoin evidence (no rejoined continuity)")
    if continuity.get("player") != guest_seen["player"]:
        raise RuntimeError("guest rejoin seat does not match its assigned seat")
    before = continuity.get("before_tick")
    at = continuity.get("tick")
    if not isinstance(before, int) or before <= 0 or not isinstance(at, int) or at < before:
        raise RuntimeError("guest rejoin continuity ticks are invalid")
    if guest_seen["tick"] <= at:
        raise RuntimeError("guest final tick shows no play after its rejoin")


def is_rating_number(value: object) -> bool:
    """Finite int or float ratings, never bools: the engine emits floats."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(value)


def is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


# float64 Elo recomputation can differ by a few ulps (~1e-13 relative); 1e-9
# relative tolerance sits ~1e3x above that noise and ~1e6x below a 0.01
# rating-point discrepancy, so only arithmetic ghosts pass, never wrong values.
RATING_REL_TOL = 1e-9
RATING_ABS_TOL = 1e-9
LEADERBOARD_FULL_SIZE = 20


def check_ratings(result: dict, host_name: str, guest_name: str, winner_id: str,
                  host_id: str, guest_id: str, starting_rating: int = 1500) -> dict:
    """Validate the receipt against each seat's own public id, never names alone."""
    ratings = result.get("ratings")
    if not isinstance(ratings, list) or len(ratings) != 2:
        raise RuntimeError("ranked receipt must carry exactly two player ratings")
    seat_ids = {"host": host_id, "guest": guest_id}
    row_by_id = {}
    for entry in ratings:
        if not isinstance(entry, dict):
            raise RuntimeError("ranked receipt carries a malformed rating entry")
        name = entry.get("name")
        if name not in (host_name, guest_name):
            raise RuntimeError(f"ranked receipt names unknown player {name!r}")
        for key in ("before", "after", "delta"):
            if not is_rating_number(entry.get(key)):
                raise RuntimeError(f"ranked receipt for {name!r} has non-numeric {key}")
        for key in ("games", "wins", "losses"):
            if not is_count(entry.get(key)):
                raise RuntimeError(f"ranked receipt for {name!r} has non-integer {key}")
        if not math.isclose(entry["after"] - entry["before"], entry["delta"],
                            rel_tol=RATING_REL_TOL, abs_tol=RATING_ABS_TOL):
            raise RuntimeError(f"ranked receipt delta does not match before/after for {name!r}")
        for key in ("games", "wins", "losses"):
            if entry[key] < 0:
                raise RuntimeError(f"ranked receipt for {name!r} has negative {key}")
        if not entry.get("player_id"):
            raise RuntimeError(f"ranked receipt for {name!r} names no player_id")
        if entry["player_id"] not in seat_ids.values():
            raise RuntimeError(f"ranked receipt row for {name!r} carries an unknown player id")
        if entry["player_id"] in row_by_id:
            raise RuntimeError("ranked receipt reuses one player_id for both seats")
        row_by_id[entry["player_id"]] = entry
    if set(row_by_id) != set(seat_ids.values()):
        raise RuntimeError("ranked receipt does not cover both seats' public ids")
    for side, seat_name in (("host", host_name), ("guest", guest_name)):
        if row_by_id[seat_ids[side]]["name"] != seat_name:
            raise RuntimeError(f"ranked receipt row for seat {side} names "
                               f"{row_by_id[seat_ids[side]]['name']!r}, not {seat_name!r}")
    if not math.isclose(row_by_id[host_id]["delta"] + row_by_id[guest_id]["delta"], 0.0,
                        rel_tol=0.0, abs_tol=RATING_ABS_TOL):
        raise RuntimeError("ranked receipt deltas do not net to zero")
    if winner_id not in seat_ids.values():
        raise RuntimeError("ranked winner id matches neither seat's public id")
    loser_id = guest_id if winner_id == host_id else host_id
    winner_delta, loser_delta = row_by_id[winner_id]["delta"], row_by_id[loser_id]["delta"]
    if winner_delta < 0 or loser_delta > 0:
        raise RuntimeError("ranked receipt moves ratings the wrong way: "
                           f"winner {winner_delta:+}, loser {loser_delta:+}")
    if row_by_id[winner_id]["before"] == row_by_id[loser_id]["before"] == starting_rating \
            and not (winner_delta > 0 and loser_delta < 0):
        raise RuntimeError("a fresh-rating match must move both ratings")
    return row_by_id


def check_leaderboard(rows: list) -> dict:
    """Validate every leaderboard row; return player_id -> row without skipping."""
    if len(rows) > LEADERBOARD_FULL_SIZE:
        raise RuntimeError("public /ratings is longer than the requested leaderboard")
    rows_by_id: dict = {}
    previous = None
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("public /ratings carries a malformed row")
        player_id = row.get("player_id")
        if not isinstance(player_id, str) or not player_id:
            raise RuntimeError("public /ratings carries a row without a player id")
        if player_id in rows_by_id:
            raise RuntimeError("public /ratings lists a player id twice")
        if not isinstance(row.get("name"), str) or not row.get("name"):
            raise RuntimeError("public /ratings carries a row without a name")
        if not is_rating_number(row.get("rating")):
            raise RuntimeError("public /ratings carries a non-numeric rating")
        for key in ("games", "wins", "losses"):
            if not is_count(row.get(key)) or row[key] < 0:
                raise RuntimeError(f"public /ratings carries a non-integer {key}")
        if previous is not None and row["rating"] > previous:
            raise RuntimeError("public /ratings is not sorted by rating descending")
        previous = row["rating"]
        rows_by_id[player_id] = row
    return rows_by_id


def fetch_route(base: str, *parts: str, query: str = "") -> dict:
    """Read one public route document over https or the local file:// seam."""
    if base.startswith("file://"):
        mapping = {("status",): "status.json",
                   ("ratings",): "ratings.json"}
        directory = base.removeprefix("file://")
        if len(parts) == 2 and parts[0] == "players":
            path = Path(directory, "players", parts[1] + ".json")
        else:
            try:
                path = Path(directory, mapping[tuple(parts)])
            except KeyError:
                raise RuntimeError(f"local route seam has no {'/'.join(parts)}")
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"local route seam unreadable for {'/'.join(parts)}: {exc}")
    url = base.rstrip("/") + "/" + "/".join(parts) + (("?" + query) if query else "")
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            return json.load(response)
    except Exception as exc:
        raise RuntimeError(f"public route {url} unreachable: {exc}")


def check_rated(args: argparse.Namespace, host_seen: dict, guest_seen: dict) -> dict:
    """Correlate both bots' server receipts with the public status/ratings routes."""
    host_result, guest_result = host_seen["result"], guest_seen["result"]
    if not isinstance(host_result, dict) or not isinstance(guest_result, dict):
        raise RuntimeError("ranked run produced no server result receipt; "
                           "the client engine ignored the ranked options")
    if host_result != guest_result:
        raise RuntimeError("seats report different ranked receipts for one match")
    result = host_result
    if result.get("winner") not in (0, 1):
        raise RuntimeError("ranked receipt names no winner in {0, 1}")
    if not result.get("match_id"):
        raise RuntimeError("ranked receipt names no match_id")
    if result.get("winner") != host_seen["winner"]:
        raise RuntimeError("ranked receipt winner differs from the authoritative winner")
    base = status_base(args)
    status = fetch_route(base, "status")
    ratings_config = status.get("ratings", {}).get(GAME_ID, {}) \
        if isinstance(status.get("ratings"), dict) else {}
    if ratings_config.get("enabled") is not True:
        raise RuntimeError(f"public /status shows ratings disabled for {GAME_ID}")
    starting_rating = ratings_config.get("starting_rating", 1500)
    host_id, guest_id = host_seen["player_id"], guest_seen["player_id"]
    if not host_id or not guest_id:
        raise RuntimeError("rated run reports no public player id for both seats")
    if host_seen["player"] == result["winner"]:
        winner_id = host_id
    elif guest_seen["player"] == result["winner"]:
        winner_id = guest_id
    else:
        raise RuntimeError("ranked receipt winner matches neither seat")
    row_by_id = check_ratings(result, args.host_player_name, args.guest_player_name,
                              winner_id, host_id, guest_id, starting_rating)
    public_players = {}
    for player_id, entry in row_by_id.items():
        name = entry["name"]
        profile = fetch_route(base, "players", player_id, query=f"game={GAME_ID}")
        if profile.get("player_id") != player_id or profile.get("name") != name \
                or profile.get("rating") != entry["after"]:
            raise RuntimeError(f"public profile for {name!r} does not match the receipt")
        for key in ("games", "wins", "losses"):
            if profile.get(key) != entry[key]:
                raise RuntimeError(f"public profile for {name!r} disagrees on {key}")
        public_players[player_id] = profile["rating"]
    board = fetch_route(base, "ratings", query=f"game={GAME_ID}&limit={LEADERBOARD_FULL_SIZE}")
    if board.get("game") != GAME_ID or not isinstance(board.get("players"), list):
        raise RuntimeError("public /ratings returned an unexpected document")
    board_rows = check_leaderboard(board["players"])
    for player_id, entry in row_by_id.items():
        row = board_rows.get(player_id)
        if row is not None:
            if row["rating"] != entry["after"] or row["name"] != entry["name"] \
                    or any(row[key] != entry[key] for key in ("games", "wins", "losses")):
                raise RuntimeError(f"public /ratings disagrees with the receipt for {entry['name']!r}")
            continue
        if len(board["players"]) != LEADERBOARD_FULL_SIZE:
            raise RuntimeError(f"public /ratings disagrees with the receipt for {entry['name']!r}: "
                               "the leaderboard has room, so an absent seat is not excused")
        if any(row["rating"] < entry["after"] for row in board_rows.values()):
            raise RuntimeError(f"public /ratings disagrees with the receipt for {entry['name']!r}: "
                               "a full leaderboard must outrank an absent seat")
    return {"match_id": result.get("match_id"),
            "deltas": {entry["name"]: entry["delta"] for entry in row_by_id.values()},
            "public_routes": {"checked": True, "rated_grace": status.get("rated_grace"),
                              "players": public_players}}


def side_summary(seen: dict) -> dict:
    return {"player": seen["player"], "player_id": seen["player_id"], "tick": seen["tick"],
            "orders": seen["orders"], "winner": seen["winner"],
            "reconnects": seen["reconnects"], "continuity": seen["continuity"]}


def run(argv=None) -> int:
    args = arguments(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    started: list[tuple[str, Path]] = []
    started_at = time.monotonic()
    report: dict = {"status": "running", "server": args.server, "rated": args.rated}
    outcome: dict | None = None
    rated_info: dict | None = None
    host_seen, guest_seen = fresh_accumulator(), fresh_accumulator()
    failure: str | None = None
    interrupted = False
    try:
        timeout = args.timeout if args.timeout is not None else args.duration + 300
        start_host(args)
        started.append(("host", args.host_target))
        room = wait_for_room(args, host_seen, time.monotonic() + args.wait_timeout)
        start_guest(args, room)
        started.append(("guest", args.guest_target))
        wait_for_finished(args, host_seen, guest_seen, started_at + timeout)
        outcome = check_match(host_seen, guest_seen)
        if args.rated:
            rated_info = check_rated(args, host_seen, guest_seen)
    except KeyboardInterrupt:
        failure = "KeyboardInterrupt: operator stopped the run"
        interrupted = True
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"
    cleanup_errors = []
    for side, target in started:
        try:
            helper_stop(args, target, side)
        except Exception as exc:
            cleanup_errors.append(f"{side}: {exc}")
    if cleanup_errors:
        cleanup_message = "cleanup failed: " + "; ".join(cleanup_errors)
        failure = f"{failure}; {cleanup_message}" if failure else cleanup_message
    report["elapsed_seconds"] = round(time.monotonic() - started_at, 3)
    if failure is None and outcome is not None:
        report.update(status="passed", **outcome,
                      host=side_summary(host_seen), guest=side_summary(guest_seen),
                      guest_rejoined=True)
        if rated_info is not None:
            report.update(match_id=rated_info["match_id"],
                          ratings={"deltas": rated_info["deltas"]},
                          public_routes=rated_info["public_routes"])
        line = (f"PASS: room {report['room']} winner {report['winner']} "
                f"seats {report['seats']} guest rejoined")
        if rated_info is not None:
            line += (f" rated {report['match_id']} "
                     f"deltas {report['ratings']['deltas']}")
        print(f"{line} in {report['elapsed_seconds']}s")
    else:
        report["status"] = "failed"
        report["error"] = failure or "unknown error"
        print(f"FAIL: {report['error']}")
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if failure is not None:
        return 130 if interrupted else 1
    return 0


def main(argv=None) -> int:
    try:
        return run(argv)
    except SystemExit as exc:
        raise
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
