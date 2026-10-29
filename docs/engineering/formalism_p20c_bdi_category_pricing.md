# P20-C — exact category-specific BDI, once only

Issue: [#20](https://github.com/brunolnetto/concilium/issues/20)  
Package PR: [#152](https://github.com/brunolnetto/concilium/pull/152)  
Stack: P19-C [#150] → P20-B [#151] → P20-C [#152].

## Contract

P20-C applies explicitly supplied BDI rates to the existing P20 ledger, once per exclusive category. Required categories are `MO`, `EQ`, `MAT`, `COMB`, and `IND`. Every rate must be an exact nonnegative `Fraction`; a missing, extra, float, or negative rate fails closed. A zero rate is valid only when explicitly supplied.

For each category (c):

```text
C_c      = sum(event.amount for event.category == c)
BDI_c    = C_c * rate_c
P_c      = C_c + BDI_c
P        = sum(P_c) = sum(C_c) + sum(BDI_c)
```

No category is recursively marked up. MOB/DEMOB and inventory holding remain in `IND` as classified by the source ledger; this package does not reclassify them. All calculations remain exact fractions and no cent rounding is introduced.

## Reconciliation with Skill 04

`ExactFinancialReconciliation.project_skill04_realization` compares the existing P11-B realized projection's total and weekly `price_once_bdi` against the independent P20 category calculation. If a P20-B event-attribution trace is present, it must match the authoritative ledger exactly before pricing. Direct P20-C pricing requires that trace by default; the legacy P11 Skill04 preview path may still price an explicitly supplied immutable ledger without a trace, but makes no ownership claim and remains preview-only. A forged trace, missing rate, unclassified event, or weekly discrepancy fails closed.

## Limits

The output is `P20_C_CATEGORY_BDI_PREVIEW_NOT_PROJECT_GO`. It is not a certified proposal price, tax opinion, or GO/NOGO certificate. P20-C does not close issue #20; remaining acceptance criteria and downstream certification remain separate.

## Focused verification

Not run on this branch's exact HEAD by the maintainer at authoring time:

```bash
uv run --python 3.14 pytest \
  tests/unit/application/scheduling/test_formalism_p20c_bdi_category_pricing.py \
  tests/unit/application/scheduling/test_formalism_p20a_financial_reconciliation.py \
  tests/reference_formalism/test_formalism_execution_dag.py -q
```

GitHub Actions remains disabled per maintainer decision.
