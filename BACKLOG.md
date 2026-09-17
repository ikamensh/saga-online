# Saga Online backlog

Keep IDs stable. Mark an item done only after its acceptance checks pass and
record the implementation commit and evidence.

| ID | Status | Task |
|---|---|---|
| SO-001 | ready | Back up a stopped WAL database through the hardened service |

## SO-001 — Back up a stopped WAL database

Discovered during the [WB-003 server rollout](docs/warband-movement-rollout.md).
The ordinary backup unit succeeds while the room server is running. After a
clean stop removes WAL helpers, SQLite's read-only connection may need to create
those helpers; `ProtectSystem=strict` permits writes only to the backup folder,
so `source.backup` fails with `unable to open database file`. The same consistent
backup API succeeds as the service UID outside the unit's filesystem sandbox.

**Acceptance before implementation:** reproduce using the actual service unit
on isolated Linux with both running and cleanly stopped WAL databases. Preserve
the online backup's consistency and least necessary filesystem access; never use
SQLite's immutable mode for a live changing database. Verify integrity and
restore/rejoin from each resulting backup. Check failure cleanup and retry, then
verify the accepted procedure on the managed host and update the runbook. Do not
run destructive host-acceptance fixtures on production.
