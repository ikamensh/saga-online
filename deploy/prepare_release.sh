#!/bin/bash
# Prepare and verify a runtime without changing the active service or proxy.
# Run as root on the managed host, or an isolated Ubuntu acceptance runner.
set -Eeuo pipefail
source_dir=$1
release_id=$2
domain=$3
[[ $release_id =~ ^[a-f0-9]{64}$ ]]
[[ $domain =~ ^[a-z0-9]+([.-][a-z0-9]+)+$ ]]
base=/opt/saga2d-online
release="$base/releases/$release_id"
mkdir -p "$base/releases"
python3 -B "$source_dir/deploy/stage_release.py" "$source_dir/release.tar.gz" "$release" "$release_id"
chown -R root:root "$release"
chmod -R u+rwX,go+rX,go-w "$release"
if [[ ! -f "$release/.ready" ]]; then
    # Bootstrap a hash-pinned uv wheel using Ubuntu's Python, then install the
    # candidate's exact managed Python outside /root (ProtectHome=true).
    bootstrap="$base/bootstrap"
    python3 -m venv "$bootstrap"
    "$bootstrap/bin/pip" install --require-hashes --only-binary=:all: -r "$release/deploy/uv-bootstrap.txt"
    export UV_PYTHON_INSTALL_DIR="$base/python" UV_CACHE_DIR="$base/cache" UV_PYTHON_PREFERENCE=only-managed
    expected_python=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["python"])' "$release/deploy/server-inputs.json")
    expected_uv=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["uv"])' "$release/deploy/server-inputs.json")
    [[ $("$bootstrap/bin/uv" --version) == "uv $expected_uv "* ]]
    "$bootstrap/bin/uv" venv --clear --python "$expected_python" "$release/.venv"
    "$bootstrap/bin/uv" pip install --python "$release/.venv/bin/python" --require-hashes -r "$release/deploy/requirements.txt"
    chmod -R go+rX,go-w "$base/python" "$release/.venv"
fi
# Reverify cached releases too; never mark an incomplete acceptance as ready.
verification=$(mktemp "$base/.verification.XXXXXX")
trap 'rm -f "$verification"' EXIT
runuser -u saga2d-online -- "$release/.venv/bin/python" -B "$release/deploy/check_release.py" "$release" \
    --release-id "$release_id" --endpoint "wss://$domain/play" > "$verification"
mv "$verification" "$release/.ready"
trap - EXIT

