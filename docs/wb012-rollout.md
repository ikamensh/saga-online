# WB-012 — rooms of three and four humans, on Saga2D 0.3.8

Started 2026-09-18 on Saga Online `e27cde9`, the fifth rollout of the day and
the second of the evening, after [the campaign and per-seat snapshots](wb016-011-rollout.md).
Ilya asked for Warband's online items now; WB-012 brings three and four humans
into one room. The room server's two seats became as many as the game says,
with a hook for which seats must be present (Saga2D's S2D-011, released as
**0.3.8**: [PyPI](https://pypi.org/project/saga2d/0.3.8/), tag `v0.3.8`, wheel
SHA-256 `0f79d1c7…`, sdist `333987cb…`). Warband takes a `players` room
option, resigning becomes an online order, and a player who is out may leave
without pausing the rest. Warband main `4e092a0` carries it, pinned to 0.3.8.

The server runs one engine for the three games it hosts, so the cohort moves
together. Tribes `server-saga2d-0.3.8` (`4c13383`) and Shardbound
`server-saga2d-0.3.8` (`b2cdcbe`) carry the pin and the lock only, from the
0.3.7 cohort commits. Their rooms stay two-seat, and a client from before
0.3.8 keeps playing in them: the protocol is unchanged, and only a room larger
than a client says it handles refuses that client, with an update message.
Sagaforge `10f4d87`, Python 3.13.2 and uv 0.12.10 stay at their pins.

## Acceptance defined before rollout

1. Warband `4e092a0` has passed its Linux suite and its Windows and Mac
   native package checks on main; that native run is the one in the server
   pins. `tools/ci_compatibility.py` on it differs from the live contract
   (`6d5ed336…`) in `warband/authority.py`, `warband/mapgen.py` and
   `packages.saga2d` (0.3.7 → 0.3.8), and in nothing else.
2. Tribes passes its whole suite on the installed 0.3.8 (189); Shardbound
   fails exactly the 19 node IDs recorded for 0.3.7 and nothing else (1,078
   pass). Saga2D's own suite, its installed-distribution check and a fresh
   install from PyPI pass.
3. Saga Online's suite runs on clean adjacent checkouts at the new pins; CI
   builds and reverifies the immutable archive as the Linux service account,
   and the locally built archive is identical.
4. Before activation: a fresh, verified off-host backup of the live rooms and
   a private rehearsal that resumes every retained seat on the candidate.
5. Activation through the existing installer only; the previous release
   `90a73f0e…` and the backup stay for rollback; the website pointer does not
   change during activation.
6. After activation: public health, the served attestation equal to the
   candidate's contract, the three-game smoke, every retained seat resumed on
   the live server, a native Warband online journey against the public
   server, `permessage-deflate` still negotiated through the proxy, and a
   three-seat Warband room on the public server that fills, starts, and
   refuses a client that says nothing of seats. Only then is the baseline
   recorded, the refused promotion dispatched again and the public downloads
   checked.

The stack's standing authorization applies; the
[deployment runbook](../deploy/README.md) gives the procedure.

## Status
