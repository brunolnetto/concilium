"""Skill 05 — Equipes e Alocação (helpers A, parte extraída de _skill_helpers_a.py)."""

from __future__ import annotations

from concilium.domain.models.canonical import CadeiaPerpetuacao, ValidacaoItem


def _merge_item_runs(sorted_items: list[dict]) -> list[dict]:
    """Coalesce items into maximal runs of mutually overlapping/tangent activities.

    Two items belong to the same run when there is no idle capacity between
    them — i.e. the UNION of everything already grouped covers up to (or past)
    the start of the next item. Uses a running MAX of end_idx (not the end_idx
    of the last item processed), so that nested/staggered activities (e.g.
    B=[2,4) nested inside A=[0,10)) are correctly merged into the same run even
    when a later item (C) starts after the end of the nested item (B) but
    still within the coverage of A.

    This is the ADR-073 fix for the nesting bug — replaces the "item vs. last
    item added" comparison with "item vs. maximum coverage seen so far".
    """
    runs: list[dict] = []
    current_items = [sorted_items[0]]
    coverage_end = sorted_items[0]["end_idx"]
    for item in sorted_items[1:]:
        if item["start_idx"] - coverage_end <= 0:
            current_items.append(item)
            coverage_end = max(coverage_end, item["end_idx"])
        else:
            runs.append({"items": current_items, "start_idx": current_items[0]["start_idx"], "end_idx": coverage_end})
            current_items = [item]
            coverage_end = item["end_idx"]
    runs.append({"items": current_items, "start_idx": current_items[0]["start_idx"], "end_idx": coverage_end})
    return runs


def _boundary_required(run: dict, at_end: bool, week_demand: dict[str, int] | None) -> int:
    """Required quantity at the run's boundary closest to a real gap.

    Prefers the real aggregate demand curve (week_demand[semana]) when
    available — correctly captures concurrent overlap of multiple items in
    the boundary week. Falls back to the boundary item's own `required` field
    when week_demand is not provided (full compat with existing call sites/tests
    that don't pass it).
    """
    items = run["items"]
    boundary_item = max(items, key=lambda it: it["end_idx"]) if at_end else min(items, key=lambda it: it["start_idx"])
    if week_demand:
        semana_key = boundary_item.get("semana_fim") if at_end else boundary_item.get("semana_inicio")
        if semana_key is not None and semana_key in week_demand:
            return int(week_demand[semana_key])
    return int(boundary_item["required"])


