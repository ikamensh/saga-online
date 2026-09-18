# Fast simulation — Warband's source contract on the shared server

Started 2026-09-18 on Saga Online `0688e92`, the sixth rollout of the day,
after [WB-012](wb012-rollout.md). Warband main `6744934` carries the fast
simulation ([Warband's note](../../warband/docs/fast-simulation.md)): the tools
that play many matches run the simulation compiled by mypyc, with C twins of
a few loops, about ten times faster. The game, the online authority and this
server run the source as before, and every result is the same to the bit.
Warband's fingerprint and its nine-match bench digest do not move.

The simulation's sources changed all the same: constants marked `Final`,
owners narrowed before comparison, caches keyed on what they were computed
from, fewer allocations. So the authoritative contract moves in
`warband/mapgen.py`, `model.py`, `path.py`, `races.py`, `rules.py`,
`worker_ai.py` and `worker_knowledge.py`, and in nothing else.
`authority.py`, `settlement.py`, the packages and Python are unchanged. The
compiled simulation (`warband/fastsim.py`, `warband/_native`) is outside the
authority's import closure and never runs here. The lock records Warband's new
`dev` extra (mypy, setuptools) and nothing else; the exported server runtime
is unchanged. Saga2D 0.3.8, Tribes `4c13383`, Shardbound `b2cdcbe`, Sagaforge
`10f4d87`, Python 3.13.2 and uv 0.12.10 stay at their pins.

## Acceptance defined before rollout

1. Warband `6744934` has passed its Linux suite and its Windows and Mac
   native package checks on main; that native run (35400377983, number 61) is
   the one in the server pins. `tools/ci_compatibility.py` on it differs from
   the live contract (`3e1deac8…`) in the seven simulation sources above and
   in nothing else; the packages are unchanged.
2. Compatibility across the change, checked before activation: the same
   authority match played by the live release (`4e092a0`) and by the
   candidate writes byte-identical snapshots for both seats and identical
   checkpoints. A checkpoint the live release wrote restores on the candidate
   and plays on exactly as it does on the live release.
3. Saga Online's suite runs on clean adjacent checkouts at the new pins. CI
   builds and reverifies the immutable archive as the Linux service account,
   and the locally built archive is identical.
4. Before activation: a fresh, verified off-host backup of the live rooms and
   a private rehearsal that resumes every retained seat on the candidate.
5. Activation through the existing installer only; the previous release
   `3bf61237…` and the backup stay for rollback; the website pointer does not
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

Compatibility (criterion 2) was checked on the reference Mac before
activation. A two-seat match (seed 7, Hard against Master) ran four minutes
through `WarbandMatch` on both releases. At every 30 seconds, both seats'
snapshots and the checkpoint hashed the same. The checkpoint the live release
wrote at two minutes, restored on each release and played for four more
minutes, hashed the same at every sample too.

The first candidate, `d4e2e19` (native run 35398431469, number 60), failed its
Linux and Windows suites in one test. That test held the compiled fingerprint
to the recorded one, which is macOS's: glibc and the Windows runtime round a
few sines, cosines and arctangents differently in the last bit, the source's
as well as the compiled simulation's. `6744934` holds the compiled simulation
to the source on the machine that runs the test. Its simulation sources are
`d4e2e19`'s, so the compatibility check above stands.

**Accepted live server, 2026-09-18 22:33 UTC.** Warband `6744934` passed
[Tests 35400377943](https://github.com/ikamensh/warband/actions/runs/35400377943)
and [native package checks 35400377983](https://github.com/ikamensh/warband/actions/runs/35400377983)
(run number 61, Windows and Mac; the Windows job runs the whole suite, so the
compiled simulation matched the source there too). Its contract differs from
the live one in the seven simulation sources and in nothing else (packages
unchanged). Saga Online `736153b` passed
[Tests 35401750400](https://github.com/ikamensh/saga-online/actions/runs/35401750400)
and [Website checks 35401750395](https://github.com/ikamensh/saga-online/actions/runs/35401750395).
The archive CI built and prepared as the service account is the one
activated, identical to the local one:
`f3302078bb5359cbf3b2881188533bbab3d5791642258c67c7954ace7b18c33c` (324
files; the one more than before is `warband/fastsim.py`, which nothing on the
server imports).

Before activation: the off-host backup `rooms-20260918T215216Z.sqlite3` (13
rooms, SHA-256 `749e626b…`) and its private rehearsal (all 25 retained seats
resumed on the candidate). A fresh backup just before activation,
`rooms-20260918T223315Z.sqlite3`, had the same bytes, and its 25 seats all
resumed too. `deploy_online.py deploy` prepared the archive as the service
account and activated it at 22:33:47 UTC. The previous release `3bf61237…`
stays at the `previous` pointer with its backups, and the website pointer did
not move.

After activation:
- Public health is `ok`.
- The served attestation names deployment `f3302078…`, Warband `6744934` and
  the compatibility contract
  `fcdc63e6d7c4dad60fbe0cd3f4369778342c4d6d762c69918c105e131033e4b1`, the
  digest `tools/ci_compatibility.py` computes on the candidate checkout.
- `deploy/smoke.py` passed create, join and order for all three games.
- `permessage-deflate` is negotiated through the public proxy.
- Every retained seat resumed on the live server with its own token (13
  rooms, 25 seats, none failed).
- A three-seat Warband room filled in order, started with 3 of 3, and refused
  a client that says nothing of seats.
- The native Warband journey (create, room-code join, accepted gameplay,
  restart and rejoin against the public server) passed. Its frames are under
  `docs/evidence/fastsim-rollout/public/`, and I looked at them: the seat's
  own corner with the rest fogged, and after the rejoin the gatherers inside
  the mine, as in the earlier rollouts' frames. The first attempt met the
  server's four-rooms-a-minute limit, right after the other checks.

The served attestation is the new
[`releases/server-baseline.json`](../releases/server-baseline.json). The
promotion of `6744934`'s publication ran at 22:30, before the activation, and
was refused as designed ("Candidate requires a different server compatibility
baseline").
