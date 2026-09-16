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

# Shared with activate_site.py; held through acceptance and any rollback.
exec 9>/var/lock/saga2d-online.publish.lock
flock 9
if [[ -e /srv/saga2d-site/pending.json ]]; then
    echo 'Recover the interrupted site promotion before activating a server.' >&2
    exit 1
fi

base=/opt/saga2d-online
release="$base/releases/$release_id"
bash "$source_dir/deploy/prepare_release.sh" "$source_dir" "$release_id" "$domain"

install_service() {
    local service_release=$1
    sed -e "s/__RELEASE_ID__/${service_release##*/}/g" -e "s/__DOMAIN__/$domain/g" \
        "$service_release/deploy/saga2d-online.service" > "$source_dir/saga2d-online.service"
    install -m 644 "$source_dir/saga2d-online.service" /etc/systemd/system/saga2d-online.service
}

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
        install_service "$previous"
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
install_service "$release"
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
python3 - "$release/.ready" <<'PY'
import json, sys, urllib.request
expected = json.load(open(sys.argv[1]))["baseline"]
with urllib.request.urlopen('http://127.0.0.1:8765/server-compatibility.json', timeout=10) as response:
    actual = json.load(response)
if actual != expected:
    raise RuntimeError('Running server does not match the accepted candidate baseline')
PY
install -m 644 "$source_dir/Caddyfile" /etc/caddy/Caddyfile
systemctl enable --now caddy
systemctl reload caddy
trap - ERR
printf 'Activated release %s\n' "$release_id"
