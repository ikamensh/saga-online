"""Remote Warband AI operator tool: guards, pass-through flags and machine status.

Behavior is exercised through the real CLI with a fake ``ssh``/``scp``
boundary, never against cloud VMs and never through private helpers.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "remote_warband_ai.py"
INSTALLER = ROOT / "deploy" / "install_warband_ai.sh"

PUBLIC_SERVER = "wss://games.tachyon-ai.eu/play"

PRIOR_JOURNAL = "\n".join([
    json.dumps({"event": "created", "room": "OLDROOM", "player": 0, "difficulty": "easy"}),
    json.dumps({"event": "finished", "reason": "winner", "room": "OLDROOM", "player": 0,
                "tick": 100, "states_received": 2, "orders_submitted": 3, "winner": 1}),
])
CURRENT_JOURNAL = "\n".join([
    json.dumps({"event": "created", "room": "NEWROOM", "player": 1, "difficulty": "medium"}),
    json.dumps({"event": "match_ready", "revision": 3}),
    json.dumps({"event": "authoritative_state", "revision": 4, "tick": 120, "winner": None,
                "orders_submitted": 0}),
    json.dumps({"event": "order_submitted", "sequence": 1, "revision": 5, "tick": 130}),
    json.dumps({"event": "match_paused", "revision": 9}),
    json.dumps({"event": "rejoined", "room": "NEWROOM", "player": 1, "before_tick": 100,
                "tick": 130, "before_units": [11, 12], "units": [11, 12],
                "before_buildings": [21], "buildings": [21]}),
    json.dumps({"event": "match_ready", "revision": 12}),
    json.dumps({"event": "finished", "reason": "winner", "room": "NEWROOM", "player": 1,
                "tick": 5400, "states_received": 40, "orders_submitted": 120, "winner": 0}),
])


def write_fake_bin(path: Path, *, marker="saga2d-warband-ai", active_state="inactive",
                   journal_current=CURRENT_JOURNAL, journal_all=None) -> Path:
    """A fake ssh/scp pair emulating one remote VM; invocations append to log files."""
    bindir = path / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    log = path / "ssh.log"
    units = path / "units.log"
    scp_log = path / "scp.log"
    (path / "INV").write_text("AAA-111\n")
    (path / "RUNS").write_text("0\n")
    (path / "journal_AAA-111").write_text(journal_current + "\n")
    (path / "journal_all").write_text((journal_all if journal_all is not None
                                       else PRIOR_JOURNAL + "\n" + journal_current + "\n"))
    lines = [
        "#!/bin/bash",
        f"DIR={path}",
        f"LOG={log}",
        f"UNITS={units}",
        f"ALL={path / 'journal_all'}",
        f"MARKER={marker}",
        f"STATE={active_state}",
        'cmd=""',
        "seen_deploy=0",
        'for arg in "$@"; do',
        '  if (( seen_deploy )); then cmd="$arg"; break; fi',
        '  [[ "$arg" == deploy@* ]] && seen_deploy=1',
        "done",
        'printf "%s\\n" "$*" >>"$LOG"',
        'case "$cmd" in',
        '  "cat /etc/saga2d-online/managed-instance") printf "%s\\n" "$MARKER";;',
        '  *"ActiveState"*) if [[ "$STATE" == active ]]; then SUB=running; else SUB=dead; fi;'
        ' printf "LoadState=loaded\\nActiveState=%s\\nSubState=%s\\nInvocationID=%s\\n'
        'ExecMainStatus=0\\nCPUUsageNSec=7\\nMemoryCurrent=8\\n"'
        ' "$STATE" "$SUB" "$(cat "$DIR/INV")";;',
        '  *"InvocationID"*"--value"*) cat "$DIR/INV";;',
        '  *"systemd-run"*) printf "%s\\n" "$cmd" >>"$UNITS";'
        ' n=$(( $(cat "$DIR/RUNS") + 1 )); echo "$n" >"$DIR/RUNS";'
        ' echo "RUN-$n" >"$DIR/INV"; : >"$DIR/journal_RUN-$n"; printf "Started\\n";;',
        '  *"journalctl"*)',
        '    if [[ "$cmd" =~ _SYSTEMD_INVOCATION_ID=([A-Za-z0-9-]+) ]]; then'
        ' id="${BASH_REMATCH[1]}";'
        ' if [[ -f "$DIR/journal_$id" ]]; then cat "$DIR/journal_$id"; fi;'
        "    else cat \"$ALL\"; fi;;",
        '  *"cloud-init"*) printf "status: done\\n";;',
        '  *"systemctl stop"*) printf "Stopped\\n";;',
        '  "sudo "*|"rm "*) printf "ok\\n";;',
        '  *) printf "ok\\n";;',
        "esac",
    ]
    ssh = bindir / "ssh"
    ssh.write_text("\n".join(lines) + "\n")
    ssh.chmod(0o755)
    scp = bindir / "scp"
    scp.write_text("#!/bin/bash\n" + f"""\
