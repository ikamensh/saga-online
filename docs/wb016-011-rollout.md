# WB-016 and WB-011 — the campaign and per-seat snapshots on the shared server

Started 2026-09-18 on Saga Online `47c803d`, the fourth rollout of the day
after [engine 0.3.5](engine-035-rollout.md), [engine 0.3.7](engine-037-rollout.md)
and [the balance rules](balance-rollout.md). Ilya adopted Warband's Thornwood
campaign (WB-016) and asked for the online items now; the first of them is
WB-011: a seat is sent the match as it may know it, not the whole world. Both
are on Warband main at `89a6587` (merges `df3ef1c` and `89a6587`; Warband's
`BACKLOG.md` WB-016 and WB-011). The campaign adds `World.scripted` and
`clear_player`, WB-011 filters `WarbandMatch.snapshot` per seat and adds
`World.shot_mark`/`shot_ground`, so the authoritative contract moves in
`warband/model.py` and `warband/authority.py` and nothing else; the simulation
fingerprint does not move. The other Warband sessions were asked first: the
backlog session has nothing landing, and the speed work on `fast-sim` (which
also moves the contract) will take its own rollout once it is done. Saga2D
0.3.7, Tribes `8ff249c`, Shardbound `f857599`, Sagaforge `10f4d87`, Python
3.13.2 and uv 0.12.10 stay at their pins.

## Acceptance defined before rollout

1. Warband `89a6587` has passed its Linux suite and its Windows and Mac
   native package checks on main; that native run is the one in the server
   pins. `tools/ci_compatibility.py` on it differs from the live contract
   (`3892c8b2…`) in `warband/authority.py` and `warband/model.py` and in
   nothing else; the packages are unchanged.
2. Compatibility across the change, checked before activation: snapshots the
   candidate writes load in the previous release's client (Warband `faed307`,
   live as 0.2.30) for both seats, and a checkpoint the previous server wrote
   restores on the candidate and plays on (it carries no record of who saw
   what, so its last five seconds of events are told to both seats once).
3. Saga Online's suite runs on clean adjacent checkouts at the new pins; CI
   builds and reverifies the immutable archive as the Linux service account,
   and the locally built archive is identical.
4. Before activation: a fresh, verified off-host backup of the live rooms and
   a private rehearsal that resumes every retained seat on the candidate.
5. Activation through the existing installer only; the previous release
   `a38f8889…` and the backup stay for rollback; the website pointer does not
   change during activation.
6. After activation: public health, the served attestation equal to the
   candidate's contract, the three-game smoke, every retained seat resumed on
   the live server, a native Warband online journey against the public
   server, `permessage-deflate` still negotiated through the proxy. Only then
   is the baseline recorded from the served attestation, the refused
   promotion dispatched again and the public downloads checked; their online
   smoke now also checks that the guest is not sent the creator's worker.

`tools/verify_warband_remote_ai.py` (manual, not part of this rollout) judged
the remote AI's progress from its units, buildings and orders in the human's
snapshot; after WB-011 a human is sent only what it sees, so the verifier now
judges it from what scouting shows (buildings beyond the starting hall, units
beyond the starting peasants).

The stack's standing authorization applies; the
[deployment runbook](../deploy/README.md) gives the procedure.

## Status

Compatibility (criterion 2) checked on the reference Mac before activation:
the previous client ran its network scene over the candidate's snapshots of
both seats (the footman in sight sent without its orders, nothing at the
rival's home), and a checkpoint from the previous server restored and played
on with each seat's snapshot filtered.
