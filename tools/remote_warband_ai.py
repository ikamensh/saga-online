"""Install and run a headless client on a separate, explicitly named Scaleway VM.

    uv run python tools/remote_warband_ai.py install --archive dist/online-ai/<sha>.tar.gz
    uv run python tools/remote_warband_ai.py create --player-name Alice --rated
    uv run python tools/remote_warband_ai.py join --room ABC123 --reconnect-after 15
    uv run python tools/remote_warband_ai.py status --json

Targets are the disposable ``saga2d-warband-ai`` instance or a slug variant
``saga2d-warband-ai-<slug>``; the ``saga2d-online`` room server is refused.
Every command verifies the remote ``/etc/saga2d-online/managed-instance``
marker matches the chosen target before any mutation. Ranked runs forward
``--rated``/``--player-name`` to the headless client; an ``--identity-file``
must already be an owner-only mode 0600 file, is uploaded without ever being
printed, and lives at ``/var/lib/saga2d-warband-ai/identity.json`` for the
unprivileged client. Provisioning and SSH credentials use the existing
deployment tooling; no cloud credentials or private tokens are echoed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat as statmod
import subprocess
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.deploy_online import ROOT, package_release, ssh, ssh_options

SERVICE = "saga2d-warband-ai"
RUNTIME = "/opt/saga2d-warband-ai/current"
STATE_DIR = "/var/lib/saga2d-warband-ai"
REMOTE_IDENTITY = STATE_DIR + "/identity.json"
PRODUCTION = "saga2d-online"
PUBLIC_SERVER = "wss://games.tachyon-ai.eu/play"

TARGET_PATTERN = re.compile(r"saga2d-warband-ai(?:-[a-z0-9-]{1,40})?\Z")
ROOM_PATTERN = re.compile(r"[A-Za-z0-9]{3,16}\Z")
PLAYER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,31}\Z")
EVENT_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,40}\Z")
SECRET_HINTS = ("token", "secret", "password", "credential", "private")
TOKEN_RUN = re.compile(r"[A-Za-z0-9_+/=-]{20,}")
DIFFICULTIES = ("easy", "medium", "hard", "master")
THEMES = ("summer", "winter", "wasteland")
RACES = ("human", "orc", "elf", "dwarf")
JOURNAL_MAX_LINES = 200


def arguments(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("install", "create", "join", "status", "stop"))
    parser.add_argument("--target", type=Path, default=ROOT / "dist/online-ai/target.json")
    parser.add_argument("--ssh-key", type=Path, default=Path.home() / ".ssh/id_ed25519.pub")
    parser.add_argument("--server", default=PUBLIC_SERVER)
    parser.add_argument("--room")
    parser.add_argument("--difficulty", choices=DIFFICULTIES, default="medium")
    parser.add_argument("--duration", type=float, default=1800)
    parser.add_argument("--reconnect-after", type=float, default=None,
                        help="deliberately reconnect this many seconds into the match")
    parser.add_argument("--disconnect-for", type=float, default=None,
                        help="stay disconnected this many seconds before rejoining")
    parser.add_argument("--require-completion", action="store_true",
                        help="refuse to stop for anything but the authoritative result")
    parser.add_argument("--seed", type=int, default=None, help="map seed for --create")
    parser.add_argument("--width", type=int, default=None, help="map width for --create (48-80)")
    parser.add_argument("--height", type=int, default=None, help="map height for --create (40-64)")
    parser.add_argument("--theme", choices=THEMES, default=None, help="map theme for --create")
    parser.add_argument("--race", choices=RACES, default=None,
                        help="this seat's race choice (bot player_options)")
    parser.add_argument("--rated", action="store_true", help="ranked run (create only)")
    parser.add_argument("--player-name", default=None, help="public bot name for this target")
    parser.add_argument("--identity-file", type=Path, default=None,
                        help="local owner-only mode 0600 identity file, uploaded not printed")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable status (systemd fields plus this run's bot events)")
    parser.add_argument("--archive", type=Path, default=None,
                        help="explicitly prepared client archive for install (content-hashed)")
    args = parser.parse_args(argv)
    validate(args, parser)
    return args


def positive_finite(parser: argparse.ArgumentParser, name: str, value: float | None) -> None:
    if value is not None and (not math.isfinite(value) or value <= 0):
        parser.error(f"{name} must be positive and finite")


def validate(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.command == "join" and not args.room:
        parser.error("join requires --room")
    if args.command == "create" and args.room:
        parser.error("create starts a new room; pass no --room")
    if args.command not in ("create", "join") and args.room:
        parser.error("--room is only valid for create or join")
    if args.room is not None and not ROOM_PATTERN.fullmatch(args.room):
        parser.error("--room must be 3-16 alphanumeric characters")
    if not math.isfinite(args.duration) or args.duration <= 0:
        parser.error("--duration must be positive and finite")
    positive_finite(parser, "--reconnect-after", args.reconnect_after)
    positive_finite(parser, "--disconnect-for", args.disconnect_for)
    if args.command in ("create", "join"):
        check_server(args.server, parser)
    validate_options(args, parser)


def check_server(server: str, parser: argparse.ArgumentParser) -> None:
    """The bots play through the public endpoint: wss with no credentials or query."""
    try:
        parts = urllib.parse.urlsplit(server)
    except ValueError:
        parts = None
    if parts is None or parts.scheme != "wss" or not parts.hostname:
        parser.error("--server must be the public wss:// endpoint")
    if parts.username or parts.password or parts.query or parts.fragment:
        parser.error("--server must carry no credentials, query or fragment")


def validate_options(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.rated and args.command != "create":
        parser.error("--rated is only valid for create")
    for flag in ("seed", "width", "height", "theme"):
        if getattr(args, flag) is not None and args.command != "create":
            parser.error(f"--{flag} is only valid for create")
    if args.width is not None and not 48 <= args.width <= 80:
        parser.error("--width must be 48-80")
    if args.height is not None and not 40 <= args.height <= 64:
        parser.error("--height must be 40-64")
    if args.player_name is not None and not PLAYER_PATTERN.fullmatch(args.player_name):
        parser.error("--player-name must be 1-32 letters, digits, spaces, _ or -")
    if args.rated and not args.player_name:
        parser.error("--rated requires --player-name")
    if args.identity_file is not None:
        if not args.player_name:
            parser.error("--identity-file requires --player-name")
        if not args.identity_file.is_file():
            parser.error(f"--identity-file does not exist: {args.identity_file}")
        mode = statmod.S_IMODE(os.stat(args.identity_file).st_mode)
        if mode & 0o077:
            parser.error("--identity-file must be a private mode 0600 file")
    if args.json and args.command != "status":
        parser.error("--json is only valid for status")
    if args.archive is not None and args.command != "install":
        parser.error("--archive is only valid for install")
    if args.archive is not None and not args.archive.is_file():
        parser.error(f"--archive does not exist: {args.archive}")


def load_target(path: Path) -> dict:
    try:
        target = json.loads(path.read_text())
    except FileNotFoundError:
        raise ValueError(f"Target file does not exist: {path}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Target file is not valid JSON: {path}: {exc}")
    if not isinstance(target, dict) or not isinstance(target.get("name"), str):
        raise ValueError(f"Target file names no instance: {path}")
    return target


def check_target_name(name: str) -> str:
    if name == PRODUCTION:
        raise ValueError(f"Refusing the {PRODUCTION} production target: bots run on separate VMs")
    if not TARGET_PATTERN.fullmatch(name):
        raise ValueError(f"Target must be saga2d-warband-ai or saga2d-warband-ai-<slug>: {name!r}")
    return name


def check_remote_marker(args: argparse.Namespace, target: dict) -> None:
    """Confirm the live VM's identity matches the chosen target before any mutation."""
    marker = ssh(args, target, ["cat", "/etc/saga2d-online/managed-instance"],
                 capture=True).stdout.strip()
    if marker != target["name"]:
        raise ValueError(f"Remote instance {marker!r} does not match target {target['name']!r}")


