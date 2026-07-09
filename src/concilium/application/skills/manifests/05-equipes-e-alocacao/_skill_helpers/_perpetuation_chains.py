"""Skill 05 — Equipes e Alocação (helpers A, parte extraída de _skill_helpers_a.py)."""

from __future__ import annotations

from concilium.domain.models.canonical import CadeiaPerpetuacao


def _build_perpetuation_chains(
    tipo_id: str,
    items: list[dict],
    custo_mob_unit: float = 0.0,
    custo_demob_unit: float = 0.0,
    custo_standby_unit: float = 0.0,
    delta_max: int = 2,
    gap_max: int = 9999,
) -> list[CadeiaPerpetuacao]:
    """Build perpetuation chains for a resource type (ADR-073).

    Groups consecutive activities that use the same resource type into chains
    where the fleet is kept mobilized between activities (no intermediate
    mob/demob events).

    Parameters
    ----------
    tipo_id         : resource type identifier (e.g. "DESMAT")
    items           : list of dicts {item_id, start_idx, end_idx, required,
                      active_weeks, machine_weeks}; already sorted or unsorted
    custo_mob_unit  : unit mob cost (e.g. per machine); 0 → use time threshold
    custo_demob_unit: unit demob cost; 0 → use time threshold
    custo_standby_unit: cost per machine-week during gap (often 0 in early catalogs)
    delta_max       : max gap (weeks) to trigger perpetuation when cost data absent
    gap_max         : ADR-079 G_r^viável — hard upper bound on gap; perpetuation
                      is NEVER allowed when gap > gap_max, regardless of cost
                      threshold. Default 9999 preserves pre-ADR-079 behaviour.

    Returns
    -------
    list[CadeiaPerpetuacao] — one entry per chain
    """
    if not items:
        return []

    # Sort by start, then by end
    sorted_items = sorted(items, key=lambda x: (x["start_idx"], x["end_idx"]))

    use_cost_threshold = (custo_mob_unit + custo_demob_unit) > 0

    chains: list[CadeiaPerpetuacao] = []
    chain_items = [sorted_items[0]]

    def _flush_chain(chain_items: list[dict], chain_n: int) -> CadeiaPerpetuacao:
        """Convert an accumulated list of items into a CadeiaPerpetuacao."""
        semanas_ativas = sum(len(it["active_weeks"]) for it in chain_items)
        machine_weeks_ativas = sum(it["machine_weeks"] for it in chain_items)

        # Gaps: between consecutive items in chain
        semanas_ociosas = 0
        custo_standby = 0.0
        for k in range(1, len(chain_items)):
            gap = max(0, chain_items[k]["start_idx"] - chain_items[k - 1]["end_idx"])
            semanas_ociosas += gap
            if custo_standby_unit > 0 and gap > 0:
                # Standby cost = gap × standby_unit × min(demand of preceding end, following start)
                demand_end = chain_items[k - 1]["required"]
                demand_start = chain_items[k]["required"]
                custo_standby += gap * custo_standby_unit * min(demand_end, demand_start)

        return CadeiaPerpetuacao(
            cadeia_id=f"cadeia-{tipo_id.lower().replace('-', '_')}-{chain_n}",
            tipo_id=tipo_id,
            item_ids=[it["item_id"] for it in chain_items],
            semana_inicio=chain_items[0].get("semana_inicio", ""),
            semana_fim=chain_items[-1].get("semana_fim", ""),
            semanas_ativas=semanas_ativas,
            semanas_ociosas=semanas_ociosas,
            n_mobilizacoes=1,
            n_desmobilizacoes=1,
            custo_standby=round(custo_standby, 2),
            machine_weeks_ativas=machine_weeks_ativas,
            delta_aplicado_semanas=delta_max,
        )

    for item in sorted_items[1:]:
        last = chain_items[-1]
        gap = item["start_idx"] - last["end_idx"]  # may be negative (overlap)

        if use_cost_threshold:
            # Cost-based: perpetuate if standby is cheaper than mob+demob
            standby_cost = max(0, gap) * custo_standby_unit * min(last["required"], item["required"])
            perpetuate = standby_cost < (custo_mob_unit + custo_demob_unit)
        else:
            # Time-based: perpetuate if gap ≤ delta_max (overlaps always perpetuate)
            perpetuate = gap <= delta_max

        # ADR-079: G_r^viável hard constraint — never perpetuate beyond gap_max
        if gap > gap_max:
            perpetuate = False

        if perpetuate:
            chain_items.append(item)
        else:
            chains.append(_flush_chain(chain_items, len(chains) + 1))
            chain_items = [item]

    # Flush final chain
    chains.append(_flush_chain(chain_items, len(chains) + 1))
    return chains


