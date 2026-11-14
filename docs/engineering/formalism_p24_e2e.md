# P24 — golden RFP projects, differential, falsifiers and metamorphic relations

Status: #24. P24-A (golden projects + phase-by-phase differential, PR #199) and P24-B (falsifiers, metamorphic relations, pinned sources, budgets).

## Scenarios

Both run end to end through `PipelineService` (skills 01–09, `procurement_intent = rfp`) on the resolved `mendeslobo` catalog plus two fixture CPUs bound to the only calibrated productions in the repository (SICRO usinagem BGTC/CBUQ). Inputs are versioned under `tests/fixtures/formalism_golden_rfp/`; provenance is in each file's `$comment`.

**Pinned sources.** `tests/support/golden_pipeline.py` runs every golden offline: the climate is the versioned Open-Meteo snapshot `climate_sao_paulo_2025.json` (CC BY 4.0) served in place of the network client, and `ano_referencia` is pinned in the spec. A request for any other location or year fails the run. (Before P24-B the goldens fetched the *previous calendar year* live, so their inputs drifted with time and network.)

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

## P24-B — falsifiers (each one pipeline run, `slow`)

Each run must not be GO, must carry the expected decision, must name the originating gate in the certificate reasons, and — where listed — keep the other gates PASS so the failure is attributed to its own cause.

| Falsifier | Mutation | Gate | Decision |
|---|---|---|---|
| V1 | calendar ends before the scope can close | V1 | NOGO |
| V2 | markup below the regulatory floor over C^cat | V2 | NOGO |
| V2 | declared basis ≠ derived C^cat | V2 | not GO |
| V3 | P16 exact tariffs withheld | V3 | NOGO |
| V4/PRICE | negative markup (P ≤ C_tot): P21 refuses negative category rates, no price is published | PRICE_PRESENT | NOGO |
| V5 | activity bound to an uncalibrated production | V5 | not GO |
| V6 | RCPSP conflict: pool smaller than the team | V6 | NOGO |
| unpriced input | catalog price of a consumed input removed | PRICE_PRESENT (P18 fails closed naming `eap-01/MA-BRITA-1`) | NOGO |
| PROFITABILITY | scenario 2, expensive plant mob/demob (R_i ≤ 1.5) at 2% markup: BDI over C^cat ≈ 27.5% ≥ 20% floor, margin 1/51 < 1/20 | PROFITABILITY only (V1–V6, regulatory basis, price, P20 PASS) | NOGO |
| RFI | skills 01–06 | — | never an RFP certificate |
| post-issuance mutation | source changed after a recorded GO | — | INVALIDATED / NOT_CERTIFIABLE |

A negative margin with BDI above the floor is unreachable by construction: category markups are nonnegative, so P ≥ C_tot. The reachable unprofitable case is the margin below the declared minimum, tested above.

Differential corruptions (no extra run): each must be reported as the first divergence in its phase — PHYSICAL cell, POOL cost booked twice, CONSUMPTION, forged C^cat (CATALOG), forged price and a duplicated P20 ledger row (PRICE, unexplained currency delta).

Not falsifiable at pipeline level: an *incomplete P15 search* — there is no input bounding the solver; it stays covered by the P23 evaluator unit tests.

## P24-B — metamorphic relations (`test_formalism_golden_metamorphic.py`, `slow`)

Every transformed run must itself be a clean GO with no DIVERGE in the differential.

| Relation | Transformation | Asserted |
|---|---|---|
| Adverse weather cannot help | scenario 2 with one extra rainy day per week (pointwise wetter snapshot) | no cell has a higher climate factor or nominal capacity n·f_clima·f_cal·f_jornada; no activity ends earlier; the makespan grows (the perturbation binds). POOL may be UNVERIFIED (window beyond the exhaustive oracle) |
| Q scales consumables | scenario 1 with Q/2 (basis recomputed by the oracle) | every (activity, good) physical quantity and exact cost is half, within coef·2·10⁻⁶ (the documented physical tolerance) |
| Idle gap toggles perpetuation at the threshold | scenario 2, plant max_idle_gap 1 vs 0 (1-week hole) | gap = 1: one hire, standby > 0, movement = mob+demob; gap = 0: two hires, no standby, movement = 2·(mob+demob); K(0) ≥ K(1); both match the exhaustive P22-C oracle |

## Budget

| Profile | Where | Content | Measured (8-core dev box) | Budget |
|---|---|---|---|---|
| fast | required `Tests` job | 2 golden runs + differential, corruptions, fronts guard, invalidation | ~3 min | inside the job |
| slow | `formalism-e2e-nightly.yml` (cron + manual) | 10 falsifier runs + 6 metamorphic runs | ~13 min, slowest test 142 s | 360 s per test, 2700 s total (`scripts/check_test_budget.py` on the JUnit report), job timeout 60 min |

## Defects found (fixed in the P24 packages)

1. **Fictitious capacity** — fronts were the *sum* of heterogeneous resource units (7 and 10 "fronts" on one plant); now m = min_g ⌊x_g / a_ig^front⌋ (N7). The first golden GO used to rely on this and is now on consistent physics.
2. Typed EAP predecessors (NEP-031) crashed DAG validation (`unhashable`).
3. A `project` ran on the EAP frozen at creation, ignoring the composed EAP (ADR-063 D3).
4. ADR-072 corridor window was an absolute deadline from t = 0; now counted from the release (owner decision; ADR amended).
5. P18 assumed one chain per unit and bounded P16 hire ids by the contract; now it bounds simultaneous presence.
6. **Q-FS release blocked by float rounding** (P24-B, metamorphic climate): weekly deliveries are floats whose exact sum can fall short of Q by ~10⁻¹²; a 100% FS successor compared delivered ≥ Q exactly and stayed blocked, so any project whose predecessor ran in a week with climate factor < 1 could become infeasible ("predecessora FS não atingiu o limiar físico"). The goldens passed only because their weeks were dry. Now a full-scope threshold releases when V1's own `scope-closure/v1` tolerance accepts the predecessor as closed; partial thresholds stay exact (rounding can only defer them).
7. Golden inputs were not immutable: climate fetched live for the previous calendar year (pinned above).
