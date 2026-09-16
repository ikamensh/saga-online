"""Prepared promotions become auditable commits through real local Git repositories."""
import json
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

from tests.test_warband_promotion import encoded, prepare, release, sha

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools/commit_warband_promotion.py"


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def checkout(data):
    root = data["root"] / "checkout"
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "Promotion integration test")
    git(root, "config", "user.email", "promotion@example.test")
    (root / "releases").mkdir()
    (root / "releases/catalog.json").write_bytes((data["root"] / "catalog.json").read_bytes())
    (root / "README.md").write_text("A file outside the promotion's scope\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "Initial catalog")
    return root


def commit(data, root, expected, *, prepared="prepared", push=False):
    return subprocess.run([sys.executable, str(CLI), "--prepared", str(data["root"] / prepared),
                           "--repository", str(root), "--expected-head", expected, *(["--push"] if push else [])],
                          capture_output=True, text=True)


def test_prepared_catalog_commits_only_its_release_facts_and_receipt(release):
    """The accepted candidate and receipt are one auditable commit with unchanged unrelated files."""
    assert prepare(release).returncode == 0
    root = checkout(release)
    before = git(root, "rev-parse", "HEAD")
    result = commit(release, root, before)
    assert result.returncode == 0, result.stderr
    assert git(root, "rev-parse", "HEAD^") == before
    assert set(git(root, "diff", "--name-only", before, "HEAD").splitlines()) == {
        "releases/catalog.json", "releases/warband-promotion.json"}
    assert (root / "releases/catalog.json").read_bytes() == (release["root"] / "prepared/catalog.json").read_bytes()
    assert (root / "releases/warband-promotion.json").read_bytes() == (release["root"] / "prepared/promotion.json").read_bytes()
    assert not git(root, "status", "--porcelain")
    assert json.loads(result.stdout) == {"commit": git(root, "rev-parse", "HEAD"), "changed": True, "pushed": False}


@pytest.mark.parametrize("changed", ["other_game", "server"])
def test_preparation_cannot_authorize_changes_outside_warband(release, changed):
    """Even internally consistent prepared hashes cannot turn a game promotion into unrelated edits."""
    assert prepare(release).returncode == 0
    root = checkout(release)
    before = git(root, "rev-parse", "HEAD")
    prepared = release["root"] / "prepared"
    catalog = json.loads((prepared / "catalog.json").read_text())
    if changed == "other_game":
        catalog["games"]["tribes"]["released"] = "2026-09-17"
    else:
        catalog["server"]["endpoint"] = "wss://different.example.test/play"
    (prepared / "catalog.json").write_bytes(encoded(catalog))
    receipt = json.loads((prepared / "promotion.json").read_text())
    receipt["catalog_sha256"] = sha(encoded(catalog))
    (prepared / "promotion.json").write_bytes(encoded(receipt))
    result = commit(release, root, before)
    assert result.returncode != 0 and "outside Warband" in result.stderr, result.stderr
    assert git(root, "rev-parse", "HEAD") == before
    assert not git(root, "status", "--porcelain")


def test_already_committed_release_keeps_its_original_receipt_and_git_history(release):
    """An activation retry validates the current desired release without making another catalog commit."""
    assert prepare(release).returncode == 0
    root = checkout(release)
    assert commit(release, root, git(root, "rev-parse", "HEAD")).returncode == 0
    before = git(root, "rev-parse", "HEAD")
    original = (root / "releases/warband-promotion.json").read_bytes()
    (release["root"] / "catalog.json").write_bytes((root / "releases/catalog.json").read_bytes())
    release["compare"]["status"] = "identical"
    result = prepare(release, output="retry", previous=root / "releases/warband-promotion.json")
    assert result.returncode == 0, result.stderr
    result = commit(release, root, before, prepared="retry")
    assert result.returncode == 0, result.stderr
    assert git(root, "rev-parse", "HEAD") == before
    assert (root / "releases/warband-promotion.json").read_bytes() == original
    assert json.loads(result.stdout) == {"commit": before, "changed": False, "pushed": False}
    assert not git(root, "status", "--porcelain")


def origin(data, root):
    remote = data["root"] / "origin.git"
    git(data["root"], "init", "--bare", "--initial-branch=main", str(remote))
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "origin", "HEAD:refs/heads/main")
    return remote


