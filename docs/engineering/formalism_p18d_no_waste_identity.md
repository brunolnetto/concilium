# P18-D — exact no-waste physical-consumption identity

Issue: [#18](https://github.com/brunolnetto/concilium/issues/18)

## Contract

For each activity i and good g, the output-based basis is U_ig = κ_ig Q_i,
after exact conversion into the good's physical unit. With no waste, no
inventory carry-over, and one declared price p_g per purchased unit, the
disjoint variable-cost ledger must satisfy:

    C^V = Σ_g p_g U_g = Σ_i Q_i (Σ_g p_g κ_ig)
    U_g = Σ_i U_ig

The identity is only valid when every rate has a declared physical basis, each
good's price/unit/category agrees across activities, and purchase events are
unique. It does not convert a monetary hourly proxy into physical quantity or
authorize PROJECT_GO.

## Pinned exact example

One aggregate good is priced at 200 currency/t:

- Activity A delivers 4 m³ at 500 kg/m³: 2 t, cost 400.
- Activity B delivers 8 m² at 250 kg/m²: 2 t, cost 400.
- Aggregate purchase is 4,000 kg = 4 t and aggregate cost is 800.
- Activity decomposition is 4 × 100 + 8 × 50 = 800, exactly equal to 200 × 4 = 800.

P18-D pins these equalities through the actual P18-B journal, including unique
purchase identities and exclusion of K/indirect postings. This is a planned
closed-scope example, not observed operation or a full project certificate.
