# WB-017 / WB-007 — Rules rollout

Started 2026-09-18 on Saga Online `b4ef8fb`, from Warband's `rules` branch
(WB-017 `bd60932`: a walk keeps its pace through waypoints; WB-007 `0ea2c1f`:
a resignation among three or more leaves abandoned buildings; `2974699`: a
worker shoved beside a building corner plans again instead of bouncing, an
older deadlock WB-017's fuzz exposed). All change `warband/model.py`, so the
authoritative compatibility contract moves and the publication gate refuses
the client until the shared server runs the same rules. The candidate is
Warband main `0bbe4ae` (the branch merged, with the backlog's done entries),
native run 35295716718. Sagaforge moves to `10f4d87` (the painted-sheet
cleaners of WB-019 and WB-023; the server uses none of them, but the identity
must match). Tribes, Shardbound, Saga2D 0.3.3, Python 3.13.2 and uv 0.12.10
stay at their pins.

## Acceptance defined before rollout

1. The exact Warband main commit that carries both items passes its Linux
   suite and its Windows/Mac native package checks; that native run is the
   only candidate recorded in the server pins. Its simulation fingerprint was
   refreshed deliberately in the WB-017 commit; the change is the intended
   rules change and nothing else (`tests/warband/test_waypoints.py`,
   `tests/warband/test_abandoned.py`, the game's full suite, seeded fuzz).
2. Saga Online's suite runs on clean adjacent checkouts at the new pins; the
   immutable server archive is built there and CI prepares and reverifies it
   as the Linux service account: three-game orders, checkpoint and restart,
   backup and restore, deployment exclusion and restricted SSH.
3. Before activation: a fresh, verified off-host backup of the live rooms; a
   private local rehearsal that starts the candidate server on a copy of that
   backup and rejoins every retained seat with its own token, so every
   retained campaign resumes with its state.
4. Activation goes through the existing installer only (preparation and the
   packaged release check as the service account, then the atomic switch);
   the previous release and the backup stay for rollback; the website pointer
   does not change during activation.
5. After activation: public health, the served compatibility attestation equal
   to the candidate's contract, the three-game smoke, a native Warband online
   journey from the candidate checkout against the public server (create,
   join, orders, rejoin) and a rejoin of the retained campaigns on the live
   server. Only then is the baseline recorded from the served attestation, the
   Warband publication re-run from its accepted native run, the promotion
   accepted and the public downloads checked.

The stack's standing authorization applies; the
[deployment runbook](../deploy/README.md) and the accepted
[melee rollout](warband-melee-rollout.md) give the procedure.

## Status

**Backup and rehearsal, 2026-09-18 00:57 UTC.** `deploy_online.py backup` took a
fresh consistent backup on the server and verified the off-host copy
`rooms-20260918T005725Z.sqlite3` (SHA-256
`e90e42adff5dea3a94c379625c2499d681ffc57fabd61f9e9d81de4a1d3cf116`,
integrity ok). `tools/rehearse_retained.py` (new: a reusable rehearsal that
starts the real room server for all three games over a private copy of a
backup and resumes every seat with its own token, at the production room and
connection limits) resumed all **9 seats of the 5 retained Shardbound
campaigns** on the candidate code, none failed; the report is in
`docs/evidence/rules-rollout/rehearsal.log`. The live server was not touched
beyond the backup unit.

**Candidate pinned, rehearsal repeated, 2026-09-18 02:40 UTC.** The branch
gained `2974699` (the corner-bounce fix its fuzz found) before merging; main
`0bbe4ae` is the candidate, with its Tests run 35295716669 and native run
35295716718 pinned in `.github/server-pins.json` together with sagaforge
`10f4d87`. The retained-seat rehearsal was run again over the same backup
copy with the sibling Warband checkout at `0bbe4ae`: all **9 seats of the 5
retained campaigns** resumed, none failed
(`docs/evidence/rules-rollout/rehearsal-0bbe4ae.log`).

**Candidate green, its promotion refused as designed, 2026-09-18 01:50 UTC.**
Warband `0bbe4ae` passed [Tests 35295716669](https://github.com/ikamensh/warband/actions/runs/35295716669)
and [native package checks 35295716718](https://github.com/ikamensh/warband/actions/runs/35295716718)
on Windows and Mac; main's automatic
[publish 35296736779](https://github.com/ikamensh/warband/actions/runs/35296736779)
produced its immutable release, and Saga Online's
[promotion 35296870787](https://github.com/ikamensh/saga-online/actions/runs/35296870787)
refused it with "Candidate requires a different server compatibility
baseline": the live site keeps 0.2.10 until the server runs the new rules.
The `rules-server` branch with the pins is pushed for CI acceptance.

**Server packaging repaired, 2026-09-18 03:25 UTC.** The branch's first CI run
([35296943073](https://github.com/ikamensh/saga-online/actions/runs/35296943073))
failed in `test_packaged_release_runs_server_entrypoint`: Warband `42dc02d`
numbers releases from the native run number and its `ci_release.py prepare`
has required `--run-number` since, while server packaging still called it
with the run id alone. This candidate is the first server pin at or after
that commit, so the live server's pin never met it. `05fc9e5` records
`warband_run_number` (36) beside the run id in the pins, passes it through,
checks the identity echoes both, and makes CI's provenance step assert the
pinned number is the run's. Local packaging with the pinned uv 0.12.10 then
produced release `58f75c42…` (314 files); CI acceptance runs again.

## Accepted live server — 2026-09-18

Saga Online `05fc9e5` passed [Tests 35297328393](https://github.com/ikamensh/saga-online/actions/runs/35297328393)
(the suite with the repaired packaging, host exclusion, restricted SSH, the
archive built and reverified as the service account) and
[Website checks 35297328394](https://github.com/ikamensh/saga-online/actions/runs/35297328394).
The archive CI built is the one activated: local packaging at the same
commit with the pinned uv gives the identical release
`58f75c4244f2a88333972b1eb6ec6d70a2849bcc883faa7e3b4d42ffd901991d`
(314 files).

Before activation a fresh backup, `rooms-20260918T020105Z.sqlite3`, was
taken and verified off host: 5 rooms, SHA-256 `e90e42ad…` — byte-identical
to the 00:57 backup the rehearsals used, so nothing had changed in the store.
`deploy_online.py deploy` uploaded the archive, prepared it as the service
account (hashed runtime, the packaged release check over a private copy of
the live rooms, Caddy validation) and activated it at 02:01:33 UTC; the
previous release `acb8cef2…` stays at the `previous` pointer with its backups.

After activation: public health `ok`; the served attestation names
deployment `58f75c42…`, Warband `0bbe4ae` and the compatibility contract
`6b33fd3829a5ddccaa0d4bd37ca5df8046a59cc4d265cca0d29c013098a8f8e3`, the same
digest `tools/ci_compatibility.py` computes on the candidate checkout;
`deploy/smoke.py` passed create, join and order for all three games; every
retained seat resumed on the live server with its own token (5 rooms, 9
seats, none failed: `docs/evidence/rules-rollout/live-rejoin.log`); the
native Tribes journey (create, room-code join, gameplay, restart and rejoin)
passed against the public server. The Warband journey first failed inside
`tools/verify_multiplayer.py`, which still imported `WarbandMatch` from
`warband.multiplayer` after Warband `2361f79` moved it to
`warband.authority`; `d55b3a1` repairs the tool and adds the test, and the
Warband journey (native create, room-code join, accepted gameplay, restart
and rejoin against the public server) then passed, and so did Shardbound's
(its first attempt found no display: the Mac's screen had slept between
runs); the frames are under `docs/evidence/rules-rollout/public/`.

The served attestation is recorded as the new
[`releases/server-baseline.json`](../releases/server-baseline.json). This
accepts the shared-server dependency of WB-017 and WB-007; the client's
promotion follows from the already published, immutable release 0.2.11.
