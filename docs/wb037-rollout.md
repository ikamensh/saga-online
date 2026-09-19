# WB-037 — Workers take cover, melee spreads round a building

Started 2026-09-19 on Saga Online `9763969`, after the
[fast simulation](fastsim-rollout.md). Warband's WB-037 answers a tower rush
(Warband's `BACKLOG.md`, `docs/ai-ladder.md`, "A tower on our ground"). Two of
its changes are in the simulation, so the authoritative contract moves in
`warband/model.py` and in nothing else:

- An automatic worker caught on ground its safe map forbids walks out to the
  nearest safe tile even when its work cannot be reached from there
  (`World._take_cover`). A tower beside the hall had left every depot in
  danger, and carriers waited in its fire until it killed them.
- A melee attacker on a building aims for an open tile of the ring round it
  (`World._siege_spot`) instead of the point on its own side, which a tree or
  a wall can close: attackers stood a path's end short of it for good.

These change play, so the live release and the candidate do not play a match
alike; a checkpoint written by either restores on the other. The brains' part
of WB-037 (`warband/pro_ai.py`, `ai.py`) is outside the authority's import
closure. Warband's `dev` extra gained `pytest-xdist` with WB-040, which the lock
records; the exported server runtime is unchanged. Sagaforge moves from
`10f4d87` to `e099051`, the commit Warband's release pins have named since its
WB-040: `restyle.recolor` converts back from HSV only the pixels that move, with
bit-identical output, and nothing on the server imports `restyle`. Saga2D
0.3.8, Tribes `4c13383`, Shardbound `b2cdcbe`, Python 3.13.2 and uv 0.12.10
stay at their pins.

## Acceptance defined before rollout

1. The Warband main commit that merges WB-037 has passed its Linux suite and
   its Windows and Mac native package checks; that native run is the one in
   the server pins. `tools/ci_compatibility.py` on it differs from the live
   contract (`fcdc63e6…`) in `warband/model.py` and in nothing else; the
   packages are unchanged.
2. A checkpoint the live release (`6744934`) wrote restores on the candidate
   and plays on; the rehearsal below covers every retained seat.
3. Saga Online's suite runs on clean adjacent checkouts at the new pins. CI
   builds and reverifies the immutable archive as the Linux service account,
   and the locally built archive is identical.
4. Before activation: a fresh, verified off-host backup of the live rooms and
   a private rehearsal that resumes every retained seat on the candidate.
5. Activation through the existing installer only; the previous release
   `f3302078…` and the backup stay for rollback; the website pointer does not
   change during activation.
6. After activation: public health, the served attestation equal to the
   candidate's contract, the three-game smoke, every retained seat resumed on
   the live server, a native Warband online journey against the public
   server, `permessage-deflate` still negotiated through the proxy, and a
   three-seat Warband room on the public server. Only then is the baseline
   recorded from the served attestation, the refused promotion dispatched
   again and the public downloads checked.

The stack's standing authorization applies; the
[deployment runbook](../deploy/README.md) gives the procedure.

## Status

**Accepted live server, 2026-09-19 00:52 UTC.** Warband `1b9880f` (the merge
of WB-037's `3859e53`) passed
[Tests 35410028696](https://github.com/ikamensh/warband/actions/runs/35410028696)
and [native package checks 35410028686](https://github.com/ikamensh/warband/actions/runs/35410028686)
(run number 78, Windows and Mac). Its contract,
`5742acaea93d68683cad9ed0959d387669e78a188d38456fb619c5868fbbe8e4`, differs
from the live one in `warband/model.py` and in nothing else (packages,
Python and registry unchanged). The first packaging stopped on the Sagaforge
pin: Warband's release identity names `e099051`, so the pins moved there
(above). Saga Online `1675cc2` passed its suite locally at the new pins (146
tests) and in CI:
[Tests 35410544956](https://github.com/ikamensh/saga-online/actions/runs/35410544956)
and [Website checks 35410544974](https://github.com/ikamensh/saga-online/actions/runs/35410544974).
The archive CI built and prepared as the service account is the one
activated, identical to the local one:
`953a83c60c1cb3bbfc2039509c622d63dc230f98ea18223ee5b9b70ca9fbfb2b` (324
files).

Checkpoints across the change (criterion 2): a two-seat match (seed 7,
64×48) played 150 s by the live release's authority, checkpointed, restored
by the candidate and played four more minutes with both seats' snapshots
taken along the way; and the same the other way round, for a rollback. Both
held, and the two checkpoints at 150 s hashed the same: with no tower and no
melee in them, the new rules had not yet come into play.

Before activation: the off-host backup `rooms-20260919T004748Z.sqlite3` (14
rooms, all retained Shardbound campaigns, SHA-256 `249e655e…`) and its
private rehearsal (all 27 retained seats resumed on the candidate). A fresh
backup just before activation, `rooms-20260919T005130Z.sqlite3`, had the same
bytes and resumed as well. `deploy_online.py deploy` prepared the archive as
the service account and activated it; the previous release `f3302078…`
stays at the `previous` pointer with its backups, and the website pointer did
not move.

After activation:
- Public health is `ok`.
- The served attestation names deployment `953a83c6…`, Warband `1b9880f` and
  the candidate's contract `5742acae…`.
- `deploy/smoke.py` passed create, join and order for all three games.
- `permessage-deflate` is negotiated through the public proxy
  (`server_max_window_bits=12`).
- Every retained seat resumed on the live server with its own token (14
  rooms, 28 seats, none failed).
- A three-seat Warband room filled in order, started with 3 of 3, and refused
  a client from before 0.3.8.
- The native Warband journey (create, room-code join, accepted gameplay,
  restart and rejoin against the public server) passed, a minute after the
  other checks for the server's four new rooms a minute. Its frames are under
  `docs/evidence/wb037-rollout/public/`, and I looked at them: the seat's own
  corner with the rest fogged and the painted gold mine, and after the rejoin
  the gatherers inside the mine.

The served attestation is the new
[`releases/server-baseline.json`](../releases/server-baseline.json). The
promotion of `1b9880f`'s publication ran at 00:50, before the activation,
and was refused as designed ("Candidate requires a different server
compatibility baseline").
