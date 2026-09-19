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

Acceptance recorded; the Warband merge is waiting for its branch's CI.
