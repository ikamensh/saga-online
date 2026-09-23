"""Prepare an independently verified Warband catalog promotion; never publish or deploy."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from release_catalog import validate
from warband_evidence import TARGETS, verify_native_release

REPOSITORY = "ikamensh/warband"
JOBS = {"inputs", "native (windows-2025, windows-x64)", "native (macos-15, darwin-arm64)", "validate"}


def require(condition, message, error=ValueError):
    if not condition:
        raise error(message)


class ServerBaseline(ValueError):
    """The candidate needs a server the live one is not (yet): the automatic server rollout's cue."""


SERVER_BASELINE_EXIT = 3


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def transport_url(url):
    parsed = urlsplit(url)
    require(parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")),
            "Use HTTPS or an explicit loopback integration service")
    require(parsed.username is None and parsed.password is None, "Credentials do not belong in URLs")


class Redirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        transport_url(new_url)
        redirected = super().redirect_request(request, fp, code, message, headers, new_url)
        if redirected is not None:
            redirected.remove_header("Authorization")
        return redirected


class GitHub:
    """Read-only GitHub and public-download adapter; tokens stay on the API origin."""
    def __init__(self, api_url):
        transport_url(api_url)
        parsed = urlsplit(api_url)
        require(api_url == "https://api.github.com" or (parsed.scheme == "http"
                and parsed.hostname in ("localhost", "127.0.0.1", "::1") and not parsed.path),
                "Use GitHub's API or a loopback integration service")
        self.base = api_url + "/repos/" + REPOSITORY
        self.public = "https://github.com" if api_url == "https://api.github.com" else api_url
        self.opener = build_opener(Redirect())

    def get(self, path):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"}
        if os.environ.get("GH_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
        with self.opener.open(Request(self.base + path, headers=headers), timeout=30) as response:
            return json.load(response)

    def download(self, tag, item, destination):
        name = item["file"]
        require(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name)), "Invalid release filename")
        require(type(item["bytes"]) is int and item["bytes"] > 0, "Invalid release size")
        require(bool(re.fullmatch(r"[0-9a-f]{64}", item["sha256"])), "Invalid release digest")
        url = self.public + f"/{REPOSITORY}/releases/download/{quote(tag, safe='')}/{name}"
        digest, size = hashlib.sha256(), 0
        with self.opener.open(url, timeout=120) as response, destination.open("wb") as out:
            while block := response.read(1024 * 1024):
                size += len(block)
                require(size <= item["bytes"], f"Public download exceeds accepted size: {name}")
                digest.update(block); out.write(block)
        require(size == item["bytes"] and digest.hexdigest() == item["sha256"], f"Public download differs: {name}")

    def pages(self, path, collection=None):
        for page in range(1, 101):
            result = self.get(f"{path}?per_page=100&page={page}")
            items = result[collection] if collection else result
            yield from items
            if len(items) < 100:
                return
        raise ValueError("GitHub pagination exceeded the supported bound")


def verify_source(api, release, identity, run_id):
    require(identity["schema_version"] == 2 and identity["game"] == "warband", "Wrong release identity")
    commit = identity["source_commit"]
    require(bool(re.fullmatch(r"[0-9a-f]{40}", commit)), "Expected a full source commit")
    require(identity["run_id"] == run_id and identity["tag"] == release["tag_name"] == "v" + identity["version"],
            "Release/run identity differs")
    base = re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", identity["base_version"])
    number, anchor = identity["run_number"], identity["version_run_base"]
    require(base is not None and type(number) is int and number > 0
            and type(anchor) is int and 0 <= anchor <= number, "Invalid version counter inputs")
    require(identity["version"] == f"{base[1]}.{base[2]}.{int(base[3]) + number - anchor}",
            "Version differs from native counter")
    require(release["target_commitish"] == commit, "Release targets different source")
    tag = api.get("/git/ref/tags/" + quote(identity["tag"], safe=""))["object"]
    require(tag["type"] == "commit" and tag["sha"] == commit,
            "Release tag points at different source")
    run = api.get(f"/actions/runs/{run_id}")
    require(run["id"] == run_id and run["head_sha"] == commit
            and type(run["run_number"]) is int and run["run_number"] == number, "Native build source differs")
    require(run["repository"]["full_name"] == run["head_repository"]["full_name"] == REPOSITORY
            and run["head_branch"] == "main" and run["event"] in ("push", "workflow_dispatch"),
            "Only this repository's main native builds may be promoted")
    require(run["status"] == "completed" and run["conclusion"] == "success", "Native build has not passed")
    require(run["path"] == ".github/workflows/native-packages.yml"
            and run["workflow_id"] == api.get("/actions/workflows/native-packages.yml")["id"], "Wrong native workflow")
    attempt = run["run_attempt"]
    require(type(attempt) is int and attempt > 0, "Invalid native run attempt")
    jobs = list(api.pages(f"/actions/runs/{run_id}/attempts/{attempt}/jobs", "jobs"))
    require(len(jobs) == len(JOBS) and {item["name"] for item in jobs} == JOBS
            and all(item["status"] == "completed" and item["conclusion"] == "success" for item in jobs),
            "Both native builds and independent validation must pass")


