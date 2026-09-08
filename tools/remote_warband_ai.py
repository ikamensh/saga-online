"""Install and run a headless client on the separate, explicitly named Scaleway VM.

    uv run python tools/remote_warband_ai.py install
    uv run python tools/remote_warband_ai.py create
    uv run python tools/remote_warband_ai.py join --room ABC123
    uv run python tools/remote_warband_ai.py status

Provisioning and SSH credentials use the existing deployment tooling; no cloud
credentials or private seat tokens are uploaded. See docs/online-multiplayer.md.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.deploy_online import ROOT, package_release, ssh, ssh_options

SERVICE = "saga2d-warband-ai"
RUNTIME = "/opt/saga2d-warband-ai/current"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "create", "join", "status", "stop"))
    parser.add_argument("--target", type=Path, default=ROOT / "dist/online-ai/target.json")
    parser.add_argument("--ssh-key", type=Path, default=Path.home() / ".ssh/id_ed25519.pub")
    parser.add_argument("--server", default="wss://games.tachyon-ai.eu/play")
    parser.add_argument("--room")
    parser.add_argument("--difficulty", choices=("easy", "normal", "hard"), default="normal")
    parser.add_argument("--duration", type=float, default=1800)
    args = parser.parse_args()
    if args.command == "join" and not args.room:
        parser.error("join requires --room")
    if not math.isfinite(args.duration) or args.duration <= 0:
        parser.error("--duration must be positive and finite")
    target = json.loads(args.target.read_text())
    if target["name"] != SERVICE:
        raise ValueError("The target must be the separate saga2d-warband-ai instance")
    marker = ssh(args, target, ["cat", "/etc/saga2d-online/managed-instance"], capture=True).stdout.strip()
    if marker != SERVICE:
        raise ValueError("Remote instance identity does not match the AI target")

    if args.command == "install":
        ssh(args, target, ["sudo", "cloud-init", "status", "--wait"])
        artifact = package_release(ROOT / "dist/online-ai")
        remote_archive = f"/tmp/warband-ai-{artifact['release']}.tar.gz"
        subprocess.run(["scp", *ssh_options(args), artifact["archive"],
                        f"deploy@{target['ip']}:{remote_archive}"], check=True)
        remote_script = "/tmp/install_warband_ai.sh"
        subprocess.run(["scp", *ssh_options(args), str(ROOT / "deploy/install_warband_ai.sh"),
                        f"deploy@{target['ip']}:{remote_script}"], check=True)
        ssh(args, target, ["sudo", "bash", remote_script, remote_archive, artifact["release"]])
        ssh(args, target, ["rm", remote_archive, remote_script])
        print(json.dumps({**target, "release": artifact["release"]}))
    elif args.command in ("create", "join"):
        client_args = (["--create"] if args.command == "create" else ["--room", args.room])
        ssh(args, target, ["sudo", "systemd-run", "--unit", SERVICE, "--collect",
            "--uid=saga2d-online", f"--working-directory={RUNTIME}",
            "--property=CPUQuota=25%", "--property=MemoryMax=256M",
            "--property=NoNewPrivileges=yes", "--property=ProtectSystem=strict",
            "--property=ProtectHome=yes", "--property=PrivateTmp=yes",
            f"{RUNTIME}/.venv/bin/python", "-u", "-m", "warband.online_ai",
            *client_args, "--server", args.server, "--difficulty", args.difficulty,
            "--duration", str(args.duration)])
        print("AI started. Use the status command to read its room code and progress.")
    elif args.command == "stop":
        ssh(args, target, ["sudo", "systemctl", "stop", SERVICE])
    else:
        ssh(args, target, ["systemctl", "show", SERVICE, "-p", "ActiveState", "-p", "SubState",
                           "-p", "ExecMainStatus", "-p", "CPUUsageNSec", "-p", "MemoryCurrent"])
        invocation = ssh(args, target, ["systemctl", "show", SERVICE, "-p", "InvocationID", "--value"], capture=True).stdout.strip()
        if invocation:
            ssh(args, target, ["sudo", "journalctl", f"_SYSTEMD_INVOCATION_ID={invocation}",
                "--grep", '"event":"(created|joined)"', "-n", "1", "--no-pager", "-o", "cat"])
        ssh(args, target, ["sudo", "journalctl", "-u", SERVICE, "-n", "20", "--no-pager", "-o", "cat"])


if __name__ == "__main__":
    main()
