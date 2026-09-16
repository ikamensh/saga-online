"""Stage a checksum-verified server archive without copying upload-side files."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tarfile
import tempfile

from runtime import inventory, require


def stage(archive: Path, destination: Path, release_id: str) -> None:
    require(re.fullmatch(r"[0-9a-f]{64}", release_id), "Expected an archive SHA-256")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="server-stage-", dir=destination.parent) as temporary:
        # Hash and extract the same private copy. Upload-side changes after
        # verification cannot replace the bytes assigned this release ID.
        verified = Path(temporary) / "archive.tar.gz"
        shutil.copyfile(archive, verified)
        with verified.open("rb") as stream:
            require(hashlib.file_digest(stream, "sha256").hexdigest() == release_id, "Uploaded archive differs from the release identifier")
        extracted = Path(temporary) / "release"
        with tarfile.open(verified) as bundle:
            members = bundle.getmembers()
            require(len({item.name for item in members}) == len(members), "Duplicate archive entry")
            require(all(item.isfile() and not PurePosixPath(item.name).is_absolute()
                        and ".." not in PurePosixPath(item.name).parts for item in members), "Unsafe archive entry")
            bundle.extractall(extracted, filter="data")
        manifest = (extracted / "deploy/server-inputs.json").read_bytes()
        expected = json.loads(manifest)["files"]
        require(inventory(extracted) == expected, "Archive source differs from its recorded inventory")
        if destination.exists() or destination.is_symlink():
            require(destination.is_dir() and not destination.is_symlink(), "Existing server release must be a directory")
            require((destination / "deploy/server-inputs.json").read_bytes() == manifest
                    and inventory(destination) == expected, "A versioned server release cannot be overwritten")
        else:
            extracted.rename(destination)


if __name__ == "__main__":
    stage(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
