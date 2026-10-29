# P17-A — Exclusive contractual and physical-acquisition ledger

This additive bridge consumes globally optimized homogeneous-instance chains for fixed physical demand from P16-E, after the demand tensor introduced in #68/#71 and reconciled against team-level physical demand in #72/#73. Each chain records its explicit active-week indices; a chain ID is not interpreted as a permanent demand-height level.

**Contractual K:** one posting per `resource_type / physical instance chain / week`, either active or idle. The active/idle nature is taken from that chain's explicit global assignment when present; legacy fixed-level witnesses remain read-only compatibility inputs. Requires an explicit resource type
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


## P16-E global instance assignment extension

The P16-E production optimizer minimizes the exact total active + standby + MOB/DEMOB cost by optional min-cost flow over week-specific demand events. It supports homogeneous instances, linear declared tariffs and a maximum idle gap, conditional on an already validated weekly demand tensor. The financial adapter reconstructs active weeks from `InstanceChain.active_week_indices` and fails closed if those paths cannot exactly reconstruct physical demand/presence or costs. A manually constructed legacy `ExactPoolResult` is marked `NOT_CERTIFIED_MANUAL_OR_LEGACY_POOL`; only results returned by `optimize_homogeneous_pool` declare `EXACT_GLOBAL_INSTANCE_ASSIGNMENT_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND`.

The independent regression vector `fungible_reassignment_92_not_fixed_layers_120` proves why vertical demand-height layers are insufficient: expected active cost 30 + idle cost 2 + movement cost 60 = 92, whereas fixed-height chains cost 120. This extension does not optimize RCPSP dates and is not a project GO certificate.
