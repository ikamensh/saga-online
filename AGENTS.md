# Saga Online — agent notes

The hosted side of the Saga games (`~/saga/`, see `../AGENTS.md`): the
authoritative room server deployment on Scaleway, the release catalog, the
self-service website at https://games.tachyon-ai.eu/ and the operator tools.
This checkout uses the published `saga2d==0.3.12` release; all three games and
Sagaforge remain editable path dependencies. Changes to the sibling engine
checkout do not affect this environment. `.github/server-pins.json` records the
exact sibling commits, Python and uv required for a server package. Use separate
adjacent checkouts for those pins; do not reset another task's working trees.
The packaged process is `python -B deploy/server.py`; it verifies recorded source
and runtime inputs before serving game sockets and `/server-compatibility.json`.

Warband is the playable release. Tribes and Shardbound are demos: keep them
available when they work, but their gameplay checks are advisory and must not
block a Warband release. Do not fix demo regressions while releasing Warband
unless the user explicitly asks for that work.

## Commands

```bash
uv sync --locked --extra dev                                # exact pinned Python/uv and sibling checkouts required
uv run --locked pytest -q -m 'not demo'                     # Warband release gate, packaging, catalog and site
uv run --locked pytest -q -m demo                           # advisory demo checks
uv run python -m saga2d.server --games tribes.multiplayer:ONLINE warband.online.authority:ONLINE eador.multiplayer:ONLINE
uv run --project publishing --locked python tools/release_catalog.py releases/catalog.json # validate the catalog
uv run --project publishing --locked python tools/build_site.py --output dist/site # render the website from the catalog and website/content.py
uv run --project publishing --locked python -m pytest -q tests/test_release_catalog.py tests/test_build_site.py # static-site checks without the hosted games
uv run python tools/deploy_online.py plan --name saga2d-online       # offline; deploy / site / setup-*-ci perform the named operation
gh workflow run server-rollout.yml -R ikamensh/saga-online           # the automatic server rollout, by hand (normally a refused promotion starts it)
SAGA2D_SILENT=1 uv run python tools/verify_online.py /tmp/online     # native create/join/rejoin journeys for every game
uv run python tools/load_online.py wss://games.tachyon-ai.eu/play warband --rooms 4
uv run python tools/verify_room_seats.py wss://games.tachyon-ai.eu/play  # a three-seat Warband room fills, starts, refuses a client without seats
```

## Layout

- `publishing/` — a separate locked environment for catalog/site checks and
  static-site publication; it installs no sibling game sources. Use it for
  website work independently of the room server's exact engine/game pins.
- `deploy/` — `prepare_release.sh` (verified immutable runtime and Warband
  order/restart/rejoin acceptance), `install.sh` (activation with rollback, and
  `--rollback` to `previous`), `server_ci.py`/`install_server_ci.py` (the
  restricted server-CI account: status, backup, install, rollback),
  `server.py`/`runtime.py` (live attestation), the systemd units, `Caddyfile`
  (TLS; `/play`, `/healthz` and `/server-compatibility.json` proxied),
  `cloud-init.yaml`, `check_release.py`/`smoke.py`, `backup.py`; `deploy/README.md`
  is the operations runbook.
- `tools/deploy_online.py` — plan, bootstrap-project, provision, package,
  deploy (first deployment and host changes), site, setup-site-ci and
  setup-server-ci against the dedicated Scaleway project; credentials come
  from `~/secrets/scaleway.md` (section `saga2d-deploy`) and never leave the laptop.
- `.github/workflows/server-rollout.yml` and `tools/server_rollout.py` — the
  automatic server rollout: newest Warband release, moved pins, the full suite
  and one archive (`tests.yml`), backup, rehearsal, activation, public and native
  checks, automatic rollback, and a machine record under `releases/rollouts/`
  with the new baseline. A promotion refused for the server baseline starts it.
  Agents do not run rollouts by hand; see `deploy/README.md`.
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
- `tools/win_desktop.py` and `tools/win_box/` — an interactive Windows desktop
  of any size and scaling on a throwaway Scaleway box, opened, used and closed
  from this laptop with no typed login (`docs/windows-test-box.md`).
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
- A Warband server refresh must run the exact published Warband source and pass
  Warband's packaged and public create/join/rejoin checks. Demo gameplay is
  advisory; do not repair Tribes or Shardbound just to release Warband. The
  shared server still carries their pinned code and data when it works.
- Clear exceptions over silent fallbacks. Delete rather than deprecate.
  Commit each working increment.
