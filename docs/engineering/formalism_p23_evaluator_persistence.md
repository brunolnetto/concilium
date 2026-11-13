# P23 — Persisted formalism evaluator

Status: implementation package in review; not a project certificate.

## Purpose and ownership

P23 consumes the evidence produced by the existing physical and financial modules. It does not reimplement the RCPSP, physical production, pool allocation, inventory projection, exclusive cost journal, or category BDI formulas.

The current ownership boundary is:

| Evidence | Producer | P23 use |
|---|---|---|
| Physical weekly closure, capacity, FS/SS/FF and pool audit | P15 physical validator + Skill 04 | V1 and V6 |
| Physical pool / standby / instance utilization | P16 exact assignment + Skill 05 | V3 |
| Exclusive K/V/IND events and event ownership | P17/P18/P19/P20 | Financial reconciliation |
| Operational price, regulatory BDI comparison, profitability | P21 | V2, V4, price, regulatory and profitability gates |
| Productivity origin, calibration and hourly rate | P10/P14 evidence | V5 and productivity provenance |

## Decision contract

A run is evaluated against eleven mandatory gates:

- V1 — exact physical scope closure and weekly delivery/capacity evidence.
- V2 — explicit, comparable regulatory BDI basis and floor.
- V3 — exact P16 weekly demand/presence/standby reconciliation: `presence = demand + standby`, `presence <= contracted units`, the activity-demand tensor closes to aggregate demand, and active/standby machine-weeks close to Skill 05 summaries. The summary denominator, contract duration and resource type must also match the typed canonical `RecursoContrato` bound to that P16 witness. Positive standby is allowed; unused capacity is not itself a violation.
- V4 — positive operational price and positive reconciled total cost.
- V5 — positive exact productivity rates with declared source and calibration provenance.
- V6 — a feasible physical calendar (FORMALISMO_LONGO §XIV.9): an audited P15 witness (status and audit PASS, at least one attempt) bound to the current schedule fingerprint. Exhausting the declared start domain is required only to turn an infeasible search into a FAIL.
- Financial reconciliation — exclusive P20 event journal, ownership, weekly totals and category totals reconstruct exactly.
- Price present — operational selling price is present and exact.
- Regulatory BDI basis — P21 regulatory comparison is PASS.
- Profitability — P21 profitability is PASS and profit is positive.
- Productivity provenance — every EAP activity has a qualifying rate source.

Decision rules are deterministic:

| Condition | Decision |
|---|---|
| Any independently proven FAIL | NOGO |
| Every gate PASS, every required source PRESENT, scope RFP, and the run has no skill ERRO/EXCEPTION | GO |
| Any UNKNOWN/NOT_EVALUATED, unavailable source, PREVIEW or RFI | NOT_CERTIFIABLE |
| Every gate PASS but the run has skill errors (owner decision 2026-11-13; the errors are fingerprinted reasons) | NOT_CERTIFIABLE |

V6 follows the normative text: "the N_i search converged with no infeasibility signal — feasible calendar". P15's bounded resolver stops at the first audited feasible calendar and reports complete_search=True only when that candidate was the last one, so requiring completeness for PASS would make V6 unsatisfiable for any feasible project (decision recorded 2026-11-13). Completeness still governs the negative side: an infeasible incomplete search is UNKNOWN, an infeasible exhausted search is FAIL, and a witness not bound to the current schedule fingerprint is UNKNOWN.

A missing regulatory BDI basis in an RFP is not a zero-rate pass. A fallback/assumed productivity rate is not certifiable. A duplicated or unowned P20 event is a financial FAIL. No legacy rounded report value is used to reconstruct the authoritative P20 ledger.

## Fingerprints and persistence

P23-A's ten-source envelope is preserved:

canonical, catalog, productivity, calendar, schedule, pool, inventory, ledger, pricing, solver.

The evaluator hashes its ordered gate evidence and reasons into an evaluation SHA-256. P15 now stores a structured physical-resolution witness on CanonicalModel, including status, audit status, bounded attempts, completeness, violation details and the SHA-256 of the final cronograma. A rejected schedule or a post-materialization pool conflict clears/invalidates the prior witness.

P21's canonical Resultado now retains a JSON-safe P20 reconciliation snapshot: exact rational amounts, unique event identities, event ownership, weekly balances and category-week balances. This permits a new process to replay the reconciliation without serializing Python objects or inferring amounts from rounded display totals.

P23-C stores a content-addressed record under:

formalism_certificates/<run_id>/<evaluation_sha256>.json

The record contains the immutable P23-A envelope, P23-B evaluation and a checksum over both. Identical writes are idempotent; conflicting content at the same key is rejected. The implementation uses only the existing ProjectHandle.read_json/write_json/exists contract, preserving the same storage path for filesystem and remote blob backends.

On every read, the stored record is checked against the current ten-source snapshot and the current formalism/oracle hashes. A change to any source, the formalism, or the oracle changes the result to:

- status = INVALIDATED
- recorded_decision = GO | NOGO | NOT_CERTIFIABLE
- effective_decision = NOT_CERTIFIABLE

The historical decision remains in the immutable record for audit, but an invalidated record cannot present project_go=true.

## Consumers

The common `certificate_presentation_payload` / `certificate_summary` projections report `project_go=true` only for a persisted certificate whose current source fingerprints validate and whose effective decision is GO.

- REST: `PipelineService.get_run` includes `formalism_certificate` and revalidates the immutable run record before returning it; `RunProjectResponse` exposes that field.
- CLI: `concilium run certificate --project <project> <run_id>` reloads the current record and prints the same gate/source summary; it never treats a historical decision as current without revalidation.
- MCP: the read-only `consultar_certificado_formalismo(project_id, run_id)` tool uses the same service functions and the same pinned run catalog.
- REST listing: `PipelineService.list_runs` does not revalidate, so each run exposes only the immutable pointer (`status = NOT_REVALIDATED`, `effective_decision = NOT_CERTIFIABLE`, `project_go = false`, recorded decision, scope, evaluation hash). The issuance-time projection stored in `runs.json` is never echoed as current.
- UI: the dashboard reads the latest run through the revalidating `GET /api/projects/{id}/runs/{run_id}` and renders the same projection (verdict, status, recorded decision, scope, gate rows, reasons). "GO certificado" requires `project_go = true`, `status = CURRENT` and `effective_decision = GO`; it never infers GO from run status or price color.

P24's consumer-contract tests now reload a persisted RFP GO, verify the same projection after restart, and prove that a post-issuance schedule mutation changes the effective result to INVALIDATED / NOT_CERTIFIABLE. These are contract tests, not yet the full multi-skill golden E2E scenarios or numeric differential oracle suite required to close #24.

P26's consumer-contract test verifies that each gate row carries its immutable source fingerprints and artifact reference plus the persisted record fingerprint. The full clause/equation-to-code/test inventory, semantic drift checks, and dashboard coverage remain open work for #26. Only a CURRENT P23 GO can count as certified; missing/invalidated records remain uncertified.

## Validation status and limitations

The implementation currently has local tests for:
- complete RFP all-gate GO and each V1–V6 / financial falsifier NOGO;
- unknown/missing/unavailable evidence and PREVIEW/RFI non-GO;
- stale P15 schedule fingerprint, arbitrary productivity and incomplete bounded search;
- P20 exact event attribution, duplicate ownership and P21/P20 cost identity;
- persistence/reload after restart, idempotent writes, record checksum tampering, source mutation, source omission, and formalism/oracle hash mutation.

Correction (2026-11-13): the earlier "32 passed; compileall passed" statement could not have applied to this branch. `formalism_evaluator.py` was not valid Python in any commit up to `98d7aa7d` (truncated first write, then overlapping splices), so the package failed to import and the full suite stopped with 22 collection errors. The module was repaired forensically in `7428573d`; exact-head local validation is recorded in PR #192, not here.

**Real-pipeline golden RFP (2026-11-13).** `tests/integration/pipeline/test_formalism_golden_rfp_e2e.py` runs `tests/fixtures/formalism_golden_rfp/spec.json` end to end through `PipelineService` (skills 01–09, RFP) and asserts a clean CURRENT **GO**: run OK, every skill OK, all eleven gates PASS, no reasons, P17-C RECONCILED. The declared C^cat basis is recomputed by the independent oracle, and a post-issuance canonical mutation turns the certificate INVALIDATED. Slow falsifiers re-run the pipeline: markup below the regulatory floor (V2 NOGO), a calendar too short to close the scope (V1 FAIL, NOGO), withheld P16 tariffs (V3, NOGO), an uncalibrated production (V5) and a declared basis different from C^cat (V2) are never GO.

The fixture uses the only calibrated productions in the repository (SICRO usinagem BGTC/CBUQ) through two fixture CPUs; no CPU of a real catalog references a calibrated production yet, so real projects cannot pass V5 until the catalogs carry calibrated productivity. Reaching the clean GO required taking activity MO/EQ cost, the utilisation summary and the R_i diagnostic from the exact P16/P18 ledgers whenever the whole team is P16-covered (`_custo_exato_p16.py`, `exactly_covered_activities`, `exact_operational_to_catalog_ratio`).

P23 issue acceptance remains open. The pipeline now issues and persists a record after run completion; REST run reads, the CLI, the explicit MCP certificate tool and the dashboard revalidate the current source fingerprints, and the run listing never presents a stored GO as current. A complete project-level golden RFP with authoritative productivity/calibration and exhausted bounded-search evidence, and the full end-to-end validation remain to be demonstrated. P24 and P26 have contract-consumer tests but still own their full E2E and traceability/anti-drift acceptance. P25 CI/branch-protection governance remains independent and is not a hard prerequisite.