def unit_states(args: argparse.Namespace, target: dict) -> dict:
    """Keyed property parse only: systemctl emits canonical order, not CLI order."""
    shown = ssh(args, target, ["systemctl", "show", SERVICE, "-p", "ActiveState",
                               "-p", "SubState", "-p", "LoadState"],
                capture=True).stdout
    return parse_show(shown)


def service_running(states: dict) -> bool:
    return states.get("ActiveState") == "active" and states.get("SubState") == "running"


def content_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def secret_key(key: object) -> bool:
    return any(hint in str(key).lower() for hint in SECRET_HINTS)


def redact_value(value: object) -> object:
    """Drop credential-shaped keys at every depth of bot evidence."""
    if isinstance(value, dict):
        return {key: redact_value(item) for key, item in value.items()
                if not secret_key(key)}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    return value


def redact_text(text: str) -> str:
    """Redact token-like runs from arbitrary free-form strings such as errors."""
    return TOKEN_RUN.sub("[redacted]", text)


def sanitize_event(event: dict) -> dict:
    """Keep bot evidence while dropping anything shaped like a private credential."""
    return {key: redact_value(item) for key, item in event.items() if not secret_key(key)}


def parse_bot_events(text: str) -> tuple[list[dict], int]:
    """Parse journal lines into sanitized bot events, capped for machine reports."""
    events: list[dict] = []
    lines = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        lines += 1
        if len(events) >= JOURNAL_MAX_LINES:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and isinstance(event.get("event"), str) \
                and EVENT_PATTERN.fullmatch(event["event"]):
            events.append(sanitize_event(event))
    return events, lines


