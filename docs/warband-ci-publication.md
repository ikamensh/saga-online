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

## Running-server attestation acceptance, before implementation

The deployment launcher must verify the package's recorded source inventory,
actual Python and dependency versions before importing game registries or
accepting connections. It must reject changed/missing/extra source files,
unsupported manifests, a different Python or package version, and a Warband
contract that does not describe those actual inputs. The package builder must
record clean exact game source commits, the engine release and locked runtime;
the installer must bind the deployment identifier to the uploaded archive hash.

The same process that owns the game sockets must serve
`/server-compatibility.json` with no caching. It reports the deployment identifier,
public endpoint, actual protocol and verified Warband source/runtime contract.
A static file written by the website is insufficient. Health, normal game
traffic, SIGTERM shutdown and final checkpoint flushing must keep working.
Game registries are Tribes, Warband's new authority and Shardbound; no game rules
move into the launcher or change as part of attestation.

First verify the deployment interface with real subprocess/HTTP/WebSocket and
checkpoint tests using tiny game fixtures. Then build the actual package from
the explicitly aligned candidate stack, launch away from its checkouts, verify
the attestation against the accepted Warband native identity and complete every
game's socket journey, including restart/rejoin. Fixtures alone cannot establish
the three-game release's compatibility. Shared locking, room draining,
backup/restore, approved activation and public packaged-client checks remain
required after this startup gate; a local attestation is not a live baseline.

The startup gate is implemented in `deploy/runtime.py` and `deploy/server.py`.
Eleven subprocess checks pass: all three registered fixture games accept real
orders alongside an uncached JSON attestation; changed/missing/extra source,
Python/dependency mismatch and a broken contract refuse startup before opening
the room store; all three fixture games retain their last accepted order and
private seats through SIGTERM and restart. The launcher checks the full packaged
source inventory, resolves Saga2D from that package and uses the engine's public
RoomServer interface for traffic, maintenance and final checkpoint flushing.
These fixtures are not actual-game package acceptance. Package construction,
installation and reverse-proxy wiring still need to adopt this launcher.

## Linux package preparation acceptance, before implementation

Separate preparing and accepting an immutable runtime from activating the
service. The same preparation command used by the installer must run on an
ephemeral Ubuntu 24.04 CI runner: verify the uploaded archive, install the exact
managed Python and hash-pinned dependencies outside root's home, and exercise
all three actual games as the unprivileged service account. Repeat preparation
of the same release, preserving its environment and accepted source bytes.
Acceptance includes orders, SIGTERM checkpoint flushing and authenticated rejoin;
the report contains no private seat tokens. This check must not activate systemd,
change the public proxy, use cloud credentials or touch a live room store.

CI must check out the exact reviewed sibling commits, use the pinned Python/uv,
run the complete server suite with native Caddy available, and retain the real
package and acceptance report. A green fixture suite alone cannot satisfy this
gate. Production activation, common server/site locking and public-client
acceptance remain separate rollout requirements.

Local package acceptance now passes with the real pinned sources in
`.github/server-pins.json`: Warband `2361f79`, Tribes `888cdac`, Shardbound
`cc070e3` and Sagaforge `2fa6fad`, using Python 3.13.2 and Saga2D 0.3.2. The
entire server/publication suite passed **103 tests in 63.94 seconds** on the
Mac host, in an isolated clean candidate stack. The package installs only its
exported hashed dependencies, starts outside source checkouts, attests the
accepted native Warband contract, and accepts real orders and restart/rejoin
for all three games. Sixteen focused startup/proxy/staging checks include
changed-source and unsafe-archive refusal. Native Caddy 2.11.4 confirms that a
static compatibility file cannot shadow the live response, that response is
uncached, and static pages retain their intended cache policy.

