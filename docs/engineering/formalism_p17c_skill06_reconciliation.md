# P17-C — Skill06 activity-K reconciliation against the exact pool ledger

## Authority and scope

This package adds an opt-in, read-only reconciliation sidecar after Skill06's existing consolidation. It consumes the P18-C3 source-backed preview and independently reconstructs the Skill05 P16/P17 pool postings. It never rewrites resultado, sale price, margin, BDI, or legacy activity costs, and never authorizes PROJECT_GO.

## Reconciliation

- Reconstruct the P16 witness ledger and require its contractual K and MOB/DEMOB postings to be preserved verbatim in the P18 preview.
- Rebuild the P18 exclusive postings from exact rational strings; reject duplicate event identities, forged totals, missing currency provenance, or a sidecar that claims GO authority.
- Derive per-activity active K from each exact P16 instance chain's active weeks and activity_by_week mapping.
- Compare those per-activity values with Skill06's weekly pre-BDI custo_contratual diagnostics (MO+EQ only). The diagnostic uses the decimal rendering of the legacy float; a one-cent tolerance is explicit and diagnostic only.
- Check that activity assignments close to active pool K, contractual pool K covers the activity K diagnostic under the baseline, and physical MAT/COMB acquisitions remain V rather than K.
- Publish CanonicalModel.p17_cost_reconciliation with exact rational totals, activity deltas, posting identities, reasons, invariants and status RECONCILED or NOGO.

## Failure behavior

Malformed or missing evidence fails closed for this sidecar and emits ERRO. A numerical mismatch is persisted as NOGO and emits ERRO. Skill06's legacy result is not silently replaced or deleted: this package is diagnostic only, and no certificate is created. The P18/P17 sidecars remain opt-in via p18_consumption_preview_enabled is True.

## Acceptance still outstanding

The implementation PR is registered as P17-C. It does not close issue #17. The issue-level dependencies #16 and #18 remain open, and #25 remains deliberately deferred by the maintainer. Those are not represented as successful acceptance by this code. Focused P17-C tests and the independent execution-DAG oracle were added but have not been executed in this environment; no CI result is claimed.
