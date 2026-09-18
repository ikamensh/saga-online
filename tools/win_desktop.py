#!/usr/bin/env python3
"""An interactive Windows desktop without a person: open, use and close a session on a Windows test box.

    python tools/win_desktop.py open  --host IP --ssh-key KEY --secret JSON --size 3840x2160 --scale 200
    python tools/win_desktop.py push  --host IP --ssh-key KEY FILE...          # into C:\\win4k
    python tools/win_desktop.py run   --host IP --ssh-key KEY warband_check.ps1 --done session_check.done
    python tools/win_desktop.py fetch --host IP --ssh-key KEY --to DIR NAME...
    python tools/win_desktop.py close --host IP --ssh-key KEY

``open`` logs any earlier session off and starts FreeRDP in a container (``tools/win_box/Dockerfile``, a virtual
X display, nothing on this machine's screen) with network-level authentication; the password goes from the
secret file to the client's standard input and nowhere else.  The size and the desktop scaling are the client's
to choose, which is what a test of a scaled desktop needs.  ``run`` starts a script of ``C:\\win4k`` inside that
session through a scheduled task with an interactive logon, because a process started over SSH has no desktop.
See docs/windows-test-box.md for creating the box and for why each step is the way it is.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
IMAGE, CONTAINER = "saga-win-desktop", "saga-win-desktop"


def ssh(args, command: str, *, check=True) -> str:
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-o", "IdentitiesOnly=yes",
                             "-i", str(args.ssh_key), f"{args.user}@{args.host}", command], capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError(f"ssh: {command}\n{result.stdout}{result.stderr}")
    return result.stdout


def sessions(args) -> list[str]:
    """Ids of the user's sessions; ``query user`` exits 1 and names nobody when there is none."""
    lines = ssh(args, "query user", check=False).splitlines()[1:]
    return [next(part for part in line.split() if part.isdigit()) for line in lines if args.user.lower() in line.lower()]


def close(args) -> None:
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    for session in sessions(args):
        ssh(args, f"logoff {session}")
    while sessions(args):
        time.sleep(3)


def open_session(args) -> None:
    close(args)  # a logon is what applies a scaling; a reconnected session keeps its old one
    subprocess.run(["docker", "build", "-q", "-t", IMAGE, str(ROOT / "tools" / "win_box")], check=True, capture_output=True)
    password = json.loads(args.secret.expanduser().read_text())["Password"]
    device = 180 if args.scale >= 180 else 140 if args.scale >= 140 else 100
    client = (f"xvfb-run -a -s '-screen 0 {args.size}x24' xfreerdp3 /v:{args.host} /u:{args.user} /from-stdin /sec:nla "
              f"/size:{args.size} /scale-desktop:{args.scale} /scale:{device} /scale-device:{device} /cert:ignore "
              f"-dynamic-resolution /gfx /log-level:ERROR")
    process = subprocess.Popen(["docker", "run", "-i", "--rm", "--name", CONTAINER, IMAGE, "sh", "-c", client],
                               stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    process.stdin.write(f"\n{password}\n".encode())  # the client asks for the domain, then the password
    process.stdin.close()
    deadline = time.time() + 120
    while "Active" not in ssh(args, "query user", check=False):
        if time.time() > deadline or process.poll() is not None:
            raise RuntimeError("No interactive session appeared; is RDP on the box set to TLS with NLA (docs/windows-test-box.md)?")
        time.sleep(4)
    time.sleep(25)  # the shell of a fresh logon is still starting
    print(f"session open on {args.host}: {args.size} at {args.scale} %")


def push(args) -> None:
    ssh(args, r"if not exist C:\win4k mkdir C:\win4k")
    subprocess.run(["scp", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-i", str(args.ssh_key), *map(str, args.files),
                    f"{args.user}@{args.host}:C:/win4k/"], check=True, capture_output=True)


def run(args) -> None:
    if args.done:
        ssh(args, rf"del C:\win4k\{args.done} 2>nul", check=False)
    print(ssh(args, rf"powershell -NoProfile -ExecutionPolicy Bypass -File C:\win4k\start_in_session.ps1 -Script {args.script}").strip())
    deadline = time.time() + args.timeout
    while args.done and "yes" not in ssh(args, rf"if exist C:\win4k\{args.done} echo yes", check=False):
        if time.time() > deadline:
            raise RuntimeError(f"{args.script} did not write {args.done} within {args.timeout} s")
        time.sleep(10)


def fetch(args) -> None:
    args.to.mkdir(parents=True, exist_ok=True)
    for name in args.names:
        subprocess.run(["scp", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-i", str(args.ssh_key),
                        f"{args.user}@{args.host}:C:/win4k/{name}", str(args.to)], check=True, capture_output=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", required=True)
    parser.add_argument("--ssh-key", required=True, type=Path)
    parser.add_argument("--user", default="Administrator")
    commands = parser.add_subparsers(dest="command", required=True)
    opener = commands.add_parser("open")
    opener.add_argument("--secret", required=True, type=Path, help="JSON from `scw instance server get-rdp-password -o json`")
    opener.add_argument("--size", default="3840x2160")
    opener.add_argument("--scale", type=int, default=200, choices=(100, 125, 150, 175, 200, 250, 300))
    commands.add_parser("close")
    pusher = commands.add_parser("push")
    pusher.add_argument("files", nargs="+", type=Path)
    runner = commands.add_parser("run")
    runner.add_argument("script")
    runner.add_argument("--done", help="a file the script writes into C:\\win4k when it has finished")
    runner.add_argument("--timeout", type=int, default=600)
    fetcher = commands.add_parser("fetch")
    fetcher.add_argument("--to", required=True, type=Path)
    fetcher.add_argument("names", nargs="+")
    args = parser.parse_args()
    {"open": open_session, "close": close, "push": push, "run": run, "fetch": fetch}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
