# WB-003 — Movement input compatibility rollout

Candidate preparation began on 2026-09-17 from Saga Online main `f3a4565`.
Server acceptance completed on 2026-09-17. The live baseline now contains the
verified candidate; client publication remains the next step.

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
deployment is accepted below. The website stayed unchanged during activation.

Warband `35b851f` passed [Tests 35210630104](https://github.com/ikamensh/warband/actions/runs/35210630104)
and [Windows/Mac native package checks 35210630105](https://github.com/ikamensh/warband/actions/runs/35210630105),
including the final artifact validation job. Local native movement and pointer
acceptance is recorded in the game diagnosis.

The isolated Saga Online candidate at `501558a` passed **135 tests in 92.38
seconds**, including the actual packaged server, three-game orders and delayed
disconnect/restart/backup-restore journey. Log:
`docs/evidence/movement-rollout/full-tests.log`. Its locked Python 3.13.2
environment contains the accepted Saga2D 0.3.2 release. A sibling engine symlink
only resolves shared documentation links; it is not installed into the runtime.

### Accepted Linux package and live rollout

[Linux run 35212059946](https://github.com/ikamensh/saga-online/actions/runs/35212059946)
on `6c125cb` passed **135 tests, zero skips/failures, 100.740 seconds**, plus
service-account preparation/retry, three-game checkpoint/restart/restore,
deployment exclusion and restricted SSH acceptance. Website checks
`35212059889` passed. The independently downloaded archive's SHA-256 is
`99e28517d6170e0957c56c3b7de8eeebdcf7befeaf54ecd371d6de11354609f7`.
It retains every accepted engine/other-game pin and changes Warband to `35b851f`.
The authoritative contract digest is
`f88cb9138d3d9208366011b6289e0d5c8cb57a465d696ccc0a28d60accd43137`.

The old public server rejected the new explicit-null context command with
`Invalid order arguments.` The accepted package, running privately under the
actual Linux service account, passed explicit empty-ground, queued entity
identity, legacy omission, malformed target rejection and foreign-unit rejection;
rejections left the existing order queue unchanged. All five retained seats
rejoined a private copy of the live backup; all three retained Shardbound
campaigns kept exactly their state and seat credentials.

After preserving service/proxy configuration and an off-host stopped checkpoint
(`rooms-20260917T110553Z.sqlite3`, SHA-256
`c419612c0084b67bd62e8bffaa448228292b63c466901b8b7b423db51b175833`),
the accepted archive was activated through the existing installer. Public health,
exact runtime attestation and all five context-command checks passed. The website
pointer and transaction state stayed unchanged. The prior accepted release
`c5193bd5…b63dca` remains available; its database/configuration rollback was
verified during WB-002. No new rollback exercise is claimed here.

Downloaded frozen Mac clients for **Tribes, Shardbound and candidate Warband**
passed public TLS create/join, authoritative orders and private-seat rejoin.
Warband's app/portable archive hashes match native run `35210630105`, its app
signature verifies, and all eight packaged online checks passed. These are
network/package checks; movement rendering evidence is in the game diagnosis.
A fresh post-activation backup also preserves all three original campaigns and
their credentials exactly. The normal online backup service succeeds.

One operator issue was found before activation: with the main process stopped,
the hardened backup unit's read-only state directory prevents SQLite from
creating missing WAL helpers. The failed attempt restarted the old service and
did not change its release. Taking the stopped checkpoint through the same
SQLite backup API as the service UID outside that filesystem sandbox succeeded.
This is tracked separately as [SO-001](../BACKLOG.md#so-001--back-up-a-stopped-wal-database).
Do not treat the normal backup unit as verified for stopped-service backups yet.

Evidence under `docs/evidence/movement-rollout/`: `host-candidate.json`,
`private-host-acceptance.json`, `activation.json`, `retained-campaigns.json`,
`public-clients/acceptance.json`, and the downloaded CI reports. Private SQLite
copies and configuration snapshots are restricted and git-ignored. The
[recorded production baseline](../releases/server-baseline.json) comes from the
actual public process, not the CI test endpoint.
