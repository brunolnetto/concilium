# P22-A — Independent formalism reference protocol

This test package is deliberately independent of `concilium` production
modules, schedulers, cost helpers, and persisted report fixtures.

**Run:** `python -m pytest tests/reference_formalism -q`

## Inputs, expected results and provenance

The file `vectors/scalar_baseline_v1.json` pins two small *manually*
computable scalar cases. Inputs and expected decimal results are represented
as **strings**, not binary JSON floating-point values. Unsupported protocol
versions, unknown fields, NaN/Inf, nonproductive activity, zero productivity,
negative costs and impossible partial-week closure must fail.

- `scope_total - quantity_before_final_week`: delivered in final week
- Contractual `K_final = contractual_rate_per_team_hour * hours_per_week * team_count`
- Consumable `V_final = variable_rate_per_team_hour * q_final / productivity_per_team_hour`
- `V_total = variable_rate_per_team_hour * Q / productivity_per_team_hour`
- `scope_residual = Q - (prior + q_final) = 0`

**Assumptions:** single-team hourly rate, no waste/idle variable consumption,
full-week K payment even when the final Q is fractional. No markups, no graph
normalization, no inventory holding. These are explicitly *not* proofs of
general numerical conformance.

P22-B will add corrected productivity, calendar and precedence mathematics.
P22-C will add independent pool/stock/BDI references and brute-force witnesses.
Never generate expected outputs from production code. Changes to the reviewed
formalism require explicit provenance and updated hand-checkable vectors.

**Related:** #8, #9–#13, #22.
