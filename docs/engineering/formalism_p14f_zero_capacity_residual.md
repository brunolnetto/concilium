# P14-F — preserve exact residual at zero productivity

Issue: [#14](https://github.com/brunolnetto/concilium/issues/14)

When the remaining real calendar has zero productivity, the duration search previously refused to materialize the best profile because its total capacity was not strictly positive. That discarded a physically meaningful witness: all actual weeks deliver zero, and the required quantity remains unmet in full.

P14-F materializes the best profile even when its capacity is zero. The normal closure gate remains authoritative and must fail closed with Q, sum(q)=0 and residual=Q. No synthetic production, extra week, or feasibility claim is introduced.

Validation was not run on this exact head. GitHub Actions remains disabled by maintainer decision. Suggested command:

```bash
uv run --python 3.14 pytest \
  tests/unit/application/skills/test_schedule_extension_quantitativo.py \
  tests/reference_formalism/test_formalism_execution_dag.py -q
```

P14-F does not close issue #14 or authorize PROJECT_GO.
