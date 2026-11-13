# P24-A — golden RFP projects and phase-by-phase differential

Status: implementation package for #24 (P24-A). P24-B (metamorphic falsifiers and stress budgets) is separate.

## Scenarios

Both run end to end through `PipelineService` (skills 01–09, `procurement_intent = rfp`) on the resolved `mendeslobo` catalog plus two fixture CPUs bound to the only calibrated productions in the repository (SICRO usinagem BGTC/CBUQ). Inputs are versioned under `tests/fixtures/formalism_golden_rfp/`; provenance is in each file's `$comment`.

| Scenario | File | Exercises |
|---|---|---|
| single_plant_sequence | `spec.json` | multi-resource teams (equipment + labour), 7 + 6 consumables, climate (São Paulo), FS sequence, exact P16 tariffs, P18/P20/P21, 13-week activities |
| sharing_theta_standby_remob | `spec_sharing.json` | Q-FS release at θ = 0.5, shared equipment across lots with a gap (plant on standby vs loaders remobilised), shared labour pool, nonzero MOB/DEMOB (IND) |

Both must be a clean CURRENT **GO**: run OK, every skill OK, 11/11 gates PASS, no reasons, P17-C RECONCILED. P23 remains the only GO decision; the E2E reads the persisted certificate and never re-decides.

## Differential (`tests/support/golden_differential.py`)

Each mandatory phase is recomputed from the run's own inputs by code that does not import the module that produced it. Report order follows the pipeline; `first_divergence` is the earliest DIVERGE with both values and the oracle provenance.

| Phase | Pipeline value | Independent computation | Tolerance |
|---|---|---|---|
| PHYSICAL | F(m) per cell, q_ij, Σq | P22-B max-flow on the production capacity elements; q_ij = min(residual, H·F(m)·climate·calendar·shift); Σ_j q_ij = Q_i | F(m): 1e-9 relative; q_ij and Σq: absolute 1e-6 (the pipeline's documented scope tolerance, floats in weekly cells) |
| POOL | P16 demand and K per contract | d_gj = Σ_i m_ij a_ig^front (fictitious-capacity guard); K by closed form when no movement cost (never bridging is optimal), else the exhaustive P22-C pool oracle (≤ 3 units, ≤ 6-week window, exact decimal tariffs); otherwise UNVERIFIED | exact |
| CONSUMPTION | P18 V per activity | Σ_j q_ij · coef · price; 0 for N6 declarations | exact |
| CATALOG | C^cat | catalog-envelope oracle | exact |
| PRICE | C_tot, P, profit, margin, BDI | P20 category totals; P = Σ_cat C·(1+β); BDI = P/C^cat − 1 | exact |
| CERTIFICATE | status/decision, fingerprints | reported only | — |

The E2E requires every phase to MATCH with nothing UNVERIFIED, and checks that a corrupted physical, consumption or price value is reported as that phase's first divergence. Expected values are never rewritten to match production.

## RFI / RFP

An RFI run of the golden project (skills 01–06) is never an RFP certificate (`project_go = false`, decision ≠ GO; slow test).

## Budget

Default (fast) profile: two golden pipeline runs per test session (~40 s each on an idle machine) plus the differential (sub-second). Falsifiers and the RFI run are `slow` (one pipeline run each, ~20–60 s).

## Defects found by the differential and the second scenario (fixed in this package)

1. **Fictitious capacity** — fronts were the *sum* of heterogeneous resource units (7 and 10 "fronts" on one plant); now m = min_g ⌊x_g / a_ig^front⌋ (N7). The first golden GO used to rely on this and is now on consistent physics.
2. Typed EAP predecessors (NEP-031) crashed DAG validation (`unhashable`).
3. A `project` ran on the EAP frozen at creation, ignoring the composed EAP (ADR-063 D3).
4. ADR-072 corridor window was an absolute deadline from t = 0; now counted from the release (owner decision; ADR amended).
5. P18 assumed one chain per unit and bounded P16 hire ids by the contract; now it bounds simultaneous presence.
