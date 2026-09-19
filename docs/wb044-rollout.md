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

**Accepted live server, 2026-09-19 07:50 UTC.** Saga Online `bccc21e`
passed its suite locally at the new pins (149 tests) and in CI:
[Tests 35429626339](https://github.com/ikamensh/saga-online/actions/runs/35429626339)
and [Website checks 35429626341](https://github.com/ikamensh/saga-online/actions/runs/35429626341).
The archive CI built and prepared as the service account is the one
activated, identical to the local one:
`2457e36b2a705908deff91d24530798d7c967850702b0d99af249032ed70a2f3` (333
files).

Before activation: the off-host backup `rooms-20260919T073645Z.sqlite3` (17
rooms, SHA-256 `72780615…`) and its private rehearsal. All 34 retained
seats, in 17 Shardbound rooms, resumed on the candidate.
`deploy_online.py deploy` prepared the archive as the service account and
activated it at 07:37 UTC. The previous release `3e3dfda8…` stays at the
`previous` pointer with its backups, and the website pointer
(`112b0d7f…`, set at 05:14) did not move.

After activation:
- `/healthz` is `ok`.
- The served attestation names deployment `2457e36b…`, Warband `dc45c0b`,
  the registry `warband.online.authority:ONLINE` and the candidate's
  contract `471b8f18…`.
- `deploy/smoke.py` passed create, join and order for all three games.
- `permessage-deflate` is negotiated through the public proxy.
- All 34 retained seats resumed on the live server with their own tokens.
- A three-seat Warband room filled in order, started with 3 of 3, and
  refused a client from before 0.3.8.
- The native Warband journey (create, room-code join, accepted gameplay,
  restart and rejoin against the public server) passed. Its first two tries,
  straight after the other checks, met the server's "Too many new rooms"
  limit; the third, a few minutes later, passed. Its frames are under
  `docs/evidence/wb044-rollout/public/`, and I looked at them: the elf
  seat's own corner with its hall, gatherers and the painted mine, the rest
  fogged, and the same match after the rejoin.

The served attestation is the new
[`releases/server-baseline.json`](../releases/server-baseline.json). The
promotion of `dc45c0b`'s publication
([35429605384](https://github.com/ikamensh/saga-online/actions/runs/35429605384))
ran at 07:32, before the activation, and was refused as designed.

**Promotion accepted, public downloads checked, 2026-09-19 07:52 UTC.**
[Promotion 35430041515](https://github.com/ikamensh/saga-online/actions/runs/35430041515),
dispatched again for release `391983618` (native run 35429071696, manifest
`fbd40ada…`) once the baseline had moved, was accepted and published the
catalog for Warband 0.2.69 (`0850984`). Warband `75dc68f` (WB-038, the
painted gold mine, art only) had meanwhile published release `391985632`
(native run 35429309561) with the same contract, `471b8f18…`; its promotion
ran at 07:40, two minutes before the baseline moved, and was refused. Dispatched
again, [35430108549](https://github.com/ikamensh/saga-online/actions/runs/35430108549)
first failed on a GitHub artifact upload timeout, then passed on rerun and
published the catalog for Warband 0.2.70 (`391a0f0`).
[Public download checks 35430293396](https://github.com/ikamensh/saga-online/actions/runs/35430293396)
passed on Windows and macOS for 0.2.70. This completes the rollout. Warband's
next main, `a2212f5` (WB-052), changes `warband/sim/model.py` and `rules.py`
again (contract `c51d9e27…`) and needs its own rollout.
