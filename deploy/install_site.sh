#!/bin/bash
# Invoked through sudo on the dedicated, tagged Saga2D instance only.
# Publishes one immutable static site release and points Caddy's root at it.
set -Eeuo pipefail
source_dir=$1
release_id=$2
instance_name=$3
[[ $release_id =~ ^[a-f0-9]{64}$ ]]
[[ $instance_name =~ ^saga2d-[a-z0-9-]+$ ]]
[[ $(cat /etc/saga2d-online/managed-instance) == "$instance_name" ]]
[[ -f $source_dir/site/index.html && -f $source_dir/site/releases.json ]]

base=/srv/saga2d-site
release="$base/releases/$release_id"
mkdir -p "$base/releases"
if [[ ! -d $release ]]; then
    rm -rf "$release.partial"
    mkdir -p "$release.partial"
    cp -a "$source_dir/site/." "$release.partial/"
    chown -R root:root "$release.partial"
    chmod -R u+rwX,go+rX,go-w "$release.partial"
    mv -T "$release.partial" "$release"
fi
ln -sfn "$release" "$base/current.next"
mv -Tf "$base/current.next" "$base/current"
# Keep the three most recent releases for manual rollback.
ls -1dt "$base"/releases/*/ | tail -n +4 | xargs -r rm -rf
printf 'Published site %s\n' "$release_id"