def _build_perpetuation_chains(
    tipo_id: str,
    items: list[dict],
    custo_mob_unit: float = 0.0,
    custo_demob_unit: float = 0.0,
    custo_standby_unit: float = 0.0,
    delta_max: int = 2,
    gap_max: int = 9999,
    validacoes: list | None = None,
    week_demand: dict[str, int] | None = None,
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
    validacoes      : ADR-137 D1 — lista opcional de ValidacaoItem; recebe um aviso
                      VAL-POOL-MOB-ZERO quando a decisão de perpetuação cai para o
                      heurístico baseado em tempo por custo_mob_unit+custo_demob_unit
                      serem 0 (ex.: rcpsp_spec derivado automaticamente nunca popula
                      esses campos — ver ADR-137 P1).
    week_demand     : ADR-073 fix (aninhamento) — curva opcional de demanda agregada
                      por semana ({semana: quantidade}), já calculada upstream em
                      `_collect_tipo_items_and_demands`. Usada só para refinar o
                      `required` na borda de um gap real (ver `_boundary_required`);
                      NÃO redefine onde os gaps estão — isso continua vindo da união
                      de intervalos `[start_idx, end_idx)` dos próprios items
                      (`_merge_item_runs`), preservando a janela sólida por item
                      assumida por `particionar_contrato` (Euler).

    Returns
    -------
    list[CadeiaPerpetuacao] — one entry per chain
    """
    if not items:
        return []

    # Sort by start, then by end
    sorted_items = sorted(items, key=lambda x: (x["start_idx"], x["end_idx"]))

    use_cost_threshold = (custo_mob_unit + custo_demob_unit) > 0

    if not use_cost_threshold and len(sorted_items) > 1 and validacoes is not None:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-POOL-MOB-ZERO",
                status="AVISO",
                mensagem=(
                    f"Tipo {tipo_id}: custo_mob_unit e custo_demob_unit ambos 0 — decisão de "
                    "perpetuação (ADR-073) usando heurístico baseado em tempo (gap ≤ "
                    f"{delta_max} semanas), não em custo real (ADR-137 P1)."
                ),
            )
        )

    # Coalesce mutually overlapping/tangent items into runs first (ADR-073
    # aninhamento fix) — a run can never be split, so gap decisions below only
    # ever compare runs that are genuinely apart in time.
    runs = _merge_item_runs(sorted_items)

    chains: list[CadeiaPerpetuacao] = []
    chain_runs = [runs[0]]

    def _flush_chain(chain_runs: list[dict], chain_n: int) -> CadeiaPerpetuacao:
        """Convert an accumulated list of runs into a CadeiaPerpetuacao."""
        chain_items = sorted(
            (it for run in chain_runs for it in run["items"]),
            key=lambda x: (x["start_idx"], x["end_idx"]),
        )
        semanas_ativas = sum(len(it["active_weeks"]) for it in chain_items)
        machine_weeks_ativas = sum(it["machine_weeks"] for it in chain_items)

        # Gaps: between consecutive runs in chain (always > 0 by construction)
        semanas_ociosas = 0
        custo_standby = 0.0
        for k in range(1, len(chain_runs)):
            gap = max(0, chain_runs[k]["start_idx"] - chain_runs[k - 1]["end_idx"])
            semanas_ociosas += gap
            if custo_standby_unit > 0 and gap > 0:
                # Standby cost = gap × standby_unit × min(demand of preceding end, following start)
                demand_end = _boundary_required(chain_runs[k - 1], at_end=True, week_demand=week_demand)
                demand_start = _boundary_required(chain_runs[k], at_end=False, week_demand=week_demand)
                custo_standby += gap * custo_standby_unit * min(demand_end, demand_start)

        semana_fim_item = max(chain_runs[-1]["items"], key=lambda it: it["end_idx"])
        return CadeiaPerpetuacao(
            cadeia_id=f"cadeia-{tipo_id.lower().replace('-', '_')}-{chain_n}",
            tipo_id=tipo_id,
            item_ids=[it["item_id"] for it in chain_items],
            semana_inicio=chain_items[0].get("semana_inicio", ""),
            semana_fim=semana_fim_item.get("semana_fim", ""),
            semanas_ativas=semanas_ativas,
            semanas_ociosas=semanas_ociosas,
            n_mobilizacoes=1,
            n_desmobilizacoes=1,
            custo_standby=round(custo_standby, 2),
            machine_weeks_ativas=machine_weeks_ativas,
            delta_aplicado_semanas=delta_max,
        )

    coverage_end = runs[0]["end_idx"]
    for run in runs[1:]:
        gap = run["start_idx"] - coverage_end  # always > 0 here (runs never overlap by construction)

        if use_cost_threshold:
            # Cost-based: perpetuate if standby is cheaper than mob+demob
            demand_end = _boundary_required(chain_runs[-1], at_end=True, week_demand=week_demand)
            demand_start = _boundary_required(run, at_end=False, week_demand=week_demand)
            standby_cost = max(0, gap) * custo_standby_unit * min(demand_end, demand_start)
            perpetuate = standby_cost < (custo_mob_unit + custo_demob_unit)
        else:
            # Time-based: perpetuate if gap ≤ delta_max
            perpetuate = gap <= delta_max

        # ADR-079: G_r^viável hard constraint — never perpetuate beyond gap_max
        if gap > gap_max:
            perpetuate = False

        if perpetuate:
            chain_runs.append(run)
            coverage_end = max(coverage_end, run["end_idx"])
        else:
            chains.append(_flush_chain(chain_runs, len(chains) + 1))
            chain_runs = [run]
            coverage_end = run["end_idx"]

    # Flush final chain
    chains.append(_flush_chain(chain_runs, len(chains) + 1))
    return chains


