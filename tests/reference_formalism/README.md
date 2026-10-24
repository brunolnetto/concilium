# P22-A — Independent formalism reference protocol

This test package is deliberately independent of `concilium` production
modules, schedulers, cost helpers, and persisted report fixtures.

**Run (isolated from the repository-wide `tests/conftest.py`):** `python -m pytest --confcutdir=tests/reference_formalism tests/reference_formalism -q`

## Inputs, expected results and provenance

The file `vectors/scalar_baseline_v1.json` pins two small *manually*
computable scalar cases. Inputs and expected decimal results are represented
as **strings**, not binary JSON floating-point values. Unsupported protocol
versions, unknown fields, NaN/Inf, nonproductive activity, zero productivity,
negative costs and impossible partial-week closure must fail.

- `scope_total - quantity_before_final_week`: delivered in final week
- Contractual `K_final = contractual_rate_per_team_hour * hours_per_week * team_count`
- Consumable `V_final = variable_rate_per_team_hour * q_final / productivity_per_team_hour`
- `V_total = variable_rate_per_team_hour * Q / productivity_per_team_hour`
- `scope_residual = Q - (prior + q_final) = 0`

**Assumptions:** single-team hourly rate, no waste/idle variable consumption,
full-week K payment even when the final Q is fractional. No markups, no graph
normalization, no inventory holding. These are explicitly *not* proofs of
general numerical conformance.

P22-B will add corrected productivity, calendar and precedence mathematics.
P22-C will add independent pool/stock/BDI references and brute-force witnesses.
Never generate expected outputs from production code. Changes to the reviewed
formalism require explicit provenance and updated hand-checkable vectors.

**Related:** #8, #9–#13, #22.

## Arithmetic invariant (post-review)

All accepted input values are exact decimal strings converted to Python `Fraction`;
no arithmetic uses the mutable `decimal.getcontext().prec` setting. Rational
answers with a finite decimal expansion are serialized exactly. Nonterminating
rational answers fail closed with `ReferenceContractError` until a separately
versioned rational-output contract is adopted. Golden comparison is rational
and exact; a 29-digit perturbation is detected rather than rounded away.

## P12-B: bounded physical-schedule feasibility oracle

`calendar_rcpsp_oracle.py` is an independent exact-`Fraction` enumerator
for at most seven activities across at most twelve absolute weeks. It
implements quantity-based end-of-week Q–FS releases, nonnegative integer
lags, weekly practicability/calendar/journey, full-week physical-resource
occupancy even when output is zero, and exhaustive start-time enumeration.

The associated `test_calendar_rcpsp_oracle.py` falsifies a previously unsafe
post-solver shift: two successors released after a rainy predecessor must
not simultaneously claim one unit of the same scarce resource. With a
sufficient horizon, the oracle deterministically moves one successor;
without enough weeks, it returns infeasible rather than certifying a
contradictory schedule.

These reference fixtures **do not** establish equivalence of production
`04-cronograma` or certify #14/#15; those require integration tests against
the actual scheduler and persisted certificates. The oracle is a
deterministic independent witness for those future tests.

## P22-B — Independent physical graph/calendar/Q–FS oracle

\`physical_reference.py\` implements an executable reference, separate from
production runtime and separate from P22-A's scalar costing baseline.

- **Graph:** bounded exact rational directed max flow (Edmonds–Karp);
  edges declare \`fixed\` bottleneck or \`per_front\` physical capacity.
  No multiplicative \`eta_s\` based on unused fronts.
- **Schedule:** absolute-week weather and performance factors; trapezoidal
  front ramp depending on candidate duration; enumerated starts/durations
  and cumulative Q–FS end-of-week release with nonnegative lag.
- **Physical constraints:** full-week resource occupancy even if weather gives
  zero production, exact scope closure and last productive-week fraction;
  deterministic minimum makespan and lexicographic tie-break.
- **Bounds:** up to five activities, ten weeks, 12 nodes/24 edges per graph,
  and 50,000 search states. Exhausting a bound raises an explicit error,
  *not* a claim of global infeasibility.
- **Numerics:** exact Fraction from decimal-string inputs; only terminating
  decimal output is admitted by the existing reference protocol. Time indices
  and fleet counts are integers, all capacities/quantities are physical.
- **Contract:** \`formalism-physical/1\` in
  \`vectors/physical_calendar_v1.json\`, pinned to the reviewed LONGO blob;
  five hand-checked cases: 2-of-4 independent fronts, a shared bottleneck,
  1→2→2→1 ramp/partial final week, rain-delayed 75%-quantity release, and
  scarce-resource contention after Q–FS release.
- **Falsification:** wrong front multiplier, premature Q-release, omitted
  ramp, weather out of range, impossible horizon, resource collisions and
  graph-flow/cut inconsistency.

No production package, solver, persisted run, finance helper or production
fixture is imported into the oracle. It is intentionally restricted to tiny
instances. Results demonstrate a reference feasible/optimal bounded schedule
for its *declared simplified problem*, not a general RCPSP optimality claim
for Skill04, a P16 economic pool minimum, or PROJECT_GO. P22-C must add
physically priced K/V/IND, consumable sources, stock and pricing oracles.

## P22-C — Independent economic ledger and exhaustive fungible-instance oracle

\`economic_reference.py\` (protocol \`formalism-economic/1\`) completes the
reference path for tiny fixed demand profiles without importing P16/P17/P18/P19:

- Enumerates **all weekly assignments of physical demand to up to three
  fungible instances**, and all feasible keep/split bridges, each checked
  against maximum idle gap and explicit off-hire weeks. Minimizes
  \(K^{active}+K^{idle}+\mathrm{MOB/DEMOB}\), with fewest transitions as tie-break.
  This is stronger than the existing P16 fixed-height-layer witness: the
  independent 4-week case d=(2,1,1,2) costs **92**, while P16's fixed layers
  cost 120. P16 global optimality remains OPEN at #16.
- Acquires measured MAT/COMB in physical units under the three named
  consumption regimes, with separate physical rate, price and loss/idle
  provenance. Supports exact g↔kg and mL↔L order conversion, and rejects
  cross-dimension or unpriced stock instead of assuming free inventory.
- Reconstructs physical inventory from orders plus lead time; checks
  nonnegative weekly stock, end-to-end quantity reconciliation, holding
  and ordering expenses. This bounded ledger currently requires zero
  initial and final stock; valuation of carry-in stock is NOT_EVALUATED.
- Separates exactly-once K (EQ/MO), V (MAT/COMB) and IND (MOB/DEMOB,
  inventory holding, orders and weekly indirect) and applies BDI to each
  category once. Emits deterministic posting IDs and a signed margin,
  without automatically certifying PROJECT_GO.
- Four versioned, manually verifiable goldens in
  \`vectors/economic_reconciliation_v1.json\`: discounted standby with
  measured fuel losses (K=250,V=1100,IND=80,total=1430), full-rate with
  60,000 mL converted to 60 L and nonzero holding/BDI,
  explicit off-hire, and the independent fungible 92-versus-120 falsifier.

The bounded exhaustive reference is not a replacement for the production
multi-resource RCPSP or a full inventory cost-flow valuation system. Cases
outside its explicit assumptions fail closed instead of inheriting P16/P18
numeric defaults. The W1 issue #22 can close only after accepted golden
coverage, code review, CI, and an independently verified production-result
comparison, not because all three PR numbers are registered.
