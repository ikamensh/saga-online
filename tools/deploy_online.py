#!/usr/bin/env python3
"""Prepare and deploy the dedicated online server; cloud credentials stay local.

``plan``, ``package`` and ``package-site`` are offline. The other subcommands
change the explicitly named Saga2D infrastructure. See deploy/README.md for the
first deployment; ``site`` publishes a built website without touching the server.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
ORGANIZATION = "17efcf03-4911-41f9-a059-4bd6fe2f3ffe"
MARKER = "Managed by Saga2D online deployment"
RESOURCE_TAG = "saga2d-online-managed"
DEPLOYMENT_PERMISSIONS = ["BlockStorageFullAccess", "InstancesFullAccess"]


@dataclass(frozen=True)
class ScalewayKey:
    access_key: str
    secret_key: str = field(repr=False)
    project_id: str | None = None


def secret_section(text: str, section: str) -> str:
    sections = re.split(r"(?m)^## +", text)[1:]
    matches = [s for s in sections if re.match(re.escape(section) + r"(?:\s|$)", s)]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one secrets heading for {section!r}")
    return matches[0]


def secret_value(text: str, label: str) -> str:
    matches = re.findall(r"(?m)^" + re.escape(label) + r"\s*[:=]\s*(\S+)\s*$", text)
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {label!r} field in credential section")
    return matches[0].strip("`\"'")


def load_scaleway_key(path: Path, section: str) -> ScalewayKey:
    text = secret_section(path.read_text(), section)
    project = secret_value(text, "Project ID") if re.search(r"(?m)^Project ID:", text) else None
    return ScalewayKey(secret_value(text, "Key ID"), secret_value(text, "Secret Key"), project)


class Scaleway:
    def __init__(self, key: ScalewayKey):
        self.key = key

    def request(self, method, path, body=None):
        request = urllib.request.Request(
            "https://api.scaleway.com" + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"X-Auth-Token": self.key.secret_key, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read()
        return json.loads(raw) if raw else None

    def list(self, path, collection, **filters):
        values = []
        # Instance v1 uses per_page; Account/IAM use page_size.
        size_arg = "per_page" if path.startswith("/instance/") else "page_size"
        for page in range(1, 101):
            query = urllib.parse.urlencode({**filters, size_arg: 100, "page": page})
            items = self.request("GET", path + "?" + query)[collection]
            values.extend(items)
            if len(items) < 100:
                return values
        raise RuntimeError(f"Unexpectedly large resource listing at {path}")


def named(items, name):
    matches = [item for item in items if item["name"] == name]
    if len(matches) > 1:
        raise RuntimeError(f"Multiple resources named {name!r}; resolve the ambiguity first")
    return matches[0] if matches else None


def bootstrap_project(args):
    """Reconcile only our isolated project/application's compute-and-disk policy."""
    import fcntl

    api = Scaleway(load_scaleway_key(args.secrets_file, "Personal admin key"))
    with args.secrets_file.with_suffix(".saga2d.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        project = named(api.list("/account/v3/projects", "projects", organization_id=ORGANIZATION),
                        args.project_name)
        if project is None:
            project = api.request("POST", "/account/v3/projects", {
                "name": args.project_name, "organization_id": ORGANIZATION, "description": MARKER})
        if project["description"] != MARKER:
            raise RuntimeError("Existing project lacks the Saga2D ownership marker")
        project_id = project["id"]
        app = named(api.list("/iam/v1alpha1/applications", "applications", organization_id=ORGANIZATION),
                    args.key_section)
        if app is None:
            app = api.request("POST", "/iam/v1alpha1/applications", {
                "name": args.key_section, "organization_id": ORGANIZATION, "description": MARKER})
        if app["description"] != MARKER:
            raise RuntimeError("Existing IAM application lacks the Saga2D ownership marker")
        policy_name = args.key_section + "-instances"
        policy = named(api.list("/iam/v1alpha1/policies", "policies", organization_id=ORGANIZATION),
                       policy_name)
        if policy is None:
            policy = api.request("POST", "/iam/v1alpha1/policies", {
                "name": policy_name, "organization_id": ORGANIZATION,
                "description": MARKER, "application_id": app["id"],
                "rules": [{"project_ids": [project_id], "permission_set_names": DEPLOYMENT_PERMISSIONS}],
            })
        if policy["application_id"] != app["id"] or policy["description"] != MARKER:
            raise RuntimeError("Existing policy belongs to a different application")
        rules = api.list("/iam/v1alpha1/rules", "rules", policy_id=policy["id"])
        if (len(rules) != 1 or rules[0].get("project_ids") != [project_id] or rules[0].get("condition")
                or not set(rules[0]["permission_set_names"]).issubset(DEPLOYMENT_PERMISSIONS)):
            raise RuntimeError("Existing deployment policy has an unexpected scope; it was not changed")
        if set(rules[0]["permission_set_names"]) != set(DEPLOYMENT_PERMISSIONS):
            api.request("PUT", "/iam/v1alpha1/rules", {"policy_id": policy["id"], "rules": [
                {"project_ids": [project_id], "permission_set_names": DEPLOYMENT_PERMISSIONS}]})
        text = args.secrets_file.read_text()
        has_section = any(re.match(re.escape(args.key_section) + r"(?:\s|$)", s)
                          for s in re.split(r"(?m)^## +", text)[1:])
        if has_section:
            key = load_scaleway_key(args.secrets_file, args.key_section)
            if key.project_id != project_id:
                raise RuntimeError("Saved deployment credential targets another project")
        else:
            key = api.request("POST", "/iam/v1alpha1/api-keys", {
                "application_id": app["id"], "default_project_id": project_id, "description": MARKER})
            appended = (text.rstrip() + f"\n\n## {args.key_section}\n"
                        "Laptop deployment only. Never copy to a game server.\n"
                        f"Project ID: {project_id}\nApplication ID: {app['id']}\n"
                        f"Key ID: {key['access_key']}\nSecret Key: {key['secret_key']}\n")
            with tempfile.NamedTemporaryFile(mode="w", dir=args.secrets_file.parent, delete=False) as saved:
                os.chmod(saved.name, 0o600)
                saved.write(appended)
                saved.flush()
                os.fsync(saved.fileno())
            os.replace(saved.name, args.secrets_file)
    return {"project_id": project_id, "project_name": args.project_name,
            "key_section": args.key_section, "application_id": app["id"]}


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "package", "bootstrap-project", "provision", "deploy", "status",
                                            "package-site", "site"])
    parser.add_argument("--name", required=True, help="Dedicated resource name, starting saga2d-")
    parser.add_argument("--project-name", default="saga2d")
    parser.add_argument("--project-id")
    parser.add_argument("--domain", default="games.tachyon-ai.eu")
    parser.add_argument("--zone", default="fr-par-1")
    parser.add_argument("--secrets-file", type=Path, default=Path.home() / "secrets/scaleway.md")
    parser.add_argument("--key-section", default="saga2d-deploy")
    parser.add_argument("--dns-secrets-file", type=Path, default=Path.home() / "secrets/infrastructure.md")
    parser.add_argument("--ssh-key", type=Path, default=Path.home() / ".ssh/id_ed25519.pub")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/online")
    parser.add_argument("--site-dir", type=Path, default=ROOT / "dist/site", help="Built website to publish")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"saga2d-[a-z0-9-]{1,40}", args.name):
        parser.error("--name must start with saga2d- and contain only lowercase letters, digits or hyphens")
    if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)+", args.domain):
        parser.error("--domain must be a DNS hostname")
    if not re.fullmatch(r"saga2d(?:-[a-z0-9-]+)?", args.project_name):
        parser.error("--project-name must be saga2d or start with saga2d-")
    if not re.fullmatch(r"saga2d-[a-z0-9-]+", args.key_section):
        parser.error("--key-section must start with saga2d-")
    return args


