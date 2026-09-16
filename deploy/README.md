# Online multiplayer operations

Tribes, Warband and Shardbound share one authoritative Python room server at
`wss://games.tachyon-ai.eu/play`. Caddy terminates TLS on port 443 and forwards
`/play` and `/healthz` to `127.0.0.1:8765`; `/healthz` returns HTTP 200 and
`ok\n`. The candidate proxy also forwards `/server-compatibility.json` to the
same running game process, with `Cache-Control: no-store`. This route becomes
available only after the candidate server is accepted and deployed. Every other
path is the static games website, served from
`/srv/saga2d-site/current`, including the release catalog at `/releases.json`
and invitation links under `/join/`.

## First deployment

Run from the repository root on the operator's laptop, with `uv`, the Scaleway
`scw` CLI, OpenSSH and an Ed25519 key available:

```sh
uv run python tools/deploy_online.py plan --name saga2d-online
uv run python tools/deploy_online.py bootstrap-project --name saga2d-online
uv run python tools/deploy_online.py provision --name saga2d-online
uv run python tools/deploy_online.py deploy --name saga2d-online
uv run python deploy/smoke.py wss://games.tachyon-ai.eu/play
```

`plan` and `package` operate offline. The remaining commands perform the named
operation; they do not prompt again. `bootstrap-project` creates a dedicated
`saga2d` project, `saga2d-deploy` IAM application and a new policy granting only
`InstancesFullAccess` and `BlockStorageFullAccess` in that project. It reads the `Personal admin key` heading
in `~/secrets/scaleway.md` and atomically appends the new key under
`## saga2d-deploy`, preserving mode 600. Subsequent operations read only that
section. Existing projects, applications and policies must have matching
ownership markers. Bootstrap reconciles only this application's compute/disk
permissions; existing administrator and hive policies are never changed.

Provisioning creates a `DEV1-S` in `fr-par-1`, a 20 GB Block 5K root disk,
a reserved IPv4 address, and a dedicated stateful firewall accepting inbound
TCP 22/80/443. Scaleway's immutable outbound SMTP blocks remain intact.
Cloud-init installs Ubuntu 24.04 packages, the public SSH key, a `deploy` operator
account and an unprivileged `saga2d-online` runtime account. SSH uses the private
key corresponding to `--ssh-key` and records the first host key; changed host
keys are rejected. Cloud and DNS credentials stay on the laptop.

Deployment creates the `games` A record through GoDaddy using the `GoDaddy DNS`
section of `~/secrets/infrastructure.md`. A conflicting existing record causes
an error. Caddy obtains and renews the TLS certificate automatically. Its
default forwarded-header handling replaces untrusted client values, allowing
the loopback-only application's `--trusted-proxy` mode to enforce per-client
limits. No managed load balancer or serverless service is required.

## Releases and validation

`package` requires clean checkouts at the exact sibling commits in
`../.github/server-pins.json`, together with its pinned Python and uv versions.
Use separate adjacent checkouts when these differ from active development
branches. It reads allowlisted game source from Git objects, verifies Saga2D's
installed PyPI source against its wheel inventory, and exports hashed runtime
dependencies using `uv export --locked`. The server lock must agree with the
Warband native release's compatibility contract. Content-addressed tarballs
under ignored `dist/online/` contain `deploy/server-inputs.json` with exact
source commits, runtime versions and file hashes. Credentials, saves, caches,
untracked source and working-tree metadata are excluded.

After checking the managed-instance marker, the installer calls
`prepare_release.sh`. Preparation verifies and extracts the uploaded archive
into `/opt/saga2d-online/releases/<sha256>`, rejecting unsafe archives or changes
to existing release bytes. It bootstraps a hash-pinned uv wheel with Ubuntu's
Python, installs the exact managed Python under `/opt/saga2d-online/python`
(accessible with `ProtectHome=true`), and installs a dedicated hashed runtime.
As the unprivileged service account, `check_release.py` then starts the actual
packaged launcher on an ephemeral loopback port, verifies its live attestation,
creates and joins **all three actual games**, submits orders, stops the server
with SIGTERM, and checks authenticated rejoin and exact paused state after
restart. Its temporary room store and private seat tokens never enter the live
store or public report. Only success writes `.ready`; a retry verifies the same
release again and preserves its environment. Preparation does not activate a
service or change the proxy, and is exercised separately by branch CI.

