# Saga Online

The hosted side of the Saga games: [Tribes](../tribes), [Warband](../warband)
and [Shardbound](../shardbound) share one authoritative room server
(`saga2d.server` from [Saga2D](../saga2d)) at `wss://games.tachyon-ai.eu/play`,
a release catalog, and the self-service website at https://games.tachyon-ai.eu/
with downloads, install steps, invite links and a status page.

The candidate server environment uses the published `saga2d==0.3.2` release. Sagaforge and the games
remain editable dependencies from their sibling checkouts; engine changes
take effect only when the pinned release is deliberately upgraded.
Updating this checkout does not deploy the hosted server.

Server packages require the clean exact sibling commits, Python 3.13.2 and
uv 0.12.10 in [.github/server-pins.json](.github/server-pins.json). Use separate
adjacent checkouts for these candidates; the current sibling main branches do
not yet share this runtime. In particular, the Shardbound engine-alignment
candidate still has client acceptance failures also present on its prior engine.
The read-only [Tests workflow](.github/workflows/tests.yml) checks out this exact
stack and verifies its actual three-game server package on Ubuntu 24.04.

For an existing environment that used the editable engine, run
`uv sync --locked --extra dev --reinstall-package saga2d` once. A plain sync
can retain an editable install of the same version. This also restores the
release after local engine testing.

```bash
uv sync --locked --extra dev                     # in the pinned candidate stack
uv run --locked pytest -q
uv run --project publishing --locked python tools/build_site.py --output dist/site
uv run python tools/deploy_online.py plan --name saga2d-online
```

Operations live in [deploy/README.md](deploy/README.md); the distribution
plan and its status in [docs/game-distribution-plan.md](docs/game-distribution-plan.md).
Server credentials stay on the operator's laptop (`~/secrets/scaleway.md`).
