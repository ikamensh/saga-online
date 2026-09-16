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

[Website checks run 35145766820](https://github.com/ikamensh/saga-online/actions/runs/35145766820)
passed on `1f63106`, running the 28 isolated catalog, site, activation and offline
operator checks and producing the seven-page static preview artifact. This was
a branch check with read-only permissions; it did not publish the site.

## Authoritative runtime integration prerequisites

Warband candidate `2361f79cecf5a584562847bdc25e2be4d2f353c8` moves its server
entry point to `warband.authority:ONLINE` and embeds a static simulation-input
contract in every native release identity. Its compatibility digest is
`ffdfe856c27cf2c9d7f507d9e1caa54e631d41cdb283e367c2e08b954bd49524`:
ten authoritative game source files, Python 3.13.2, Saga2D 0.3.2, Pillow 12.3.0,
pyglet 2.1.16 and websockets 17.1. This describes the candidate's required
inputs; it is not evidence about the running server.

Before building the first server compatibility baseline, update this repo's
service, deployment checks and test registry strings together with that Warband
integration. Resolve the exact engine conflict normally: Warband and Tribes
require 0.3.2, while this repo and Shardbound currently require 0.3.1. Do not
silently ignore lockfiles or dependency metadata to construct the baseline.
Verify the packaged server's actual Python, installed dependency versions and
authoritative source bytes, then all three games' socket journeys outside the
source checkout. A live baseline needs the separately reviewed deployment,
room draining, backup/restore and public packaged-client checks.

Shardbound alignment candidate `cc070e3` is isolated on
`codex/warband-server-runtime`. Its full 0.3.2 suite produced 1,078 passes and
19 failures; all 19 also reproduce under 0.3.1. Its native verifier stops at the
same battle-victory assertion on both releases. The inspected engine diff only
changes the version string and Banner placement; the candidate has not been
merged or accepted. See [Shardbound's recorded acceptance findings](../../shardbound/docs/shardbound-release.md).
These findings must not be presented as a green client release or a verified
shared-server deployment.