Activation replaces the `current` symlink
atomically, followed by a systemd restart and health check. An activation failure
restores the previous release's service and proxy configuration. First-time
activation failure stops the failed service and reports the error.
The process's compatibility response must match the accepted candidate before
the proxy is reloaded. This startup gate does not replace rollout acceptance:
room draining, reviewed backup/restore, restricted CI access and public
packaged-client checks still need to be completed for unattended publication.

The systemd service has `MemoryMax=1200M`, `CPUQuota=150%`, `TasksMax=128`,
`LimitNOFILE=4096`, 32 rooms and 96 connections. Rooms expire 15 minutes after
both seats leave, so automated checks and abandoned rooms occupy slots for that
long; suspended campaigns do not count. It runs without root privileges,
with a read-only filesystem except its private state directory. Runtime logs
go to journald, capped at 200 MB for the instance. Releases are retained for
manual rollback; monitor disk usage and remove obsolete releases after review.

Persistent room checkpoints are stored in `/var/lib/saga2d-online`. Releasing
code preserves that directory; a code rollback does not roll back the database.
Clients use their private resume tokens to reconnect after a restart. A single
VM is an initial capacity choice, not high availability: host or zone failures
interrupt play until service is restored.

## Routine operation

```sh
uv run python tools/deploy_online.py status --name saga2d-online
uv run python tools/deploy_online.py deploy --name saga2d-online
uv run python deploy/smoke.py wss://games.tachyon-ai.eu/play
```

## Website and release catalog

`releases/catalog.json` is the single source of release facts: per game, the
online ids, current version, source commit and each package's URL, size and
SHA-256. `tools/release_catalog.py` validates it; the website and the installed
games read the same document. Update the catalog only after a release has
passed acceptance, and never overwrite a versioned binary.

```sh
uv run --project publishing --locked python tools/release_catalog.py
uv run --project publishing --locked python tools/build_site.py
# Set SITE_EXPECTED to the reviewed current SHA-256 (or none for first use),
# and SITE_GENERATION to the reviewed next promotion generation.
uv run --project publishing --locked python tools/deploy_online.py site --name saga2d-online \
  --expected-site "$SITE_EXPECTED" --site-generation "$SITE_GENERATION"
```

Before preparing publication, read `/srv/saga2d-site/state.json` and the
`/srv/saga2d-site/current` symlink on the named host. The first transaction can
adopt an existing legacy SHA-256 release as generation zero; use that release
as `SITE_EXPECTED` and a positive generation. Subsequent generations must exceed
the recorded accepted generation. Do not automatically substitute a newer head
if the reviewed expected release is rejected: reconcile the catalog first.

For an independently prepared Warband promotion, build from its `catalog.json`
and pass `--promotion-receipt PATH/TO/promotion.json` to `package-site` or `site`.
The archive carries that receipt outside the public website and verifies its
catalog digest. `site` selects explicit `warband-promotion` mode on the host;
that mode requires the receipt and checks the uncached live compatibility
response immediately before exposing downloads and after public acceptance,
including retries. Ordinary operator site publication uses explicit `operator`
mode. A promotion archive cannot be passed to operator mode. The future
restricted CI entry point must always require promotion mode; this operator
command is not a substitute for that credential restriction.

`site` bundles `dist/site` with `deploy/install_site.sh` and `activate_site.py`,
uploads it and installs an immutable release under
`/srv/saga2d-site/releases/<sha256>`. The transaction holds
`/var/lock/saga2d-online.publish.lock`, shared with the server installer,
through expected-head/generation checks, the atomic `current` symlink swap,
verification of every public file and `/healthz`, and state recording. Failed
acceptance restores the previous site; an interrupted process leaves a journal
that the next site invocation recovers before accepting another promotion.
The server installer refuses activation while that journal remains. Preserve
the lock file; do not unlink it while either operation might hold it. Once this
deployment protocol is installed, use these entry points for all publications
and server refreshes, not an older archived installer with a different lock.
It does
not touch the room server; `deploy`
does not touch the site. The Caddy routes ship with the server release, so the
first site publication requires a server deployment that carries the current
`deploy/Caddyfile`. The `previous` pointer and immutable releases are retained;
there is no automatic pruning. An intentional rollback is a new promotion of
the reviewed previous bytes with a higher generation and the current expected
head. Do not move the symlink manually while leaving `state.json` unchanged.
There is no production server baseline recorded yet; the CI runner's
`games.example.test` acceptance report must not be used as one.

Installed games fetch `/releases.json` when the player opens Multiplayer and
offer the download page when the catalog version differs from their build.
Clients whose protocol or game id the server no longer accepts receive a
structured `incompatible` rejection and show the same download page.

