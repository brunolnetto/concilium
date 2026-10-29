# P21-A — operational pricing and catalog comparison diagnostics

Issue: [#21](https://github.com/brunolnetto/concilium/issues/21)  
Package PR: [#153](https://github.com/brunolnetto/concilium/pull/153)  
Stack: P19-C [#150] → P20-B [#151] → P20-C [#152] → P21-A [#153].

## Canonical source of truth

The operational price (P) is derived from the P20 exclusive ledger through the explicit P20-C category BDI projection. Direct cost (C_D), indirect cost (C_{ind}), and total cost (C_{tot}) are read from that same ledger. The catalog amount (C_{cat}) is a separate typed benchmark with explicit source, reference, currency, and physical-scope fingerprint.

The output derives:

```text
P       = sum_c C_c * (1 + BDI_c)
C_D     = C_pool + C_cons
C_tot   = C_D + C_ind
profit  = P - C_tot
mu      = (P - C_tot) / P        if P > 0
beta_eq = P / C_tot - 1          if C_tot > 0
BDI_cat = P / C_cat - 1          only when comparison is valid and C_cat > 0
R       = C_tot / C_cat          only when comparison is valid and C_cat > 0
```

All values are exact `Fraction` objects; there is no hidden percentage, rounding, or second source of financial costs.

## Comparability contract

The catalog BDI and cost ratio are **diagnostics**, not regulatory BDI values. They remain `None` when currencies differ, the catalog and operational physical-scope fingerprints differ, or the catalog denominator is zero. The result records the reason and preserves operational cost, price, profit, margin, and equivalent markup independently.

Currency must be read from the resolved catalog metadata object, including its `catalog_metadata.json` provenance marker, and must be an uppercase ASCII three-letter code. A deterministic SHA-256 fingerprint binds the diagnostics to that canonical JSON metadata snapshot; independent currency/source scalar arguments are not accepted. No FX conversion is attempted. A matching fingerprint is caller-supplied evidence of equivalent physical scope; this module does not invent or infer it.

## Boundary with P21-B

P21-A does not decide regulatory-floor compliance, economic GO, or profitability acceptance. P21-B must treat regulatory BDI-floor comparison and (P > C_{tot})/margin as separate gates, with missing or incomparable inputs remaining undefined/not certified.

Authority: `P21_A_PRICING_DIAGNOSTICS_PREVIEW_NOT_PROJECT_GO`.

## Focused verification

Not run on this branch's exact HEAD by the maintainer at authoring time:

```bash
uv run --python 3.14 pytest \
  tests/unit/application/scheduling/test_formalism_p21a_operational_pricing.py \
  tests/unit/application/scheduling/test_formalism_p20c_bdi_category_pricing.py \
  tests/reference_formalism/test_formalism_execution_dag.py -q
```

GitHub Actions remains disabled per maintainer decision. P21-A does not close issue #21.
