# P17-A — Exclusive contractual and physical-acquisition ledger

This additive bridge consumes the exact fixed-demand instance chains introduced
in #68/#71 and reconciled against team-level physical demand in #72/#73.

**Contractual K:** one posting per `resource_type / instance level / contractual
chain / week`, either active or idle. Requires an explicit resource type
classification **MO** or **EQ**; a composite team mixing both must be decomposed
first. The algorithm will not pretend that team type names imply a valid tariff
split. **Mob/demob** is booked once per chain as an **indirect** event, separate
from K. The resulting ledger must reconstruct each P16 active, standby and
mobility monetary subtotal exactly or fail.

**Variable V:** only explicitly identified physically measured goods with
`quantity: Fraction`, `physical_unit`, `price/unit` and stable acquisition
evidence IDs. `MAT` and `COMB` are not active/idle pool charges. No inferred
quantity from an hourly money proxy, and zero physical quantity does not
create a purchase.

**Accounting:** `C_direct = C_K + C_V`, `C_total = C_direct + C_ind`.
Movements remain indirect. All amounts are exact `Fraction`; presentation
rounding happens outside this contract. A duplicate source event is rejected.

**Proof boundary:** this is P17-A only — no automatic real-money authority
over existing Skill 05/06 yet. P17-B maps the canonical mixed MO/EQ
composition and active/idle/off rates to these exact instancial entries.
P17-C makes Skill06 reconcile against them. P18 adds physical conversion
and purchase evidence from the actual catalog. P20 adds differentiated BDI
and the final certified finance ledger. A project cannot claim GO from this
adapter alone.
