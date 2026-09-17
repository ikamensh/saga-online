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
mode=$7
[[ $release_id =~ ^[a-f0-9]{64}$ ]]
[[ $instance_name =~ ^saga2d-[a-z0-9-]+$ ]]
[[ $domain =~ ^[a-z0-9]+([.-][a-z0-9]+)+$ ]]
[[ $(cat /etc/saga2d-online/managed-instance) == "$instance_name" ]]
[[ -f $source_dir/site/index.html && -f $source_dir/site/releases.json ]]
promotion=()
if [[ $mode == warband-promotion ]]; then
    promotion=(--promotion-receipt "$source_dir/promotion.json")
else
    [[ $mode == operator && ! -e $source_dir/promotion.json ]]
fi

# The operator uses the same account as CI so accepted state remains readable
# by future publications. Upload data stays owned by deploy for later cleanup.
chgrp -R saga2d-site-ci "$source_dir"
chmod -R g+rX "$source_dir"
trusted=$(readlink -f /usr/local/lib/saga2d-site-ci/current)
exec runuser -u saga2d-site-ci -- /usr/bin/python3 -I -B "$trusted/activate_site.py" \
    --source "$source_dir/site" --base /srv/saga2d-site \
    --release "$release_id" --generation "$generation" --expected "$expected" \
    --public-url "https://$domain" --health-url "https://$domain/healthz" \
    --mode "$mode" "${promotion[@]}"