printf '%s\\n' "$*" >>"{scp_log}"
""")
    scp.chmod(0o755)
    return bindir


def write_target(path: Path, *, name="saga2d-warband-ai", ip="10.0.0.1", server_id="srv-1") -> Path:
    target = path / "target.json"
    target.write_text(json.dumps({"name": name, "ip": ip, "server_id": server_id,
                                  "zone": "nl-ams-1", "state": "running"}) + "\n")
    return target


def write_ssh_key(path: Path) -> Path:
    pub = path / "id_ed25519.pub"
    pub.write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFAKEKEY test@example\n")
    (path / "id_ed25519").write_text("fake-private\n")
    return pub


def run_tool(env_path: Path, *argv: str, path: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = str(env_path) + os.pathsep + env.get("PATH", "")
    return subprocess.run([sys.executable, str(TOOL), *argv], capture_output=True, text=True,
                          cwd=str(path), env=env, timeout=60)


@pytest.fixture()
def rig(tmp_path):
    bindir = write_fake_bin(tmp_path)
    target = write_target(tmp_path)
    pub = write_ssh_key(tmp_path)
    return tmp_path, bindir, target, pub


def base_args(target: Path, pub: Path) -> list[str]:
    return ["--target", str(target), "--ssh-key", str(pub), "--server", PUBLIC_SERVER]


def ssh_log(path: Path) -> str:
    log = path / "ssh.log"
    return log.read_text() if log.exists() else ""


def test_help_advertises_rated_json_archive_and_reconnect_options(tmp_path):
    """Operators discover the ranked, machine-status and reconnect surface from --help."""
    result = subprocess.run([sys.executable, str(TOOL), "--help"], capture_output=True, text=True,
                            timeout=60)
    assert result.returncode == 0
    for flag in ("--rated", "--player-name", "--identity-file", "--json", "--archive",
                 "--reconnect-after", "--disconnect-for", "--require-completion",
                 "--seed", "--width", "--height", "--theme", "--race"):
        assert flag in result.stdout


def test_production_target_refused_before_any_ssh(rig):
    """The room server name can never be a bot target, even with a matching marker."""
    path, bindir, _, pub = rig
    target = write_target(path, name="saga2d-online", ip="51.159.207.49", server_id="srv-prod")
    result = run_tool(bindir, "status", *base_args(target, pub), path=path)
    assert result.returncode != 0
    assert "production" in result.stderr.lower() or "saga2d-online" in result.stderr
    assert ssh_log(path) == "", "refusal must happen before contacting SSH"


def test_slug_marker_mismatch_refuses_before_mutation(rig):
    """A slug target whose remote marker names another instance stops before systemd-run."""
    path, bindir, _, pub = rig
    target = write_target(path, name="saga2d-warband-ai-guest")
    result = run_tool(bindir, "create", *base_args(target, pub), path=path)
    assert result.returncode != 0
    assert "does not match" in result.stderr
    assert "systemd-run" not in ssh_log(path)


def test_matching_slug_target_passes_guard(rig):
    """A slug target with its own exact marker is an allowed separate VM."""
    path, bindir, _, pub = rig
    write_fake_bin(path / "guest", marker="saga2d-warband-ai-guest")
    guest_bin = path / "guest" / "bin"
    target = write_target(path, name="saga2d-warband-ai-guest", ip="10.0.0.2", server_id="srv-2")
    result = run_tool(guest_bin, "status", "--target", str(target), "--ssh-key", str(pub),
                      "--json", path=path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["target"] == "saga2d-warband-ai-guest"


def test_create_refuses_already_active_service(rig):
    """Starting over a running bot would silently overwrite its match, so it is refused."""
    path, _, target, pub = rig
    bindir = write_fake_bin(path / "busy", marker="saga2d-warband-ai", active_state="active")
    result = run_tool(bindir, "create", *base_args(target, pub), path=path)
    assert result.returncode != 0
    assert "already" in result.stderr.lower() or "active" in result.stderr.lower()
    assert "systemd-run" not in (path / "busy" / "ssh.log").read_text()


def test_create_forwards_reconnect_rated_seed_and_map_options(rig):
    """Pass-through flags reach the headless client verbatim on the remote unit."""
    path, bindir, target, pub = rig
    result = run_tool(bindir, "create", *base_args(target, pub),
                      "--reconnect-after", "5", "--disconnect-for", "2",
                      "--require-completion", "--rated", "--player-name", "Alice",
                      "--seed", "7", "--width", "64", "--height", "48", "--theme", "winter",
                      "--race", "orc", path=path)
    assert result.returncode == 0, result.stderr
    unit = (path / "units.log").read_text()
    for fragment in ("--reconnect-after 5", "--disconnect-for 2", "--require-completion",
                     "--rated", "--player-name Alice", "--seed 7",
                     "--width 64", "--height 48", "--theme winter", "--race orc",
                     "--identity-file /var/lib/saga2d-warband-ai/identity.json",
                     "ReadWritePaths=/var/lib/saga2d-warband-ai",
                     "RemainAfterExit=yes"):
        assert fragment in unit, fragment
    assert "--collect" not in unit
    assert not (path / "scp.log").exists(), "automatic identity needs no upload"


def test_join_forwards_race_and_player_choice(rig):
    """Each seat chooses its own race; the joiner inherits ranked from the room."""
    path, bindir, target, pub = rig
    result = run_tool(bindir, "join", *base_args(target, pub), "--room", "ABC123",
                      "--race", "elf", "--player-name", "Guest", "--reconnect-after", "15",
                      path=path)
    assert result.returncode == 0, result.stderr
    unit = (path / "units.log").read_text()
    for fragment in ("--room ABC123", "--race elf", "--player-name Guest",
                     "--reconnect-after 15",
                     "--identity-file /var/lib/saga2d-warband-ai/identity.json"):
        assert fragment in unit, fragment
    assert "--rated" not in unit


def test_join_rejects_create_only_options(rig):
    """--rated and map creation options belong to the room creator, not the joiner."""
    path, bindir, target, pub = rig
    for extra in (["--rated"], ["--seed", "7"], ["--width", "64"], ["--theme", "winter"]):
        result = run_tool(bindir, "join", *base_args(target, pub), "--room", "ABC123",
                          *extra, path=path)
        assert result.returncode == 2, extra
    assert ssh_log(path) == "", "option misuse must fail before contacting SSH"


def test_server_with_credentials_or_query_is_refused(rig):
    """The endpoint carries no userinfo, query or fragment; tokens never ride the URL."""
    path, bindir, target, pub = rig
    base = ["create", "--target", str(target), "--ssh-key", str(pub)]
    for server in ("wss://bot:secret@games.tachyon-ai.eu/play",
                   "wss://games.tachyon-ai.eu/play?token=abc",
                   "wss://games.tachyon-ai.eu/play#frag",
                   "ws://games.tachyon-ai.eu/play"):
        result = run_tool(bindir, *base, "--server", server, path=path)
        assert result.returncode == 2, server
    assert ssh_log(path) == ""


def test_cli_choices_match_warband_domain_enums():
    """Race/theme literals track warband.sim.rules; difficulty stays a bot subset."""
    try:
        from warband.sim.rules import Difficulty, MapTheme, Race
    except ImportError as exc:
        pytest.skip(f"warband stack not importable here: {exc}")
    sys.path.insert(0, str(ROOT))
    from tools.remote_warband_ai import DIFFICULTIES, RACES, THEMES
    assert tuple(item.value for item in Race) == RACES
    assert tuple(item.value for item in MapTheme) == THEMES
    assert set(DIFFICULTIES) <= {item.value for item in Difficulty}


def test_room_duration_and_sizes_validated_before_ssh(rig):
    """Malformed room codes and non-positive or out-of-range numbers never reach SSH."""
    path, bindir, target, pub = rig
    cases = [
        ["create", "--room", "BAD ROOM!"],
        ["join", "--room", "abc 123"],
        ["create", "--duration", "0"],
        ["create", "--reconnect-after", "-1"],
        ["create", "--disconnect-for", "nan"],
        ["create", "--width", "10"],
        ["create", "--height", "999"],
        ["create", "--theme", "desert"],
        ["create", "--player-name", ""],
    ]
    for argv in cases:
        result = run_tool(bindir, *argv, *base_args(target, pub), path=path)
        assert result.returncode == 2, argv
    assert ssh_log(path) == ""


def test_status_json_reports_current_invocation_only(rig):
    """Machine status carries systemd fields plus this run's bot events, not prior runs'."""
    path, bindir, target, pub = rig
    result = run_tool(bindir, "status", "--target", str(target), "--ssh-key", str(pub),
                      "--json", path=path)
    assert result.returncode == 0, result.stderr
    status = json.loads(result.stdout)
    assert status["target"] == "saga2d-warband-ai"
    assert status["systemd"]["ActiveState"] == "inactive"
    assert status["invocation_id"] == "AAA-111"
    assert status["room"] == "NEWROOM" and status["player"] == 1
    assert status["finished"] is True and status["reason"] == "winner"
    assert status["winner"] == 0 and status["tick"] == 5400
    assert status["orders_submitted"] == 120 and status["reconnects_observed"] == 2
    assert status["rejoin_continuity"] == {"player": 1, "before_tick": 100, "tick": 130,
                                           "before_units": [11, 12], "units": [11, 12],
                                           "before_buildings": [21], "buildings": [21]}
    assert "OLDROOM" not in result.stdout
    assert status["journal_kept"] <= 200 and status["journal_lines"] >= status["journal_kept"]


def test_status_json_never_emits_private_tokens(rig):
    """Journal secrets are sanitized at every depth, including free-form errors."""
    path, _, target, pub = rig
    journal = (CURRENT_JOURNAL + "\n"
               + json.dumps({"event": "note", "token": "SECRET-TOKEN-123",
                             "resume_token": "RESUME-SECRET-456"}) + "\n"
               + json.dumps({"event": "authoritative_state", "revision": 5, "tick": 140,
                             "debug": {"resume_token": "NESTED-SECRET-9999999999"}}) + "\n"
               + json.dumps({"event": "error",
                             "error": "login failed with token SECRETVALUE1234567890abcdef end"}))
    bindir = write_fake_bin(path / "leaky", marker="saga2d-warband-ai", journal_current=journal,
                            journal_all=journal)
    result = run_tool(bindir, "status", "--target", str(target), "--ssh-key", str(pub),
                      "--json", path=path)
    assert result.returncode == 0, result.stderr
    assert "SECRET-TOKEN-123" not in result.stdout
    assert "RESUME-SECRET-456" not in result.stdout
    assert "NESTED-SECRET-9999999999" not in result.stdout
    assert "SECRETVALUE1234567890abcdef" not in result.stdout
    assert "[redacted]" in result.stdout


def test_completed_unit_stays_observable_and_prior_runs_do_not_leak(tmp_path):
    """A finished unit is not collected: its terminal event stays readable under a new id."""
    run1 = "\n".join([
        json.dumps({"event": "created", "room": "OLDROOM", "player": 0, "difficulty": "easy"}),
        json.dumps({"event": "finished", "reason": "winner", "room": "OLDROOM", "player": 0,
                    "tick": 100, "states_received": 2, "orders_submitted": 3, "winner": 1}),
    ])
    bindir = write_fake_bin(tmp_path, marker="saga2d-warband-ai", journal_current=run1,
                            journal_all=run1)
    target = write_target(tmp_path)
    pub = write_ssh_key(tmp_path)
    status_argv = ["status", "--target", str(target), "--ssh-key", str(pub), "--json"]
    first = json.loads(run_tool(bindir, *status_argv, path=tmp_path).stdout)
    assert (first["invocation_id"], first["room"], first["finished"]) == ("AAA-111", "OLDROOM", True)
    started = run_tool(bindir, "create", "--target", str(target), "--ssh-key", str(pub),
                       "--server", PUBLIC_SERVER, path=tmp_path)
    assert started.returncode == 0, started.stderr
    units = (tmp_path / "units.log").read_text()
    assert "--collect" not in units
    second = json.loads(run_tool(bindir, *status_argv, path=tmp_path).stdout)
    assert second["invocation_id"] == "RUN-1" and second["finished"] is False
    assert second["room"] is None and "OLDROOM" not in json.dumps(second)
    assert "RUN-1" in (second["note"] or "")
    (tmp_path / "journal_RUN-1").write_text("\n".join([
        json.dumps({"event": "created", "room": "NEWROOM", "player": 0, "difficulty": "medium"}),
        json.dumps({"event": "finished", "reason": "winner", "room": "NEWROOM", "player": 0,
                    "tick": 5400, "states_received": 40, "orders_submitted": 120, "winner": 0}),
    ]) + "\n")
    third = json.loads(run_tool(bindir, *status_argv, path=tmp_path).stdout)
    assert (third["invocation_id"], third["room"], third["finished"], third["winner"]) == \
        ("RUN-1", "NEWROOM", True, 0)
    assert "OLDROOM" not in json.dumps(third)


def test_install_with_explicit_archive_hashes_it_locally(rig):
    """A reviewed archive is content-addressed by the tool; the hash reaches the installer."""
    path, bindir, target, pub = rig
    archive = path / "client.tar.gz"
    archive.write_bytes(b"reviewed-client-source")
    digest = hashlib.sha256(b"reviewed-client-source").hexdigest()
    result = run_tool(bindir, "install", *base_args(target, pub),
                      "--archive", str(archive), path=path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["release"] == digest
    log = ssh_log(path)
    assert log.index("managed-instance") < (path / "scp.log").read_text().find("client.tar.gz")
    assert digest in log and "saga2d-warband-ai" in log
    assert "systemd-run" not in log


def test_install_refuses_production_marker_before_upload(rig):
    """An installer pointed at the room server stops before any archive is copied."""
    path, _, target, pub = rig
    bindir = write_fake_bin(path / "prod", marker="saga2d-online")
    archive = path / "client.tar.gz"
    archive.write_bytes(b"reviewed-client-source")
    result = run_tool(bindir, "install", "--target", str(target), "--ssh-key", str(pub),
                      "--server", PUBLIC_SERVER, "--archive", str(archive), path=path)
    assert result.returncode != 0
    assert not (path / "prod" / "scp.log").exists(), "no upload may happen after a guard failure"


def test_identity_file_requires_private_mode_and_stays_sanitized(rig):
    """Identity files must already be owner-only; their bytes never appear in output."""
    path, bindir, target, pub = rig
    identity = path / "guest.identity"
    identity.write_text("PRIVATE-IDENTITY-BYTES-789")
    identity.chmod(0o644)
    result = run_tool(bindir, "create", *base_args(target, pub), "--player-name", "Guest",
                      "--identity-file", str(identity), path=path)
    assert result.returncode != 0
    assert "0600" in result.stderr or "private" in result.stderr.lower()
    identity.chmod(0o600)
    result = run_tool(bindir, "create", *base_args(target, pub), "--player-name", "Guest",
                      "--identity-file", str(identity), path=path)
    assert result.returncode == 0, result.stderr
    unit = (path / "units.log").read_text()
    assert "--identity-file /var/lib/saga2d-warband-ai/identity.json" in unit
    assert "PRIVATE-IDENTITY-BYTES-789" not in result.stdout + result.stderr
    assert "PRIVATE-IDENTITY-BYTES-789" not in (path / "scp.log").read_text()


def test_installer_script_refuses_production_and_foreign_instances(tmp_path):
    """The shell installer guards the room server even when invoked directly."""
    assert subprocess.run(["bash", "-n", str(INSTALLER)], capture_output=True).returncode == 0
    text = INSTALLER.read_text()
    assert "saga2d-online" in text and "/var/lib/saga2d-warband-ai" in text
    fake_cat = tmp_path / "bin"
    fake_cat.mkdir()
    script = fake_cat / "cat"
    script.write_text("#!/bin/bash\nprintf '%s\\n' \"$FAKE_MARKER\"\n")
    script.chmod(0o755)
    env = dict(os.environ, PATH=str(fake_cat) + os.pathsep + os.environ.get("PATH", ""))
    digest = hashlib.sha256(b"x").hexdigest()
    for marker, expected in (("saga2d-online", "saga2d-warband-ai"),
                             ("saga2d-warband-ai", "saga2d-warband-ai-guest"),
                             ("saga2d-online", "saga2d-online")):
        run_env = dict(env, FAKE_MARKER=marker)
        result = subprocess.run(["bash", str(INSTALLER), "/tmp/archive.tar.gz", digest, expected],
                                capture_output=True, text=True, env=run_env, timeout=30)
        assert result.returncode != 0, (marker, expected)


def test_real_bot_help_when_dependencies_available():
    """The packaged headless client still exposes its CLI when the stack imports."""
    python = shutil.which("python3")
    assert python
    result = subprocess.run([sys.executable, "-m", "warband.online.online_ai", "--help"],
                            capture_output=True, text=True, timeout=60, cwd=str(ROOT))
    if result.returncode != 0:
        pytest.skip(f"warband stack not importable here: {result.stderr.strip()[:200]}")
    assert "--create" in result.stdout and "--difficulty" in result.stdout
