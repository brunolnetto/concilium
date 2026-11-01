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
- V6 — physical precedence/pool feasibility plus a bounded search whose entire declared start domain has been exhausted.
- Financial reconciliation — exclusive P20 event journal, ownership, weekly totals and category totals reconstruct exactly.
- Price present — operational selling price is present and exact.
- Regulatory BDI basis — P21 regulatory comparison is PASS.
- Profitability — P21 profitability is PASS and profit is positive.
- Productivity provenance — every EAP activity has a qualifying rate source.

Decision rules are deterministic:

| Condition | Decision |
|---|---|
| Any independently proven FAIL | NOGO |
| Every gate PASS, every required source PRESENT, scope RFP | GO |
| Any UNKNOWN/NOT_EVALUATED, unavailable source, PREVIEW or RFI | NOT_CERTIFIABLE |

GO is deliberately stricter than a feasible physical witness. P15's bounded resolver returns complete_search=False when it stops after finding one feasible candidate without enumerating the complete caller-declared search domain. P23 therefore treats that witness as UNKNOWN for V6, not GO. This prevents a locally admissible calendar from being misrepresented as global search convergence.

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
- UI: dashboard-level presentation of the gate matrix is still pending. UI must consume this same projection; it must not independently infer GO from legacy status or price color.

P24's consumer-contract tests now reload a persisted RFP GO, verify the same projection after restart, and prove that a post-issuance schedule mutation changes the effective result to INVALIDATED / NOT_CERTIFIABLE. These are contract tests, not yet the full multi-skill golden E2E scenarios or numeric differential oracle suite required to close #24.

P26's consumer-contract test verifies that each gate row carries its immutable source fingerprints and artifact reference plus the persisted record fingerprint. The full clause/equation-to-code/test inventory, semantic drift checks, and dashboard coverage remain open work for #26. Only a CURRENT P23 GO can count as certified; missing/invalidated records remain uncertified.

## Validation status and limitations

The implementation currently has local tests for:
- complete RFP all-gate GO and each V1–V6 / financial falsifier NOGO;
- unknown/missing/unavailable evidence and PREVIEW/RFI non-GO;
- stale P15 schedule fingerprint, arbitrary productivity and incomplete bounded search;
- P20 exact event attribution, duplicate ownership and P21/P20 cost identity;
- persistence/reload after restart, idempotent writes, record checksum tampering, source mutation, source omission, and formalism/oracle hash mutation.

Local execution on the earlier development snapshot: **32 passed**; Python compileall passed. The additional P23 consumer-contract and deterministic-set-serialization tests have not yet been run on the exact current PR head. Exact-head WSL validation, Ruff, ty and the full relevant suite remain pending. The latest hosted CI run completed with failure conclusions but exposed zero steps for each failed job and no downloadable logs; that is insufficient to attribute the failure to either code or runner/account infrastructure. Do not merge until exact-head validation is recorded.

P23 issue acceptance remains open. The pipeline now issues and persists a record after run completion; REST run reads and the explicit MCP certificate tool revalidate the current source fingerprints. UI presentation, a complete project-level golden RFP with authoritative productivity/calibration and exhausted bounded-search evidence, and the full end-to-end validation remain to be demonstrated. P24 and P26 have contract-consumer tests but still own their full E2E and traceability/anti-drift acceptance. P25 CI/branch-protection governance remains independent and is not a hard prerequisite.
