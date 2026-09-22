"""A packaged rule module can read its declared data without borrowing the source checkout."""

import hashlib
import subprocess
import sys

from tools.server_package import tracked_package


def test_a_pinned_package_carries_declared_rule_data_and_excludes_unrelated_assets(tmp_path):
    source = tmp_path / "source"
    data = source / "warband/assets/constants/units.toml"
    data.parent.mkdir(parents=True)
    data.write_text("hp = 73\n")
    rules = source / "warband/rules.py"
    rules.write_text("from pathlib import Path\nimport tomllib\n"
                     "print(tomllib.loads((Path(__file__).parent / 'assets/constants/units.toml').read_text())['hp'])\n")
    (data.parent / "unused.toml").write_text("not_a_rule = true\n")
    (source / "warband/assets/picture.png").write_bytes(b"image")
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "-qm", "rules and assets"], check=True)
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    declared = {data.relative_to(source).as_posix(): hashlib.sha256(data.read_bytes()).hexdigest()}
    # Reading the commit must not pick up a later edit, even for declared data.
    data.write_text("hp = 999\n")
    files = tracked_package(source, commit, "warband", declared)
    bundle = tmp_path / "bundle"
    for name, content in files.items():
        target = bundle / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    result = subprocess.run([sys.executable, str(bundle / "warband/rules.py")], cwd=tmp_path,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "73"
    assert set(files) == {"warband/rules.py", "warband/assets/constants/units.toml"}
