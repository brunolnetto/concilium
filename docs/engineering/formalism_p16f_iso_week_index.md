# P16-F — one absolute ISO-week index for economic and physical gaps

Issue: [#16](https://github.com/brunolnetto/concilium/issues/16)  
Package PR: [#161](https://github.com/brunolnetto/concilium/pull/161)

The Skill 05 opportunity preprocessor previously reduced ISO dates such as 2026-W48 to week number 48, while the pool-demand/contract path used an absolute week index. This makes temporal gaps incorrect at ISO-year boundaries and can cause the economic comparison and contract chain builder to disagree.

P16-F introduces one shared parser for ISO weeks, anchored at 2000-W01. Both paths now use the same absolute integer index. Invalid ISO weeks such as 2021-W53 fail explicitly rather than silently becoming zero. Legacy S### benchmark indices retain their existing semantics and are not implicitly converted into ISO dates.

This establishes calendar-index consistency only; it does not prove the whole schedule/pool/finance problem globally optimal or certify PROJECT_GO.

Validation was not run on this exact head. GitHub Actions remains disabled by maintainer decision.

Suggested validation:

```bash
uv run --python 3.14 pytest \
  tests/unit/application/scheduling/test_adr078_pre_processamento.py \
  tests/reference_formalism/test_formalism_execution_dag.py -q
```
