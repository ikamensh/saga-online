#!/bin/bash
# Installs only a client runtime on the dedicated AI instance, never the room server.
set -Eeuo pipefail
archive=$1
release_id=$2
[[ $release_id =~ ^[a-f0-9]{64}$ ]]
[[ $(cat /etc/saga2d-online/managed-instance) == saga2d-warband-ai ]]
printf '%s  %s\n' "$release_id" "$archive" | sha256sum --check --status
base=/opt/saga2d-warband-ai
release="$base/releases/$release_id"
mkdir -p "$release"
if [[ ! -f "$release/.ready" ]]; then
    tar -xzf "$archive" -C "$release" --no-same-owner
    chown -R root:root "$release"
    chmod -R u+rwX,go+rX,go-w "$release"
    python3 -m venv "$release/.venv"
    "$release/.venv/bin/pip" install --require-hashes -r "$release/deploy/requirements.txt"
    (cd "$release" && "$release/.venv/bin/python" -m warband.online_ai --help)
    touch "$release/.ready"
fi
ln -sfn "$release" "$base/current.next"
mv -Tf "$base/current.next" "$base/current"
# The common VM bootstrap installs Caddy; this outbound-only client has no web service.
systemctl disable --now caddy
printf 'Installed AI client %s\n' "$release_id"
