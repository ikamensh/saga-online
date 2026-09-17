# WB-004 — Melee and renderer rollout

Started 2026-09-17. This is the release dependency of Warband WB-004; pause
backlog execution after that item is accepted. The shared server rollout below
is accepted; final public Warband publication checks follow.

Warband's melee presentation preserves the authoritative game fingerprint.
Its crowded-battle acceptance required the verified Saga2D 0.3.3 renderer
candidate. The publishing contract includes the exact engine/runtime lock,
so the shared server must adopt the same released engine before the new
Warband client is promoted. Keep the strict compatibility check intact.

## Acceptance before rollout

- Publish verified, immutable Saga2D artifacts only after engine/consumer
  checks, native pixels and the existing Warband frame-time gate pass.
- Deliberately align the three hosted games and Saga Online with that exact
  PyPI release, preserving Python 3.13.2, uv 0.12.10 and the Sagaforge pin.
  Require the Warband candidate's Windows/Mac native checks and full suites.
- Build the exact clean server inputs in isolated adjacent checkouts. Require
  Linux service-account preparation, three-game orders, checkpoint/restart,
  backup/rejoin and deployment exclusion through the existing CI workflow.
- Preserve the live configuration and an off-host SQLite backup. Rejoin the
  retained campaigns on a private copy using the prepared candidate. Keep the
  prior release and backup for rollback; do not change the website pointer
  during server activation.
- Activate the accepted archive through the existing installer. Verify health,
  exact live runtime attestation, public three-game create/join/orders/rejoin,
  and retained campaigns before recording the new server baseline.
- Merge the accepted Warband item through main-push publication and promotion;
  verify actual public Windows/Mac downloads before marking WB-004 done.

The stack's standing authorization applies. Use the
[deployment runbook](../deploy/README.md) and the previously accepted
[movement rollout procedure](warband-movement-rollout.md). SO-001 remains open:
for a stopped checkpoint use the same SQLite backup API under the service UID,
outside the hardened backup unit's read-only filesystem sandbox.

## Prepared engine and client

Saga2D 0.3.3 is published from `9a1a58c` / `v0.3.3`; engine/consumer tests,
installed-wheel native checks and fresh PyPI installation passed. Warband's
unchanged battle passes whole-run p95 15.58 ms. Its candidate `cac35b7` pins
that exact release, with native run `35241590924` awaiting acceptance.

The installed 0.3.2 → 0.3.3 package comparison changes only `__init__.py` and
`backends/pyglet_backend.py`. All authoritative Warband source hashes and all
other runtime versions match the live baseline. The new strict contract is
`99dac00a423c6660f2c30d604136c2f46dc2b463a95046026884de074d4333ce`.
The engine version is still aligned on the server before client publication.

Isolated Tribes `ddb9169` passes all 189 installed-PyPI tests. Tribes and
Shardbound alignment branches are server inputs; their published clients and
main checkouts retain their existing pins. Shardbound's 19 previously reproduced
failures are compared explicitly before making a server-only acceptance decision.
A fresh off-host live backup passes SQLite integrity and hash verification;
its private receipt is in `docs/evidence/melee-rollout/backup-receipt.json`.

Shardbound `68a5fac` completes **1,078 passing tests and the exact same 19
failed node IDs** as the previously recorded 0.3.1/0.3.2 baseline, in 341.70 s.
No failures are suppressed or assertions relaxed. Since the installed engine
changes only its renderer/version, accept this as a headless server input
subject to the independent packaged/live gates below. It is not a new
Shardbound client release or a claim that its full suite passes.

The first Warband 0.3.3 CI run exposed a package-format fixture that hard-coded
0.3.2 while reading the current lock. Correct that fixture to derive its valid
engine identity from the lock, retain strict production validation, and require
a new source-bound native run before server packaging.

The corrected Warband source is `cac35b7`; its 32 release CLI/HTTP tests pass
locally, and new native run **35241590924** is the only candidate recorded
in the server pins. The earlier failed/cancelled run is excluded. Full Linux
game and Windows/Mac package acceptance are still required before activation.

The exact isolated cohort passes all **135 Saga Online tests in 91.78 s**.
The off-host checkpoint contains four retained Shardbound campaigns; all four
must survive the private rehearsal and activation. Linux service-account
package acceptance and the live checks remain required.

## Accepted live server — 2026-09-17

Warband source `cac35b7` passes Linux Tests run **35241591056** (1,048 tests,
12 skips), and native run **35241590924** passes Windows, Mac and independent
archive validation. Saga Online source `a28623f` passes Linux run
**35243222879**, including the full suite, real restricted SSH, deployment
exclusion, service-account preparation, three-game orders, checkpoint/restart,
backup restore and unchanged-release retry. Website checks also pass.

The exact accepted archive is
`acb8cef212b94daad035a604dc6319fd9e9d025703f131e39202f213de53e082`
(6,679,612 bytes). Production preparation preserved the live service and site.
A private copy of the live backup successfully resumed all **four retained
Shardbound campaigns and seven saved seats**, preserving state and tokens.

After a stopped checkpoint, the existing installer activated that archive.
Public health and runtime attestation match its preparation receipt. Real
Warband smart-order checks pass: explicit ground targets, queued entity IDs,
invalid target rejection, omitted legacy targets and ownership rejection.
Downloaded frozen Mac clients for the existing Tribes and Shardbound releases
and the accepted Warband candidate pass public TLS create/join, orders and
private-seat rejoin; all eight Warband online checks pass. A fresh off-host
checkpoint passes SQLite integrity and preserves all four prior campaigns'
state and seat tokens. The website pointer and publication state are unchanged.

The live baseline is recorded in `releases/server-baseline.json`. The prior
server `99e28517d6170e0957c56c3b7de8eeebdcf7befeaf54ecd371d6de11354609f7`
remains installed at the `previous` pointer. Its stopped off-host checkpoint
has SHA-256 `b5eef9dd456f53430fb8a8aacf17fde9c5529c9afdd877646172486a4a343181`.
Private backups/configuration and the exact receipts are under the ignored
`docs/evidence/melee-rollout/` directory; no private seat tokens are committed.

This accepts the shared-server dependency of WB-004. Its public client release
must still complete automatic publication and Windows/Mac download checks.
