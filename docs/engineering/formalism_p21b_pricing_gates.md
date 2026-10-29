# P21-B — independent regulatory BDI and economic viability gates

Issue: [#21](https://github.com/brunolnetto/concilium/issues/21)  
Package PR: [#154](https://github.com/brunolnetto/concilium/pull/154)  
Stack: P19-C [#150] → P20-B [#151] → P20-C [#152] → P21-A [#153] → P21-B [#154].

## Regulatory BDI floor

A typed `RegulatoryBdiBasis` carries an exact positive denominator, currency, physical-scope fingerprint, explicit minimum rate, source and reference. The operational BDI on that basis is (P/C_{reg}-1). The regulatory gate is:

- `PASS` only when the currency and physical-scope fingerprint match the operational diagnostics and the calculated rate meets the explicit floor.
- `FAIL` when a comparable calculated rate is below the floor.
- `UNKNOWN` when the basis is missing or incomparable. Missing evidence never becomes a zero rate or a pass.

The catalog BDI diagnostic from P21-A is not substituted for this regulatory basis.

## Economic viability

Profitability is an independent gate. It requires (P>C_{tot}); if an explicit minimum margin is supplied, (mu=(P-C_{tot})/P) must also meet that threshold. A regulatory BDI pass cannot override a loss or a failed margin floor. Conversely, profitability cannot override a failed regulatory BDI floor.

Combined status is `FAIL` if either gate fails, `UNKNOWN` if no gate fails but any required gate is unknown, and `PASS` only when both pass. This is a preview eligibility signal, not a PROJECT_GO certificate.

## Input integrity and limits

The evaluator verifies exact arithmetic identities for direct + indirect = total, profit = price − total cost, realized margin, and equivalent markup. The regulatory denominator/floor and currency provenance must be explicit. It does not certify source fingerprints or replace P23's authoritative certificate; that remains downstream.

Authority: `P21_B_PRICING_GATES_PREVIEW_NOT_PROJECT_GO`.

## Focused verification

Not run on this branch's exact HEAD by the maintainer at authoring time:

```bash
uv run --python 3.14 pytest \
  tests/unit/application/scheduling/test_formalism_p21b_pricing_gates.py \
  tests/unit/application/scheduling/test_formalism_p21a_operational_pricing.py \
  tests/reference_formalism/test_formalism_execution_dag.py -q
```

GitHub Actions remains disabled per maintainer decision. P21-B does not close issue #21.
