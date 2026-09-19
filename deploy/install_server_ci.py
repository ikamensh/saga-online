"""Install the restricted server-CI account and its trusted host tools on the named managed host.

Run with the operator's root authority, never with the CI credential. The
account's SSH key runs one forced command, which accepts ``status``, ``backup``,
``install`` or ``rollback`` and passes it to sudo; sudo allows exactly
``/usr/local/lib/saga2d-server-ci/run`` with one of those four words. That entry
point executes only the files installed here: ``server_ci.py``, ``install.sh``,
the preparation scripts, the service units and the proxy configuration. It does
not reload SSH, activate a release or change the running service.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_site_ci import ci_account, ed25519_key, point_current, require, restrict_ssh, tool_revision, write

USER = "saga2d-server-ci"
HOME = Path("/var/lib/saga2d-server-ci")
CONFIG = Path("/etc/saga2d-online")
TOOLS = Path("/usr/local/lib/saga2d-server-ci")
DROP_IN = Path("/etc/ssh/sshd_config.d/00-saga-server-ci.conf")
SUDOERS = Path("/etc/sudoers.d/saga2d-server-ci")
KEYS = CONFIG / "server-ci-authorized-keys"
OPERATIONS = ("status", "backup", "install", "rollback")
# Everything root runs for a rollout; prepare_release.sh refuses a release whose copies differ.
HOST_FILES = ("server_ci.py", "install.sh", "prepare_release.sh", "stage_release.py", "runtime.py", "uv-bootstrap.txt",
              "saga2d-online.service", "saga2d-backup.service", "saga2d-backup.timer", "Caddyfile")
COMMAND = f'''#!/bin/sh
# Forced SSH command of {USER}; runs unprivileged.
case "${{SSH_ORIGINAL_COMMAND:-}}" in
    {"|".join(OPERATIONS)}) exec sudo -n {TOOLS}/run "$SSH_ORIGINAL_COMMAND" ;;
    *) echo 'Only {", ".join(OPERATIONS[:-1])} and {OPERATIONS[-1]} are permitted' >&2; exit 64 ;;
esac
'''
RUN = f'''#!/bin/sh
# Root entry point; sudoers allows it only with one of: {" ".join(OPERATIONS)}.
set -eu
release=$(readlink -f {TOOLS}/current)
exec /usr/bin/python3 -I -B "$release/server_ci.py" "$1"
'''
SUDO_RULE = (f"# Managed by Saga Online: the server-CI account may run exactly these commands.\n"
             f"Defaults:{USER} env_reset, !setenv, !use_pty\n"
             f"{USER} ALL=(root) NOPASSWD: " + ", ".join(f"{TOOLS}/run {op}" for op in OPERATIONS) + "\n")


def install(instance, domain, public_key):
    require(sys.platform == "linux" and os.geteuid() == 0, "Server CI setup requires root on the managed Linux host")
    require(re.fullmatch(r"saga2d-[a-z0-9-]+", instance), "Invalid managed instance name")
    require(re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)+", domain), "Invalid domain")
    require((CONFIG / "managed-instance").read_text().strip() == instance, "Managed instance does not match")
    encoded = ed25519_key(public_key)
    ci_account(USER, HOME, CONFIG / "server-ci-account.json", instance)
    files = {name: (Path(__file__).parent / name).read_bytes() for name in HOST_FILES}
    files["config.json"] = json.dumps({"schema_version": 1, "instance": instance, "domain": domain},
                                      sort_keys=True, indent=2).encode() + b"\n"
    revision = tool_revision(TOOLS, files)
    write(TOOLS / "run", RUN.encode(), 0o755)
    write(TOOLS / "command", COMMAND.encode(), 0o755)
    point_current(TOOLS, revision)
    # A broken sudoers file disables sudo for everyone, the operator included: validate a copy first.
    candidate = SUDOERS.with_name(".saga2d-server-ci.candidate")
    write(candidate, SUDO_RULE.encode(), 0o440)
    try:
        subprocess.run(["visudo", "-cf", str(candidate)], check=True, capture_output=True)
        os.replace(candidate, SUDOERS)
    finally:
        candidate.unlink(missing_ok=True)
    listed = subprocess.run(["sudo", "-l", "-U", USER], check=True, capture_output=True, text=True).stdout
    allowed = sorted(line.strip().removeprefix("(root) NOPASSWD: ") for line in listed.splitlines() if "NOPASSWD:" in line)
    commands = sorted(part.strip() for line in allowed for part in line.split(","))
    require(commands == sorted(f"{TOOLS}/run {op}" for op in OPERATIONS), f"Unexpected effective sudo rights: {commands}")
    restrict_ssh(USER, KEYS, TOOLS / "command", DROP_IN, encoded)
    return {"schema_version": 1, "account": USER, "revision": revision, "sudo": commands, "ssh_reload_required": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(install(args.instance, args.domain, args.public_key), sort_keys=True))
