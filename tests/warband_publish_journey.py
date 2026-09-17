"""Acceptance of catalog-to-site orchestration through real Git, HTTP and SSH."""
import json
from pathlib import Path
import shlex
import subprocess
import sys

from tests.test_warband_promotion import release_data, prepare
from tests.test_warband_catalog_commit import checkout, origin, git
from tests.test_warband_site import build
from tests.test_site_activation import site, promotion_receipt
from tests.test_site_receiver import upload

ROOT = Path(__file__).resolve().parents[1]


def verify(folder, base, client, faults):
    root = folder / "workflow"
    root.mkdir()
    data = release_data(root)
    faults["baseline"] = data["baseline"]
    result = prepare(data)
    assert result.returncode == 0, result.stderr
    result = build(data, "prepared", "first-site")
    assert result.returncode == 0, result.stderr
    repository = checkout(data)
    remote = origin(data, repository)
    before = git(repository, "rev-parse", "HEAD")
    accepted = (base / "state.json").read_bytes()
    command = [sys.executable, str(ROOT / "tools/apply_warband_promotion.py"), "--repository", str(repository),
               "--expected-head", before, "--prepared", str(root / "prepared"), "--site", str(root / "first-site"), *client[2:]]
    plan = json.loads((root / "first-site/site-plan.json").read_bytes())
    archive = root / "first-site" / plan["archive"]
    original = archive.read_bytes()
    archive.write_bytes(original + b"changed")
    rejected = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert rejected.returncode != 0 and "Prepared archive bytes changed" in rejected.stderr
    assert git(remote, "rev-parse", "main") == before and (base / "state.json").read_bytes() == accepted
    archive.write_bytes(original)
    # A real Git hook removes only this fixture's SSH identity after status
    # inspection. Git can push to the local bare remote, but upload cannot run.
    key = Path(client[client.index("--identity") + 1])
    saved = key.with_suffix(".saved")
    hook = repository / ".git/hooks/pre-push"
    hook.write_text("#!/bin/sh\nset -eu\nmv " + shlex.quote(str(key)) + " " + shlex.quote(str(saved)) + "\n")
    hook.chmod(0o700)
    failed = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert failed.returncode != 0 and "Missing identity" in failed.stderr, failed.stderr
    committed = git(remote, "rev-parse", "main")
    assert committed != before and committed == git(repository, "rev-parse", "HEAD")
    assert (base / "state.json").read_bytes() == accepted
    saved.rename(key)
    hook.unlink()
    (root / "catalog.json").write_bytes((repository / "releases/catalog.json").read_bytes())
    data["compare"]["status"] = "identical"
    result = prepare(data, output="retried", previous=repository / "releases/warband-promotion.json")
    assert result.returncode == 0, result.stderr
    assert build(data, "retried", "retry-site").returncode == 0
    first = json.loads((root / "first-site/site-plan.json").read_bytes())
    second = json.loads((root / "retry-site/site-plan.json").read_bytes())
    assert first == second
    command = [sys.executable, str(ROOT / "tools/apply_warband_promotion.py"), "--repository", str(repository),
               "--expected-head", committed, "--prepared", str(root / "retried"), "--site", str(root / "retry-site"), *client[2:]]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["activation"]["release"] == first["release"]
    assert (base / "current/releases.json").read_bytes() == (repository / "releases/catalog.json").read_bytes()
    successful_state = (base / "state.json").read_bytes()
    previous = (base / "previous").resolve()
    repeated = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert repeated.returncode == 0, repeated.stderr
    assert json.loads(repeated.stdout) == json.loads(completed.stdout)
    assert (base / "state.json").read_bytes() == successful_state and (base / "previous").resolve() == previous
    assert git(remote, "rev-parse", "main") == committed
    faults["health"] = True
    failed = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert failed.returncode != 0 and "Room server health check failed" in failed.stderr
    assert (base / "state.json").read_bytes() == successful_state
    del faults["health"]
    stale = [before if part == committed else part for part in command]
    rejected = subprocess.run(stale, capture_output=True, text=True, timeout=30)
    assert rejected.returncode != 0 and "Catalog checkout changed" in rejected.stderr
    assert git(remote, "rev-parse", "main") == committed and (base / "state.json").read_bytes() == successful_state
    # A competing real host publication between status and upload cannot be
    # overwritten by the stale preconditions, even when the Git push is a no-op.
    current = json.loads(successful_state)
    competing = site(root, "competing")
    upload_bytes, competing_release = upload(competing, promotion_receipt(competing, data["baseline"]),
                                              generation=current["generation"] + 1, expected=current["release"])
    competing_archive = root / "competing.tar.gz"
    competing_archive.write_bytes(upload_bytes.split(b"\n", 1)[1])
    competing_command = [*client, "publish", "--archive", str(competing_archive), "--generation", str(current["generation"] + 1),
                         "--expected", current["release"]]
    hook.write_text("#!/bin/sh\nset -eu\n" + shlex.join(competing_command) + " > " + shlex.quote(str(root / "competing-result.json")) + "\n")
    hook.chmod(0o700)
    rejected = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert rejected.returncode != 0 and "Current site changed" in rejected.stderr, rejected.stderr
    assert json.loads((base / "state.json").read_bytes())["release"] == competing_release
    assert (base / "current/index.html").read_bytes() == (competing / "index.html").read_bytes()
    hook.unlink()
    return {"git_push_then_upload_failure_recovered": True, "repeated_site_keeps_generation_and_previous": True,
            "already_committed_catalog_still_verifies_site": True, "changed_archive_and_stale_catalog_refused": True,
            "competing_host_publication_preserved": True}
