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

Acceptance recorded; the Warband merge is waiting for its branch's CI.