## Load checks

`uv run python tools/load_online.py --game warband --rooms 4 --seconds 90`
drives several rooms with two real clients each issuing valid orders, and
reports time to ready, state cadence, Warband's simulation rate against wall
time and `/healthz` latency. The server admits four new rooms per minute per
address, so larger runs pace themselves; rooms expire afterwards under normal
retention. Results are kept under `docs/evidence/online-load-<date>/`.

## Backups

`saga2d-backup.timer` runs `deploy/backup.py` hourly as the service user: a
consistent SQLite online backup of `/var/lib/saga2d-online/rooms.sqlite3` into
`/var/backups/saga2d-online/rooms-<UTC>.sqlite3` (mode 600, integrity-checked,
14 days retained). The backups live on the same disk as the database, so they
protect against a corrupted or mistakenly emptied database, not against losing
the volume. `deploy_online.py backup --name saga2d-online` takes a fresh backup,
copies the newest file to `dist/online/backups/` on the laptop and verifies its
integrity; run it before every server deployment and keep the copies off-host.

To restore: stop `saga2d-online`, copy the chosen backup to
`/var/lib/saga2d-online/rooms.sqlite3` (owned by `saga2d-online`, mode 600,
removing any `-wal`/`-shm` files), start the service and check `/healthz`.
Players reconnect with their saved seats; rooms that expired in the meantime
are purged at startup.

## Room retention

Match rooms (Tribes, Warband) expire after `--room-ttl` (15 minutes) without
both players. Shardbound campaign rooms are retained for `--campaign-ttl`
(seven days): after `--room-ttl` with no seat connected they are suspended to
SQLite and leave memory, freeing the room limit, and return when either seat
resumes or joins. The `suspended` table is additive, so an earlier server
release can still read the database after a code rollback.

`dist/online/target.json` records the server ID and IP after provisioning. SSH
to `deploy@<IP>` for service status, logs, or disk inspection:

```sh
sudo systemctl status saga2d-online caddy
sudo journalctl -u saga2d-online -u caddy --since '15 minutes ago'
df -h /var/lib/saga2d-online /opt/saga2d-online
readlink /opt/saga2d-online/current
readlink /opt/saga2d-online/previous
```

The public smoke check creates three small rooms, which expire under the
server's disconnected-room retention policy. It must be run deliberately, not
used as a frequent liveness probe. Use `/healthz` for liveness monitoring.

## Account discovery and cost

Verified 2026-09-07: `tachyon-ai.eu` is active at GoDaddy. The separate game
project ID is `42ae77f6-b012-4e0f-b76d-93be6a61c56f`; deployment application ID is
`907c7ed5-0c62-4665-9cfb-8957e1495db1`. The dedicated instance is
`d56b46e5-fe7d-404c-9b5d-48bc87143433` at `51.159.207.49`, in `fr-par-1`.
The existing `hive` project contains
`hive-vm` and `hive-droid`; neither is a target of this deployment tooling.
Hive's spend guard powers off hive-project instances when organization spending
reaches €1,000 per month. The separate game project avoids tying game uptime to
that agent-workload policy, while preserving the guard unchanged.

The personal administrator key can manage projects and IAM but its resource
policy excludes compute. That is why bootstrap creates a separate app with
permission only for game instances; it does not modify the administrator or
hive policies.

At the verified prices and 730 hours per month, the initial estimate is
**€11.37/month before tax**: DEV1-S €6.55, public IPv4 €2.92, 20 GB Block 5K
€1.90. Actual monthly hours and later price changes affect billing. The
Scaleway API reported DEV1-S capacity available in `fr-par-1` during discovery.

Sources:

- [Scaleway instance pricing](https://www.scaleway.com/en/pricing/virtual-instances/?cpu_type=shared)
- [Scaleway block storage pricing](https://www.scaleway.com/en/pricing/storage/)
- [Instance API and volumes](https://www.scaleway.com/en/developers/api/instance/v1)
- [Scaleway cloud-init](https://www.scaleway.com/en/docs/instances/how-to/use-cloud-init/)
- [Project API](https://www.scaleway.com/en/developers/api/account/project)
- [IAM rules and scope](https://www.scaleway.com/en/developers/api/iam/rules)
- [Compute and Block Storage permission sets](https://www.scaleway.com/en/docs/iam/reference-content/permission-sets/)
- [Caddy WebSockets and forwarded headers](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
