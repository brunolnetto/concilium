# P21-C — propagate pricing diagnostics through the canonical result

Issue: #21. Package PR: #163.

P21-A and P21-B calculations must not remain detached utilities. Skill 06 now attaches their exact diagnostic fields and independent gate statuses to the canonical `Resultado` model. REST, MCP, UI, RFI and RFP paths that serialize the canonical result therefore expose the same fields instead of recomputing a separate margin or regulatory outcome.

The adapter consumes an explicit `p21_pricing_evidence` context containing the authoritative P20 reconciliation, exact category BDI rates, typed catalog benchmark and currency metadata, physical-scope fingerprint, regulatory basis, and optional minimum profit margin. It never reconstructs the authoritative ledger from rounded legacy display fields.

If the context is missing or invalid, both gates are UNKNOWN. PREVIEW reports a warning; AUTO_GO and CERTIFIED produce an error. Even a PASS is pricing eligibility evidence only, not PROJECT_GO or a substitute for certificate #23.

Validation was not run on this exact HEAD. GitHub Actions remains disabled by maintainer decision.
