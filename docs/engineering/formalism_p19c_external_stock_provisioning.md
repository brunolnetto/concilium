# P19-C — External stock provisioning as paired physical and financial evidence

## Scope

P19-C closes the typed P19 stock-preview path for an externally provisioned shortage. It does not replace the legacy ADR-151/ADR-184 fields, calculate BDI, issue a project certificate, or make PROJECT_GO eligible.

An external stock provision contains **two separate facts**:

1. A physical receipt: stable receipt identity, good, quantity/unit, order week and arrival week. P19-A checks consecutive ISO weeks, unit compatibility, and the good's declared lead time. It never derives a receipt from a cost posting.
2. A priced acquisition: stable purchase identity, physical quantity/unit, explicit price basis, exact Fraction unit price, source, reference date, category and currency. The external acquisition becomes a unique MAT/COMB V posting. It cannot be added if price or price provenance is absent.

The receipt ID (EXTERNAL_RECEIPT:<source>) and financial event ID (CONSUMABLE / EXTERNAL_PROVISION:<source>) are intentionally distinct. They identify the physical event and the financial event respectively, while both retain the same source purchase reference.

## Currency and price evidence

The caller must supply the financial currency and the fixed provenance marker catalog_metadata.json from the verified P18-C3 metadata contract. Each purchase must declare the same currency. The current contract does not perform FX conversion.

Price reference dates use canonical YYYY-MM-DD. Physical and priced units must have matching dimensions; conversions are exact. An explicit zero unit price may be recorded with a source and date, but a missing price is an error and is never turned into zero. The adapter labels all provisioned purchase rows PLANNED_CLOSED_SCOPE: the record is not an invoice and does not claim an observed purchase or delivery.

## Inventory and financial reconciliation

book_external_stock_provisioning projects the original P18 physical demand plus any explicitly supplied internal-generation arrivals and external receipts. It rejects duplicate source IDs, unknown goods, delivery before the configured lead time, and unresolved stockout. New purchase evidence is held in a separate P19-C journal and is never appended to P18 demand. If P18 has already priced use of the same good, P19-C rejects the extra acquisition until a source allocation can prove it is not a duplicate charge.

The original PhysicalConsumptionJournalResult remains unchanged and continues to represent P18 usage evidence only. P19-C returns a separate ledger plus its paired purchase/receipt evidence. P20-A accepts this journal through an optional stock_provisioning argument, verifies that its base is exactly the supplied P18 result, rebuilds each acquisition posting, and independently replays the P19-A inventory projection. The resulting ledger can feed P19-B's post_exact_weekly_holding; P20-A then reconciles K, V and holding IND without rewriting either source. Inventory holding is not folded into V, K, or physical demand.

## Authority boundary

The output is EXTERNAL_STOCK_PROVISIONING_PREVIEW_NOT_PROJECT_GO. It represents declared and planned evidence, not proof of invoice settlement or realized operations. Missing inputs, incompatible evidence, late receipt, duplicate ownership or remaining physical shortage fail closed. Project-wide BDI, final financial pricing, formal V1–V6 certification, and acceptance of issue #19 remain downstream obligations.
