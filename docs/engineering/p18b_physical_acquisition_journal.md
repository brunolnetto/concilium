# P18-B — Physical consumption to exclusive acquisition entries

P18-A [#76] provides rate κ, quantity units, price units and exact
conversions. P17-A [#74] provides unique financial event ownership.

This integration emits one `PhysicalPurchase` from each positively
quantified weekly source `WeeklyConsumptionEvidence`:
- `PER_DELIVERED_UNIT`: `U=κ_out*q_ij` in an explicitly declared unit;
- `PER_OPERATING_HOUR`: `U=κ_h*H_real`; NEVER `q/F(m)`
  unless the user separately proves the operating-hour identity;
- `C=U_in_price_unit * p_g` with exact Fraction arithmetic;
- identifiers are unique, category MAT/COMB explicit, and zero quantities
  create no purchase.

Each record must preserve whether its input is a **planned closed-scope**
estimate or an **observed operating** quantity. This adapter deliberately
does not claim that a planned cost has been invoiced. Existing monetary
hourly proxies are *not* transformed into U_g.

This is an **intermediate P18-B bridge**; actual ingestion of catalog
`MaterialEquipe`, `Insumo`, `EquipamentoEquipe`, ISO-week
`DistribuicaoSemanal` and purchase evidence still needs downstream
application adapters and tests. The global GO/NOGO authority belongs to
#23, after P17-C/#19/#20/#21 prove all cost and schedule ledgers.
