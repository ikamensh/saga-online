# Internet play with a remote AI opponent

The AI runs the ordinary Warband brain in a headless client. It receives the
server's world and submits the same validated orders as a player. It neither
hosts nor advances the match simulation. A human can create a room for it to
join, or join a room created by the AI.

```text
Human's game ── public TLS WebSocket ──> Paris room server
Amsterdam AI ─ public TLS WebSocket ──> Paris room server
```

The game server remains `wss://games.tachyon-ai.eu/play` on `saga2d-online`
(`51.159.207.49`, `fr-par-1`). The temporary Amsterdam client successfully
played against the native human client through that public endpoint; see the
[Internet-play evidence](evidence/warband-internet-2026-09-08/README.md).

On 2026-09-08, after that verification, `saga2d-warband-ai` was retired at the
user's request. Its VM, 20 GB disk and reserved IPv4 were deleted and each
returned HTTP 404 on verification. The old `51.158.175.125` address is released
and must not be reused. Paris remained running and its public health endpoint
returned HTTP 200 before and after retirement. The
[retirement receipts and retained AI journal](evidence/warband-internet-2026-09-08/ai-retirement/README.md)
record the exact resources. There is no running Amsterdam AI client or retained
AI compute, disk or IPv4 to bill.

## Run a client anywhere

```sh
uv run python -m warband.online.online_ai --create --difficulty medium --duration 1800
uv run python -m warband.online.online_ai --room ROOMCODE --difficulty hard --duration 1800
```

The first JSON line reports the shareable room code and assigned player.
Progress lines report orders submitted and the authoritative state observed;
private seat credentials are never printed. `--duration` limits total running
time, including the lobby; `--wait-timeout` limits time waiting for a partner.
Closing either seat pauses the match. A room without both players expires
after the server's retention interval, currently 15 minutes.

## Recreate and operate a temporary Amsterdam client

These commands provision a new billable VM when another remote-client run is
needed. Run them from the repository on the laptop with its existing SSH key.
No Scaleway or DNS credentials are copied onto either VM. Retirement removed
`dist/online-ai/target.json`; its historical record is now
`dist/online-ai/target.retired.json` and cannot be used as an active target.
Provisioning creates a fresh target with the new instance identity and address.

```sh
# Provision a new client; records dist/online-ai/target.json.
uv run python tools/deploy_online.py provision --name saga2d-warband-ai --zone nl-ams-1 --output dist/online-ai

# Install a content-addressed source archive and locked dependencies.
# --archive installs an explicitly prepared archive (hashed locally);
# without it the tool packages the pinned release itself.
uv run python tools/remote_warband_ai.py install --archive dist/online-ai/<sha>.tar.gz

# Start one bounded, unprivileged client. Read its room code in status.
uv run python tools/remote_warband_ai.py create --duration 1800
uv run python tools/remote_warband_ai.py status
uv run python tools/remote_warband_ai.py status --json

# Alternatively, create a room in the human game and send the AI there.
uv run python tools/remote_warband_ai.py join --room ROOMCODE --duration 1800

# Stop the current client before starting another.
uv run python tools/remote_warband_ai.py stop
```

Targets are `saga2d-warband-ai` or a slug variant
`saga2d-warband-ai-<slug>` (one service per VM, the natural two-seat
match). The `saga2d-online` room server is always refused, and every
command verifies the remote `/etc/saga2d-online/managed-instance`
marker matches the chosen target before any mutation; the installer
takes the expected instance name explicitly for the same reason.
Starting over a running bot is refused. The unit is kept (no
`--collect`, `RemainAfterExit=yes`) so its terminal `finished` event
stays observable under its InvocationID until stopped; `status --json`
reports systemd fields plus only that invocation's sanitized bot
events, never prior runs and never private tokens.

Pass-through bot options are forwarded only when set, so older clients
keep working: `--reconnect-after`, `--disconnect-for`,
`--require-completion`, `--seed/--width/--height/--theme` (create),
`--race` (each seat's own choice, create or join), `--rated` with
`--player-name` (create; the joiner inherits ranked from the room).
With `--player-name` and no `--identity-file`, the engine mints and
keeps a per-VM private identity at
`/var/lib/saga2d-warband-ai/identity.json` across matches; pass an
owner-only mode 0600 `--identity-file` only to reuse an existing one.
Identity bytes are uploaded, never printed. A rated `finished` event
carries only the seat's public player id and rating profile, and
`status --json` reports them; the harness binds each receipt row to
its seat by that public id (duplicate aliases are refused), so no
private token is ever needed for correlation.

The client runs as a transient systemd service with a 25% CPU quota, a 256 MB
memory limit and a read-only system filesystem. It stops on errors or when
its duration ends; errors remain in the journal. The VM stays running after
the client stops, so its compute, disk and public IPv4 continue to be billed.
Provisioning uses the same DEV1-S and 20 GB disk configuration documented in
[online operations](../deploy/README.md), estimated at about €11.37/month
before tax in addition to the room server. The instance API checked on
2026-09-08 reports €0.008976/hour for its compute; storage and IPv4 are extra.

## Verify a full match between two remote clients

Provision two disposable VMs with distinct names, for example
`saga2d-warband-ai-host` and `saga2d-warband-ai-guest`, install the
client on each, then run the harness from the laptop:

```sh
uv run python tools/verify_remote_warband_match.py \
  --host-target dist/online-ai/host.json --guest-target dist/online-ai/guest.json \
  --server wss://games.tachyon-ai.eu/play --output /tmp/remote-match
```

The host creates the room, the guest joins and deliberately rejoins
mid-match, and the run passes only on an authoritative winner observed
by both seats: same room, opposite seats, tick/order progress, guest
rejoin with preserved seat, and consistent winners. The rejoin must be
the driver's own rejoined continuity for the guest seat with later
play after it; a pause/resume wobble alone does not count. A crashed
bot fails the run on its reported error or exit status at once instead
of waiting out the timeout. A duration expiry or a timeout is a
failure, never a completion. Only services started by the run are
stopped, always (a failed stop fails the run without hiding the
primary error), and a compact sanitized `report.json` is written
either way. The server must be the public
TLS endpoint; two seats on one VM are refused.

For a real ranked run, add `--rated` with both player names (and an
identity file per side only to reuse one). Both bots must then report
the same server result receipt with a nonempty match id, a winner in
{0, 1}, distinct player ids, and deltas that net to zero with the
movement pointing the right way (winner up, loser down; a fresh
1500-v-1500 pairing must move both). The engine emits ratings as
floats (1500.0, ±16.0, fractional after rematches); the harness
recomputes with a tight floating-point tolerance and never rounds
authoritative values, while games/wins/losses stay integers and
NaN, infinities and bools are refused. The harness also checks the
public `/status`, `/players/{id}?game=warband-v2` and
`/ratings?game=warband-v2` routes, recording `rated_grace` in the
report. A ranked run with no receipt fails loudly: the client engine
ignored the ranked options.
The proxy serves those routes from the room server with `no-store`,
never from the static site.

## Verify a human client against it

Start the remote client with at least 180 seconds remaining, then run:

```sh
SAGA2D_SILENT=1 uv run python tools/verify_warband_remote_ai.py /tmp/warband-remote-ai --room ROOMCODE
```

This uses the native game menu and real input to join, issue player orders,
and observe the remote opponent's authoritative progress. Inspect the saved
screenshots alongside the JSON report. The live room contains no local AI.
