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

Acceptance recorded; nothing activated.
