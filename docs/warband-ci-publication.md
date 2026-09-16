# Warband CI publication

WB-002 is in progress on `codex/warband-publishing`, beginning at `c33c195`.
The acceptance criteria and cross-repository decisions are recorded before
implementation in [Warband's CI publication plan](../../warband/docs/ci-publication.md).

Saga Online's part is release validation, compatibility-gated catalog/site
promotion, stale-run rejection, atomic activation and tested rollback. It must
preserve other games' downloads and remain independent of room-server activation.
Local test servers and temporary site roots establish the failure/retry behavior;
the real GitHub and hosted journey is still required before WB-002 can be done.

No production activation or credential change has happened as part of this item.

## Isolated site checks

`publishing/pyproject.toml`, `.python-version` and `uv.lock` define the website
environment independently of the server and game checkouts. Python 3.13.2,
Saga2D 0.3.2 (for its bundled font) and Pillow 12.3.0 are pinned; the lock records
transitive dependencies and hashes. The read-only Website checks workflow uses
uv 0.12.10, runs catalog/site integration checks, renders the complete site and
retains it as a CI preview artifact. It does not publish the artifact.

Local verification: 15 existing catalog/site tests passed in this environment.
The separate server environment still needs deliberate engine/game alignment
before a server rollout; these checks make no claim about that environment.

## Static activation transaction

`deploy/activate_site.py` is an offline-tested activation entry point. It takes
an explicitly named site root, candidate source, expected current release and
monotonic promotion generation. It stages immutable files, serializes activation
with a filesystem lock, swaps the current symlink atomically, checks every
served file and `/healthz`, and retains the previous release. Failed public
acceptance restores the prior pointer and publication state. A durable journal
allows the next invocation to recover an interrupted activation.

Six CLI integration checks use temporary roots and real loopback HTTP servers:
successful activation/retry, wrong public bytes, unhealthy server, stale/rebound
promotion, concurrent publishers, and killing the publisher after its pointer
swap followed by successful recovery. These checks are part of Website checks.

The operator's `site` command now packages this helper and invokes it through
`install_site.sh`. `--expected-site` and `--site-generation` are mandatory and
validated before opening credentials. The former unprotected symlink swap and
three-release pruning have been removed. An integration check extracts the
actual upload archive, runs its bundled helper outside the checkout and verifies
the served files; the offline deployment and site suites pass 28 tests. The
server-package test is deliberately outside the isolated publishing environment.

This wiring has not been deployed. Server compatibility, candidate-source order,
scoped CI remote access, the caller's promotion generation and the promotion
workflow still need the remaining WB-002 implementation and rollout verification.
No live state was changed.
