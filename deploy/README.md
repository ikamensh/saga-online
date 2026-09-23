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
operation; they do not prompt again. `deploy` is the operator's path for the
first deployment and for changes to the host itself (service units, proxy
configuration, installer); routine releases go out through the
[automatic server rollout](#automatic-server-rollout). `bootstrap-project` creates a dedicated
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
`prepare_release.sh` from its own directory. Preparation verifies and extracts the uploaded archive
into `/opt/saga2d-online/releases/<sha256>`, rejecting unsafe archives or changes
to existing release bytes. It then refuses a release whose copies of the host
files (the installer, preparation scripts, `uv-bootstrap.txt`, the systemd units
and the `Caddyfile`) differ from the ones it runs with: root runs only those, and
the release's own code runs only as the service account. Runtime wheels install
with `--no-build`, so no source build runs as root. It bootstraps a hash-pinned uv wheel with Ubuntu's
Python, installs the exact managed Python under `/opt/saga2d-online/python`
(accessible with `ProtectHome=true`), and installs a dedicated hashed runtime.
As the unprivileged service account, `check_release.py` then starts the actual
packaged launcher on an ephemeral loopback port, verifies its live attestation,
creates and joins **Warband**, submits an order, stops the server
with SIGTERM and backs up the paused checkpoint with the actual SQLite tool.
It checks authenticated rejoin and exact paused state after restarting the
original database, then after restoring only the backup into a fresh private
state directory. Taking the backup before rejoining avoids comparing against
RTS ticks that advance while both players are present. Its private seat tokens
never enter the live store or public report. Only success writes `.ready`; a retry verifies the same
release again and preserves its environment. Preparation does not activate a
service or change the proxy, and is exercised separately by branch CI.

Activation replaces the `current` symlink
atomically, followed by a systemd restart and health check. An activation failure
restores the previous release's service and proxy configuration. First-time
activation failure stops the failed service and reports the error.
The process's compatibility response must match the accepted candidate before
the proxy is reloaded. Re-activating the running release keeps the distinct
release behind it at `previous`. `install.sh --rollback FROM` reactivates
`previous` while `FROM` is current, under the same lock and checks, and swaps
the two pointers.

The systemd service has `MemoryMax=1200M`, `CPUQuota=150%`, `TasksMax=128`,
`LimitNOFILE=4096`, 32 rooms and 96 connections. Rooms expire 15 minutes after
both seats leave, so automated checks and abandoned rooms occupy slots for that
long; suspended campaigns do not count. It runs without root privileges,
with a read-only filesystem except its private state directory. Runtime logs
go to journald, capped at 200 MB for the instance. Releases are retained for
rollback; monitor disk usage and remove obsolete releases after review.

Persistent room checkpoints are stored in `/var/lib/saga2d-online`. Releasing
code preserves that directory; a code rollback does not roll back the database.
Clients use their private resume tokens to reconnect after a restart. A single
VM is an initial capacity choice, not high availability: host or zone failures
interrupt play until service is restored.

## Automatic server rollout

`.github/workflows/server-rollout.yml` puts the newest published Warband on the
live server and promotes it, with nobody at the laptop. Warband's "Publish
verified Warband" dispatches "Promote verified Warband"; when that promotion is
refused because the candidate needs a server the live one is not (its source or
contract differs from `releases/server-baseline.json`, or the live attestation differs
from that file), `tools/warband_promotion.py` exits 3 and the promotion's
`request-rollout` job dispatches the rollout. An operator or agent can dispatch
it too (`gh workflow run server-rollout.yml -R ikamensh/saga-online`), with
`force` to rebuild and re-activate the current contract and
`fail_after_activation` to exercise the rollback. There is no schedule: every
published build already asks, and a schedule would only retry a failing
rollout against the live server.

One run at a time (`concurrency: saga-server-rollout`); a newer request waits
in place of an older one. Each run deploys the newest Warband release, not the
one that asked, so a batch of rules changes goes out together.

| Job | Runs on | What it does |
|-----|---------|--------------|
| `resolve` | Ubuntu | `server_rollout.py resolve`: the newest immutable Warband release, its native run verified as the promotion does. The same source and contract as the baseline, served live, is `current`: a clean exit that dispatches the promotion only if the catalog names another build. Otherwise `deploy`: moves the Warband, run and Sagaforge pins, relocks if the games' metadata moved, and pushes the commit to `server-rollout/<run>` (never main). A candidate behind the pins, or one needing another Python or uv, is refused. |
| `candidate` | Ubuntu | `tests.yml` on that commit: Warband's server and publication suite, advisory demo gameplay checks, the host-entry-point checks, the one archive built and prepared as the service account, and `tests/host_server_ci.py` (install, rollback and refusals through the real CI account on the runner's systemd). |
| `deploy` | Ubuntu, `server-rollout` environment | Status; a fresh backup through the CI account, kept off the host as an age-encrypted artifact (`server-backup-<run>`, 90 days); every retained Warband seat resumed on a private copy with the candidate's server (`rehearse_retained.py --game warband-v2`); activation through the host's installer; then `server_rollout.py accept`: public health, the served attestation equal to the archive's, Warband create/join/order, `permessage-deflate` through the proxy, retained Warband seats resumed live and a three-seat Warband room. A failure after activation rolls back to `previous`. |
| `native` | Windows and macOS | The candidate's own frozen client, downloaded from its immutable release, plays its online journey against the activated public server (`check_public_warband.py --candidate-tag`). |
| `rollback` | Ubuntu, `server-rollout` environment | Only when a native journey failed: back to `previous`. |
| `record` | Ubuntu | Writes `releases/rollouts/<UTC>-<warband>.json` (candidate, previous baseline, pins, backup, rehearsal, activation, every check, native receipts, rollback) for every run that reached the host. Accepted: merges the pin commit, writes the served attestation as the baseline, pushes to main and dispatches the promotion again. Anything else fails the run. |

