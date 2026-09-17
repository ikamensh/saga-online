"""Exercise the restricted upload protocol with real processes, archives and public HTTP."""
import hashlib
import gzip
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import threading

import pytest

from tests.test_site_activation import public_site, site, promotion_receipt
from tools.deploy_online import _stable_tar, package_site

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "deploy/site_receiver.py"


def request(config, operation, payload=b""):
    return subprocess.run([sys.executable, "-I", "-B", str(CLI), "--config", str(config)], input=payload,
                          env={**os.environ, "SSH_ORIGINAL_COMMAND": operation}, capture_output=True, timeout=15)


def settings(root, endpoint):
    path = root / "receiver.json"
    path.write_text(json.dumps({"schema_version": 1, "base": str(root / "host"),
                               "lock": str(root / "deployment.lock"), "public_url": endpoint}))
    return path


def upload(source, receipt, *, generation=1, expected="none"):
    files = {"site/" + path.relative_to(source).as_posix(): path.read_bytes() for path in source.rglob("*") if path.is_file()}
    files["promotion.json"] = receipt.read_bytes()
    archive = _stable_tar(files)
    release = hashlib.sha256(archive).hexdigest()
    header = {"schema_version": 1, "release": release, "bytes": len(archive), "generation": generation, "expected": expected}
    return json.dumps(header).encode() + b"\n" + archive, release


def test_restricted_protocol_reports_state_publishes_verified_bytes_and_retries(tmp_path):
    """Fixed status/publish operations activate an exact archive without executing any uploaded code."""
    source = site(tmp_path, "candidate")
    baseline = {"schema_version": 1, "deployment_release": "d" * 64}
    receipt = promotion_receipt(source, baseline)
    payload, release = upload(source, receipt)
    with public_site(tmp_path / "host", {"baseline": baseline}) as endpoint:
        config = settings(tmp_path, endpoint)
        initial = request(config, "status")
        assert initial.returncode == 0, initial.stderr
        assert json.loads(initial.stdout) == {"schema_version": 1, "accepted": {"release": "none", "generation": 0}, "pending": False}
        assert not (tmp_path / "host").exists()
        first = request(config, "publish", payload)
        assert first.returncode == 0, first.stderr
        result = json.loads(first.stdout)
        assert result["release"] == release and result["generation"] == 1
        repeated = request(config, "publish", payload)
        assert repeated.returncode == 0 and json.loads(repeated.stdout) == result, repeated.stderr
        status = request(config, "status")
        assert json.loads(status.stdout) == {"schema_version": 1, "accepted": result, "pending": False}
        assert (tmp_path / "host/current/releases.json").read_bytes() == (source / "releases.json").read_bytes()


def test_operator_archive_is_data_only_and_accepted_by_the_trusted_receiver(tmp_path):
    """The real packager and receiver share one upload format; deployment scripts never travel with site content."""
    source = site(tmp_path, "candidate")
    baseline = {"schema_version": 1, "deployment_release": "d" * 64}
    package = package_site(source, tmp_path / "packages", promotion_receipt(source, baseline))
    archive = Path(package["archive"]).read_bytes()
    header = {"schema_version": 1, "release": package["release"], "bytes": len(archive), "generation": 1, "expected": "none"}
    with public_site(tmp_path / "host", {"baseline": baseline}) as endpoint:
        result = request(settings(tmp_path, endpoint), "publish", json.dumps(header).encode() + b"\n" + archive)
        assert result.returncode == 0, result.stderr
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        assert all(name.startswith("site/") or name == "promotion.json" for name in bundle.getnames())


