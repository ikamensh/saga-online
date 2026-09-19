# WB-041 — Warband's folders on the shared server

Started 2026-09-19 on Saga Online `039d698`, after
[WB-045](wb045-rollout.md). Warband's WB-041 moves its flat modules into
folders: `sim/`, `online/`, `brains/`, `league/`, `records/`, `art/`,
`audio/`, `ui/` and `story/` (Warband's `BACKLOG.md` and `AGENTS.md`). It is
a move and nothing else. The simulation fingerprint and the replays are
unchanged, and no rule, order or snapshot differs. But the authoritative
contract hashes file paths, and its registry moves from
`warband.authority:ONLINE` to `warband.online.authority:ONLINE`. So every
file of the contract changes name, and Saga Online's own code changes with
it: the registries it loads and rehearses with, the runtime attestation and
the promotion gate that check the registry, and the tools and installer
that start `warband.online.online_ai`. Saga2D 0.3.8, Tribes `4c13383`,
Shardbound `b2cdcbe`, Sagaforge `e099051`, Python 3.13.2 and uv 0.12.10 stay
at their pins.

## Acceptance defined before rollout

1. The Warband main commit that merges WB-041 has passed its Linux suite and
   its Windows and Mac native package checks; that native run is the one in
   the server pins. `tools/ci_compatibility.py` on it names the registry
   `warband.online.authority:ONLINE`. Every file in its contract is a file of
   the live contract (`3e324a4f…`) moved, and changed only where it names
   another module in an import or a path. The exceptions are the new
   folders' `__init__.py`, each a docstring alone, and the package's own
   docstring. The packages are unchanged.
2. The same two-seat match, played by the live release (`6ad2779`) and by the
   candidate with a brain on each seat, gives identical snapshots for both
   seats and identical checkpoints all the way. A checkpoint either release
   writes restores on the other and plays on.
3. Saga Online's suite runs on clean adjacent checkouts at the new pins, with
   every reference to the old module names changed. CI builds and
   reverifies the immutable archive as the Linux service account, and the
   locally built archive is identical.
4. Before activation: a fresh, verified off-host backup of the live rooms and
   a private rehearsal that resumes every retained seat on the candidate.
5. Activation through the existing installer only; the previous release
   `db6c4681…` and the backup stay for rollback; the website pointer does not
   change during activation.
6. After activation: public health, and a served attestation that equals the
   candidate's contract under the new registry. Then the three-game smoke,
   every retained seat resumed on the live server, and a native Warband
   online journey against the public server. Then `permessage-deflate` still
   negotiated through the proxy, a three-seat Warband room on the public
   server, and the remote AI's module starting from the live release. Only
   then is the baseline recorded from the served attestation, the refused
   promotion dispatched again and the public downloads checked. The stack
   root's `make server` and the other repositories' mentions follow the new
   names.

The stack's standing authorization applies; the
[deployment runbook](../deploy/README.md) gives the procedure.

## Status

**Accepted live server, 2026-09-19 05:12 UTC.** Warband `62e4970` (the merge
of WB-041's `3e459ab`, `dbae175` and `178f034`) passed
[Tests 35422242847](https://github.com/ikamensh/warband/actions/runs/35422242847)
and [native package checks 35422242848](https://github.com/ikamensh/warband/actions/runs/35422242848)
(run number 92, Windows and Mac). Its contract,
`c7462b6726ba…`, names the registry `warband.online.authority:ONLINE`. Every
one of its files is a file of the live contract (`3e324a4f…`) moved, and
every changed line names a module in an import or a path: `authority` 8,
`model` 22, `settlement` 24, `worker_ai` 12, `mapgen`, `rules` and
`worker_knowledge` 6 each, `races` 4, `path` 2. The new files are the
docstrings of `warband/`, `warband/sim/` and `warband/online/`, and the
packages and Python are unchanged. Saga Online's lock took one line,
Warband's `hypothesis` dev extra from WB-042. Saga Online `ad81670` passed
its suite locally at the new pins (146 tests) and in CI:
[Tests 35422844570](https://github.com/ikamensh/saga-online/actions/runs/35422844570)
and [Website checks 35422844560](https://github.com/ikamensh/saga-online/actions/runs/35422844560).
The archive CI built is the one activated, identical to the local one:
`3e3dfda812ef038e196c89e531ab7bed16153a468e66ea74ab4063efc7f793c7` (333
files).

The same two-seat match (seed 7, 64×48, a Hard brain on each seat) played
3,000 steps by the live release's authority and by the candidate's gives the
same snapshots for both seats and the same checkpoint every 600 steps. The
checkpoint either one wrote, restored by both and played 3,000 steps more,
ends the same on both (criterion 2).

Before activation: the off-host backup `rooms-20260919T050622Z.sqlite3`
(SHA-256 `4b198413…`) and its private rehearsal. All 32 retained seats, in 16
Shardbound rooms, resumed on the candidate. `deploy_online.py deploy`
prepared the archive as the service account and activated it at 05:07 UTC.
The previous release `db6c4681…` stays at the `previous` pointer with its
backups, and the website pointer did not move.

After activation:
- `/healthz` is `ok`.
- The served attestation names deployment `3e3dfda8…`, Warband `62e4970`,
  the registry `warband.online.authority:ONLINE` and the candidate's
  contract.
- `deploy/smoke.py` passed create, join and order for all three games.
- `permessage-deflate` is negotiated through the public proxy.
- All 32 retained seats resumed on the live server with their own tokens.
- A three-seat Warband room filled in order, started with 3 of 3, and
  refused a client from before 0.3.8.
- `python -m warband.online.online_ai --help` starts from the live release.
  No remote AI instance is deployed; its installer runs the same check.
- The native Warband journey (create, room-code join, accepted gameplay,
  restart and rejoin against the public server) failed first, in the tool:
  `verify_online` and `verify_multiplayer` built `warband.style` and
  `warband.title` from the game's name. `849706e` looks them up in
  `warband.ui` and adds the test that would have caught it. The journey then
  passed. Its frames are under `docs/evidence/wb041-rollout/public/`, and I
  looked at them: the orc seat's own corner with its hall, peons and the
  painted mine, the rest fogged, and the same match after the rejoin.

The served attestation is the new
[`releases/server-baseline.json`](../releases/server-baseline.json)
(`013387b`). The promotion of `62e4970`'s publication ran at 04:58, before
the activation, and was refused as designed ("Unsupported compatibility
contract": saga-online main still expected the old registry).

**Promotion accepted, public downloads checked, 2026-09-19 05:16 UTC.**
[Promotion 35423390470](https://github.com/ikamensh/saga-online/actions/runs/35423390470),
dispatched again for release `391920017` (native run 35422242848, manifest
`de96737e…`) once saga-online main and the baseline had moved, was accepted
and published the catalog for Warband 0.2.67.
[Public download checks 35423450265](https://github.com/ikamensh/saga-online/actions/runs/35423450265)
passed on Windows and macOS. This completes the rollout. The stack root's
`make server`, Saga2D's and Tribes' docs follow the new names.
