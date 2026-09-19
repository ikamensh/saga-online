"""Install the trusted, unprivileged SSH publisher on the named managed Linux host.

Run with the operator's root authority, never with the CI credential. This
installs account/code/configuration only; it does not reload SSH or publish a
site. Validate the printed result before reloading ssh.service.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

USER = "saga2d-site-ci"
HOME = Path("/var/lib/saga2d-site-ci")
CONFIG = Path("/etc/saga2d-online")
TOOLS = Path("/usr/local/lib/saga2d-site-ci")
SITE = Path("/srv/saga2d-site")
LOCK = Path("/var/lock/saga2d-online.publish.lock")
DROP_IN = Path("/etc/ssh/sshd_config.d/00-saga-site-ci.conf")
KEYS = CONFIG / "site-ci-authorized-keys"
LAUNCHER = f'''#!/bin/sh
set -eu
release=$(readlink -f {TOOLS}/current)
exec /usr/bin/python3 -I -B "$release/site_receiver.py" --config "$release/config.json"
'''


def ssh_config(user, keys, command):
    return f'''# Managed by Saga Online: this CI key runs only its forced command.
Match User {user}
    AuthorizedKeysFile {keys}
    ForceCommand {command}
    AuthenticationMethods publickey
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    DisableForwarding yes
    PermitTTY no
    PermitUserRC no
    PermitTunnel no
    MaxSessions 1
Match all
'''


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write(path, data, mode=0o644):
    """Replace root-owned trusted files atomically, including their permissions."""
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
        os.fchmod(output.fileno(), mode)
    os.replace(output.name, path)


def ed25519_key(path):
    """The base64 body of one plain Ed25519 public key, without authorization options."""
    match = re.fullmatch(r"ssh-ed25519 ([A-Za-z0-9+/=]+)(?: [^\r\n]+)?", path.read_text().strip())
    require(match is not None, "Expected one plain Ed25519 public key without authorization options")
    wire = base64.b64decode(match[1], validate=True)
    require(len(wire) == 51 and wire.startswith(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"), "Invalid Ed25519 public key")
    return match[1]


def ci_account(user, home, record, instance):
    """Create or recognise a dedicated system account with no supplementary groups and a root-owned home."""
    try:
        account = pwd.getpwnam(user)
    except KeyError:
        require(not record.exists() and not home.exists(), "Unexpected previous CI account state")
        subprocess.run(["useradd", "--system", "--user-group", "--no-create-home", "--home-dir", str(home),
                        "--shell", "/bin/bash", user], check=True)
        account = pwd.getpwnam(user)
        write(record, json.dumps({"instance": instance, "uid": account.pw_uid, "gid": account.pw_gid}).encode())
    require(json.loads(record.read_bytes()) == {"instance": instance, "uid": account.pw_uid, "gid": account.pw_gid}
            and account.pw_dir == str(home) and account.pw_shell == "/bin/bash"
            and os.getgrouplist(user, account.pw_gid) == [account.pw_gid], "Refusing an unmanaged or privileged CI account")
    home.mkdir(exist_ok=True)
    require(not home.is_symlink(), "CI home must be an operator-owned directory")
    os.chown(home, 0, 0)
    home.chmod(0o755)
    return account


def tool_revision(tools, files):
    """Install trusted files as an immutable, content-addressed revision under tools/releases."""
    revision = hashlib.sha256(b"".join(name.encode() + b"\0" + files[name] for name in sorted(files))).hexdigest()
    releases = tools / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    tools.chmod(0o755)
    releases.chmod(0o755)
    destination = releases / revision
    if destination.exists():
        require(not destination.is_symlink() and {p.name: p.read_bytes() for p in destination.iterdir()} == files,
                "Installed tool revision has changed")
    else:
        with tempfile.TemporaryDirectory(dir=releases) as temporary:
            prepared = Path(temporary) / "release"
            prepared.mkdir(mode=0o755)
            prepared.chmod(0o755)
            for name, data in files.items():
                write(prepared / name, data)
            prepared.rename(destination)
    return revision


def point_current(tools, revision):
    temporary = tools / "current.next"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(Path("releases") / revision)
    temporary.replace(tools / "current")


def restrict_ssh(user, keys, command, drop_in, encoded):
    """Install the forced-command SSH drop-in, check sshd enforces it, then authorise the key."""
    old_config = drop_in.read_bytes() if drop_in.exists() else None
    write(drop_in, ssh_config(user, keys, command).encode())
    try:
        subprocess.run(["/usr/sbin/sshd", "-t"], check=True, capture_output=True)
        effective = subprocess.run(["/usr/sbin/sshd", "-T", "-C", f"user={user},host=localhost,addr=127.0.0.1"],
                                   check=True, capture_output=True, text=True).stdout
        options = dict(line.split(" ", 1) for line in effective.splitlines())
        expected = {"forcecommand": str(command), "authorizedkeysfile": str(keys),
                    "authenticationmethods": "publickey", "passwordauthentication": "no", "kbdinteractiveauthentication": "no",
                    "disableforwarding": "yes", "permittty": "no", "permituserrc": "no", "permittunnel": "no", "maxsessions": "1"}
        require(all(options.get(name) == value for name, value in expected.items()), "Active sshd configuration does not enforce CI restrictions")
    except BaseException:
        if old_config is None:
            drop_in.unlink()
        else:
            write(drop_in, old_config)
        raise
    write(keys, f"restrict ssh-ed25519 {encoded}\n".encode())


def install(instance, public_key, public_url):
    require(sys.platform == "linux" and os.geteuid() == 0, "Site CI setup requires root on the managed Linux host")
    require(re.fullmatch(r"saga2d-[a-z0-9-]+", instance), "Invalid managed instance name")
    require((CONFIG / "managed-instance").read_text().strip() == instance, "Managed instance does not match")
    encoded = ed25519_key(public_key)
    url = urlsplit(public_url)
    require(url.hostname and not url.username and not url.password and not url.query and not url.fragment
            and url.path in ("", "/") and (url.scheme == "https" or
            (url.scheme == "http" and url.hostname in ("127.0.0.1", "::1", "localhost"))),
            "Use the public HTTPS origin (loopback HTTP is only for acceptance tests)")
    account = ci_account(USER, HOME, CONFIG / "site-ci-account.json", instance)
    receiver_config = {"schema_version": 1, "base": str(SITE), "lock": str(LOCK), "public_url": public_url.rstrip("/")}
    files = {name: (Path(__file__).parent / name).read_bytes()
             for name in ("site_receiver.py", "activate_site.py", "install_site.sh")}
    files["config.json"] = json.dumps(receiver_config, sort_keys=True, indent=2).encode() + b"\n"
    revision = tool_revision(TOOLS, files)
    # Preserve the existing lock inode: replacing it would split active writers.
    descriptor = os.open(LOCK, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o660)
    with os.fdopen(descriptor, "w") as lock:
        info = os.fstat(lock.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1, "Unexpected deployment lock owner/type")
        fcntl.flock(lock, fcntl.LOCK_EX)
        os.fchown(lock.fileno(), 0, account.pw_gid)
        os.fchmod(lock.fileno(), 0o660)
        require(not SITE.is_symlink(), "Website root must be a directory")
        SITE.mkdir(exist_ok=True)
        SITE.chmod(0o755)
        for path in [SITE, *SITE.rglob("*")]:
            os.chown(path, account.pw_uid, account.pw_gid, follow_symlinks=False)
        write(TOOLS / "command", LAUNCHER.encode(), 0o755)
        point_current(TOOLS, revision)
        restrict_ssh(USER, KEYS, TOOLS / "command", DROP_IN, encoded)
    return {"schema_version": 1, "account": USER, "revision": revision, "public_url": receiver_config["public_url"],
            "ssh_reload_required": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--public-url", required=True)
    args = parser.parse_args()
    print(json.dumps(install(args.instance, args.public_key, args.public_url), sort_keys=True))
