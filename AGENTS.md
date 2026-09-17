# Saga Online — agent notes

The hosted side of the Saga games (`~/saga/`, see `../AGENTS.md`): the
authoritative room server deployment on Scaleway, the release catalog, the
self-service website at https://games.tachyon-ai.eu/ and the operator tools.
This checkout uses the published `saga2d==0.3.2` release; all three games and
Sagaforge remain editable path dependencies. Changes to the sibling engine
checkout do not affect this environment. `.github/server-pins.json` records the
exact sibling commits, Python and uv required for a server package. Use separate
adjacent checkouts for those pins; do not reset another task's working trees.
Shardbound's pinned engine-alignment candidate is not yet accepted on its main.
The packaged process is `python -B deploy/server.py`; it verifies recorded source
and runtime inputs before serving game sockets and `/server-compatibility.json`.

## Commands

```bash
uv sync --locked --extra dev                                # exact pinned Python/uv and sibling checkouts required
uv run --locked pytest -q                                   # packaging, catalog, site and load checks (spawns real servers)
uv run python -m saga2d.server --games tribes.multiplayer:ONLINE warband.authority:ONLINE eador.multiplayer:ONLINE
uv run --project publishing --locked python tools/release_catalog.py releases/catalog.json # validate the catalog
uv run --project publishing --locked python tools/build_site.py --output dist/site # render the website from the catalog and website/content.py
uv run --project publishing --locked python -m pytest -q tests/test_release_catalog.py tests/test_build_site.py # static-site checks without the hosted games
uv run python tools/deploy_online.py plan --name saga2d-online       # offline; deploy / site / backup perform the named operation
SAGA2D_SILENT=1 uv run python tools/verify_online.py /tmp/online     # native create/join/rejoin journeys for every game
uv run python tools/load_online.py wss://games.tachyon-ai.eu/play warband --rooms 4
```

## Layout

- `publishing/` — a separate locked environment for catalog/site checks and
  static-site publication; it installs no sibling game sources. Use it for
  website work independently of the room server's exact engine/game pins.
- `deploy/` — `prepare_release.sh` (verified immutable runtime and three-game
  order/restart/rejoin acceptance), `install.sh` (activation with rollback),
  `server.py`/`runtime.py` (live attestation), the systemd units, `Caddyfile`
  (TLS; `/play`, `/healthz` and `/server-compatibility.json` proxied),
  `cloud-init.yaml`, `check_release.py`/`smoke.py`, `backup.py`; `deploy/README.md`
  is the operations runbook.
- `tools/deploy_online.py` — plan, bootstrap-project, provision, package,
  deploy, site, backup against the dedicated Scaleway project; credentials come
  from `~/secrets/scaleway.md` (section `saga2d-deploy`) and never leave the laptop.
- `tools/server_package.py` — copies tracked files from clean pinned Git commits
  and the verified PyPI engine wheel; records their inventory and locked runtime.
  Packaging requires clean inputs, including this repo. The read-only Tests
  workflow uses the pinned stack and exercises preparation on Ubuntu 24.04.
- Server/site activation share `/var/lock/saga2d-online.publish.lock`.
  Automated Warband promotion requires its verified receipt; explicit operator
  mode is for the trusted operator. A pending site transaction blocks server
  activation until site recovery. `tests/host_deployment_exclusion.py` exercises
  the real host entry points only as root on an isolated GitHub Linux runner;
  never run it on the production host.
- `tools/site_publish.py` — CI's host-key-pinned SSH status/publish client.
  `deploy/site_receiver.py` accepts website data and a required promotion
  receipt, executing only operator-installed activation code. Install/update
  that code and the dedicated unprivileged account through
  `tools/deploy_online.py setup-site-ci --name saga2d-online --site-public-key PATH`.
  `tests/host_site_ssh.py` exercises real SSH on a disposable Linux host; never
  run it on production. See `deploy/README.md` for credentials and protocol limits.
- `tools/prepare_warband_site.py` and `tools/apply_warband_promotion.py` — stable
  upload preparation and the Git-to-SSH publication transaction used by
  `.github/workflows/warband-promotion.yml`. A catalog commit is desired state,
  never proof of site acceptance. Retrying an already-current catalog must
  still verify/activate the site. `docs/warband-ci-publication.md` records the
  completed live acceptance, credentials and retry/disable/rollback procedure.
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

- Saga is AI-owned and currently has no users. Agents have standing user
  authorization for releases, deploys, server refreshes, VM changes, site
  publishes and CI publishing credentials/settings; no further go-ahead is
  needed. Verify the candidate, compatibility and rollback path, then proceed
  and record the result (`plan` and `package` are offline).
- After any game release: update `releases/catalog.json`, validate it, rebuild
  and publish the site; never overwrite a versioned binary. Downloads are
  GitHub Releases on the game repos.
- A server refresh must ship the game versions the published clients expect
  (protocol and game ids in the catalog); check with `deploy/smoke.py` and a
  public three-game create/join before calling it done.
- Clear exceptions over silent fallbacks. Delete rather than deprecate.
  Commit each working increment.
