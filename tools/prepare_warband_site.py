"""Build a reproducible site upload from an independently verified Warband promotion.

The output is immutable. The deployment receipt excludes preparation-only
bookkeeping; the recorded release date and actual rendering inputs determine
the site identity. No Git, SSH or public state is changed.
"""
from __future__ import annotations

import argparse
from datetime import date
import importlib.metadata
import json
from pathlib import Path
import platform
import tempfile

from build_site import build, FONTS, ROOT
from deploy_online import package_site
from release_catalog import validate
from warband_promotion import directory_contents, encoded, require, sha

FIELDS = ("schema_version", "release_id", "build_run_id", "source_commit", "manifest_sha256",
          "catalog_sha256", "game_sha256", "baseline")


def rendering_inputs():
    paths = [ROOT / name for name in ("tools/build_site.py", "tools/prepare_warband_site.py", "tools/deploy_online.py",
                                     "website/content.py", "publishing/pyproject.toml", "publishing/uv.lock")]
    paths.extend(path for folder in ("templates", "static", "media") for path in (ROOT / "website" / folder).rglob("*") if path.is_file())
    require(all(not path.is_symlink() for path in paths), "Rendering inputs must not be symlinks")
    files = {path.relative_to(ROOT).as_posix(): sha(path.read_bytes()) for path in sorted(paths)}
    files.update({"engine-fonts/" + path.name: sha(path.read_bytes()) for path in sorted(FONTS.iterdir())})
    return {"python": platform.python_version(), "saga2d": importlib.metadata.version("saga2d"),
            "pillow": importlib.metadata.version("pillow"), "files": files}


def prepare_site(prepared, output):
    catalog_bytes = (prepared / "catalog.json").read_bytes()
    original = (prepared / "promotion.json").read_bytes()
    receipt = json.loads(original)
    catalog = validate(json.loads(catalog_bytes))
    manifest_bytes = (prepared / "downloads/release.json").read_bytes()
    identity = json.loads(manifest_bytes)["identity"]
    game = catalog["games"]["warband"]
    require(receipt["schema_version"] == 1 and receipt["catalog_sha256"] == sha(catalog_bytes)
            and receipt["game_sha256"] == sha(encoded(game)), "Prepared catalog differs from its receipt")
    require(receipt["manifest_sha256"] == sha(manifest_bytes) and identity["game"] == "warband"
            and game["source_commit"] == receipt["source_commit"] == identity["source_commit"]
            and receipt["build_run_id"] == identity["run_id"] and game["version"] == identity["version"],
            "Prepared site differs from the verified release identity")
    require(isinstance(receipt["baseline"], dict), "Site publication requires a compatibility baseline")
    inputs = rendering_inputs()
    built = date.fromisoformat(game["released"])
    deployment = {key: receipt[key] for key in FIELDS}
    deployment["site_build"] = {"date": built.isoformat(), "inputs_sha256": sha(encoded(inputs))}
    require(not output.is_symlink(), "Prepared site must not be a symlink")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="warband-site-", dir=output.parent) as temporary:
        folder = Path(temporary)
        site = folder / "site"
        build(site, prepared / "catalog.json", build_date=built)
        promotion = folder / "promotion.json"
        promotion.write_bytes(encoded(deployment))
        staged = folder / "prepared"
        package = package_site(site, staged, promotion)
        archive = Path(package["archive"])
        plan = {"schema_version": 1, "archive": archive.name, "release": package["release"], "bytes": archive.stat().st_size,
                "catalog_sha256": sha(catalog_bytes), "promotion_sha256": sha(promotion.read_bytes()),
                "build_date": built.isoformat(), "rendering_inputs": inputs}
        (staged / "site-plan.json").write_bytes(encoded(plan))
        require(catalog_bytes == (prepared / "catalog.json").read_bytes()
                and original == (prepared / "promotion.json").read_bytes() and inputs == rendering_inputs(),
                "Publication inputs changed while rendering")
        if output.exists():
            require(directory_contents(staged) == directory_contents(output), "A prepared site cannot be overwritten")
        else:
            staged.rename(output)
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_site(args.prepared, args.output), sort_keys=True, indent=2))
