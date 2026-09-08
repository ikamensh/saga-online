# Online multiplayer operations

Tribes, Warband and Shardbound share one authoritative Python room server at
`wss://games.tachyon-ai.eu/play`. Caddy terminates TLS on port 443 and forwards
`/play` and `/healthz` to `127.0.0.1:8765`; `/healthz` returns HTTP 200 and
`ok\n`. Every other path is the static games website, served from
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

`package` allowlists Python source from all three games, Saga2D and the server,
plus deployment templates. It exports hashed dependencies from `uv.lock` using
`uv export --frozen`. Keep the lock current with `pyproject.toml` before release.
Artifacts are content-addressed tarballs under ignored `dist/online/`; local
credential files, saves, caches and the working tree's metadata are excluded.

The installer verifies the remote instance marker and upload checksum, creates
an isolated venv under `/opt/saga2d-online/releases/<sha256>`, then starts a
candidate on an ephemeral loopback port. Before activation, the candidate must
pass health and create/join a room for **each of the three games**, exercising
their lazy imports and model constructors. The `current` symlink is replaced
atomically, followed by a systemd restart and health check. An activation failure
restores the previous release's service and proxy configuration. First-time
activation failure stops the failed service and reports the error.

The systemd service has `MemoryMax=1200M`, `CPUQuota=150%`, `TasksMax=128`,
`LimitNOFILE=4096`, 16 rooms and 64 connections. It runs without root privileges,
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
uv run python tools/release_catalog.py                     # validate
uv run python tools/build_site.py                          # render dist/site
uv run python tools/deploy_online.py site --name saga2d-online
```

`site` bundles `dist/site` with `deploy/install_site.sh`, uploads it, installs
it as an immutable release under `/srv/saga2d-site/releases/<sha256>`, swaps the
`current` symlink and verifies that the public home page and `/releases.json`
serve the exact local bytes. It does not touch the room server; `deploy`
does not touch the site. The Caddy routes ship with the server release, so the
first site publication requires a server deployment that carries the current
`deploy/Caddyfile`. The three most recent site releases are retained for manual
rollback by re-pointing the symlink.

Installed games fetch `/releases.json` when the player opens Multiplayer and
offer the download page when the catalog version differs from their build.
Clients whose protocol or game id the server no longer accepts receive a
structured `incompatible` rejection and show the same download page.

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
