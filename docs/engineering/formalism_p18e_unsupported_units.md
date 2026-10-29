# P18-E — fail-closed physical-unit registry boundary

Issue: [#18](https://github.com/brunolnetto/concilium/issues/18)

The dimensional conversion function must distinguish incompatible declared dimensions from units that the engineering registry does not support. Unsupported input previously leaked a raw KeyError from the internal conversion table. P18-E turns this into an explicit ValueError naming the unsupported unit, regardless of whether the unknown unit is the source or target.

This is a boundary-quality correction only: it does not add conversion factors, infer density, permit mass-volume conversion, or promote legacy monetary proxies to physical consumption. The registry remains intentionally finite.

## Focused verification

Not run on the exact PR head. Suggested command:

```bash
uv run --python 3.14 pytest \
  tests/unit/application/scheduling/test_formalism_p18b_acquisition_journal.py \
  tests/reference_formalism/test_formalism_execution_dag.py -q
```

CI remains disabled by maintainer decision. This package does not close issue #18 or authorize PROJECT_GO.
