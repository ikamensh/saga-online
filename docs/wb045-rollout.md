# WB-045 — The ogres' armour on the shared server

Started 2026-09-19 on Saga Online `b613cc0`, after
[WB-037](wb037-rollout.md). Warband's WB-045 halves the ogres' armour penalty
(−2 to −1), which lifts the orcs from 41% to 45% of Master-against-Master
matches (Warband's `BACKLOG.md` and `docs/balance.md`). Races are rules, so
the authoritative contract moves in `warband/races.py` and in nothing else.
The live release and the candidate play a match with an ogre in it
differently; a checkpoint written by either restores on the other, since the
ogre's armour is read from the table and not saved. Saga2D 0.3.8, Tribes
`4c13383`, Shardbound `b2cdcbe`, Sagaforge `e099051`, Python 3.13.2 and uv
0.12.10 stay at their pins.

## Acceptance defined before rollout

1. The Warband main commit that merges WB-045 has passed its Linux suite and
   its Windows and Mac native package checks; that native run is the one in
   the server pins. `tools/ci_compatibility.py` on it differs from the live
   contract (`5742acae…`) in `warband/races.py` and in nothing else; the
   packages are unchanged.
2. A checkpoint the live release (`1b9880f`) wrote restores on the candidate
   and plays on, and the reverse, for a rollback; the rehearsal below covers
   every retained seat.
3. Saga Online's suite runs on clean adjacent checkouts at the new pins. CI
   builds and reverifies the immutable archive as the Linux service account,
   and the locally built archive is identical.
4. Before activation: a fresh, verified off-host backup of the live rooms and
   a private rehearsal that resumes every retained seat on the candidate.
5. Activation through the existing installer only; the previous release
   `953a83c6…` and the backup stay for rollback; the website pointer does not
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

**Accepted live server, 2026-09-19 03:08 UTC.** Warband `6ad2779` (the merge
of WB-045's `a6d22f0`) passed
[Tests 35416900214](https://github.com/ikamensh/warband/actions/runs/35416900214)
and [native package checks 35416900239](https://github.com/ikamensh/warband/actions/runs/35416900239)
(run number 86, Windows and Mac). Its contract,
`3e324a4fa4174d9c594730288a29c935f277201c9edae0dcffefe2394534e62e`, differs
from the live one in `warband/races.py` and in nothing else (packages,
Python and registry unchanged). The saga-online lock needed no change. Saga
Online `a8cfa9d` passed its suite locally at the new pins (146 tests) and in
CI: [Tests 35417443472](https://github.com/ikamensh/saga-online/actions/runs/35417443472)
and [Website checks 35417443367](https://github.com/ikamensh/saga-online/actions/runs/35417443367).
The archive CI built and prepared as the service account is the one
activated, identical to the local one:
`db6c46818e4d5e7414a1a564f595f764230b9d88d50639180c5820142f8d047e` (324
files).

Checkpoints across the change (criterion 2): the same two-seat match (seed 7,
64×48) as in the WB-037 rollout, played 150 s by the live release's authority,
restored by the candidate and played four more minutes, and the other way
round; both held. A unit's save carries no armour (its keys are position,
hit points, orders and work), so an ogre saved by either release takes the
armour of the one that restores it.

Before activation: the off-host backup `rooms-20260919T030716Z.sqlite3` (15
rooms, SHA-256 `293bddc5…`) and its private rehearsal (all 30 retained seats
resumed on the candidate). `deploy_online.py deploy` prepared the archive as
the service account and activated it at 03:07 UTC; the previous release
`953a83c6…` stays at the `previous` pointer with its backups, and the website
pointer did not move.

After activation:
- Public health is `ok`.
- The served attestation names deployment `db6c4681…`, Warband `6ad2779` and
  the candidate's contract `3e324a4f…`.
- `deploy/smoke.py` passed create, join and order for all three games.
- `permessage-deflate` is negotiated through the public proxy.
- Every retained seat resumed on the live server with its own token (15
  rooms, 30 seats, none failed).
- A three-seat Warband room filled in order, started with 3 of 3, and refused
  a client from before 0.3.8.
- The native Warband journey (create, room-code join, accepted gameplay,
  restart and rejoin against the public server) passed, a minute after the
  other checks. Its frames are under `docs/evidence/wb045-rollout/public/`,
  and I looked at them: the seat's own corner, an orc one this time, with its
  hall, peons and the painted mine, and the rest fogged.

The served attestation is the new
[`releases/server-baseline.json`](../releases/server-baseline.json). The
promotion of `6ad2779`'s publication ran at 03:00, before the activation,
and was refused as designed.
