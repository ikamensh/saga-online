"""The independently verified promotion produces a stable, bounded site upload."""
import json
from pathlib import Path
import subprocess
import sys
import tarfile

from tests.test_warband_promotion import release, prepare
from tests.test_warband_catalog_commit import checkout, commit, git

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools/prepare_warband_site.py"


def build(data, prepared, output):
    return subprocess.run([sys.executable, str(CLI), "--prepared", str(data["root"] / prepared),
                           "--output", str(data["root"] / output)], capture_output=True, text=True)


def test_catalog_commit_and_fresh_preparation_do_not_change_upload_bytes(release):
    """A retry after the desired catalog commit keeps the archive identity despite changed preparation bookkeeping."""
    assert prepare(release).returncode == 0
    first = build(release, "prepared", "first-site")
    assert first.returncode == 0, first.stderr
    repository = checkout(release)
    assert commit(release, repository, git(repository, "rev-parse", "HEAD")).returncode == 0
    (release["root"] / "catalog.json").write_bytes((repository / "releases/catalog.json").read_bytes())
    release["compare"]["status"] = "identical"
    retried = prepare(release, output="retried", previous=repository / "releases/warband-promotion.json")
    assert retried.returncode == 0, retried.stderr
    assert json.loads(retried.stdout)["already_current"] is True
    second = build(release, "retried", "second-site")
    assert second.returncode == 0, second.stderr
    plans = [json.loads((release["root"] / name / "site-plan.json").read_bytes()) for name in ("first-site", "second-site")]
    assert plans[0] == plans[1]
    archives = [release["root"] / name / plan["archive"] for name, plan in zip(("first-site", "second-site"), plans)]
    assert archives[0].read_bytes() == archives[1].read_bytes()
    with tarfile.open(archives[0]) as archive:
        assert b"Built 2026-09-16" in archive.extractfile("site/index.html").read()
        receipt = json.load(archive.extractfile("promotion.json"))
        assert receipt["baseline"] == release["baseline"]
        assert "already_current" not in receipt and "before_catalog_sha256" not in receipt
