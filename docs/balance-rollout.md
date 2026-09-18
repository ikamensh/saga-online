# WB-014 — The balance rules on the shared server

Started 2026-09-18 on Saga Online `569263f`, the third rollout of the day
after [engine 0.3.5](engine-035-rollout.md) and
[engine 0.3.7](engine-037-rollout.md). Ilya reviewed Warband's `balance` work
and asked for it on main; the balance session merged it (`4366789`, then
`faed307`: the mine cap, Master expanding when its mine fails, price and race
changes, the repair-cost fix, settled matches, re-measured difficulty ratings;
Warband's `BACKLOG.md` WB-014 and `docs/balance.md`). It changes
`warband/model.py`, `races.py`, `rules.py` and `worker_ai.py`, so the
authoritative contract moves and the publication gate has refused every
Warband build since 0.2.30
([promotion 35374587491](https://github.com/ikamensh/saga-online/actions/runs/35374587491)).
That session recorded the item as blocked on a server rollout; a note to it
was held for approval on its side, the review session confirmed nothing else
is on its way to main, and this session, which ran the two earlier rollouts,
runs this one. The candidate is Warband `faed307` (main `6623e5b` adds a
documentation commit), native run 35372085715. Saga2D 0.3.7, Tribes `8ff249c`,
Shardbound `f857599`, Sagaforge `10f4d87`, Python 3.13.2 and uv 0.12.10 stay
at their pins, accepted with the 0.3.7 cohort a few hours ago.

## Acceptance defined before rollout

1. Warband `faed307` has passed its Linux suite and its Windows and Mac
   native package checks on main; that native run is the one in the server
   pins. `tools/ci_compatibility.py` on it differs from the live contract in
   `model.py`, `races.py`, `rules.py` and `worker_ai.py` and in nothing else;
   the packages are unchanged.
2. Saga Online's suite runs on clean adjacent checkouts at the new pins; CI
   builds and reverifies the immutable archive as the Linux service account,
   and the locally built archive is identical.
3. Before activation: a fresh, verified off-host backup of the live rooms and
   a private rehearsal that resumes every retained seat on the candidate.
4. Activation through the existing installer only; the previous release
   `443319e9…` and the backup stay for rollback; the website pointer does not
   change during activation.
5. After activation: public health, the served attestation equal to the
   candidate's contract, the three-game smoke, every retained seat resumed on
   the live server, a native Warband online journey against the public
   server, `permessage-deflate` still negotiated through the proxy. Only then
   is the baseline recorded from the served attestation, the refused
   promotion dispatched again and the public downloads checked.

The stack's standing authorization applies; the
[deployment runbook](../deploy/README.md) gives the procedure.

## Status
