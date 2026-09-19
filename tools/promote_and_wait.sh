#!/bin/bash
# Dispatch "Promote verified Warband" for a release and wait for its verdict.
#   GH_TOKEN=... GITHUB_REPOSITORY=owner/repo tools/promote_and_wait.sh BUILD_RUN_ID RELEASE_ID MANIFEST_SHA256
# The rollout waits, so the next queued rollout sees the promoted catalog and
# the rollout's own run is red when its promotion is.
set -euo pipefail
since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
gh workflow run warband-promotion.yml --repo "$GITHUB_REPOSITORY" --ref main \
    -f build_run_id="$1" -f release_id="$2" -f manifest_sha256="$3"
run=
for attempt in $(seq 30); do
    run=$(gh run list --repo "$GITHUB_REPOSITORY" --workflow warband-promotion.yml --event workflow_dispatch \
          --json databaseId,createdAt --jq "[.[] | select(.createdAt >= \"$since\")] | last | .databaseId // empty")
    [[ -n $run ]] && break
    sleep 5
done
[[ -n $run ]] || { echo '::error::The dispatched promotion did not appear'; exit 1; }
echo "Promotion: $GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$run"
gh run watch "$run" --repo "$GITHUB_REPOSITORY" --exit-status --interval 20 > /dev/null
