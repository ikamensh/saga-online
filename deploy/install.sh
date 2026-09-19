#!/bin/bash
# Invoked through sudo on the dedicated, tagged Saga2D instance only.
#
#   install.sh SOURCE_DIR RELEASE_ID INSTANCE DOMAIN     prepare SOURCE_DIR/release.tar.gz and activate it
#   install.sh --rollback FROM_RELEASE INSTANCE DOMAIN   while FROM_RELEASE is current, reactivate `previous`
#
# Preparation, service units and proxy configuration come from this script's
# own directory. Preparation refuses a release whose copies of them differ, so
# nothing from an upload runs as root: the restricted server-CI account runs the
# operator-installed copy of this script, never the one inside an archive.
set -Eeuo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [[ $1 == --rollback ]]; then
    mode=rollback
    release_id=$2
else
    mode=install
    source_dir=$1
    release_id=$2
fi
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
work=$(mktemp -d /run/saga2d-install.XXXXXXXX)
trap 'rm -rf "$work"' EXIT
current=$(readlink "$base/current" || test ! -e "$base/current")

install_service() {
    sed -e "s/__RELEASE_ID__/${1##*/}/g" -e "s/__DOMAIN__/$domain/g" \
        "$here/saga2d-online.service" > "$work/saga2d-online.service"
    install -m 644 "$work/saga2d-online.service" /etc/systemd/system/saga2d-online.service
}

# Point `current` at a prepared release, restart and accept it: health, then the
# served compatibility equal to the one its preparation verified, then the proxy.
activate() {
    local target=$1
    sed "s/__DOMAIN__/$domain/g" "$here/Caddyfile" > "$work/Caddyfile"
    caddy validate --config "$work/Caddyfile" --adapter caddyfile
    install_service "$target"
    install -m 644 "$here/saga2d-backup.service" /etc/systemd/system/saga2d-backup.service
    install -m 644 "$here/saga2d-backup.timer" /etc/systemd/system/saga2d-backup.timer
    install -d -m 700 -o saga2d-online -g saga2d-online /var/backups/saga2d-online
    ln -sfn "$target" "$base/current.next"
    mv -Tf "$base/current.next" "$base/current"
    systemctl daemon-reload
    systemctl enable saga2d-online
    systemctl restart saga2d-online
    systemctl enable --now saga2d-backup.timer
    local healthy=false
    for attempt in {1..30}; do
        if curl --fail --silent http://127.0.0.1:8765/healthz > /dev/null; then
            healthy=true
            break
        fi
        sleep 1
    done
    if [[ $healthy != true ]]; then
        journalctl -u saga2d-online --no-pager -n 40
        echo 'Server failed its health check.' >&2
        return 1
    fi
    python3 - "$target/.ready" <<'PY'
import json, sys, urllib.request
expected = json.load(open(sys.argv[1]))["baseline"]
with urllib.request.urlopen('http://127.0.0.1:8765/server-compatibility.json', timeout=10) as response:
    actual = json.load(response)
if actual != expected:
    raise RuntimeError('Running server does not match the accepted release baseline')
PY
    install -m 644 "$work/Caddyfile" /etc/caddy/Caddyfile
    systemctl enable --now caddy
    systemctl reload caddy
}

cp /etc/caddy/Caddyfile "$work/Caddyfile.previous"
restore_proxy() {
    install -m 644 "$work/Caddyfile.previous" /etc/caddy/Caddyfile
    systemctl reload caddy
}

if [[ $mode == rollback ]]; then
    if [[ ${current##*/} != "$release_id" ]]; then
        echo "Refusing rollback: the current release is ${current##*/}, not $release_id." >&2
        exit 1
    fi
    target=$(readlink "$base/previous" || true)
    if [[ -z $target || ${target##*/} == "$release_id" || ! -f $target/.ready ]]; then
        echo 'Refusing rollback: no distinct prepared previous release.' >&2
        exit 1
    fi
    failed_rollback() {
        trap - ERR
        echo 'Rollback failed; the proxy configuration is restored, the service needs the operator.' >&2
        restore_proxy
        exit 1
    }
    trap failed_rollback ERR
    activate "$target"
    ln -sfn "$current" "$base/previous"
    trap - ERR
    printf 'Rolled back to release %s\n' "${target##*/}"
    exit 0
fi

release="$base/releases/$release_id"
bash "$here/prepare_release.sh" "$source_dir" "$release_id" "$domain"
# Re-activating the current release keeps the distinct release behind it.
if [[ -n $current && ${current##*/} != "$release_id" ]]; then
    ln -sfn "$current" "$base/previous"
fi
rollback() {
    trap - ERR
    echo 'Activation failed; restoring the previous service and proxy configuration.' >&2
    if [[ -n $current ]]; then
        ln -sfn "$current" "$base/current.next"
        mv -Tf "$base/current.next" "$base/current"
        install_service "$current"
        systemctl daemon-reload
        systemctl restart saga2d-online
    else
        systemctl stop saga2d-online
    fi
    restore_proxy
    exit 1
}
trap rollback ERR
activate "$release"
trap - ERR
printf 'Activated release %s\n' "$release_id"
