# Saga Online — agent notes

The hosted side of the Saga games (`~/saga/`, see `../AGENTS.md`): the
authoritative room server deployment on Scaleway, the release catalog, the
self-service website at https://games.tachyon-ai.eu/ and the operator tools.
This repo uses the published `saga2d==0.2.0` release; all three games and
Sagaforge remain editable path dependencies. Changes to the sibling engine
checkout do not affect this environment. The server process is
`python -m saga2d.server --games tribes.multiplayer:ONLINE
warband.multiplayer:ONLINE eador.multiplayer:ONLINE`.

## Commands

```bash
uv sync --extra dev
uv run pytest -q                                            # packaging, catalog, site and load checks (spawns real servers)
uv run python -m saga2d.server --games tribes.multiplayer:ONLINE warband.multiplayer:ONLINE eador.multiplayer:ONLINE
uv run python tools/release_catalog.py releases/catalog.json # validate the catalog
uv run python tools/build_site.py dist/site                 # render the website from the catalog and website/content.py
uv run python tools/deploy_online.py plan --name saga2d-online       # offline; deploy / site / backup perform the named operation
SAGA2D_SILENT=1 uv run python tools/verify_online.py /tmp/online     # native create/join/rejoin journeys for every game
uv run python tools/load_online.py wss://games.tachyon-ai.eu/play warband --rooms 4
```

## Layout

- `deploy/` — `install.sh` (release activation with rollback), the systemd
  units, `Caddyfile` (TLS; `/play` and `/healthz` proxied, everything else is
  the static site), `cloud-init.yaml`, `check_release.py`/`smoke.py` (every
  game's create/join path before activation), `backup.py`; `deploy/README.md`
  is the operations runbook.
- `tools/deploy_online.py` — plan, bootstrap-project, provision, package,
  deploy, site, backup against the dedicated Scaleway project; credentials come
  from `~/secrets/scaleway.md` (section `saga2d-deploy`) and never leave the laptop.
- `releases/catalog.json` — the single source of release facts (versions,
  download URLs, hashes, minimum client protocol); games fetch it when
  Multiplayer opens, the server rejects incompatible clients.
- `website/` — copy, curated screenshots (`website/media/`), templates and
  static files; `tools/build_site.py` renders it. `.claude/launch.json` serves
  `dist/site` for a browser preview.
- `tools/remote_warband_ai.py` — a headless Warband AI client on a separate VM
  as a real remote opponent (`docs/warband-remote-ai.md`).
- `docs/game-distribution-plan.md` — the distribution plan and its status.

## Rules

- Deploys, server refreshes, VM changes and site publishes are outward-facing:
  confirm with the user before performing them (`plan` and `package` are offline).
- After any game release: update `releases/catalog.json`, validate it, rebuild
  and publish the site; never overwrite a versioned binary. Downloads are
  GitHub Releases on the game repos.
- A server refresh must ship the game versions the published clients expect
  (protocol and game ids in the catalog); check with `deploy/smoke.py` and a
  public three-game create/join before calling it done.
- Clear exceptions over silent fallbacks. Delete rather than deprecate.
  Commit each working increment.