def deployment_plan(args):
    return {
        "endpoint": f"wss://{args.domain}/play",
        "health": f"https://{args.domain}/healthz",
        "project": args.project_id or args.project_name,
        "instance": {"name": args.name, "type": "DEV1-S", "zone": args.zone,
                     "root_volume": "sbs:20GB:5000", "ipv4": "reserved"},
        "inbound_tcp_ports": [22, 80, 443],
        "server": "python -m online_server --host 127.0.0.1 --port 8765",
        "monthly_eur_before_tax_at_730_hours": 11.37,
        "secrets_on_server": False,
    }


def package_release(output: Path):
    """Allowlist source files and hashed, frozen dependencies into a stable tar."""
    files = {}
    for package in ("saga2d", "tribes", "warband", "eador", "online_server"):
        for path in sorted((ROOT / package).rglob("*.py")):
            if path.is_symlink():
                raise ValueError(f"Refusing symlink in release: {path}")
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for name in ("install.sh", "check_release.py", "smoke.py", "saga2d-online.service", "Caddyfile"):
        files[f"deploy/{name}"] = (ROOT / "deploy" / name).read_bytes()
    files["deploy/requirements.txt"] = subprocess.run(
        ["uv", "export", "--frozen", "--no-dev", "--no-emit-project", "--no-header"],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout
    payload = _stable_tar(files)
    digest = hashlib.sha256(payload).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{digest}.tar.gz"
    path.write_bytes(payload)
    return {"release": digest, "archive": str(path.resolve()), "files": len(files)}


def _stable_tar(files: dict) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, content in sorted(files.items()):
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            entry.mode = 0o644
            archive.addfile(entry, io.BytesIO(content))
    return gzip.compress(buffer.getvalue(), mtime=0)


def package_site(site_dir: Path, output: Path):
    """Bundle a built website with its installer; the archive digest names the release."""
    site_dir = site_dir.resolve()
    if not (site_dir / "index.html").is_file() or not (site_dir / "releases.json").is_file():
        raise FileNotFoundError(f"Build the website first; {site_dir} lacks index.html or releases.json")
    files = {"deploy/install_site.sh": (ROOT / "deploy/install_site.sh").read_bytes()}
    for path in sorted(site_dir.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Refusing symlink in site release: {path}")
        if path.is_file():
            files["site/" + path.relative_to(site_dir).as_posix()] = path.read_bytes()
    payload = _stable_tar(files)
    digest = hashlib.sha256(payload).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"site-{digest}.tar.gz"
    path.write_bytes(payload)
    return {"release": digest, "archive": str(path.resolve()), "files": len(files) - 1}


def deployment_api(args):
    key = load_scaleway_key(args.secrets_file, args.key_section)
    project_id = args.project_id or key.project_id
    if not project_id or project_id != key.project_id:
        raise ValueError("Deployment project must match Project ID in its dedicated credential section")
    if project_id == "d56850e6-57a4-4e0f-b503-9b6e785a05d2":
        raise ValueError("Game servers require their own project; the hive project is not a deployment target")
    return Scaleway(key), project_id


def instance_path(args):
    return f"/instance/v1/zones/{args.zone}"


def find_server(api, args, project_id):
    server = named(api.list(instance_path(args) + "/servers", "servers", project=project_id), args.name)
    if server is not None:
        if RESOURCE_TAG not in server["tags"] or server["project"] != project_id:
            raise RuntimeError("Named server lacks the Saga2D ownership tag or targets another project")
        if server["commercial_type"] != "DEV1-S":
            raise RuntimeError("Named server has an unexpected instance type")
    return server


def target_details(args, project_id, server):
    ipv4 = next(ip["address"] for ip in server["public_ips"] if ip["family"] == "inet")
    return {"name": args.name, "project_id": project_id, "server_id": server["id"],
            "zone": args.zone, "ip": ipv4, "domain": args.domain, "state": server["state"]}


def firewall_ports(rules):
    """Validate our ingress while preserving Scaleway's immutable SMTP blocks."""
    ports = set()
    for rule in rules:
        if not rule["editable"] and rule["direction"] == "outbound" and rule["action"] == "drop":
            continue
        if (rule["action"] != "accept" or rule["direction"] != "inbound" or rule["protocol"] != "TCP"
                or rule["ip_range"] != "0.0.0.0/0" or rule["dest_port_from"] not in {22, 80, 443}
                or rule["dest_port_to"] not in (None, rule["dest_port_from"])):
            raise RuntimeError("Unexpected existing firewall rule; no rules were overwritten")
        ports.add(rule["dest_port_from"])
    return ports


def provision(args):
    api, project_id = deployment_api(args)
    server = find_server(api, args, project_id)
    if server is None:
        path = instance_path(args)
        group = named(api.list(path + "/security_groups", "security_groups", project=project_id),
                      args.name + "-firewall")
        if group is None:
            group = api.request("POST", path + "/security_groups", {
                "name": args.name + "-firewall", "description": MARKER, "project": project_id,
                "stateful": True, "inbound_default_policy": "drop", "outbound_default_policy": "accept",
                "tags": [RESOURCE_TAG],
            })["security_group"]
        if (RESOURCE_TAG not in group["tags"] or group["inbound_default_policy"] != "drop"
                or group["outbound_default_policy"] != "accept" or not group["stateful"]):
            raise RuntimeError("Existing firewall differs from the dedicated Saga2D configuration")
        rules_path = path + f"/security_groups/{group['id']}/rules"
        rules = api.list(rules_path, "rules")
        expected_ports = {22, 80, 443}
        existing_ports = firewall_ports(rules)
        for port in sorted(expected_ports - existing_ports):
            api.request("POST", rules_path, {"action": "accept", "direction": "inbound", "protocol": "TCP",
                                            "ip_range": "0.0.0.0/0", "dest_port_from": port})
        public_key = args.ssh_key.read_text().strip()
        if not re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/=]+(?: [^\n]+)?", public_key):
            raise ValueError("--ssh-key must contain a single Ed25519 public key")
        cloud_init = (ROOT / "deploy/cloud-init.yaml").read_text()
        cloud_init = cloud_init.replace("__SSH_PUBLIC_KEY__", json.dumps(public_key))
        cloud_init = cloud_init.replace("__INSTANCE_NAME__", json.dumps(args.name))
        args.output.mkdir(parents=True, exist_ok=True)
        cloud_path = args.output / "cloud-init.yaml"
        cloud_path.write_text(cloud_init)
        environment = {**os.environ, "SCW_SECRET_KEY": api.key.secret_key,
                       "SCW_ACCESS_KEY": api.key.access_key, "SCW_DEFAULT_PROJECT_ID": project_id}
        subprocess.run(
            ["scw", "instance", "server", "create", f"name={args.name}", "type=DEV1-S", f"zone={args.zone}",
             f"project-id={project_id}", "image=ubuntu_noble", "root-volume=sbs:20GB:5000", "ip=new",
             f"security-group-id={group['id']}", f"tags.0={RESOURCE_TAG}", f"cloud-init=@{cloud_path}", "--wait"],
            env=environment, check=True, stdout=subprocess.DEVNULL,
        )
        server = find_server(api, args, project_id)
    if server["state"] != "running":
        raise RuntimeError(f"Named server is {server['state']}; it was not restarted automatically")
    target = target_details(args, project_id, server)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "target.json").write_text(json.dumps(target, indent=2) + "\n")
    return target


