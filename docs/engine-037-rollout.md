# WB-021, WB-029 to WB-033, S2D-015 and S2D-019 to S2D-021 — one rollout on Saga2D 0.3.7

Started 2026-09-18 on Saga Online `3d36a41`, a few hours after the
[0.3.5 rollout](engine-035-rollout.md). Two sessions had a server rollout
coming and agreed on one:

- **The 4K Windows report** (Warband WB-021, engine S2D-015, Saga2D 0.3.6):
  window sizes in desktop units and a fitted canvas made for the desktop.
  Client-side display code; nothing the server runs changes, but the engine
  version is part of Warband's compatibility contract.
- **The review's rules and network fixes** (Warband WB-029 to WB-033; engine
  S2D-019 to S2D-021, Saga2D 0.3.7 = 0.3.6 plus these): orders go to the
  running world, a seat's snapshot tells it the match and not the server's
  dice or the other seat's map, refusals are atomic, abandoned towers are
  inert; the online client asks for `permessage-deflate`, a realtime room
  publishes on its tick instead of on every order, a LAN peer drains its
  socket. These change `warband/authority.py`, `model.py`, `rules.py` and
  `settlement.py` and the room server's publishing, so the contract moves in
  files as well as in `packages.saga2d`.

The candidate is Warband main with both, Tribes and Shardbound on
`server-saga2d-0.3.7` (the pin and the lock only, from the 0.3.5 cohort
commits), Sagaforge `10f4d87`, Python 3.13.2 and uv 0.12.10 at their pins.

## Acceptance defined before rollout

1. The exact Warband main commit passes its Linux suite and its Windows and
   Mac native package checks; that native run is the one in the server pins.
   `tools/ci_compatibility.py` on it differs from the live contract in the
   four rule files and `packages.saga2d`, nothing else; the simulation
   fingerprint is the recorded one.
2. Tribes passes its whole suite on the installed 0.3.7; Shardbound fails
   exactly the node IDs recorded for it and nothing else.
3. Saga Online's suite runs on clean adjacent checkouts at the new pins; CI
   builds and reverifies the immutable archive as the Linux service account,
   and the locally built archive is identical.
4. Before activation: a fresh, verified off-host backup of the live rooms and
   a private rehearsal that resumes every retained seat on the candidate.
5. Activation through the existing installer only; the previous release
   `8b187785…` and the backup stay for rollback; the website pointer does not
   change during activation.
6. After activation: public health, the served attestation equal to the
   candidate's contract, the three-game smoke, every retained seat resumed on
   the live server, a native Warband online journey against the public server
   (it exercises orders reflected on the next tick and the per-seat
   snapshot), and `permessage-deflate` negotiated through the public proxy.
   Only then is the baseline recorded from the served attestation, the
   refused promotion dispatched again, and the public downloads checked.
7. The published Windows build is looked at on the 3840×2160 test desktop at
   200 % ([the test box](windows-test-box.md)): the window uses the desktop
   and the HUD is readable.

The stack's standing authorization applies; the
[deployment runbook](../deploy/README.md) gives the procedure.

## Status

**Cohort prepared, 2026-09-18 16:10 UTC.** Saga2D 0.3.7 is on PyPI (wheel
SHA-256 `31c93847cb9268e8fd22a0a20d9f16e135aec905291dbfde103301715c1c7d21`,
tag `v0.3.7` = engine `76cb7cb`; 0.3.6, wheel `c7b4139f…`, is its ancestor)
and passes the installed-distribution check from a fresh environment.
Tribes `8ff249c`: 189 passed. Shardbound `f857599`: 1,078 passed, 19 failed,
the failed node IDs identical to the recorded baseline. Warband on 0.3.7:
1,242 passed, the simulation fingerprint matches the recorded one. The
contract differs from the live one in `warband/authority.py`, `model.py`,
`rules.py`, `settlement.py` and `packages.saga2d` (0.3.5 to 0.3.7), nothing
else.

**Candidate green, its promotion refused as designed, 2026-09-18 16:25 UTC.**
Warband main `2e2dd88` passed [Tests 35366637939](https://github.com/ikamensh/warband/actions/runs/35366637939)
and [native package checks 35366638004](https://github.com/ikamensh/warband/actions/runs/35366638004)
(run number 51) on Windows and Mac; the display change had passed the native
checks on its branch before (35364770056). Main's
[publish 35368085005](https://github.com/ikamensh/warband/actions/runs/35368085005)
produced the immutable release and
[promotion 35368383355](https://github.com/ikamensh/saga-online/actions/runs/35368383355)
refused it with "Candidate requires a different server compatibility
baseline".

## Accepted live server — 2026-09-18

Saga Online `6f60434` passed [Tests 35368158377](https://github.com/ikamensh/saga-online/actions/runs/35368158377)
and [Website checks 35368158174](https://github.com/ikamensh/saga-online/actions/runs/35368158174).
The archive CI built is the one activated: local packaging at the same
commit with the pinned uv gives the identical release
`443319e92ded10c9e25a6114520ba4be27bb8b4292af20b43273b2860f6ae497` (315
files).

Before activation: the off-host backups `rooms-20260918T161127Z.sqlite3` and
`rooms-20260918T162728Z.sqlite3` (9 rooms, SHA-256 `c4ccd3f3…`, identical) and
the private rehearsal on both: all **17 seats of the 9 retained Shardbound
campaigns** resumed on the candidate, none failed. `deploy_online.py deploy`
prepared the archive as the service account and activated it at 16:27 UTC;
the previous release `8b187785…` stays at the `previous` pointer with its
backups.

After activation: public health `ok`; the served attestation names deployment
`443319e9…`, Warband `2e2dd88` and the compatibility contract
`9ab6e7ac51507f488b02ce24bc1c156ed7be532b1985c4ebb2fd8a8eca183595`, the same
digest `tools/ci_compatibility.py` computes on the candidate checkout;
`deploy/smoke.py` passed create, join and order for all three games;
`permessage-deflate` is negotiated through the public proxy; every retained
seat resumed on the live server with its own token (9 rooms, none failed:
`docs/evidence/engine-037-rollout/live-rejoin.log`); the native Warband
journey (create, room-code join, accepted gameplay, restart and rejoin
against the public server) passed, its frames under
`docs/evidence/engine-037-rollout/public/` looked at.

The served attestation is recorded as the new
[`releases/server-baseline.json`](../releases/server-baseline.json). The
refused promotion is dispatched again from its accepted native run; the
public download checks and the look at the published Windows build follow.
