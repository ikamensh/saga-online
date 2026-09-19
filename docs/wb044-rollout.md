# WB-044 — Armourless frames on the shared server

Started 2026-09-19 on Saga Online `cec08d1`, after
[WB-041](wb041-rollout.md). Warband's merge `f8ba0eb` carries WB-039 and
WB-044 (Warband's `BACKLOG.md` record `a8951a7`). WB-044 is the rules change:
`World.armor_of` gives a building still going up no armour, so peasants can
pull a tower frame down, and the "construction", "built" and "trained" events
now name the building's or unit's type (`target_type`). Every AI sends up to
eight peasants at an enemy tower frame near its hall or mine, but the brains
are not part of the authoritative contract. WB-039 (a quieter selection cue,
at most once in 30 s) is client-only. So the contract moves in
`warband/sim/model.py` and in `warband/sim/rules.py`, whose change is one
docstring line, and in nothing else. The live release and the candidate play
a match in which a frame is struck differently. A building's save carries
`done` and its progress, not its armour, so a checkpoint written by either
restores on the other and the frame takes the armour of the one that restores
it. Saga2D 0.3.8, Tribes `4c13383`, Shardbound `b2cdcbe`, Sagaforge
`e099051`, Python 3.13.2 and uv 0.12.10 stay at their pins.

## Acceptance defined before rollout

1. The Warband main commit that merges WB-044 has passed its Linux suite and
   its Windows and Mac native package checks; that native run is the one in
   the server pins. `tools/ci_compatibility.py` on it differs from the live
   contract (`c7462b67…`) in `warband/sim/model.py` and
   `warband/sim/rules.py` and in nothing else; the packages, Python and
   registry are unchanged.
2. A checkpoint the live release (`62e4970`) wrote, holding a building still
   going up, restores on the candidate and plays on, and the reverse, for a
   rollback; the rehearsal below covers every retained seat.
3. Saga Online's suite runs on clean adjacent checkouts at the new pins. CI
   builds and reverifies the immutable archive as the Linux service account,
   and the locally built archive is identical.
4. Before activation: a fresh, verified off-host backup of the live rooms and
   a private rehearsal that resumes every retained seat on the candidate.
5. Activation through the existing installer only; the previous release
   `3e3dfda8…` and the backup stay for rollback; the website pointer does not
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

Warband `f8ba0eb` failed its fast tier: WB-039's new selection test took
7.92 s against the 3 s budget
([Tests 35428559762](https://github.com/ikamensh/warband/actions/runs/35428559762)).
The rollout stopped there. The promotion of `f8ba0eb`'s publication
([35428998314](https://github.com/ikamensh/saga-online/actions/runs/35428998314))
was refused as designed, since its contract is not the live one. Warband
`dc45c0b` changes that test file alone and passed
[Tests 35429071580](https://github.com/ikamensh/warband/actions/runs/35429071580)
and [native package checks 35429071696](https://github.com/ikamensh/warband/actions/runs/35429071696)
(run number 94, Windows and Mac). Its contract,
`471b8f18058857e698d0d467a4e2bbf1bc6c3acfe35f5c01709e6f3ef05584e8`, differs
from the live one in `warband/sim/model.py` and `warband/sim/rules.py` and in
nothing else (packages, Python and registry unchanged). The saga-online lock
needed no change.

Checkpoints across the change (criterion 2): a two-seat match (seed 7,
64×48, a Medium brain on each seat) played 3,000 steps by the live release's
authority (`62e4970`), its checkpoint restored by the candidate and played
4,800 steps more, and the other way round. Both held. Each checkpoint held a
farm still going up (`done` false, progress 2.15, 70 of 400 hp). On restore,
both seats' snapshots and the checkpoint itself hashed the same as the ones
written, and the frame wore the armour of the release that restored it: 2 on
the live release, 0 on the candidate. Each release also restored its own
checkpoint to the same world.
