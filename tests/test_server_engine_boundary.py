"""The server owns one exact engine version.

The server stages its engine upgrade through its own direct pin plus a
server-only ``[tool.uv] override-dependencies`` entry, which supersedes the
demos' older engine requirements within the server environment only. The demo
sources stay at their pinned commits; only the server lock moves, and only
after the staged engine release is published.
"""

import importlib.metadata
import shutil
import subprocess
import tomllib
import zipfile

import pytest

from tools.server_package import locked_runtime, server_engine_pin

ENGINE = "saga2d"


def write_pyproject(root, *, direct, overrides, sources=None):
    lines = ["[project]", 'name = "saga-online"', 'version = "0.1.0"',
             f"dependencies = [{', '.join(repr(item) for item in direct)}]",
             "", "[tool.uv]", "package = false"]
    if overrides is not None:
        lines.append(f"override-dependencies = [{', '.join(repr(item) for item in overrides)}]")
    lines.append("[tool.uv.sources]")
    for name, target in (sources or {}).items():
        lines.append(f'{name} = {{ path = "{target}", editable = true }}')
    (root / "pyproject.toml").write_text("\n".join(lines) + "\n")


def test_matching_direct_pin_and_override_select_the_engine(tmp_path):
    write_pyproject(tmp_path, direct=["saga2d==0.3.17"], overrides=["saga2d==0.3.17"])

    assert server_engine_pin(tmp_path) == "0.3.17"


def test_direct_pin_drift_from_override_is_refused(tmp_path):
    write_pyproject(tmp_path, direct=["saga2d==0.3.17"], overrides=["saga2d==0.3.16"])

    with pytest.raises(ValueError):
        server_engine_pin(tmp_path)


@pytest.mark.parametrize("direct,overrides", [
    ([], ["saga2d==0.3.17"]),
    (["saga2d==0.3.17"], []),
    (["saga2d>=0.3.17"], ["saga2d==0.3.17"]),
    (["saga2d==0.3.17"], ["saga2d>=0.3.17"]),
    (["saga2d==0.3.17"], ["saga2d==0.3.17", "saga2d==0.3.17"]),
    (["saga2d==0.3.16", "saga2d==0.3.17"], ["saga2d==0.3.17"]),
    (["saga2d===0.3.17"], ["saga2d==0.3.17"]),
    (["saga2d==0.3.17; python_version > '3.12'"], ["saga2d==0.3.17"]),
])
def test_incomplete_or_inexact_engine_selection_is_refused(tmp_path, direct, overrides):
    write_pyproject(tmp_path, direct=direct, overrides=overrides)

    with pytest.raises(ValueError):
        server_engine_pin(tmp_path)


def test_a_saga2d_source_override_is_refused(tmp_path):
    write_pyproject(tmp_path, direct=["saga2d==0.3.17"], overrides=["saga2d==0.3.17"],
                    sources={"saga2d": "../saga2d"})

    with pytest.raises(ValueError):
        server_engine_pin(tmp_path)


def write_lock(root, *, version, registry=True):
    source = '{ registry = "https://pypi.org/simple" }' if registry else '{ editable = "../saga2d" }'
    (root / "uv.lock").write_text(
        "version = 1\n"
        'requires-python = ">=3.12"\n'
        "\n"
        "[[package]]\n"
        'name = "saga-online"\n'
        'version = "0.1.0"\n'
        'source = { editable = "." }\n'
        'dependencies = [{ name = "saga2d" }]\n'
        "\n"
        "[[package]]\n"
        'name = "saga2d"\n'
        f'version = "{version}"\n'
        f"source = {source}\n")


def staged_root(tmp_path, pin):
    write_pyproject(tmp_path, direct=[f"saga2d=={pin}"], overrides=[f"saga2d=={pin}"])
    return tmp_path


def test_matching_staged_pin_and_pypi_lock_is_accepted(tmp_path):
    installed = importlib.metadata.version(ENGINE)
    write_lock(staged_root(tmp_path, installed), version=installed)

    assert locked_runtime(tmp_path)["saga2d"] == installed


def test_a_stale_engine_lock_is_refused(tmp_path):
    installed = importlib.metadata.version(ENGINE)
    staged = "0.3.17" if installed != "0.3.17" else "0.3.16"
    write_lock(staged_root(tmp_path, staged), version=installed)

    with pytest.raises(ValueError):
        locked_runtime(tmp_path)


def test_a_non_pypi_engine_substitution_is_refused(tmp_path):
    installed = importlib.metadata.version(ENGINE)
    write_lock(staged_root(tmp_path, installed), version=installed, registry=False)

    with pytest.raises(ValueError):
        locked_runtime(tmp_path)


def make_wheel(directory, version):
    """A metadata-only wheel: enough for the real resolver, nothing to install."""
    dist_info = f"saga2d-{version}.dist-info"
    files = {
        "saga2d/__init__.py": f'__version__ = "{version}"\n',
        f"{dist_info}/METADATA": f"Metadata-Version: 2.1\nName: saga2d\nVersion: {version}\n",
        f"{dist_info}/WHEEL": "Wheel-Version: 1.0\nGenerator: server-boundary-fixture\n"
                              "Root-Is-Purelib: true\nTag: py3-none-any\n",
    }
    files[f"{dist_info}/RECORD"] = "".join(f"{path},,\n" for path in (*files, f"{dist_info}/RECORD"))
    with zipfile.ZipFile(directory / f"saga2d-{version}-py3-none-any.whl", "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv demonstrates the resolver boundary")
def test_override_forces_the_new_engine_despite_old_demo_metadata(tmp_path):
    old, new = "0.3.14", "0.3.17"
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    make_wheel(wheelhouse, old)
    make_wheel(wheelhouse, new)
    demo = tmp_path / "demo-old"
    demo.mkdir()
    (demo / "pyproject.toml").write_text(
        "[project]\nname = \"demo-old\"\nversion = \"0.1.0\"\n"
        f"dependencies = [\"saga2d=={old}\"]\n")
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = \"server-override-probe\"\nversion = \"0.1.0\"\n"
        'requires-python = ">=3.12"\n'
        f"dependencies = [\"saga2d=={new}\", \"demo-old\"]\n"
        "\n[tool.uv.sources]\n"
        'demo-old = { path = "demo-old", editable = true }\n')

    def lock():
        return subprocess.run(["uv", "lock", "--offline", "--no-index", "--find-links", str(wheelhouse)],
                              cwd=tmp_path, capture_output=True, text=True, timeout=300)

    # The demo's older engine requirement conflicts with the server's newer one.
    conflict = lock()
    assert conflict.returncode != 0
    assert f"saga2d=={old}" in conflict.stderr and f"saga2d=={new}" in conflict.stderr
    with open(tmp_path / "pyproject.toml", "a") as handle:
        handle.write("\n[tool.uv]\n"
                     "override-dependencies = [\n"
                     f"  \"saga2d=={new}\",\n"
                     "]\n")
    resolved = lock()
    assert resolved.returncode == 0, resolved.stderr
    lock_data = tomllib.loads((tmp_path / "uv.lock").read_text())
    selected = [item for item in lock_data["package"] if item["name"] == ENGINE]
    assert len(selected) == 1 and selected[0]["version"] == new