def test_status_reports_accepted_state_after_a_killed_upload_and_retry_recovers(tmp_path):
    """An unverified pointer is never reported as committed, even on the first interrupted promotion."""
    source = site(tmp_path, "candidate")
    baseline = {"schema_version": 1, "deployment_release": "d" * 64}
    payload, release = upload(source, promotion_receipt(source, baseline))
    entered, resume = threading.Event(), threading.Event()
    faults = {"baseline": baseline, "block": "/index.html", "entered": entered, "resume": resume, "abort": True}
    with public_site(tmp_path / "host", faults) as endpoint:
        config = settings(tmp_path, endpoint)
        with subprocess.Popen([sys.executable, "-I", "-B", str(CLI), "--config", str(config)],
                              env={**os.environ, "SSH_ORIGINAL_COMMAND": "publish"}, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            try:
                process.stdin.write(payload)
                process.stdin.close()
                process.stdin = None
                assert entered.wait(10)
            finally:
                process.kill()
                process.communicate(timeout=5)
                faults.pop("block")
                resume.set()
        state = request(config, "status")
        assert state.returncode == 0, state.stderr
        assert json.loads(state.stdout) == {"schema_version": 1, "accepted": {"release": "none", "generation": 0}, "pending": True}
        assert (tmp_path / "host/current").resolve().name == release
        result = request(config, "publish", payload)
        assert result.returncode == 0, result.stderr
        assert json.loads(request(config, "status").stdout)["pending"] is False


@pytest.mark.parametrize("fault", ["checksum", "truncated", "trailing", "absolute", "parent", "symlink", "hardlink", "duplicate", "code", "no_receipt",
                                 "compressed_limit", "expanded_limit", "file_count"])
def test_bad_uploads_leave_the_accepted_site_and_outside_files_untouched(tmp_path, fault):
    """Framing and tar validation reject damaged or unsafe archives before the site transaction begins."""
    source = site(tmp_path, "candidate")
    baseline = {"schema_version": 1, "deployment_release": "d" * 64}
    payload, release = upload(source, promotion_receipt(source, baseline))
    with public_site(tmp_path / "host", {"baseline": baseline}) as endpoint:
        config = settings(tmp_path, endpoint)
        assert request(config, "publish", payload).returncode == 0
        before = (tmp_path / "host/state.json").read_bytes()
        line, archive = payload.split(b"\n", 1)
        header = {**json.loads(line), "generation": 2, "expected": release}
        if fault == "compressed_limit":
            header["bytes"] = 64 * 1024 * 1024 + 1
            damaged = archive
        elif fault == "expanded_limit":
            out = io.BytesIO()
            with gzip.GzipFile(fileobj=out, mode="wb") as compressed:
                for _ in range(257):
                    compressed.write(b"\0" * (1024 * 1024))
            damaged = out.getvalue()
            header.update(bytes=len(damaged), release=hashlib.sha256(damaged).hexdigest())
        elif fault in ("checksum", "truncated", "trailing"):
            damaged = archive[:-1] if fault == "truncated" else archive + b"extra"
            if fault == "checksum":
                header["bytes"] = len(damaged)
        else:
            out = io.BytesIO()
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as original, tarfile.open(fileobj=out, mode="w:gz") as changed:
                for member in original:
                    if fault != "no_receipt" or member.name != "promotion.json":
                        changed.addfile(member, original.extractfile(member))
                if fault == "file_count":
                    for number in range(2048):
                        changed.addfile(tarfile.TarInfo(f"site/file{number}"), io.BytesIO())
                elif fault != "no_receipt":
                    name = {"absolute": str(tmp_path / "escaped"), "parent": "../escaped", "duplicate": "site/index.html",
                            "code": "deploy/site_receiver.py"}.get(fault, "site/escape")
                    member = tarfile.TarInfo(name)
                    if fault in ("symlink", "hardlink"):
                        member.type = tarfile.SYMTYPE if fault == "symlink" else tarfile.LNKTYPE
                        member.linkname = str(tmp_path / "escaped")
                        changed.addfile(member)
                    else:
                        member.size = 1
                        changed.addfile(member, io.BytesIO(b"x"))
            damaged = out.getvalue()
            header.update(bytes=len(damaged), release=hashlib.sha256(damaged).hexdigest())
        rejected = request(config, "publish", json.dumps(header).encode() + b"\n" + damaged)
        assert rejected.returncode != 0, fault
        expected_error = {"compressed_limit": b"archive limit", "expanded_limit": b"expanded limit", "file_count": b"too many upload files"}
        if fault in expected_error:
            assert expected_error[fault] in rejected.stderr
        assert (tmp_path / "host/state.json").read_bytes() == before
        assert (tmp_path / "host/current").resolve().name == release
        assert not (tmp_path / "escaped").exists()


@pytest.mark.parametrize("operation", ["", "sh", "status; id", "publish extra", "internal-sftp"])
def test_arbitrary_ssh_commands_are_rejected_before_publication(tmp_path, operation):
    """The original SSH command is data, never a shell command to execute."""
    config = settings(tmp_path, "http://127.0.0.1:1")
    result = request(config, operation)
    assert result.returncode != 0 and b"Only status and publish" in result.stderr
    assert not (tmp_path / "host").exists()
