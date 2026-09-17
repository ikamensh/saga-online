# WB-004 — Melee and renderer rollout

Started 2026-09-17. This is the release dependency of Warband WB-004; pause
backlog execution after that item is accepted. No deployment is claimed yet.

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
unchanged battle passes whole-run p95 15.58 ms. Its candidate `2bae3b2` pins
that exact release, with native run `35240528494` awaiting acceptance.

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