The accepted promotion then triggers "Public Warband download checks", the
public bytes on Windows and macOS against the public server. The records under
`releases/rollouts/` replace a rollout document per change. A change the
automation cannot take (saga-online code that must move with Warband, an engine
or runtime upgrade, a host change) fails in `resolve`, `candidate` or at
preparation, before activation; fix it on main and dispatch the rollout.

### Restricted server-CI account

Prepare a dedicated Ed25519 key. With its **public** key, the operator installs
the account and its trusted host tools (repeat to update them or rotate the key):

```sh
uv run python tools/deploy_online.py setup-server-ci --name saga2d-online \
  --server-public-key ~/secrets/saga-server-ci/id_ed25519.pub
```

Setup creates `saga2d-server-ci`: no password, no supplementary groups, a
root-owned home. Its SSH key has a forced command
(`/usr/local/lib/saga2d-server-ci/command`) that accepts exactly `status`,
`backup`, `install` or `rollback` and passes that word to
`sudo -n /usr/local/lib/saga2d-server-ci/run`. `/etc/sudoers.d/saga2d-server-ci`
(checked with `visudo` before it is installed, and read back with `sudo -l`)
allows exactly those four command lines as root and nothing else. `run`
executes the installed `server_ci.py`, which reads a bounded JSON line and,
for `install`, the archive from stdin:

- `status`: current and previous releases, service state, health and the
  locally served attestation.
- `backup`: starts the installed backup unit and streams the newest backup
  with its size, SHA-256 and room count.
- `install`: requires the named current release, verifies size and SHA-256 and
  runs the **installed** `install.sh`, which refuses a release carrying other
  host files. A host change therefore needs this setup command first.
- `rollback`: while the named release is current, reactivates `previous`.

Forwarding, TTY, user rc files and passwords are disabled for the account, and
setup validates the effective `sshd -T` settings before installing the key. It
does not reload SSH itself when run by hand; `setup-server-ci` reloads it. What
the key can do: deploy code built from main to run as the service account
(which holds the room database), read room backups, and move between prepared
releases. It cannot run anything else as root, change the host tools, the
units, the proxy or the site, or read credentials. Cloud and DNS credentials
stay on the laptop.

GitHub's `server-rollout` environment (branch `main` only) holds
`SAGA_SERVER_SSH_KEY` and `SAGA_SERVER_KNOWN_HOSTS` and the variables
`SAGA_SERVER_HOST` and `SAGA_BACKUP_AGE_RECIPIENT`. The laptop keeps the key,
the pinned host key and the age identity that decrypts backups under
`~/secrets/saga-server-ci/` (Secrets index in `~/.config/agents/registry.md`).
`tests/host_server_ci.py` exercises the account on a disposable runner; never
run it on the production host.

## Routine operation

