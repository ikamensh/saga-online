# Saga Online

The hosted side of the Saga games: [Tribes](../tribes), [Warband](../warband)
and [Shardbound](../shardbound) share one authoritative room server
(`saga2d.server` from [Saga2D](../saga2d)) at `wss://games.tachyon-ai.eu/play`,
a release catalog, and the self-service website at https://games.tachyon-ai.eu/
with downloads, install steps, invite links and a status page.

```bash
uv sync --extra dev
uv run pytest -q
uv run python tools/build_site.py dist/site        # render the site locally
uv run python tools/deploy_online.py plan --name saga2d-online
```

Operations live in [deploy/README.md](deploy/README.md); the distribution
plan and its status in [docs/game-distribution-plan.md](docs/game-distribution-plan.md).
Server credentials stay on the operator's laptop (`~/secrets/scaleway.md`).
