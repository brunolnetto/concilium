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


## P22-C — Bounded independent finance, inventory and fungible assignment

`financial_reference.py` implements `formalism-financial/1` without importing
production finance, scheduling, persistence or billing services. Inputs are
strict exact decimal strings and explicitly proven contract/good identifiers.
It exhaustively enumerates all labeled weekly physical instance assignments
(up to three instances and six weeks), then enumerates allowable keep/split
decisions for each chain. This is intentionally **stronger** than the fixed
height-layer oracle used by P16: for `d=(2,1,1,2)`, active 5, idle 1,
movement 30, max idle gap 1, reference cost is **92**, not **120**.

It separately computes active/idle K, physical MAT/COMB acquisitions V, mobility
events, weekly stock holding, order fees (IND), category-specific single-pass
BDI, total unmarked cost and realized selling-price margin. All inputs have
explicitly checked units, price/rate sources and unique purchase event IDs;
negative inventory, double acquisition IDs, unknown fields and binary floats
fail closed. Three hand-checkable vectors appear in
`vectors/financial_cost_v1.json` and tests in `test_p22c_financial_oracle.py`.

**Scope limitation:** The tiny reference is an exact bounded accounting and
pool-assignment witness for the declared input. It does not establish
actual procurement, price provenance, legal contract admissibility,
multi-good stock optimality, cash-flow timing, or production implementation
parity. A positive margin alone does not establish `PROJECT_GO`. P16's
optimality falsifier remains open as issue #16.
