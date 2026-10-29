# P20-B — exact financial event attribution and category balances

Issue: [#20](https://github.com/brunolnetto/concilium/issues/20)  
Package PR: [#151](https://github.com/brunolnetto/concilium/pull/151)  
Depends on P20-A [#84] and the P19-C receipt/acquisition contract in [#150](https://github.com/brunolnetto/concilium/pull/150).

## Purpose

Expose the authoritative P20 ledger through a source-attributed, weekly and category-level projection. P20-B does not post, reprice, allocate, or mark up costs. It makes the ownership of each existing event inspectable and conserves the exact project ledger.

## Ownership contract

Every ledger posting appears once in `ExactFinancialReconciliation.event_attribution`, with its stable `event_id`, typed nature, category, exact amount, source, week, and ownership scope:

- `ACTIVITY`: only a P18 MAT/COMB acquisition whose source evidence explicitly identifies the activity.
- `INSTANCE`: contractual active/idle and MOB/DEMOB events from the pool. The event ID retains the underlying instance/event identity.
- `GOOD`: physical acquisition or inventory-holding event whose owner is a stock good.
- `SOURCE`: other explicitly sourced indirect events without an evidenced activity/instance allocation.

Shared contractual K, mobilization and holding are **not** apportioned to activities by output share, elapsed weeks, or heuristic. This avoids charging a prolonged contract again at each activity and avoids inventing activity ownership where the ledger only proves project/resource-instance ownership.

## Exact projections

- `category_balances` aggregates the same postings by ISO week and exclusive category (`MO`, `EQ`, `MAT`, `COMB`, `IND`).
- `activity_attributable_consumables` includes only P18 acquisitions backed by explicit activity evidence. It is not a full activity cost and must not be presented as one.
- Every amount remains a `Fraction`; BDI is not applied here. P20-C owns category-specific BDI behavior.

## Invariants

1. Each event in the ledger appears once in the event trace.
2. Event-trace and weekly/category totals each equal `ledger.total` exactly.
3. Explicit activity-attributable consumables cannot exceed project consumable acquisitions.
4. No cost is created by the projection and no original event is modified.
5. Output remains `FINANCIAL_SOURCES_RECONCILED_PREVIEW_NOT_PROJECT_GO`; this is not a GO/NOGO certificate.

## Focused verification

Not run on this branch's exact HEAD by the maintainer at authoring time:

```bash
uv run --python 3.14 pytest \
  tests/unit/application/scheduling/test_formalism_p20a_financial_reconciliation.py \
  tests/reference_formalism/test_formalism_execution_dag.py -q
```

GitHub Actions remains disabled per maintainer decision. P20-B does not close issue #20; P20-C remains mandatory.
