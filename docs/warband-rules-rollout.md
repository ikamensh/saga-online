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

CI acceptance, activation and the public checks follow once the candidate's
Linux suite and native run are green.
