# WB-026 / S2D-018 — Engine 0.3.5 on the shared server

Started 2026-09-18 on Saga Online `bdb0423`. Warband's builds get their own
icon (WB-026) through the engine's packaging recipe (S2D-018, Saga2D 0.3.5).
Nothing the server runs changes: 0.3.4 made the mock backend derive its scale
from the window and 0.3.5 adds the icon to `saga2d.packaging`; the room
server, the protocol and Warband's authoritative sources are byte for byte
what the live bundle `58f75c42…` runs. The engine version is nevertheless
part of Warband's compatibility contract, so the publication gate refuses the
client until the shared server is built on the same release, and the server
hosts three games on one engine version. The candidate is Warband main at the
`icon` branch's head, with Tribes `46189a8` and Shardbound `e900366`
(`server-engine-035` branches: the pin and the lock only); Sagaforge stays at
`10f4d87`, Python 3.13.2 and uv 0.12.10 at their pins.

## Acceptance defined before rollout

1. The exact Warband main commit passes its Linux suite and its Windows and
   Mac native package checks, the first builds whose `verify` requires the
   executable and the bundle to carry the converted icon; that native run is
   the one recorded in the server pins. The simulation fingerprint and the
   authoritative file hashes are unchanged from the live contract; only
   `packages.saga2d` moves, 0.3.3 to 0.3.5.
2. Tribes passes its whole suite on the installed 0.3.5; Shardbound fails
   exactly its 19 recorded node IDs and nothing else (a server input, not a
   client release, as in the melee rollout).
3. Saga Online's suite runs on clean adjacent checkouts at the new pins; CI
   builds and reverifies the immutable archive as the Linux service account.
4. Before activation: a fresh, verified off-host backup of the live rooms and
   a private rehearsal that resumes every retained seat on the candidate.
5. Activation through the existing installer only; the previous release
   `58f75c42…` and the backup stay for rollback; the website pointer does not
   change during activation.
6. After activation: public health, the served attestation equal to the
   candidate's contract, the three-game smoke, every retained seat resumed on
   the live server, and a native Warband online journey against the public
   server. Only then is the baseline recorded from the served attestation,
   the refused promotion dispatched again, and the public downloads checked;
   the downloaded Mac app must show Warband's icon.

The stack's standing authorization applies; the
[deployment runbook](../deploy/README.md) and the
[rules rollout](warband-rules-rollout.md) give the procedure.

## Status

**Cohort prepared, 2026-09-18 10:30 UTC.** Saga2D 0.3.5 is on PyPI (wheel
SHA-256 `6374965477152dc76a496ca38cd0b83c74d75111f2797fe2ac23461712557de2`,
engine Tests 35333175476) and passes the installed-distribution check from a
fresh environment. Tribes `46189a8`: 189 passed. Shardbound `e900366`: 1,078
passed, 19 failed, the failed node IDs identical to the recorded baseline
(`docs/evidence/engine-0.3.5/failed-ids.json` in that checkout against
`engine-0.3.3/baseline-failed-ids.json`). Warband on 0.3.5: 1,192 passed, the
simulation fingerprint matches the recorded one.

**Candidate green, its promotion refused as designed, 2026-09-18 11:14 UTC.**
Warband main `dbd8bed` passed [Tests 35337133332](https://github.com/ikamensh/warband/actions/runs/35337133332)
and [native package checks 35337133223](https://github.com/ikamensh/warband/actions/runs/35337133223)
(run number 46) on Windows and Mac: the first builds whose `verify` requires
the executable and the bundle to carry the converted icon. The same commit
had passed both on its branch first (35334774625, 35334774501), and the
Windows artifact was inspected: the executable and the Inno Setup installer
hold all seven images of the converted `.ico` byte for byte, and the
conversion on the Windows runner equals the one on the reference Mac. Main's
[publish 35338448502](https://github.com/ikamensh/warband/actions/runs/35338448502)
produced the immutable release and
[promotion 35338620671](https://github.com/ikamensh/saga-online/actions/runs/35338620671)
refused it with "Candidate requires a different server compatibility
baseline". The contract differs from the live one in `packages.saga2d` alone
(0.3.3 to 0.3.5); the authoritative file hashes are identical.

## Accepted live server — 2026-09-18

Saga Online `0885642` passed [Tests 35338500304](https://github.com/ikamensh/saga-online/actions/runs/35338500304)
and [Website checks 35338500334](https://github.com/ikamensh/saga-online/actions/runs/35338500334).
The archive CI built is the one activated: local packaging at the same
commit with the pinned uv gives the identical release
`8b1877852198f763384f933888e219380e7498994972f7b54167fc6a7834ef85` (315
files; the one new file is `saga2d/packaging/icon.py`).

Before activation: the off-host backups `rooms-20260918T102915Z.sqlite3` and
`rooms-20260918T111751Z.sqlite3` (8 rooms, SHA-256 `7a102a4e…`, identical, so
the store had not changed) and the private rehearsal on both: all **15 seats
of the 8 retained Shardbound campaigns** resumed on the candidate, none
failed. `deploy_online.py deploy` prepared the archive as the service account
and activated it at 11:18 UTC; the previous release `58f75c42…` stays at the
`previous` pointer with its backups.

After activation: public health `ok`; the served attestation names deployment
`8b187785…`, Warband `dbd8bed` and the compatibility contract
`68d01092abf96568791c974de727622969f1683c52e0ecdef7cca5436e49b08f`, the same
digest `tools/ci_compatibility.py` computes on the candidate checkout;
`deploy/smoke.py` passed create, join and order for all three games; every
retained seat resumed on the live server with its own token (8 rooms, none
failed: `docs/evidence/engine-035-rollout/live-rejoin.log`); the native
Warband journey (create, room-code join, accepted gameplay, restart and
rejoin against the public server) passed, its frames under
`docs/evidence/engine-035-rollout/public/` looked at.

The served attestation is recorded as the new
[`releases/server-baseline.json`](../releases/server-baseline.json). The
refused promotion is dispatched again from its accepted native run; the
public download checks follow.

**Promotion accepted, public downloads checked, 2026-09-18 11:22 UTC.**
[Promotion 35339144196](https://github.com/ikamensh/saga-online/actions/runs/35339144196),
dispatched again from native run 35337133223 (release 391412408, manifest
`e7891120…`), was accepted against the new baseline and published the catalog
for Warband 0.2.21 (`dd2f496`); the site offers the 0.2.21 downloads.
[Public download checks 35339235957](https://github.com/ikamensh/saga-online/actions/runs/35339235957)
passed on Windows and macOS. The Mac app downloaded from the public link names
`icon.icns` in `CFBundleIconFile`, holds the converted file (SHA-256
`dc6b816b…`, the one the local build produced) and shows Warband's shield in
Finder. This completes the rollout; Tribes' and Shardbound's published
clients are unchanged and keep working against the shared server (the smoke
and the retained seats above).