```sh
uv run python tools/deploy_online.py status --name saga2d-online
gh run list -R ikamensh/saga-online --workflow server-rollout.yml --limit 5
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
mode. A promotion archive cannot be passed to operator mode. The restricted
CI receiver always requires promotion mode; this operator
command is not a substitute for that credential restriction.

`site` uploads only `dist/site` and the optional promotion receipt. Trusted
activation code, installed separately with `setup-site-ci` (below), installs
an immutable release under
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
The accepted production baseline is recorded in
[`releases/server-baseline.json`](../releases/server-baseline.json); the
automatic rollout writes it from the served attestation after acceptance, and
its records are under [`releases/rollouts/`](../releases/rollouts/).
CI's `games.example.test` reports are test evidence, not production baselines.

### Restricted CI publisher

Installed on `saga2d-online` on 2026-09-17. The dedicated account's real SSH
`status` check passed with the pinned host key, reporting the unchanged legacy
site `43836139…ddfb9`, generation zero, and no pending transaction. GitHub's
`warband-promotion` environment holds `SAGA_SITE_SSH_KEY`,
`SAGA_SITE_KNOWN_HOSTS` and the `SAGA_SITE_HOST` variable; only `main` can use it.
The local Secrets index records the dedicated credential files and rotation
instructions. See [CI publication status](../docs/warband-ci-publication.md)
for enablement and the first complete release journey.

Prepare a dedicated Ed25519 key for website CI. Keep the operator's SSH key and
cloud/DNS credentials local. With the dedicated **public** key, the operator can
prepare the trusted host tools offline, then install them on the named host:

```sh
uv run --project publishing --locked python tools/deploy_online.py package-site-ci \
  --name saga2d-online --site-public-key /path/to/site-ci.pub
uv run --project publishing --locked python tools/deploy_online.py setup-site-ci \
  --name saga2d-online --site-public-key /path/to/site-ci.pub
```

Setup creates `saga2d-site-ci` with no sudo or supplementary groups. Its home,
authorized keys, versioned tools and configuration are root-owned; it owns only
the website tree and can use the existing shared lock. Existing site transaction
files move to this account without replacing the lock inode or site pointer.
The operator's `site` command also runs the trusted transaction as this account.
Setup validates the effective SSH restrictions before installing the key and
reloading SSH. It does not publish a site or restart the game server. Repeat the
same command to update trusted tools or rotate the dedicated key.

The account's forced command accepts exactly `status` and `publish`. It executes
host-installed Python in isolated mode. Uploads contain only bounded website
data and a receipt; even script-shaped public files remain data. Forwarding,
TTY, user startup hooks, password authentication and arbitrary commands are
disabled. Both `ForceCommand` and forwarding restrictions are required; see
[OpenSSH's configuration reference](https://man.openbsd.org/sshd_config).

Give CI the dedicated private key and an independently verified `known_hosts`
entry for the host. The client requires the pinned key, ignores ambient SSH
configuration/agents, and never accepts a new host key automatically:

```sh
python tools/site_publish.py --host HOST --identity /path/to/site-ci \
  --known-hosts /path/to/known_hosts status
python tools/site_publish.py --host HOST --identity /path/to/site-ci \
  --known-hosts /path/to/known_hosts publish --archive /path/to/site-SHA256.tar.gz \
  --generation GENERATION --expected EXPECTED_SHA256
```

`status` returns accepted state and whether an interrupted transaction remains;
it never adopts an unverified pointer. Reconcile that accepted state with the
prepared catalog before choosing a generation. Use `none` for the expected
release only on a first publication. A retry uses the same archive and ordering
preconditions. Limits are 64 MiB compressed, 256 MiB expanded, 2,048 regular
files, and 300 seconds on the host; failures are explicit and preserve/recover
the last accepted site.

`tests/host_site_ssh.py` verifies the actual setup, client, forced command and
rollback through a loopback SSH daemon on a disposable Linux container or GitHub
runner. It writes production paths and refuses an already managed host. Never
run this acceptance program on the live server.

### Installed client update notices

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
the volume. Every rollout takes a fresh one before activation and keeps it off
the host, encrypted to the laptop's age key, as the artifact
`server-backup-<run>` for 90 days:

```sh
gh run download RUN -R ikamensh/saga-online -n server-backup-RUN -D /tmp/backup
age -d -i ~/secrets/saga-server-ci/backup-age-identity.txt -o rooms.sqlite3 /tmp/backup/rooms-*.age
```

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