def summarize_events(events: list[dict]) -> dict:
    summary: dict = {"room": None, "player": None, "difficulty": None, "finished": False,
                     "reason": None, "winner": None, "tick": 0, "states_received": 0,
                     "orders_submitted": 0, "reconnects_observed": 0, "result": None,
                     "player_id": None, "profile": None,
                     "rejoin_continuity": None, "error": None}
    saw_pause = False
    saw_ready = False
    for event in events:
        kind = event["event"]
        if kind in ("created", "joined") and summary["room"] is None:
            summary["room"] = event.get("room")
            summary["player"] = event.get("player")
            summary["difficulty"] = event.get("difficulty")
        elif kind == "match_ready":
            if saw_pause:
                summary["reconnects_observed"] += 1
                saw_pause = False
            saw_ready = True
        elif kind == "match_paused":
            if saw_ready:
                saw_pause = True
        elif kind in ("reconnected", "rejoined"):
            summary["reconnects_observed"] += 1
            if kind == "rejoined":
                continuity = {}
                for key in ("player", "before_tick", "tick"):
                    value = event.get(key)
                    if isinstance(value, int) and not isinstance(value, bool):
                        continuity[key] = value
                for key in ("before_units", "units", "before_buildings", "buildings"):
                    value = event.get(key)
                    if isinstance(value, list) and all(
                            isinstance(item, int) and not isinstance(item, bool)
                            for item in value):
                        continuity[key] = list(value)
                if {"player", "before_tick", "tick"} <= set(continuity):
                    summary["rejoin_continuity"] = continuity
                if continuity:
                    summary["rejoin_continuity"] = continuity
        elif kind == "authoritative_state":
            summary["states_received"] += 1
            if isinstance(event.get("tick"), int):
                summary["tick"] = max(summary["tick"], event["tick"])
            if event.get("winner") is not None:
                summary["winner"] = event["winner"]
        elif kind == "order_submitted":
            sequence = event.get("sequence")
            if isinstance(sequence, int):
                summary["orders_submitted"] = max(summary["orders_submitted"], sequence)
        elif kind == "finished":
            summary["finished"] = True
            summary["reason"] = event.get("reason")
            summary["winner"] = event.get("winner", summary["winner"])
            if isinstance(event.get("tick"), int):
                summary["tick"] = max(summary["tick"], event["tick"])
            for key in ("states_received", "orders_submitted"):
                if isinstance(event.get(key), int):
                    summary[key] = max(summary[key], event[key])
            if isinstance(event.get("result"), dict):
                summary["result"] = sanitize_event(event["result"])
            # Public identity rides with a rated receipt; private tokens never do
            # (sanitize_event strips credential-shaped keys at every depth).
            if isinstance(event.get("player_id"), str) and event["player_id"]:
                summary["player_id"] = event["player_id"]
            if isinstance(event.get("profile"), dict):
                summary["profile"] = sanitize_event(event["profile"])
        elif kind == "error" and summary["error"] is None:
            summary["error"] = redact_text(str(event.get("error", "bot error")))[:200]
    return summary


def parse_show(text: str) -> dict:
    fields = {}
    for line in text.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            fields[key.strip()] = value.strip()
    return fields


