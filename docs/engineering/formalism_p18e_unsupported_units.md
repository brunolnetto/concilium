# P18-E — reject unsupported physical units explicitly

Issue: [#18](https://github.com/brunolnetto/concilium/issues/18)  
Package PR: [#159](https://github.com/brunolnetto/concilium/pull/159)

The physical-consumption conversion boundary must reject unsupported units with a domain-level error naming the source or target unit. Unknown units must not leak a raw `KeyError`, be normalized into a fabricated conversion, or silently produce a cost.

This is a boundary-quality correction only. It does not add conversion factors, infer density, permit mass-volume conversion, or promote legacy monetary proxies to physical consumption. The registry remains intentionally finite.

The tests cover an unsupported source unit and an unsupported target unit. They assert an explicit `ValueError` rather than an implementation-level lookup exception.

Validation was not run on this exact head. GitHub Actions remains disabled by maintainer decision.

Suggested validation:

```bash
uv run --python 3.14 pytest \
  tests/unit/application/scheduling/test_formalism_p18b_acquisition_journal.py \
  tests/reference_formalism/test_formalism_execution_dag.py -q
```

P18-E does not close issue #18 or authorize PROJECT_GO.