def verify_baseline(baseline, catalog, identity):
    require(set(baseline) == {"schema_version", "deployment_release", "endpoint", "protocol", "warband"}
            and baseline["schema_version"] == 1, "Unsupported reviewed server baseline")
    require(bool(re.fullmatch(r"[0-9a-f]{64}", baseline["deployment_release"])), "Invalid baseline deployment")
    require({"endpoint": baseline["endpoint"], "protocol": baseline["protocol"]} == catalog["server"],
            "Reviewed baseline addresses another server")
    require(set(baseline["warband"]) == {"source_commit", "compatibility"}
            and bool(re.fullmatch(r"[0-9a-f]{40}", baseline["warband"]["source_commit"])), "Invalid baseline source")
    contract = identity["compatibility"]
    require(set(contract) == {"schema_version", "registry", "python", "packages", "files", "sha256"}
            and contract["schema_version"] == 1 and contract["registry"] == "warband.online.authority:ONLINE",
            "Unsupported compatibility contract")
    contents = {key: value for key, value in contract.items() if key != "sha256"}
    require(sha(json.dumps(contents, sort_keys=True, separators=(",", ":")).encode()) == contract["sha256"],
            "Invalid compatibility contract digest")
    require(contract["python"] == identity["python"] and contract["packages"]["saga2d"] == identity["saga2d_version"],
            "Compatibility runtime differs from release identity")
    require(contract["files"] and all(re.fullmatch(
                r"warband/(?:(?:[A-Za-z_]\w*/)*[A-Za-z_]\w*\.py|assets/constants/[A-Za-z_]\w*\.toml)", name)
            and re.fullmatch(r"[0-9a-f]{64}", digest) for name, digest in contract["files"].items()),
            "Invalid authoritative source inventory")
    require(contract == baseline["warband"]["compatibility"], "Candidate requires a different server compatibility baseline", ServerBaseline)


def verify_live_baseline(api, url, baseline, site):
    transport_url(url)
    parsed = urlsplit(url)
    require(url == site.rstrip("/") + "/server-compatibility.json"
            or (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")),
            "Read the attestation from the catalog's own server")
    request = Request(url + "?deployment=" + baseline["deployment_release"], headers={"Cache-Control": "no-cache"})
    with api.opener.open(request, timeout=30) as response:
        require(response.geturl().split("?")[0] == url, "Server attestation must not redirect elsewhere")
        require(json.load(response) == baseline, "Live server differs from the reviewed compatibility baseline", ServerBaseline)


def verify_order(api, catalog, identity, previous, release_id, manifest_sha256):
    current = catalog["games"]["warband"]
    before, after = current["source_commit"], identity["source_commit"]
    if previous is not None:
        require(previous["schema_version"] == 1 and previous["game_sha256"] == sha(encoded(current))
                and previous["source_commit"] == before, "Previous promotion receipt differs from current Warband catalog")
    comparison = api.get(f"/compare/{before}...{after}")
    require(comparison["status"] == ("identical" if before == after else "ahead"),
            "Candidate source is older than or diverges from the current catalog")
    # The previous catalog can still name an immutable legacy preview. A plain
    # version sorts after its prerelease; compare numeric components, not text.
    def version_key(value):
        match = re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-preview\.([1-9]\d*))?", value)
        require(match is not None, "Invalid ordered release version")
        return (*map(int, match.group(1, 2, 3)), match[4] is None, int(match[4] or 0))

    before_version, after_version = version_key(current["version"]), version_key(identity["version"])
    require(after_version >= before_version, "An older version cannot replace the current release")
    if after_version > before_version:
        if previous is not None:
            require(identity["run_id"] > previous["build_run_id"], "An older build cannot replace the current release")
        return False
    require(before == after, "An accepted version cannot be rebound to different source")
    require(previous is not None and previous["release_id"] == release_id and previous["build_run_id"] == identity["run_id"]
            and previous["manifest_sha256"] == manifest_sha256, "An accepted version must retain its original release and manifest receipt")
    return True


