# P21-C — propagate pricing diagnostics through the canonical result

Issue: #21. Package PR: #163.

P21-A and P21-B calculations must not remain detached utilities. Skill 06 now attaches their exact diagnostic fields and independent gate statuses to the canonical `Resultado` model. REST, MCP, UI, RFI and RFP paths that serialize the canonical result therefore expose the same fields instead of recomputing a separate margin or regulatory outcome.

The adapter consumes an explicit `p21_pricing_evidence` context containing the authoritative P20 reconciliation, exact category BDI rates, typed catalog benchmark and currency metadata, physical-scope fingerprint, regulatory basis, optional minimum profit margin, and a provenance-bearing `InventoryEvidenceScope` declaring either `NO_INVENTORY` or `COMPLETE`. When the typed reconciliation is absent, Skill 06 can compose it from the exact P17/P18 witnesses plus the declared P19 holding/provisioning journals. It never reconstructs the authoritative ledger from rounded legacy display fields.

If the context is missing or invalid, both gates are UNKNOWN. PREVIEW reports a warning; AUTO_GO and CERTIFIED produce an error. Even a PASS is pricing eligibility evidence only, not PROJECT_GO or a substitute for certificate #23.

Validation was not run on this exact HEAD. GitHub Actions remains disabled by maintainer decision.

## Runtime JSON contract

The production Skill 06 boundary accepts a versioned JSON declaration under
\`inputs.p21_pricing_evidence\`. The client does **not** send Python dataclasses,
a serialized \`ExactFinancialReconciliation\`, P17 ledgers, P18 journals, or P19
journals. Skill 06 rebuilds those authoritative objects from the current
canonical P16/P18 witnesses and the server-resolved catalog.

The contract schema is \`concilium.p21.pricing-evidence.v1\`:

- \`inventory_scope\`: \`status\` (\`NO_INVENTORY\` or \`COMPLETE\`), \`source\`,
  \`reference_id\`, and \`fingerprint\`.
- \`bdi_by_category\`: exact rational strings for all five categories
  (\`MO\`, \`EQ\`, \`MAT\`, \`COMB\`, \`IND\`).
- \`catalog\`: benchmark \`amount\`, \`currency\`, \`source\`, \`reference_id\`, and
  \`basis_fingerprint\`. Its currency must match the server-resolved catalog.
- \`operational_basis_fingerprint\`: explicit physical-scope identity.
- \`regulatory_basis\`: optional \`amount\`, \`currency\`, \`basis_fingerprint\`,
  \`minimum_rate\`, \`source\`, and \`reference_id\`.
- \`minimum_profit_margin\`: optional exact rational string.
- \`inventory\`: required only for \`COMPLETE\` scope. It declares
  \`calendar_weeks\`, \`goods\`, optional \`internal_arrivals\`, optional \`purchases\`,
  and optional \`holding_tariffs\`. At least one explicit purchase or holding
  tariff is required for \`COMPLETE\`.

All financial and physical quantities/rates cross the JSON boundary as strings
and are parsed to \`Fraction\`; floats and JSON numbers are not accepted for
fractional values. \`lead_time_weeks\` is an integer. Holding tariffs must declare
\`END_OF_WEEK\`. External receipts can only be created by a paired, priced
purchase; \`internal_arrivals\` accepts only \`INTERNAL_GENERATION\`.

The only currency metadata used for P19/P21 is reconstructed from the resolved
catalog loaded by the runtime (\`currency\` and \`currency_source\` from
\`catalog_metadata.json\`). A caller cannot override it. P17/P18 ledgers and
journals are rebuilt internally. Unknown fields, unsupported schemas, missing
provenance, invalid units, stockouts, delivery timing errors, and duplicate
ownership fail closed to \`UNKNOWN\`; \`PREVIEW\` surfaces a warning and
\`AUTO_GO\`/\`CERTIFIED\` surface an error.

Example (illustrative values, not a project quote):

\`\`\`json
{
  "schema": "concilium.p21.pricing-evidence.v1",
  "inventory_scope": {
    "status": "COMPLETE",
    "source": "physical-inventory-count",
    "reference_id": "stocktake-2026-10-01",
    "fingerprint": "inventory-scope-v1"
  },
  "bdi_by_category": {
    "MO": "0", "EQ": "0", "MAT": "0", "COMB": "1", "IND": "0"
  },
  "catalog": {
    "amount": "100",
    "currency": "BRL",
    "source": "resolved-project-catalog",
    "reference_id": "catalog-price-2026-10",
    "basis_fingerprint": "physical-scope-v1"
  },
  "operational_basis_fingerprint": "physical-scope-v1",
  "regulatory_basis": {
    "amount": "40",
    "currency": "BRL",
    "basis_fingerprint": "physical-scope-v1",
    "minimum_rate": "1/10",
    "source": "regulatory-basis",
    "reference_id": "regulatory-2026-v1"
  },
  "minimum_profit_margin": "1/5",
  "inventory": {
    "calendar_weeks": ["2026-W18", "2026-W19"],
    "goods": [
      {
        "good_id": "DIESEL",
        "unit": "L",
        "initial_quantity": "10",
        "capacity": null,
        "lead_time_weeks": 0
      }
    ],
    "internal_arrivals": [],
    "purchases": [],
    "holding_tariffs": [
      {
        "good_id": "DIESEL",
        "amount_per_unit_week": "1/10",
        "physical_unit": "L",
        "basis": "END_OF_WEEK"
      }
    ]
  }
}
\`\`\`

The integration test exercises this JSON boundary through \`run_resultado_financeiro\`,
builds the P19-C purchase and P19-B holding journals, reconciles P20, and checks
the canonical P21 gates. This is a pricing-eligibility preview only; it does not
authorize PROJECT_GO.
