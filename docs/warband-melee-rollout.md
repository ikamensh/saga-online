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
