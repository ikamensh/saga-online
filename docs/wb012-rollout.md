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

**Accepted live server, 2026-09-18 20:57 UTC.** Warband `4e092a0` passed
[Tests 35391932290](https://github.com/ikamensh/warband/actions/runs/35391932290)
and [native package checks 35391932264](https://github.com/ikamensh/warband/actions/runs/35391932264)
(run number 59, Windows and Mac) on main. Its contract differs from the live
one in `warband/authority.py`, `warband/mapgen.py` and `packages.saga2d`
(0.3.7 → 0.3.8) and in nothing else. The cohort held on 0.3.8 (criterion 2,
recorded under Saga2D's S2D-011 at `d677391`): Tribes 189 passed, Shardbound
exactly its 19 recorded failures with 1,078 passing, Saga2D 416 with its
installed-distribution check and a fresh install from PyPI. Saga Online
`8f5a42d` passed [Tests 35393905630](https://github.com/ikamensh/saga-online/actions/runs/35393905630)
and [Website checks 35393905629](https://github.com/ikamensh/saga-online/actions/runs/35393905629);
the archive CI built and prepared as the service account is the one
activated, identical to the local one:
`3bf61237afe1b40257df294658710858b281ac50971cc0fc403270bbbb0488e7` (323 files).

Before activation: the off-host backup `rooms-20260918T203641Z.sqlite3` (14
rooms, SHA-256 `c6452e96…`) and its private rehearsal (all 27 retained seats
resumed on the candidate), then a fresh one just before activation,
`rooms-20260918T205649Z.sqlite3` (12 rooms, `938eb79a…`), whose 23 seats all
resumed too. `deploy_online.py deploy` prepared the archive as the service
account and activated it at 20:57 UTC; the previous release `90a73f0e…` stays
at the `previous` pointer with its backups, and the website pointer did not
move.

After activation: public health `ok`; the served attestation names deployment
`3bf61237…`, Warband `4e092a0`, Saga2D 0.3.8 and the compatibility contract
`3e1deac86b3ae8dfc738d16e2cf35e7df0207fb84769c23272235e73d148c264`, the digest
`tools/ci_compatibility.py` computes on the candidate checkout.
`deploy/smoke.py` passed create, join, order and resume for all three games,
speaking the hello of a client from before 0.3.8 (no `seats`): old clients keep
playing in rooms of two. `permessage-deflate` is negotiated through the public
proxy; every retained seat resumed on the live server with its own token (12
rooms, 23 seats, none failed); the native Warband journey (create, room-code
join, accepted gameplay, restart and rejoin against the public server) passed,
its frames under `docs/evidence/wb012-rollout/public/` looked at: the seat's
own corner and the rest fogged, and after the rejoin at 00:07 the gatherers
inside the mine, as in the previous two rollouts' frames.
[`tools/verify_room_seats.py`](../tools/verify_room_seats.py) opened a
three-seat Warband room on the public server: it filled in order, started with
3 of 3 present, each seat was sent only its own units at home, and a client
that declares no seats was refused with "This match has 3 seats. Update your
game client to play it." The served attestation is the new
[`releases/server-baseline.json`](../releases/server-baseline.json). The
promotion of `4e092a0`'s publication ran at 20:55, before the activation, and
was refused as designed: the candidate needed the new baseline.
