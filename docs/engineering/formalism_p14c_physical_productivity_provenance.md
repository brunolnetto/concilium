# P14-C — Physical productivity provenance at the Skill 04 boundary

**Status:** preparatory W2 draft; **issue:** #14; **parent epic:** #8.
This work does not close W1 #25, which requires GitHub server-side branch protection; the repository owner declined to purchase an eligible GitHub plan. No change to that acceptance condition and no `PROJECT_GO`.

## Intent and fail-closed semantics

`run_cronograma(inputs={"certification_intent": "PREVIEW" | "CERTIFIED"})` defaults to `PREVIEW` for backward compatibility. Unknown values return `VAL-CRON-CERT-INTENT` in `ERRO` status.

- `PREVIEW` can evaluate an arbitrary missing-CPU fallback such as `P=1000`, but any unverified physical rate marks the schedule `is_feasible=False` and adds `VAL-CRON-PROD-PREVIEW`; previously cached financial and analytic projections are cleared. It is never a certified price.
- `CERTIFIED` requires a real referenced production graph (`grafo_sinergia`), nonempty versioned `source_id/fonte` and `source_version/versao`, and absence of `cpu_meta.producao_horaria` and legacy `valor_horario` overrides. Missing provenance returns `VAL-CRON-PROD-CERT` with no authoritative schedule or derived finances, even when the raw numeric rate is positive.
- Any explicitly provided physical rate of zero, negative, NaN, infinite, boolean or nonnumeric returns `VAL-CRON-PROD-INVALID` **before** running the MANUAL/AUTO physical scheduler. No exception is reinterpreted as a successful outcome.
- The latest canonical for an invalid/rejected run clears `resultado`, `resultado_reconciliado`, point-of-equilibrium and analytical cubes, along with cached schedule-dependent derivatives. Never combine a newly invalid preview schedule with an old profitable financial report.

Source identity and graph presence are admission conditions, not third-party verification of the catalog graph, calibrated F(m), global RCPSP optimum or project financial GO. Independent certification and persistence still belong to #23; exact fungible resource optimum is separately falsified in #16.

## Adversarial checks

`tests/unit/application/skills/test_formalism_p14b_schedule_gate.py` invokes the real Skill 04 with:
- no CPU/prod source and explicit CERTIFIED versus PREVIEW;
- identical numeric rates with `valor_horario` versus `producao_horaria` and no graph/source;
- physical rates 0, -1, NaN and infinity;
- pre-populated prior `resultado`, `resultado_reconciliado`, `ponto_equilibrio`, `cubo_analitico`, `s_curve` and `plan_space_result`.

A green CI confirms local regressions only. The W2 wave is not declared complete, and the W1 #25 server-side required-status-check gap remains recorded.
