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
