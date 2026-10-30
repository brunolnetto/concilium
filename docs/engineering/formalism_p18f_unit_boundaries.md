# P18-F — validate every physical-unit model boundary

Issue: [#18](https://github.com/brunolnetto/concilium/issues/18)

P18-E made `convert_physical` fail closed for unknown source and target units. The same unit registry was still called directly by `PhysicalConsumptionRate` and `PhysicallyPricedGood`; constructing those public value objects with an unsupported good, activity, or price unit could therefore leak a raw registry exception before conversion was reached.

P18-F centralizes normalization and validation in `_normalize_physical_unit` and applies it to conversion inputs, the good unit, delivered activity unit, and price unit. Every boundary rejects unsupported units with a domain `ValueError`; the supported dimensional conversion factors and exact `Fraction` arithmetic remain unchanged.

Regression coverage includes unknown source and target conversion units, unknown good units, unknown activity units, and unknown price units. It does not add units, infer physical dimensions, or authorize currency/physical proxy conversion.

## Verification

Exact-head tests have not been run in this session. CI remains disabled by maintainer decision. Suggested focused gate:

```bash
uv run --python 3.14 pytest \
  tests/unit/application/scheduling/test_formalism_p18b_acquisition_journal.py \
  tests/reference_formalism/test_formalism_execution_dag.py -q
uv run --python 3.14 ruff check src/concilium/application/scheduling/physical_consumption_rates.py tests/unit/application/scheduling/test_formalism_p18b_acquisition_journal.py tests/reference_formalism/test_formalism_execution_dag.py
```

P18-F does not close issue #18 and does not authorize PROJECT_GO.
