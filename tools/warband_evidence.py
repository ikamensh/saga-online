"""Independently inspect native Warband evidence in downloaded release assets.

This consumes the public format without importing the game's publisher or
executing downloaded code. Native execution itself must come from the verified
GitHub producer. Evidence ZIPs are bounded to 64 MiB uncompressed and never extracted.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import zipfile

TARGETS = ("windows-x64", "darwin-arm64")
SOCKET_CHECKS = ("create_join", "authoritative_movement", "foreign_order_rejected", "private_seat_rejoin",
                 "global_production", "automatic_plan_builder", "cancel_plans", "assembly_point")
NATIVE_CHECKS = ("native_multiplayer_input", "native_clipboard_join", "live_match_menu", "native_settlement_planning")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_native_release(directory: Path, manifest: dict) -> None:
    """Require both native distributions, full regression evidence and exact tested executables."""
    require(manifest["schema_version"] == 1 and set(manifest["targets"]) == set(TARGETS), "Incomplete native release")
    identity = manifest["identity"]
    assets = {item["file"]: item for item in manifest["assets"]}
    require(len(assets) == len(manifest["assets"]) == 6, "Expected four downloads and two evidence archives")

    def same(receipt):
        require(receipt["source_commit"] == identity["source_commit"] and receipt["version"] == identity["version"],
                "Native receipt belongs to different source/version")

    def executable(archive, member):
        with zipfile.ZipFile(directory / archive) as bundle:
            require(bundle.namelist().count(member) == 1, "Missing or duplicate archived executable")
            with bundle.open(member) as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest()

    expected_assets = set()
    for target in TARGETS:
        windows = target == "windows-x64"
        candidate = manifest["targets"][target]
        require(candidate["schema_version"] == 1 and candidate["identity"] == identity and candidate["target"] == target,
                "Native candidate differs from release identity/target")
        prefix = f"Warband-{identity['version']}-{target}"
        portable = prefix + "-portable.zip"
        installed = prefix + ("-setup.exe" if windows else "-app.zip")
        archive = f"evidence-{target}.zip"
        expected_assets.update((portable, installed, archive))
        artifacts = candidate["artifacts"]
        require(len(artifacts) == 2 and {item["file"] for item in artifacts} == {portable, installed}
                and all(assets[item["file"]] == item for item in artifacts), "Native artifact identity differs from release assets")
        with zipfile.ZipFile(directory / archive) as bundle:
            names = bundle.namelist()
            require(len(names) == len(set(names)) and set(names) == set(candidate["evidence"]), "Evidence ZIP inventory differs")
            require(sum(item.file_size for item in bundle.infolist()) <= 64 * 1024 * 1024, "Evidence ZIP exceeds supported size")
            evidence = {}
            for name in names:
                require(bool(re.fullmatch(r"(?:verification/)?[A-Za-z0-9][A-Za-z0-9._-]*", name)), "Unsafe evidence path")
                data = bundle.read(name)
                require(hashlib.sha256(data).hexdigest() == candidate["evidence"][name], "Evidence bytes differ from accepted digest")
                evidence[name] = data

        inputs = json.loads(evidence["build-inputs.json"])
        require(inputs["identity"] == identity and inputs["target"] == target, "Native build inputs differ")
        packages = {name.lower(): version for name, version in inputs["packages"].items()}
        require(all(packages[name] == version for name, version in identity["compatibility"]["packages"].items()),
                "Native runtime differs from compatibility contract")
        if windows:
            require(inputs["inno_setup"] == identity["inno_setup"] and re.fullmatch(r"[0-9a-f]{64}", inputs["inno_setup_sha256"]),
                    "Installer compiler differs from release pin")
        regression = json.loads(evidence["regression.json"])
        require(regression["identity"] == identity and regression["exit_code"] == 0
                and regression["command"] == ["-m", "pytest", "-q"]
                and regression["log_sha256"] == hashlib.sha256(evidence["regression.log"]).hexdigest()
                and re.search(rb"\b[1-9][0-9]* passed\b", evidence["regression.log"]), "Missing passing full regression evidence")
        build = json.loads(evidence["build-manifest.json"])
        same(build)
        require(build["game"] == "warband" and build["product"] == "Warband" and build["working_tree_dirty"] is False
                and build["python"] == identity["python"] and build["artifacts"] == artifacts, "Invalid native build manifest")
        require(build["packages"] == {name: version for name, version in inputs["packages"].items() if name not in ("saga2d", "sagaforge")},
                "Build dependencies differ from installed native inputs")
        require(build["architecture"].lower() in ({"amd64", "x86_64"} if windows else {"arm64"})
                and build["platform"].startswith("Windows" if windows else ("macOS", "Darwin")), "Wrong native platform/architecture")
        require(evidence["SHA256SUMS"].decode("ascii").splitlines() == [f"{x['sha256']}  {x['file']}" for x in artifacts],
                "Native checksums differ from accepted artifacts")
        report = json.loads(evidence["verification.json"])
        same(report)
        require(report["passed"] is True, "Native verification failed")
        portable_digest = executable(portable, "Warband/Warband.exe" if windows else "Warband/Warband")
        installed_digest = portable_digest if windows else executable(installed, "Warband.app/Contents/MacOS/Warband")

        def receipt(name, digest, *, native=False):
            value = report[name]
            same(value)
            require(value["passed"] is True and value["executable_sha256"] == digest, "Native receipt does not accept the archived executable")
            if native:
                require(value["backend"] == "pyglet" and all(value[key] is True for key in NATIVE_CHECKS), "Incomplete native input/rendering checks")
                require(value["images"] and all(evidence["verification/" + name].startswith(b"\x89PNG\r\n\x1a\n") for name in value["images"]),
                        "Missing native captured images")
            else:
                require(value["frozen"] is True and value["bundled_fonts"] is True
                        and all(value["online"][key] is True for key in SOCKET_CHECKS), "Incomplete packaged socket checks")

        receipt("portable", portable_digest)
        receipt("installed", installed_digest)
        receipt("native", installed_digest if windows else portable_digest, native=True)
        if windows:
            require(report["install_shortcut_uninstall"] is True, "Windows installer/shortcut/uninstall checks failed")
        else:
            receipt("app_native", installed_digest, native=True)
    require(set(assets) == expected_assets, "Unexpected release assets")
