# WB-003 — Movement input compatibility rollout

Candidate preparation began on 2026-09-17 from Saga Online main `f3a4565`.
This is pending acceptance; the live baseline and catalog are unchanged.

Warband `35b851f` fixes local/replay presentation and makes pointer actions
follow the displayed units. Its optional `smart.target_id` field preserves the
clicked identity: an integer selects that entity; explicit null means empty
ground; omission keeps the existing model-point behavior. The current server
rejects the new field, so this client needs a verified server update before
publication. The default simulation fingerprint is unchanged. See
[the game diagnosis](../../warband/docs/movement-diagnosis.md).

## Acceptance defined before rollout

1. Require the exact Warband source's Windows/Mac native checks and full game
   suite. The recorded candidate run is `35210630105`; recording its ID here
   does not claim it has passed. Keep engine, Python, uv, Sagaforge, Tribes and
   Shardbound inputs at the accepted pins.
2. Run the complete Saga Online suite with clean, adjacent pinned checkouts.
   Build the immutable server package, verify its authoritative source/runtime
   contract against the native candidate identity, and run the Linux service
   account preparation, three-game orders, checkpoint/restart and backup/rejoin
   checks through the existing workflow. A desired pin is not runtime evidence.
3. Exercise explicit empty-ground and entity-target smart orders through the
   candidate server, including queued movement and ordinary omitted-target
   orders. Retain the original ownership/type validation and verify rejected
   orders leave state unchanged. The game suite already covers these cases
   across a real LAN socket and JSON replay; verify the packaged path too.
4. Preserve the actual current database and service/proxy configuration. Rejoin
   the retained campaigns from a private backup copy with the candidate before
   activation. Keep the prior release and backup available for rollback. The
   existing activation/rollback mechanism is unchanged by this candidate.
5. After activation, verify public health, the exact runtime attestation,
   three-game create/join/orders/rejoin and the new pointer intent. Keep the
   website pointer unchanged during server activation. Only then record the
   actual server baseline, integrate the completed game item, and let the
   established main-push pipeline publish and promote its native builds.

Use [the deployment runbook](../deploy/README.md) and the accepted procedures
and evidence in [WB-002](warband-ci-publication.md). There is standing authority
to perform the verified rollout; no further approval is required.

## Status

Separate worktrees under `~/saga/.worktrees/wb003-server/` hold the candidate
and all exact sibling pins, preserving the active game worktrees. Candidate
checks and deployment remain pending. No live state has changed for WB-003.