def bot_args(args: argparse.Namespace, remote_identity: str | None) -> list[str]:
    """Command line for the headless client; new flags are only sent when set."""
    if args.command == "create":
        argv = ["--create"]
    else:
        argv = ["--room", args.room]
    argv += ["--server", args.server, "--difficulty", args.difficulty,
             "--duration", str(args.duration)]
    if args.reconnect_after is not None:
        argv += ["--reconnect-after", str(args.reconnect_after)]
    if args.disconnect_for is not None:
        argv += ["--disconnect-for", str(args.disconnect_for)]
    if args.require_completion:
        argv.append("--require-completion")
    if args.race is not None:
        argv += ["--race", args.race]
    if args.command == "create":
        if args.seed is not None:
            argv += ["--seed", str(args.seed)]
        if args.width is not None:
            argv += ["--width", str(args.width)]
        if args.height is not None:
            argv += ["--height", str(args.height)]
        if args.theme is not None:
            argv += ["--theme", args.theme]
        if args.rated:
            argv.append("--rated")
    if args.player_name is not None:
        argv += ["--player-name", args.player_name]
    if remote_identity is not None:
        argv += ["--identity-file", remote_identity]
    return argv


def upload_identity(args: argparse.Namespace, target: dict) -> str:
    """Stage the local owner-only identity file for the unprivileged client.

    Only the remote path is ever returned or forwarded; file bytes are copied
    by scp and never printed.
    """
    assert args.identity_file is not None
    staging = f"/tmp/warband-ai-identity-{target['name']}"
    subprocess.run(["scp", *ssh_options(args), str(args.identity_file),
                    f"deploy@{target['ip']}:{staging}"],
                   check=True, capture_output=True, text=True)
    ssh(args, target, ["sudo", "mkdir", "-p", STATE_DIR], capture=True)
    ssh(args, target, ["sudo", "install", "-m", "600", "-o", "saga2d-online",
                       "-g", "saga2d-online", staging, REMOTE_IDENTITY], capture=True)
    ssh(args, target, ["rm", "-f", "--", staging], capture=True)
    return REMOTE_IDENTITY


def do_install(args: argparse.Namespace, target: dict) -> None:
    ssh(args, target, ["sudo", "cloud-init", "status", "--wait"], capture=True)
    if args.archive is not None:
        release = content_hash(args.archive)
        archive = str(args.archive.resolve())
    else:
        artifact = package_release(ROOT / "dist/online-ai")
        release = artifact["release"]
        archive = artifact["archive"]
    remote_archive = f"/tmp/warband-ai-{release}.tar.gz"
    subprocess.run(["scp", *ssh_options(args), archive,
                    f"deploy@{target['ip']}:{remote_archive}"],
                   check=True, capture_output=True, text=True)
    remote_script = "/tmp/install_warband_ai.sh"
    subprocess.run(["scp", *ssh_options(args), str(ROOT / "deploy/install_warband_ai.sh"),
                    f"deploy@{target['ip']}:{remote_script}"],
                   check=True, capture_output=True, text=True)
    installed = ssh(args, target, ["sudo", "bash", remote_script, remote_archive,
                                   release, target["name"]], capture=True)
    ssh(args, target, ["rm", "-f", "--", remote_archive, remote_script], capture=True)
    tail = installed.stdout.strip().splitlines()
    if tail:
        print(tail[-1], file=sys.stderr)
    print(json.dumps({**target, "release": release}))


def do_start(args: argparse.Namespace, target: dict) -> None:
    states = unit_states(args, target)
    if service_running(states):
        raise ValueError(f"Service {SERVICE} is already running on {target['name']}; "
                         "stop it before starting another bot")
    if states.get("LoadState", "not-found") != "not-found":
        # Unload the previous (completed or failed) transient unit so the service
        # name is reusable. Journal evidence stays queryable by InvocationID.
        ssh(args, target, ["sudo", "systemctl", "stop", SERVICE], capture=True)
    # Identity bytes are only staged while no bot runs on this VM: the explicit
    # file when the operator reuses one, else the automatic per-VM path where
    # the engine mints and keeps its private ranked identity across matches.
    if args.identity_file is not None:
        remote_identity = upload_identity(args, target)
    elif args.player_name is not None:
        remote_identity = REMOTE_IDENTITY
    else:
        remote_identity = None
    # No --collect plus RemainAfterExit: the transient unit keeps its InvocationID
    # and terminal finished event observable after the bot exits, until stopped.
    ssh(args, target, ["sudo", "systemd-run", "--unit", SERVICE,
        "--uid=saga2d-online", f"--working-directory={RUNTIME}",
        "--property=CPUQuota=25%", "--property=MemoryMax=256M",
        "--property=NoNewPrivileges=yes", "--property=ProtectSystem=strict",
        f"--property=ReadWritePaths={STATE_DIR}",
        "--property=RemainAfterExit=yes",
        "--property=ProtectHome=yes", "--property=PrivateTmp=yes",
        f"{RUNTIME}/.venv/bin/python", "-u", "-m", "warband.online.online_ai",
        *bot_args(args, remote_identity)], capture=True)
    print("AI started. Use the status command to read its room code and progress.")


