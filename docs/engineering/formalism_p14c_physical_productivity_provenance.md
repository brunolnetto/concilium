# P14-C — Physical productivity provenance at the Skill 04 boundary

**Status:** preparatory W2 draft; **issue:** #14; **parent epic:** #8.
This work does not close W1 #25, which requires GitHub server-side branch protection; the repository owner declined to purchase an eligible GitHub plan. No change to that acceptance condition and no `PROJECT_GO`.

## Intent and fail-closed semantics

`run_cronograma(inputs={"certification_intent": "PREVIEW" | "CERTIFIED"})` defaults to `PREVIEW` for backward compatibility. Unknown values return `VAL-CRON-CERT-INTENT` in `ERRO` status.

- `PREVIEW` can evaluate an arbitrary missing-CPU fallback such as `P=1000`, but any unverified physical rate adds `VAL-CRON-PROD-PREVIEW`; the physical `cronograma.is_feasible` retains its actual scheduling meaning, while previously cached financial and analytic projections are cleared. A physically feasible PREVIEW is not a certification. It is never a certified price.
- `CERTIFIED` requires a real referenced production graph (`grafo_sinergia`), nonempty versioned `origem.fonte_id` and `auditoria.versao` (or documented top-level aliases), and absence of a `cpu_meta.producao_horaria` override (the graph-derived `producao_horaria` is allowed). Missing provenance returns `VAL-CRON-PROD-CERT` with no authoritative schedule or derived finances, even when the raw numeric rate is positive.
- Any explicitly provided physical rate of zero, negative, NaN, infinite, oversized integer (float conversion overflow), boolean or nonnumeric returns `VAL-CRON-PROD-INVALID` **before cost-calibration/enrichment and before** the MANUAL/AUTO physical scheduler. A nonempty graph also requires typed parsing, valid referenced resources, and strictly positive finite *derived* physical capacity; graph presence alone is never sufficient. No exception is reinterpreted as a successful outcome.
- When a catalog graph is supplied, the EAP quantity unit must match the production graph's declared unit (with `m³`/`m3` spelling normalized). Mismatched or missing units return `VAL-CRON-PROD-UNIT` as an error in **both** modes. A t/h catalog cannot close a m³ scope without an independently supplied unit-conversion/density contract, which is not silently inferred here. The same compatibility is enforced against each typed `grafo_sinergia.capacidades[].unidade`: changing only the top-level production label does not change the internal measured capacity. As `capacidade_horaria` is always a rate per hour, supported rate spellings (`t/h`, `t/hr`, `m³/h`, etc.) are normalized to their *output quantity* (`t`, `m3`) before comparison; these are equivalent declarations, **not** a physical conversion between dimensions. Flow graph arcs currently inherit the production output unit because the `ArestaFluxoSinergia` schema has no separate unit field; this assumption must be addressed by any future independently certified conversion mechanism.
- The latest canonical for an invalid/rejected run clears `resultado`, `resultado_reconciliado`, point-of-equilibrium and analytical cubes, along with cached schedule-dependent derivatives. Newly computed physical consumable/stock observations remain present for exploratory analysis. Never combine a newly invalid preview schedule with an old profitable financial report.

Source identity and graph presence are admission conditions, not third-party verification of the catalog graph, calibrated F(m), global RCPSP optimum or project financial GO. Independent certification and persistence still belong to #23; exact fungible resource optimum is separately falsified in #16.

## Adversarial checks

`tests/unit/application/skills/test_formalism_p14b_schedule_gate.py` invokes the real Skill 04 with:
- no CPU/prod source and explicit CERTIFIED versus PREVIEW;
- identical numeric rates with `valor_horario` versus `producao_horaria` and no graph/source;
- physical rates 0, -1, NaN, infinity, malformed textual rates (including a malformed price to prove that physical rejection precedes accounting enrichment) and malformed non-object graphs;
- orphaned graph capacity identifiers, empty physical-capacity graphs, incompatible EAP/catalog units and catalog labels that disagree with the internal graph capacities, in PREVIEW/CERTIFIED and MANUAL/AUTO;
- real-catalog positive cases with equivalent explicit hourly-rate units, feasible materialized schedule and exactly conserved Q (not merely absence of an error code);
- pre-populated prior `resultado`, `resultado_reconciliado`, `ponto_equilibrio`, `cubo_analitico`, `s_curve` and `plan_space_result`.

A green CI confirms local regressions only. The W2 wave is not declared complete, and the W1 #25 server-side required-status-check gap remains recorded.