def directory_contents(directory):
    require(directory.is_dir() and not directory.is_symlink(), "Prepared candidate must be a directory")
    records = {}
    for path in directory.rglob("*"):
        require(not path.is_symlink(), "Prepared candidates cannot contain symlinks")
        if path.is_file():
            with path.open("rb") as stream:
                records[path.relative_to(directory).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
        else:
            require(path.is_dir(), "Unsupported prepared candidate entry")
            records[path.relative_to(directory).as_posix()] = None
    return records


def prepare(args):
    require(args.build_run_id > 0 and args.release_id > 0, "Release and native run IDs must be positive")
    paths = [args.catalog, args.baseline]
    if args.previous_promotion:
        paths.append(args.previous_promotion)
    inputs = {path: path.read_bytes() for path in paths}
    catalog = validate(json.loads(inputs[args.catalog]))
    baseline = json.loads(inputs[args.baseline])
    previous = json.loads(inputs[args.previous_promotion]) if args.previous_promotion else None
    api = GitHub(args.api_url)
    release = api.get(f"/releases/{args.release_id}")
    require(release["id"] == args.release_id and release["draft"] is False and release["immutable"] is True
            and release["prerelease"] is True, "Expected the requested immutable published early access release")
    tag = release["tag_name"]
    require(bool(re.fullmatch(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", tag)), "Invalid release tag")
    records = list(api.pages(f"/releases/{args.release_id}/assets"))
    remote = {item["name"]: item for item in records}
    require(len(remote) == len(records) == 7 and "release.json" in remote, "Expected exactly seven public release assets")
    item = remote["release.json"]
    require(not args.output.is_symlink(), "Prepared candidate must not be a symlink")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="warband-promotion-", dir=output.parent) as temporary:
        staged = Path(temporary) / "prepared"
        downloads = staged / "downloads"
        downloads.mkdir(parents=True)
        api.download(tag, {"file": "release.json", "bytes": item["size"], "sha256": args.manifest_sha256}, downloads / "release.json")
        manifest = json.loads((downloads / "release.json").read_text())
        identity = manifest["identity"]
        verify_source(api, release, identity, args.build_run_id)
        verify_baseline(baseline, catalog, identity)
        already_current = verify_order(api, catalog, identity, previous, args.release_id, args.manifest_sha256)
        expected = {item["file"]: item for item in manifest["assets"]}
        require(len(expected) == len(manifest["assets"]) == 6 and "release.json" not in expected, "Invalid release asset inventory")
        expected["release.json"] = {"file": "release.json", "bytes": remote["release.json"]["size"], "sha256": args.manifest_sha256}
        require(set(expected) == set(remote), "Public release asset inventory differs from the accepted manifest")
        require(all(remote[name]["state"] == "uploaded" and remote[name]["size"] == item["bytes"]
                    and remote[name]["digest"] == "sha256:" + item["sha256"] for name, item in expected.items()),
                "Public asset metadata differs from accepted bytes")
        for item in manifest["assets"]:
            api.download(tag, item, downloads / item["file"])
        verify_native_release(downloads, manifest)
        verify_live_baseline(api, args.server_attestation, baseline, catalog["site"])
        candidate = deepcopy(catalog)
        game = candidate["games"]["warband"]
        game.update(version=identity["version"], source_commit=identity["source_commit"], channel="preview",
                    released=release["published_at"][:10], notes=f"https://github.com/{REPOSITORY}/releases/tag/{tag}",
                    game_ids=["warband-v2"], packages=[])
        for target in TARGETS:
            for artifact in manifest["targets"][target]["artifacts"]:
                name = artifact["file"]
                windows = target == "windows-x64"
                game["packages"].append({**artifact, "os": "windows" if windows else "macos", "arch": "x64" if windows else "arm64",
                    "kind": "portable-zip" if name.endswith("-portable.zip") else "installer" if windows else "app-zip",
                    "url": f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}",
                    "min_os": "Windows 10" if windows else "macOS 14 on Apple Silicon", "signed": False})
        validate(candidate)
        receipt = {"schema_version": 1, "release_id": args.release_id, "build_run_id": args.build_run_id,
                   "already_current": already_current,
                   "source_commit": identity["source_commit"], "manifest_sha256": args.manifest_sha256,
                   "baseline": baseline, "before_catalog_sha256": sha(inputs[args.catalog]),
                   "catalog_sha256": sha(encoded(candidate)), "game_sha256": sha(encoded(game))}
        for path, original in inputs.items():
            require(path.read_bytes() == original, f"Input changed during preparation: {path}")
        (staged / "catalog.json").write_bytes(encoded(candidate))
        (staged / "promotion.json").write_bytes(encoded(receipt))
        if output.exists():
            require(directory_contents(staged) == directory_contents(output), "A prepared candidate cannot be overwritten")
        else:
            staged.rename(output)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-run-id", type=int, required=True)
    parser.add_argument("--release-id", type=int, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--previous-promotion", type=Path, help="Receipt recorded with the current desired Warband catalog")
    parser.add_argument("--server-attestation", default="https://games.tachyon-ai.eu/server-compatibility.json")
    parser.add_argument("--api-url", default="https://api.github.com")
    parser.add_argument("--output", type=Path, required=True)
    try:
        receipt = prepare(parser.parse_args())
    except ServerBaseline as refusal:
        print(f"Refused until the server serves this candidate: {refusal}", file=sys.stderr)
        sys.exit(SERVER_BASELINE_EXIT)
    print(json.dumps(receipt, sort_keys=True, indent=2))
