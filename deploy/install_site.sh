#!/bin/bash
# Invoked through sudo on the dedicated, tagged Saga2D instance only.
# The Python transaction owns the lock, public verification and rollback.
set -Eeuo pipefail
source_dir=$1
release_id=$2
instance_name=$3
domain=$4
generation=$5
expected=$6
[[ $release_id =~ ^[a-f0-9]{64}$ ]]
[[ $instance_name =~ ^saga2d-[a-z0-9-]+$ ]]
[[ $domain =~ ^[a-z0-9]+([.-][a-z0-9]+)+$ ]]
[[ $(cat /etc/saga2d-online/managed-instance) == "$instance_name" ]]
[[ -f $source_dir/site/index.html && -f $source_dir/site/releases.json ]]

exec python3 "$source_dir/deploy/activate_site.py" \
    --source "$source_dir/site" --base /srv/saga2d-site \
    --release "$release_id" --generation "$generation" --expected "$expected" \
    --public-url "https://$domain" --health-url "https://$domain/healthz"
