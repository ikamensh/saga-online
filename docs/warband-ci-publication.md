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

Retry acceptance: activating the same bytes with a newer promotion generation
must reverify the public site, advance the generation and retain the previous
distinct release as the rollback target. A repeated current release must never
replace that target with itself. Failed reverification preserves the accepted
state and rollback target. Exercise this through the actual activation CLI.
Verified by the new CLI regression and all 14 activation/offline operator checks:
both successful newer-generation verification and failed health checks retain
the previous distinct release. The helper and bundled upload path pass together.

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

## Promotion consumer acceptance, before implementation

The read-only consumer takes a producer run ID, immutable release ID and manifest
SHA-256, the current catalog, and a separately reviewed server baseline. It must:

- Read release/tag/workflow provenance from GitHub, require a successful native
  main build of that same commit, and independently download/recheck every
  public asset, both platforms' native/socket receipts and executable digests.
- Verify the candidate's complete compatibility contract against the reviewed
  baseline and the live server's attestation. A missing or mismatched baseline
  refuses promotion; desired pins or a matching game ID alone are insufficient.
- Compare the catalog's Warband source with the candidate through Git ancestry;
  reject older/divergent sources and older runs of the same source. Repeating
  the exact accepted release is harmless and cannot rebind its manifest.
- Produce a reviewable candidate catalog and promotion receipt only after all
  gates pass. Preserve every other game, server and site field. Use the exact
  accepted download bytes; never build or republish a game in this repo.
  Bind the receipt to the input bytes actually read, and refuse preparation if
  the catalog, baseline or previous receipt changes during download/verification.
- Exercise successful preparation, retry, stale/divergent sources, corrupted or
  incomplete downloads/receipts, and mismatched runtime/live baseline through
  the CLI with real temporary files, ZIPs and loopback HTTP services. These are
  protocol fixtures, not claims of native execution or a deployed baseline.

The later write-enabled workflow must serialize against the latest catalog,
commit its desired change for audit, activate through the existing transaction,
recheck server compatibility while holding the deployment lock, and verify the
public result. Consumer success alone does not satisfy the live publication gate.

## Independent release consumer

`tools/warband_promotion.py` prepares a candidate using the three dispatch
values, the current catalog and a reviewed server baseline:

```bash
uv run --project publishing --locked python tools/warband_promotion.py \
  --build-run-id BUILD_RUN_ID --release-id RELEASE_ID \
  --manifest-sha256 MANIFEST_SHA256 --catalog releases/catalog.json \
  --baseline SERVER_BASELINE_JSON --output dist/warband-promotion
```

The uppercase arguments are required values from the verified publisher and
reviewed server deployment, not supplied example releases. No production server
baseline has been created or accepted yet. GitHub API reads may use `GH_TOKEN`;
all public asset downloads and live attestation reads are unauthenticated.
Only HTTPS is accepted outside explicit loopback integration services.

The output contains `catalog.json`, `promotion.json` and all seven downloaded
release assets. Preparation independently verifies GitHub main/native provenance,
the immutable release and source ancestry, both native receipt archives and
the actual packaged executable hashes. It imports no producer or downloaded game
code. It replaces only Warband's catalog entry, retaining the other games and
server/site configuration. The receipt records both the input catalog digest
and the candidate digest so the later Git writer can reject a concurrent edit.
Input files are read once and checked again before the output becomes visible.

Record `promotion.json` with the accepted desired catalog. Pass that receipt as
`--previous-promotion` on subsequent runs. It binds an already accepted version
to its original release ID, build ID, source and manifest, while permitting
independent updates to other games. The `already_current` flag only describes
the desired catalog; it does not prove site activation. A failed activation
must still be retried and publicly verified. An existing output directory can
be reused only if every prepared file is identical; it is never overwritten.

The CLI integration suite uses real HTTP, ZIPs and temporary files to exercise
provenance rejection, stale/divergent source order, same-version retries,
download/evidence corruption, baseline mismatch and concurrent input edits.
`tools/warband_evidence.py` also accepts the actual downloaded native artifacts
from Warband producer `35149564980`; those are the native-execution evidence,
whereas test fixtures deliberately contain no runnable game executable.
The complete public-release preparation cannot run against that branch producer:
it has not been published as an immutable main release and there is no live
attested server baseline. Publication, compatibility-aware activation and the
write-enabled workflow remain unfinished.

Local verification: all 43 promotion CLI checks and the 28 isolated catalog,
site, activation and operator checks passed. Website checks now runs both sets.

## Desired catalog commit acceptance, before implementation

The Git writer consumes only a completed prepared promotion, a clean repository
checkout and the exact checkout commit used by preparation. It must validate
the candidate/receipt hashes against the current catalog, preserve all other
games and server/site facts, and commit only the Warband catalog change plus
its receipt. Another local edit or commit must cause an explicit failure.
A retry of an already committed identical release must leave Git history and
the original release receipt unchanged. A candidate marked already current
cannot introduce a catalog change.

Pushing is a separate explicit option, using an ordinary fast-forward push to
the existing main branch. Test successful commit/push and a concurrent remote
main advance against temporary bare Git repositories. A rejected push must
preserve the remote's newer catalog; the workflow should start again from that
head and rerun preparation. It must never force-push, automatically merge stale
catalogs or treat a desired Git commit as proof of successful site activation.

`tools/commit_warband_promotion.py` implements that step:

```bash
uv run --project publishing --locked python tools/commit_warband_promotion.py \
  --prepared dist/warband-promotion --repository . --expected-head CHECKOUT_COMMIT
```

The checkout must be clean and `CHECKOUT_COMMIT` must be the full Git commit
captured before preparation. The tool rechecks hashes, manifest identity and
scope, then commits only `releases/catalog.json` and
`releases/warband-promotion.json`. Retrying the same desired release keeps the
original receipt and commit. `--push` explicitly enables an ordinary push to
existing `origin/main`, after checking that remote main still names the expected
checkout. Git also rejects a concurrent advance during the push itself. If a
push is rejected after the local commit, that commit remains available for
inspection; restart the workflow from current main and prepare again. There is
no automatic merge or force-push and no site activation in this command.

The Git integration tests run entirely against temporary local/bare repos. A
real pre-push hook advances the competing repo after the writer's remote-head
check: the stale publication push is rejected, and the competing game's new
catalog remains intact. No live catalog commit or push has been made by this
tool. The production workflow, runtime attestation, deployment lock and final
public acceptance still need to be connected and verified before enabling it.

Local verification: all 11 Git integration checks passed; the complete isolated
publication suite passed 83 tests. The server-package test remains outside that
environment and is not claimed as passing. Workflow lint and stack Markdown
links also passed. The consumer and rollback changes already passed on Linux
in [Website checks 35154038265](https://github.com/ikamensh/saga-online/actions/runs/35154038265)
at `fbfccd4` (72 checks and a rebuilt seven-page preview). The new Git writer is
now included in that same branch workflow.

[Website checks 35154907841](https://github.com/ikamensh/saga-online/actions/runs/35154907841)
then passed on `21f31c48e1e879c9b01ee3494b46d5c84c11243e`: all 83 isolated
publication checks passed on Linux in 48.13 seconds, followed by the site build
and preview artifact upload. This is branch CI evidence, not production
publication or a verified server compatibility baseline.
