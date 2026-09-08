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
uv run python -m warband.online_ai --create --difficulty normal --duration 1800
uv run python -m warband.online_ai --room ROOMCODE --difficulty hard --duration 1800
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
uv run python tools/remote_warband_ai.py install

# Start one bounded, unprivileged client. Read its room code in status.
uv run python tools/remote_warband_ai.py create --duration 1800
uv run python tools/remote_warband_ai.py status

# Alternatively, create a room in the human game and send the AI there.
uv run python tools/remote_warband_ai.py join --room ROOMCODE --duration 1800

# Stop the current client before starting another.
uv run python tools/remote_warband_ai.py stop
```

The client runs as a transient systemd service with a 25% CPU quota, a 256 MB
memory limit and a read-only system filesystem. It stops on errors or when
its duration ends; errors remain in the journal. The VM stays running after
the client stops, so its compute, disk and public IPv4 continue to be billed.
Provisioning uses the same DEV1-S and 20 GB disk configuration documented in
[online operations](../deploy/README.md), estimated at about €11.37/month
before tax in addition to the room server. The instance API checked on
2026-09-08 reports €0.008976/hour for its compute; storage and IPv4 are extra.

## Verify a human client against it

Start the remote client with at least 180 seconds remaining, then run:

```sh
SAGA2D_SILENT=1 uv run python tools/verify_warband_remote_ai.py /tmp/warband-remote-ai --room ROOMCODE
```

This uses the native game menu and real input to join, issue player orders,
and observe the remote opponent's authoritative progress. Inspect the saved
screenshots alongside the JSON report. The live room contains no local AI.
