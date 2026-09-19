#!/bin/bash
# Prepare and verify a runtime without changing the active service or proxy.
# Run as root on the managed host, or an isolated Ubuntu acceptance runner.
# Everything root executes comes from this script's own directory; the release
# must carry identical copies (HOST_FILES), and its own code runs only as the
# unprivileged service account.
set -Eeuo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source_dir=$1
release_id=$2
domain=$3
[[ $release_id =~ ^[a-f0-9]{64}$ ]]
[[ $domain =~ ^[a-z0-9]+([.-][a-z0-9]+)+$ ]]
base=/opt/saga2d-online
release="$base/releases/$release_id"
mkdir -p "$base/releases"
python3 -B "$here/stage_release.py" "$source_dir/release.tar.gz" "$release" "$release_id"
chown -R root:root "$release"
chmod -R u+rwX,go+rX,go-w "$release"
for name in install.sh prepare_release.sh stage_release.py runtime.py uv-bootstrap.txt \
            saga2d-online.service saga2d-backup.service saga2d-backup.timer Caddyfile; do
    if ! cmp -s "$here/$name" "$release/deploy/$name"; then
        echo "Release $release_id carries a different deploy/$name than the installed host tools;" \
             'the operator installs host changes with deploy_online.py setup-server-ci.' >&2
        exit 1
    fi
done
if [[ ! -f "$release/.ready" ]]; then
    # Bootstrap a hash-pinned uv wheel using Ubuntu's Python, then install the
    # candidate's exact managed Python outside /root (ProtectHome=true).
    bootstrap="$base/bootstrap"
    python3 -m venv "$bootstrap"
    "$bootstrap/bin/pip" install --require-hashes --only-binary=:all: -r "$here/uv-bootstrap.txt"
    export UV_PYTHON_INSTALL_DIR="$base/python" UV_CACHE_DIR="$base/cache" UV_PYTHON_PREFERENCE=only-managed
    expected_python=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["python"])' "$release/deploy/server-inputs.json")
    expected_uv=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["uv"])' "$release/deploy/server-inputs.json")
    [[ $("$bootstrap/bin/uv" --version) == "uv $expected_uv "* ]]
    "$bootstrap/bin/uv" venv --clear --python "$expected_python" "$release/.venv"
    # Wheels only: a source build would run the upload's code as root.
    "$bootstrap/bin/uv" pip install --no-build --python "$release/.venv/bin/python" --require-hashes -r "$release/deploy/requirements.txt"
    chmod -R go+rX,go-w "$base/python" "$release/.venv"
fi
# Reverify cached releases too; never mark an incomplete acceptance as ready.
verification=$(mktemp "$base/.verification.XXXXXX")
trap 'rm -f "$verification"' EXIT
runuser -u saga2d-online -- "$release/.venv/bin/python" -B "$release/deploy/check_release.py" "$release" \
    --release-id "$release_id" --endpoint "wss://$domain/play" > "$verification"
mv "$verification" "$release/.ready"
trap - EXIT
