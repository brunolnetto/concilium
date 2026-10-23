# P18-A — Measured physical rates and unit prices

The single existing engineering unit registry
(`concilium.domain.units.normalize_unidade`) remains authoritative.

For a consumable `g` distinguish:
- `κ_out`: physical units of good per delivered unit of activity.
- `κ_hour`: physical units per actual productive/operating hour.
- `p_g`: R$ per **physical unit**, not a monetary hourly proxy.

`U_g` is calculated only against the basis that was explicitly declared;
`C_g=p_g U_g` with exact rational arithmetic and proven unit conversions
kg↔t, L↔m³, m↔km. Dimensional mismatches are errors. A bag (`sc`) is NOT
an individual unit (`unid`) without an explicit packaging conversion.
A `R$/h` signal can be preserved as
`LegacyHourlyMoneyProxy(evidence_status=UNVERIFIED_LEGACY_MONETARY_PROXY)`
but cannot be converted into a measured physical quantity.

This P18-A module is a **type and conversion boundary**, not yet a runtime
catalog migration, purchase invoice, or GO certificate. P18-B must wire
catalog physical inputs and observed operation/delivery into the P17
exclusive acquisition ledger, then reconcile with material and fuel costs.