The upload-layout test caught `release.tar.gz` being copied into the runtime;
staging now verifies and extracts a private copy of those exact bytes. The proxy
test caught the global static cache header overriding `no-store`; cache policy
now applies to static routes only. No acceptance condition was weakened.
Shell syntax, workflow lint and the stack's 389 Markdown files passed their
checks. The local suite does not establish Linux service activation.
The two previously local game pins were pushed only to
`codex/warband-server-runtime` branches so CI can fetch their exact commits.
No game main, version tag, release or live deployment changed.

### Linux acceptance of the real package

[Server Tests 35158657345](https://github.com/ikamensh/saga-online/actions/runs/35158657345)
passed on `126f2201193ba2eb8ed5cd9bdd2e3ff4e1f91ee7`: **103 passed, none skipped,
in 65.69 seconds**, with Ubuntu 24.04's Caddy 2.6.2. The same run built the real
archive, bootstrapped its exact managed Python and hashed dependencies as root,
and ran three-game order/restart/rejoin acceptance as `saga2d-online`. Repeating
preparation preserved the environment and produced the identical acceptance
report; the service account could not write the authoritative source.

The retained artifact was downloaded and independently checked. Its 6,674,467
bytes are **identical to the archive built on the Mac** from the same commit:
`cce03f0b961a05269c364a840274cf9a505d9ed46e062d0177c7a2baf2f03a10`.
Every recorded file hash and the native Warband compatibility contract agree.
The local package entry-point check also passed after switching the isolated
stack to that real committed source. Evidence is retained in
`dist/server-acceptance/github-35158657345/` and its adjacent log; the CI artifact
contains the archive, package identity, JUnit result and token-free acceptance
report. Its endpoint is deliberately `wss://games.example.test/play`, identifying
the isolated acceptance target rather than a fabricated production baseline.

[Website checks 35158657342](https://github.com/ikamensh/saga-online/actions/runs/35158657342)
passed on the same commit: 98 passed, one native Caddy check skipped in that
smaller environment, and the actual server-package test deselected there. The
complete server job above exercised both. Website rendering and its preview
artifact upload also passed. No root installer activation/systemd restart,
public packaged-client acceptance or production rollout is claimed by these
preparation checks. Shardbound's previously recorded client failures remain.

## Promotion/activation exclusion acceptance, before implementation

Server activation and site promotion must hold the same host filesystem lock
through their live checks and commit/rollback. Check the running compatibility
baseline again under that lock immediately before exposing a prepared Warband
catalog, and after verifying public bytes. A baseline change while a promotion
waits must cause rejection with the previous site intact. A failed check after
the pointer swap must restore the previous site and leave its generation and
rollback target unchanged. Retries must still verify the live baseline.

Exercise contention with separate real processes, including a publisher paused
inside its HTTP acceptance check. Preserve crash recovery under the shared lock.
The deployed entry points must use the common lock; serializing only GitHub jobs
or only two static-site publishers is insufficient. The eventual restricted CI
entry point must bind the baseline and candidate catalog to the independently
verified promotion receipt. Keep the generic operator and automated promotion
paths explicit so an omitted promotion receipt cannot silently bypass this gate.

If a publisher dies after changing the site pointer, releasing its lock does not
make that transaction accepted. Server activation must refuse an outstanding
site journal until the site transaction recovers it. Verify this on the isolated
Linux host by killing a real publisher during public acceptance, observing the
actual installer refuse, then retrying the publisher and checking the installer
can proceed to preparation again.

The shared lock and receipt gate are implemented. `activate_site.py` and the
server installer use `/var/lock/saga2d-online.publish.lock`; the latter refuses a
pending site journal before preparation. Site activation has explicit operator
and Warband-promotion modes. Promotion requires its receipt, binds the exact
built catalog digest, and checks the uncached live baseline immediately before
the pointer swap and after public acceptance, including already-current retries.
A failed post-swap check restores the old site without changing its generation
or previous-release pointer. An absent or null baseline cannot bypass the gate.

`package-site --promotion-receipt PATH` carries the receipt outside the public
site, and the operator `site` command passes the corresponding explicit mode.
The deployment installer rejects treating a promotion archive as an operator
archive. This still needs the restricted CI credential/entry point before
unattended publication; the trusted operator path is intentionally distinct.

The complete pinned-stack suite passed **112 tests in 71.75 seconds** locally.
Real processes exercise lock contention, a baseline changing while a publisher
waits, post-swap rollback and retry, and receipt omission/catalog mutation. One
integration journey runs the independent consumer against HTTP/release format
fixtures, renders its actual catalog, packages it with the receipt, extracts the
upload and activates those exact bytes through HTTP. These format fixtures do
not replace the separately recorded native game execution evidence.
Workflow lint, shell syntax and 389 Markdown link checks passed. The new
Linux-only host verification refuses this Mac and is guarded against an
existing managed host. No production operation occurred.

[Server Tests 35160355976](https://github.com/ikamensh/saga-online/actions/runs/35160355976)
then passed on `7bb54110864b5abd8b44bd1c3cd80d60c9e29fa5`: **112 passed, no
skips, in 75.17 seconds**. On the isolated Ubuntu host, the actual server
installer waited while the site CLI verified public files using their unchanged
production lock paths. Killing a real publisher left its journal; the installer
refused until a successful site retry recovered it. Deliberately absent upload
inputs stopped the installer at preparation, so this test performed no server
activation, proxy update or live-store operation. Root bootstrap, service-account
three-game acceptance and repeat preparation also passed for the new archive.

The downloaded archive's SHA-256 is
`73e2db2e7fc432c0ee32bc302382d55ddcb3c1c8af1024eeceb3f4f4b4626d47`.
Its source identity, full file inventory and actual installer bytes were checked
locally against the committed candidate. The host-exclusion report, JUnit,
archive and runtime acceptance are retained in
`dist/server-acceptance/github-35160355976/`, with the adjacent CI log.
[Website checks 35160355978](https://github.com/ikamensh/saga-online/actions/runs/35160355978)
passed the same source with 107 checks, one native Caddy skip and one actual
server-package deselection in its smaller environment; both were exercised by
the complete server job. The site preview build/upload also passed.

## Restricted CI upload acceptance, before implementation

The CI credential must only inspect accepted site state and submit a prepared
static-site promotion. It must not grant an interactive shell, arbitrary command
execution, forwarding, cloud/DNS access, service administration, or access to
room checkpoints. Keep the existing operator credential out of CI. Pin the host
key and use a dedicated account/key with a forced command and narrowly scoped
privilege for the trusted site transaction.

Execute host-installed, reviewed activation code; never execute code carried
inside an upload. Accept a bounded, checksum-bound archive through the fixed
publication operation, reject unsafe paths, links, special/duplicate entries and
unrelated payloads, and require the promotion receipt. Preserve the shared lock,
live baseline, expected-head/generation, retry and crash-recovery behavior already
verified above. Status must give enough accepted-state information to retry an
interrupted promotion without treating an unverified pointer as committed.

Exercise real SSH with a temporary key and isolated daemon on the Linux runner:
successful publication/retry, wrong host key, arbitrary command/subsystem or
forwarding refusal, malformed/unsafe uploads, and failed compatibility checks
with the previous site intact. Verify that upload-supplied scripts cannot run
and that server files and private room state remain unchanged. Build the reviewable
host setup and CI caller locally; install credentials and activate production
after these checks pass. The user's 2026-09-17 standing Saga authorization covers
CI setup, publication and deployment without another go-ahead.

Implementation choice: use a dedicated unprivileged site account with write
access to the website tree and the shared lock, not a root upload receiver or
sudo grant. Its home, authorized keys, configuration and receiver code remain
root-owned. The trusted operator must use the same site account for transactions
after setup so subsequent CI runs can read the accepted state. Server processes,
checkpoints and deployment directories retain their separate ownership.
