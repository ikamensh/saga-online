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