def test_explicit_push_advances_the_existing_main_branch(release):
    """The exact desired commit reaches main via a fast-forward, without publishing a website."""
    assert prepare(release).returncode == 0
    root = checkout(release)
    remote = origin(release, root)
    before = git(root, "rev-parse", "HEAD")
    result = commit(release, root, before, push=True)
    assert result.returncode == 0, result.stderr
    head = git(root, "rev-parse", "HEAD")
    assert git(remote, "rev-parse", "main") == head
    assert git(remote, "rev-parse", "main^") == before
    assert json.loads(result.stdout) == {"commit": head, "changed": True, "pushed": True}


def test_remote_main_advancing_during_push_preserves_the_other_games_new_catalog(release):
    """A competing real Git push after remote-head inspection makes the publication push fail safely."""
    assert prepare(release).returncode == 0
    root = checkout(release)
    remote = origin(release, root)
    before = git(root, "rev-parse", "HEAD")
    competitor = release["root"] / "competitor"
    git(release["root"], "clone", str(remote), str(competitor))
    git(competitor, "config", "user.name", "Other game publisher")
    git(competitor, "config", "user.email", "other@example.test")
    catalog_path = competitor / "releases/catalog.json"
    catalog = json.loads(catalog_path.read_text())
    catalog["games"]["tribes"]["released"] = "2026-09-17"
    catalog_path.write_bytes(encoded(catalog))
    git(competitor, "add", "releases/catalog.json")
    git(competitor, "commit", "-m", "Update Tribes release date")
    competing_head = git(competitor, "rev-parse", "HEAD")
    hook = root / ".git/hooks/pre-push"
    hook.write_text("#!/bin/sh\nexec env -u GIT_DIR -u GIT_WORK_TREE git -C "
                    + shlex.quote(str(competitor)) + " push origin HEAD:refs/heads/main\n")
    hook.chmod(0o755)
    result = commit(release, root, before, push=True)
    assert result.returncode != 0 and "push failed" in result.stderr, result.stderr
    assert git(remote, "rev-parse", "main") == competing_head
    assert json.loads(git(remote, "show", "main:releases/catalog.json")) == catalog
    assert git(root, "rev-parse", "HEAD^") == before


@pytest.mark.parametrize("changed", ["dirty", "local_commit", "remote_commit"])
def test_changed_checkout_or_remote_cannot_accept_old_preparation(release, changed):
    """Preparation is bound to its clean checkout and main head, including changes outside the catalog."""
    assert prepare(release).returncode == 0
    root = checkout(release)
    remote = origin(release, root)
    before = git(root, "rev-parse", "HEAD")
    (root / "README.md").write_text("A concurrent change\n")
    if changed != "dirty":
        git(root, "add", "README.md")
        git(root, "commit", "-m", "Other work")
    if changed == "remote_commit":
        git(root, "push", "origin", "HEAD:refs/heads/main")
        git(root, "checkout", "--detach", before)
    current = git(root, "rev-parse", "HEAD")
    remote_before = git(remote, "rev-parse", "main")
    status = git(root, "status", "--porcelain")
    result = commit(release, root, before, push=True)
    assert result.returncode != 0, changed
    assert git(root, "rev-parse", "HEAD") == current
    assert git(root, "status", "--porcelain") == status
    assert git(remote, "rev-parse", "main") == remote_before


@pytest.mark.parametrize("changed", ["manifest", "source"])
def test_prepared_commit_stays_bound_to_its_downloaded_release_identity(release, changed):
    """Candidate hashes alone cannot disconnect catalog facts from the verified release manifest."""
    assert prepare(release).returncode == 0
    root = checkout(release)
    before = git(root, "rev-parse", "HEAD")
    prepared = release["root"] / "prepared"
    if changed == "manifest":
        path = prepared / "downloads/release.json"
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        path = prepared / "catalog.json"
        catalog = json.loads(path.read_bytes())
        catalog["games"]["warband"]["source_commit"] = "f" * 40
        path.write_bytes(encoded(catalog))
        receipt_path = prepared / "promotion.json"
        receipt = json.loads(receipt_path.read_bytes())
        receipt.update(catalog_sha256=sha(encoded(catalog)), game_sha256=sha(encoded(catalog["games"]["warband"])))
        receipt_path.write_bytes(encoded(receipt))
    result = commit(release, root, before)
    assert result.returncode != 0 and "release identity" in result.stderr, result.stderr
    assert git(root, "rev-parse", "HEAD") == before
    assert not git(root, "status", "--porcelain")