def ssh_options(args):
    private_key = args.ssh_key.with_suffix("")
    if not private_key.is_file():
        raise FileNotFoundError(f"Private SSH key does not exist: {private_key}")
    return ["-i", str(private_key), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
            "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=5"]


def ssh(args, target, command, *, capture=False):
    return subprocess.run(["ssh", *ssh_options(args), f"deploy@{target['ip']}", shlex.join(command)],
                          check=True, text=True, capture_output=capture)


def publish_dns(args, ipv4):
    apex = "tachyon-ai.eu"
    if not args.domain.endswith("." + apex):
        raise ValueError("Automated DNS deployment supports subdomains of tachyon-ai.eu only")
    label = args.domain[:-(len(apex) + 1)]
    text = secret_section(args.dns_secrets_file.read_text(), "GoDaddy DNS")
    authorization = "sso-key " + secret_value(text, "GODADDY_KEY") + ":" + secret_value(text, "GODADDY_SECRET")
    base = f"https://api.godaddy.com/v1/domains/{apex}/records"
    request = urllib.request.Request(base, headers={"Authorization": authorization})
    with urllib.request.urlopen(request, timeout=30) as response:
        records = [r for r in json.load(response) if r["name"] == label]
    desired = [{"data": ipv4, "ttl": 600}]
    if records and (len(records) != 1 or records[0]["type"] != "A" or records[0]["data"] != ipv4):
        raise RuntimeError(f"Existing DNS record for {args.domain} differs; it was not overwritten")
    if not records:
        request = urllib.request.Request(base + "/A/" + urllib.parse.quote(label, safe=""),
            method="PUT", data=json.dumps(desired).encode(),
            headers={"Authorization": authorization, "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()


def running_target(args):
    api, project_id = deployment_api(args)
    server = find_server(api, args, project_id)
    if server is None or server["state"] != "running":
        raise RuntimeError("Provision the dedicated server before deploying")
    return target_details(args, project_id, server)


def upload(args, target, package):
    """Verify the instance marker, then stage the archive and return its remote directory."""
    deadline = time.monotonic() + 300
    while True:
        result = subprocess.run(["ssh", *ssh_options(args), f"deploy@{target['ip']}", "true"],
                                capture_output=True, text=True)
        if result.returncode == 0:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(f"SSH did not become ready: {result.stderr.strip()}")
        time.sleep(5)
    ssh(args, target, ["sudo", "cloud-init", "status", "--wait"])
    actual_name = ssh(args, target, ["cat", "/etc/saga2d-online/managed-instance"], capture=True).stdout.strip()
    if actual_name != args.name:
        raise RuntimeError("Remote instance marker does not match the explicit deployment name")
    staging = ssh(args, target, ["mktemp", "-d", "/tmp/saga2d-deploy.XXXXXXXX"], capture=True).stdout.strip()
    if not re.fullmatch(r"/tmp/saga2d-deploy\.[A-Za-z0-9]+", staging):
        raise RuntimeError("Remote mktemp returned an unexpected staging directory")
    subprocess.run(["scp", *ssh_options(args), package["archive"],
                    f"deploy@{target['ip']}:{staging}/release.tar.gz"], check=True)
    actual_digest = ssh(args, target, ["sha256sum", staging + "/release.tar.gz"], capture=True).stdout.split()[0]
    if actual_digest != package["release"]:
        raise RuntimeError("Uploaded release checksum does not match the local artifact")
    ssh(args, target, ["tar", "-xzf", staging + "/release.tar.gz", "-C", staging])
    return staging


def deploy(args):
    target = running_target(args)
    package = package_release(args.output)
    staging = upload(args, target, package)
    publish_dns(args, target["ip"])
    ssh(args, target, ["sudo", "bash", staging + "/deploy/install.sh", staging,
                       package["release"], args.name, args.domain])
    ssh(args, target, ["rm", "-rf", "--", staging])
    deadline = time.monotonic() + 300
    while True:
        try:
            health = check_health(f"https://{args.domain}/healthz")
            break
        except (urllib.error.URLError, TimeoutError):
            if time.monotonic() >= deadline:
                raise RuntimeError("Public HTTPS health check failed; inspect Caddy logs and DNS")
            time.sleep(5)
    return {**target, **package, "endpoint": f"wss://{args.domain}/play", "health": health}


def check_health(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        if response.status != 200 or response.read() != b"ok\n":
            raise RuntimeError(f"Unexpected health response from {url}")
    return "ok"


def fetch(url):
    with urllib.request.urlopen(url, timeout=15) as response:
        return response.read()


def publish_site(args):
    """Install a built website release beside the running server and verify it publicly."""
    target = running_target(args)
    package = package_site(args.site_dir, args.output)
    staging = upload(args, target, package)
    ssh(args, target, ["sudo", "bash", staging + "/deploy/install_site.sh", staging, package["release"], args.name])
    ssh(args, target, ["rm", "-rf", "--", staging])
    served = {}
    for name in ("index.html", "releases.json"):
        expected = (args.site_dir / name).read_bytes()
        public = f"https://{args.domain}/" + ("" if name == "index.html" else name)
        if fetch(public) != expected:
            raise RuntimeError(f"{public} does not serve the published bytes; inspect Caddy's site root")
        served[name] = public
    return {**target, **package, "served": served, "health": check_health(f"https://{args.domain}/healthz")}


def status(args):
    api, project_id = deployment_api(args)
    server = find_server(api, args, project_id)
    if server is None:
        return {"name": args.name, "provisioned": False}
    target = target_details(args, project_id, server)
    if server["state"] == "running":
        target["service"] = ssh(args, target, ["systemctl", "is-active", "saga2d-online"], capture=True).stdout.strip()
        target["health"] = check_health(f"https://{args.domain}/healthz")
    return target


def main(argv=None):
    args = arguments(argv)
    if args.command == "plan":
        result = deployment_plan(args)
    elif args.command == "package":
        result = package_release(args.output)
    elif args.command == "bootstrap-project":
        result = bootstrap_project(args)
    elif args.command == "provision":
        result = provision(args)
    elif args.command == "deploy":
        result = deploy(args)
    elif args.command == "package-site":
        result = package_site(args.site_dir, args.output)
    elif args.command == "site":
        result = publish_site(args)
    else:
        result = status(args)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
