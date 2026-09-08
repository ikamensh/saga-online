#!/bin/bash
# Invoked through sudo on the dedicated, tagged Saga2D instance only.
set -Eeuo pipefail
source_dir=$1
release_id=$2
instance_name=$3
domain=$4
[[ $release_id =~ ^[a-f0-9]{64}$ ]]
[[ $instance_name =~ ^saga2d-[a-z0-9-]+$ ]]
[[ $domain =~ ^[a-z0-9]+([.-][a-z0-9]+)+$ ]]
[[ $(cat /etc/saga2d-online/managed-instance) == "$instance_name" ]]

base=/opt/saga2d-online
release="$base/releases/$release_id"
mkdir -p "$base/releases"
if [[ ! -f "$release/.ready" ]]; then
    mkdir -p "$release"
    cp -a "$source_dir"/. "$release/"
    chown -R root:root "$release"
    chmod -R u+rwX,go+rX,go-w "$release"
    python3 -m venv "$release/.venv"
    "$release/.venv/bin/pip" install --require-hashes -r "$release/deploy/requirements.txt"
    python3 "$release/deploy/check_release.py" "$release"
    touch "$release/.ready"
fi

# Validate proxy configuration before replacing either live configuration.
sed "s/__DOMAIN__/$domain/g" "$release/deploy/Caddyfile" > "$source_dir/Caddyfile"
caddy validate --config "$source_dir/Caddyfile" --adapter caddyfile
previous=$(readlink "$base/current" || test ! -e "$base/current")
if [[ -n $previous ]]; then
    ln -sfn "$previous" "$base/previous"
fi
cp /etc/caddy/Caddyfile "$source_dir/Caddyfile.previous"
rollback() {
    trap - ERR
    echo 'Activation failed; restoring the previous service and proxy configuration.' >&2
    if [[ -n $previous ]]; then
        ln -sfn "$previous" "$base/current.next"
        mv -Tf "$base/current.next" "$base/current"
        install -m 644 "$previous/deploy/saga2d-online.service" /etc/systemd/system/saga2d-online.service
        systemctl daemon-reload
        systemctl restart saga2d-online
    else
        systemctl stop saga2d-online
    fi
    install -m 644 "$source_dir/Caddyfile.previous" /etc/caddy/Caddyfile
    systemctl reload caddy
    exit 1
}
trap rollback ERR
install -m 644 "$release/deploy/saga2d-online.service" /etc/systemd/system/saga2d-online.service
install -m 644 "$release/deploy/saga2d-backup.service" /etc/systemd/system/saga2d-backup.service
install -m 644 "$release/deploy/saga2d-backup.timer" /etc/systemd/system/saga2d-backup.timer
install -d -m 700 -o saga2d-online -g saga2d-online /var/backups/saga2d-online
ln -sfn "$release" "$base/current.next"
mv -Tf "$base/current.next" "$base/current"
systemctl daemon-reload
systemctl enable saga2d-online
systemctl restart saga2d-online
systemctl enable --now saga2d-backup.timer

healthy=false
for attempt in {1..30}; do
    if curl --fail --silent http://127.0.0.1:8765/healthz > /dev/null; then
        healthy=true
        break
    fi
    sleep 1
done
if [[ $healthy != true ]]; then
    journalctl -u saga2d-online --no-pager -n 40
    echo 'New server failed its health check.' >&2
    false
fi
install -m 644 "$source_dir/Caddyfile" /etc/caddy/Caddyfile
systemctl enable --now caddy
systemctl reload caddy
trap - ERR
printf 'Activated release %s\n' "$release_id"
