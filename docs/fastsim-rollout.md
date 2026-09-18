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