def do_stop(args: argparse.Namespace, target: dict) -> None:
    ssh(args, target, ["sudo", "systemctl", "stop", SERVICE], capture=True)
    print(json.dumps({"target": target["name"], "stopped": True}))


def do_status(args: argparse.Namespace, target: dict) -> None:
    if args.json:
        do_status_json(args, target)
        return
    ssh(args, target, ["systemctl", "show", SERVICE, "-p", "ActiveState", "-p", "SubState",
                       "-p", "ExecMainStatus", "-p", "CPUUsageNSec", "-p", "MemoryCurrent"])
    invocation = ssh(args, target, ["systemctl", "show", SERVICE, "-p", "InvocationID",
                                    "--value"], capture=True).stdout.strip()
    if invocation and set(invocation) == {"0"}:
        invocation = ""
    if invocation:
        ssh(args, target, ["sudo", "journalctl", f"_SYSTEMD_INVOCATION_ID={invocation}",
            "--grep", '"event":"(created|joined)"', "-n", "1", "--no-pager", "-o", "cat"])
        ssh(args, target, ["sudo", "journalctl", f"_SYSTEMD_INVOCATION_ID={invocation}",
                           "-n", "20", "--no-pager", "-o", "cat"])
    else:
        ssh(args, target, ["sudo", "journalctl", "-u", SERVICE, "-n", "20",
                           "--no-pager", "-o", "cat"])


def do_status_json(args: argparse.Namespace, target: dict) -> None:
    shown = ssh(args, target, ["systemctl", "show", SERVICE, "-p", "ActiveState",
                               "-p", "SubState", "-p", "InvocationID", "-p", "ExecMainStatus",
                               "-p", "CPUUsageNSec", "-p", "MemoryCurrent"],
                capture=True).stdout
    fields = parse_show(shown)
    invocation = fields.get("InvocationID", "")
    if not invocation or set(invocation) == {"0"}:
        invocation = ""
    events: list[dict] = []
    journal_lines = 0
    if invocation:
        journal = ssh(args, target, ["sudo", "journalctl",
            f"_SYSTEMD_INVOCATION_ID={invocation}",
            "-n", str(JOURNAL_MAX_LINES), "--no-pager", "-o", "cat"],
            capture=True).stdout
        events, journal_lines = parse_bot_events(journal)
    summary = summarize_events(events)
    note = None
    if invocation and not events:
        note = (f"no usable bot events in invocation {invocation} "
                f"({journal_lines} journal lines)")
    print(json.dumps({
        "target": target["name"], "service": SERVICE,
        "active": service_running(fields), "systemd": fields,
        "invocation_id": invocation or None, **summary,
        "journal_lines": journal_lines, "journal_kept": len(events), "note": note,
    }))


def run(argv=None) -> int:
    args = arguments(argv)
    if not args.target.is_file():
        raise ValueError(f"Target file does not exist: {args.target}")
    target = load_target(args.target)
    if "ip" not in target:
        raise ValueError(f"Target file names no address: {args.target}")
    check_target_name(target["name"])
    check_remote_marker(args, target)
    if args.command == "install":
        do_install(args, target)
    elif args.command in ("create", "join"):
        do_start(args, target)
    elif args.command == "stop":
        do_stop(args, target)
    else:
        do_status(args, target)
    return 0


def main(argv=None) -> int:
    try:
        return run(argv)
    except (ValueError, RuntimeError, FileNotFoundError, OSError,
            subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
