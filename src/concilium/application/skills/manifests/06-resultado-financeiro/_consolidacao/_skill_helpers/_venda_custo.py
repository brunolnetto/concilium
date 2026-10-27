"""Skill 06 (_consolidacao) — Consolidação Financeira (parte extraída de _skill_helpers_a.py)."""

from __future__ import annotations

import logging

from concilium.domain.models.canonical import (
    AtividadeCustoCompleto,
    AtividadeInsumo,
    CanonicalModel,
    CustoDiretoSemanalAtividade,
    InsumoComponenteAtividade,
    MobilizacaoAtividade,
    ValidacaoItem,
)

from ._categorial import (  # ty: ignore[unresolved-import]
    _build_custo_categorial_bottom_up,
    _resolve_custo_equipe_agregado,
)

logger = logging.getLogger(__name__)



def _calc_venda_com_bdi(
    canonical_in: CanonicalModel,
    bdi_rates: dict[str, float],
    bdi_indireto_efetivo: float | None = None,
    custos_atividades: list[AtividadeCustoCompleto] | None = None,
) -> tuple[float, float, float]:
    """ADR-085 D5 / ADR-090: preço de venda bottom-up com BDI por sub-propriedade.

    Diretos:
      mao_obra (salario_encargos)  × BDI_mao_obra
      equipamento (aluguel)        × BDI_servicos
      material (combustivel)       × BDI_material  ← diesel = material (ADR-090)
      material (consumivel)        × BDI_material

    Indiretos (ADR-090 D5): BDI por sub-categoria em vez de taxa plana.
      mao_obra    × BDI_mao_obra   | equipamentos × BDI_servicos
      combustivel × BDI_material   | verba/mob    × BDI_indireto
    """
    cat = _build_custo_categorial_bottom_up(canonical_in)

    def _bdi(categoria: str) -> float:
        rate = bdi_rates.get(categoria)
        if rate is None:
            logger.warning("BDI sem taxa para '%s' — markup zero aplicado (preço de venda subavaliado)", categoria)
            return 0.0
        return float(rate)

    # ADR-184: déficit de estoque provisionado externamente (ADR-151) é custo de
    # material por natureza (uma compra), à mesma alíquota — sem categoria de BDI
    # dedicada (ver ADR-184 D4).
    custo_deficit_externo = cat.get("deficit_estoque_externo", 0.0)
    artifacts = (
        custos_atividades if custos_atividades is not None else _build_custos_atividades(canonical_in, bdi_rates)
    )
    venda_direto_eq = sum(custo.custo_direto_com_bdi for custo in artifacts)
    venda_direto_eq += custo_deficit_externo * (1 + _bdi("material"))

    # Indireto: BDI por sub-categoria (ADR-090 D5)
    r_mo = _bdi("mao_obra")
    r_eq = _bdi("equipamentos")
    r_mat = _bdi("material")
    r_indir = float(bdi_indireto_efetivo) if isinstance(bdi_indireto_efetivo, (int, float)) else _bdi("indireto")

    venda_indireto = 0.0
    custo_indireto_total = 0.0
    for ind in canonical_in.indiretos:
        ct = float(ind.custo_total or 0.0)
        custo_indireto_total += ct

        c_mo = float(ind.custo_mao_obra or 0.0)
        c_eq = float(ind.custo_equipamentos or 0.0)
        c_comb = float(ind.custo_combustivel or 0.0)
        c_verba = float(ind.custo_verba or 0.0)
        c_mob = float(ind.custo_mobilizacao or 0.0)
        c_sub = c_mo + c_eq + c_comb + c_verba + c_mob

        if c_sub > 0:
            # Sub-custos disponíveis: aplica BDI por categoria
            venda_indireto += (
                c_mo * (1 + r_mo) + c_eq * (1 + r_eq) + c_comb * (1 + r_mat) + (c_verba + c_mob) * (1 + r_indir)
            )
        else:
            # Fallback: taxa plana de indireto (quando skill-07 não calculou sub-custos)
            venda_indireto += ct * (1 + r_indir)
    venda_indireto += sum(
        custo.custo_mobilizacao_atividade * (1 + r_indir)
        for custo in artifacts
    )

    return round(venda_direto_eq, 2), round(venda_indireto, 2), round(custo_indireto_total, 2)


def _cpu_familia(cpu_id: str) -> str:
    if not cpu_id:
        return ""
    if "-" in cpu_id:
        return cpu_id.split("-")[0]
    if "_" in cpu_id:
        return cpu_id.split("_")[0]
    return cpu_id


def _activity_cost_components(equipe: object | None) -> tuple[float, float, float, float]:
    """Resolve MO, EQ, MAT e COMB existentes para uma atividade."""
    if equipe is None:
        return 0.0, 0.0, 0.0, 0.0
    if getattr(equipe, "custo_inst_mo", None) is not None:
        components = (
            float(getattr(equipe, "custo_inst_mo", 0.0) or 0.0),
            float(getattr(equipe, "custo_inst_eq", 0.0) or 0.0),
            float(getattr(equipe, "custo_inst_mat", 0.0) or 0.0),
            float(getattr(equipe, "custo_inst_comb", 0.0) or 0.0),
        )
        if (
            getattr(equipe, "custo_reconciliado_planejamento", False)
            and not getattr(equipe, "contrato_tipo_id", "")
        ):
            # Non-pool planning reconciliation is an aggregate direct-cost
            # authority. F3's decomposition closes custo_total including its
            # mob/demob partition, while Skill06 prices mob/demob separately.
            # Pool-backed instancial components are measured postings and must
            # remain authoritative even if the planning provenance flag remains
            # set from before pool allocation.
            target = float(getattr(equipe, "custo_operacional_agregado", 0.0) or 0.0)
            total = sum(components)
            if target > 0 and total > 0:
                factor = target / total
                components = tuple(value * factor for value in components)
        return components

    total = _resolve_custo_equipe_agregado(equipe)
    mo = float(getattr(equipe, "custo_mao_obra_mensal", 0.0) or 0.0) + float(
        getattr(equipe, "custo_encargos_mensal", 0.0) or 0.0
    )
    eq = float(getattr(equipe, "custo_equipamentos_mensal", 0.0) or 0.0)
    mat = float(getattr(equipe, "custo_material_mensal", 0.0) or 0.0)
    comb = float(getattr(equipe, "custo_combustivel_total_mensal", 0.0) or 0.0)
    base = mo + eq + mat + comb
    if base <= 0:
        return total, 0.0, 0.0, 0.0
    return tuple(total * component / base for component in (mo, eq, mat, comb))


def _formal_activity_cost_rates(equipe: object | None) -> tuple[float, float, float, float, float, float] | None:
    """Returns (rho, hours/week, gamma_mo, gamma_eq, gamma_mat, gamma_comb) when persisted by Skill 05."""
    if equipe is None:
        return None
    rho = float(getattr(equipe, "produtividade_horaria", 0.0) or 0.0)
    horas_semana = float(getattr(equipe, "horas_dia", 0.0) or 0.0) * float(
        getattr(equipe, "dias_semana", 0.0) or 0.0
    )
    gammas = tuple(
        float(getattr(equipe, field, 0.0) or 0.0)
        for field in (
            "gamma_mao_obra_catalogo",
            "gamma_equipamentos_catalogo",
            "gamma_material_catalogo",
            "gamma_combustivel_catalogo",
        )
    )
    if rho <= 0 or horas_semana <= 0 or not any(gammas):
        return None
    return rho, horas_semana, gammas[0], gammas[1], gammas[2], gammas[3]


def _activity_mobilization(equipe: object | None, act: object) -> MobilizacaoAtividade | None:
    """Materializa mob/demob como evento indireto, fora dos blocos diretos K e V."""
    if equipe is None:
        return None
    custo = float(getattr(equipe, "custo_mob_desmob", 0.0) or 0.0)
    if custo <= 0:
        return None
    distribuicao = getattr(act, "distribuicao_semanal", None) or {}
    semanas = list(distribuicao)
    if not semanas:
        return None
    return MobilizacaoAtividade(
        atividade_id=str(getattr(act, "activity_id", "")),
        fase="both",
        equipamentos=InsumoComponenteAtividade(nome="MOB_DEMOB", custo_total=custo),
        alocacao="ambas",
    )


def _build_activity_direct_cost(
    act: object,
    equipe: object | None,
    bdi_rates: dict[str, float],
) -> tuple[list[AtividadeInsumo], list[CustoDiretoSemanalAtividade], float, float, float]:
    mo, eq, mat, comb = _activity_cost_components(equipe)
    distribution = getattr(act, "distribuicao_semanal", None) or {}
    # F3 fills all four custo_inst_* fields for *non-pool* teams and closes
    # against custo_total, normally ONE reference front. A planning override
    # can change custo_total to an AGGREGATE subtotal *before* F3; that
    # provenance must be honoured. Pool-backed instancial components are
    # already measured aggregates regardless of front count.
    has_instancial_breakdown = equipe is not None and all(
        getattr(equipe, name, None) is not None
        for name in ("custo_inst_mo", "custo_inst_eq", "custo_inst_mat", "custo_inst_comb")
    )
    active_weeks = sum(1 for cell in distribution.values() if float(cell.num_equipes) > 0)
    team_weeks = sum(float(cell.num_equipes) for cell in distribution.values())
    one_front_f3 = (
        has_instancial_breakdown
        and not getattr(equipe, "contrato_tipo_id", "")
        # F3 is one-front ONLY before planning cost reconciliation. Skill05
        # explicitly records the aggregate source when its planning override
        # has replaced custo_total and custo_operacional_agregado.
        and not getattr(equipe, "custo_reconciliado_planejamento", False)
        and any(
            float(cell.num_equipes) > 0 and abs(float(cell.num_equipes) - 1.0) > 1e-9
            for cell in distribution.values()
        )
    )
    # For non-pool F3 with any non-unit effective fronts, reconstruct K/V over the actual
    # schedule from rates and physical quantities. This also retains consumed
    # materials excluded from custo_operacional_agregado. Do NOT use catalog
    # gamma for pool-backed measured postings (the original GOLDEN defect).
    formal_rates = (
        _formal_activity_cost_rates(equipe)
        if distribution and (not has_instancial_breakdown or one_front_f3)
        else None
    )
    if one_front_f3 and formal_rates is None and active_weeks:
        # Older / incomplete records may not have persisted formal gamma.
        # F3 is per active week of ONE front, so expand the reference K/V
        # components by actual team-weeks, without silently selling one front.
        factor = team_weeks / active_weeks
        mo, eq, mat, comb = (value * factor for value in (mo, eq, mat, comb))
    quantity_total = sum(float(cell.qtd_executada) for cell in distribution.values())
    weekly: list[CustoDiretoSemanalAtividade] = []
    for week, cell in distribution.items():
        if formal_rates is not None:
            rho, horas_semana, gamma_mo, gamma_eq, gamma_mat, gamma_comb = formal_rates
            week_mo = gamma_mo * horas_semana * float(cell.num_equipes)
            week_eq = gamma_eq * horas_semana * float(cell.num_equipes)
            week_mat = gamma_mat * float(cell.qtd_executada) / rho
            week_comb = gamma_comb * float(cell.qtd_executada) / rho
        else:
            team_share = float(cell.num_equipes) / team_weeks if team_weeks > 0 else 0.0
            quantity_share = float(cell.qtd_executada) / quantity_total if quantity_total > 0 else 0.0
            week_mo, week_eq = mo * team_share, eq * team_share
            week_mat, week_comb = mat * quantity_share, comb * quantity_share
        contractual = week_mo + week_eq
        variable = week_mat + week_comb
        operational = contractual + variable
        operational_bdi = (
            week_mo * (1 + float(bdi_rates.get("mao_obra", 0.0)))
            + week_eq * (1 + float(bdi_rates.get("equipamentos", 0.0)))
            + week_mat * (1 + float(bdi_rates.get("material", 0.0)))
            + week_comb * (1 + float(bdi_rates.get("diesel", bdi_rates.get("material", 0.0))))
        )
        weekly.append(
            CustoDiretoSemanalAtividade(
                semana_iso=week,
                quantitativo=float(cell.qtd_executada),
                frentes=float(cell.num_equipes),
                custo_mao_obra=week_mo,
                custo_equipamentos=week_eq,
                custo_material=week_mat,
                custo_combustivel=week_comb,
                custo_contratual=contractual,
                custo_variavel=variable,
                custo_operacional=operational,
                custo_operacional_com_bdi=operational_bdi,
                bdi_equivalente=operational_bdi / operational - 1 if operational > 0 else 0.0,
            )
        )
    if formal_rates is not None:
        mo = sum(cost.custo_mao_obra for cost in weekly)
        eq = sum(cost.custo_equipamentos for cost in weekly)
        mat = sum(cost.custo_material for cost in weekly)
        comb = sum(cost.custo_combustivel for cost in weekly)
    total_operacional = mo + eq + mat + comb
    total_com_bdi = (
        sum(cost.custo_operacional_com_bdi for cost in weekly)
        if formal_rates is not None
        else (
            mo * (1 + float(bdi_rates.get("mao_obra", 0.0)))
            + eq * (1 + float(bdi_rates.get("equipamentos", 0.0)))
            + mat * (1 + float(bdi_rates.get("material", 0.0)))
            + comb * (1 + float(bdi_rates.get("diesel", bdi_rates.get("material", 0.0))))
        )
    )
    bdi_equivalente = total_com_bdi / total_operacional - 1 if total_operacional > 0 else 0.0
    components = [
        AtividadeInsumo(
            categoria="DIRETO",
            mao_de_obra=InsumoComponenteAtividade(nome="MAO_DE_OBRA", custo_total=mo),
            equipamentos=InsumoComponenteAtividade(nome="EQUIPAMENTOS", custo_total=eq),
            material=InsumoComponenteAtividade(nome="MATERIAL", custo_total=mat),
            combustivel=InsumoComponenteAtividade(nome="COMBUSTIVEL", custo_total=comb),
        )
    ]
    return components, weekly, total_operacional, total_com_bdi, bdi_equivalente


def _catv_from_scheduled(
    acts: list,
    eap_by_id: dict,
    equipes_by_item: dict[str, object],
    bdi_rates: dict[str, float],
) -> list[AtividadeCustoCompleto]:
    out: list[AtividadeCustoCompleto] = []
    for act in acts:
        eap_item = eap_by_id.get(act.activity_id)
        nome = (eap_item.descricao or act.activity_id) if eap_item else act.activity_id
        components, weekly, operational, direct_bdi, bdi_equivalente = _build_activity_direct_cost(
            act, equipes_by_item.get(act.activity_id), bdi_rates
        )
        out.append(
            AtividadeCustoCompleto(
                atividade_id=act.activity_id,
                nome=nome,
                semana_inicio=max(0, int(getattr(act, "start_week", 0) or 0)),
                semana_fim=max(0, int(getattr(act, "end_week", 0) or 0)),
                custos_diretos=components,
                custos_diretos_semanais=weekly,
                custo_operacional_direto=operational,
                custo_direto_com_bdi=direct_bdi,
                bdi_equivalente_direto=bdi_equivalente,
                custo_indireto_atribuido=0.0,
                mobilizacao=_activity_mobilization(equipes_by_item.get(act.activity_id), act),
            )
        )
    return out


def _catv_from_equipes(
    equipes_diretas: list,
    eap_by_id: dict,
    bdi_rates: dict[str, float],
) -> list[AtividadeCustoCompleto]:
    out: list[AtividadeCustoCompleto] = []
    for eq in equipes_diretas:
        if not eq.item_id:
            continue
        eap_item = eap_by_id.get(eq.item_id)
        nome = (eap_item.descricao or eq.item_id) if eap_item else eq.item_id
        components, weekly, operational, direct_bdi, bdi_equivalente = _build_activity_direct_cost(
            object(), eq, bdi_rates
        )
        out.append(
            AtividadeCustoCompleto(
                atividade_id=eq.item_id,
                nome=nome,
                semana_inicio=0,
                semana_fim=0,
                custos_diretos=components,
                custos_diretos_semanais=weekly,
                custo_operacional_direto=operational,
                custo_direto_com_bdi=direct_bdi,
                bdi_equivalente_direto=bdi_equivalente,
                custo_indireto_atribuido=0.0,
            )
        )
    return out


def _build_custos_atividades(
    canonical_in: CanonicalModel,
    bdi_rates: dict[str, float] | None = None,
) -> list[AtividadeCustoCompleto]:
    eap_by_id = {e.item_id: e for e in (getattr(canonical_in, "eap", None) or [])}
    cronograma = getattr(canonical_in, "cronograma", None)
    acts = getattr(cronograma, "scheduled_activities", None) or []
    rates = bdi_rates or {}
    equipes = getattr(canonical_in, "equipes_diretas", None) or []
    equipes_by_item = {eq.item_id: eq for eq in equipes if eq.item_id}
    out = _catv_from_scheduled(acts, eap_by_id, equipes_by_item, rates)
    if not out:
        out = _catv_from_equipes(equipes, eap_by_id, rates)
    return out


def _bvc_totais_planejamento(planejamento: list) -> tuple[float, float, float]:
    venda_sem_bdi = sum(p.subtotal.sem_bdi.total for p in planejamento if p.subtotal is not None)
    venda_com_bdi = sum(p.subtotal.com_bdi.total for p in planejamento if p.subtotal is not None)
    custo_materiais = sum(p.subtotal.sem_bdi.material for p in planejamento if p.subtotal is not None)
    return venda_sem_bdi, venda_com_bdi, custo_materiais


def _bvc_apply_fallback(venda_sem_bdi: float, venda_com_bdi: float, custo_direto_equipe: float) -> tuple[float, float]:
    """Fallback: se planejamento vazio, venda_sem_bdi/venda_com_bdi = custo_direto_equipe."""
    if not venda_sem_bdi and custo_direto_equipe > 0:
        venda_sem_bdi = custo_direto_equipe
    if not venda_com_bdi and custo_direto_equipe > 0:
        venda_com_bdi = custo_direto_equipe
    return venda_sem_bdi, venda_com_bdi


def _br_build_venda_custo(canonical_in: CanonicalModel) -> tuple[float, float, float, float, float]:
    """Returns (venda_sem_bdi, venda_com_bdi, custo_direto_equipe, custo_materiais, custo_direto_pool).

    custo_direto_pool = custo real das equipes via pool (mob/demob/ociosidade incluídos).
    venda_sem_bdi     = PU×Q de catálogo (referência de mercado para confronto).
    Usar sempre o pool como base do custo operacional — o trunfo do pool é exatamente
    executar abaixo do PU×Q de catálogo, e isso deve aparecer no resultado financeiro.
    """
    venda_sem_bdi, venda_com_bdi, custo_materiais = _bvc_totais_planejamento(canonical_in.planejamento)

    # Issue #139 (parte 2): custo_total só é agregado (todas as frentes) para itens
    # cobertos por pool — para os demais, é "1 frente" (ADR-091/ADR-162 D4).
    # _resolve_custo_equipe_agregado trata os dois casos de forma consistente.
    custo_direto_equipe = sum(_resolve_custo_equipe_agregado(e) for e in canonical_in.equipes_diretas)

    venda_sem_bdi, venda_com_bdi = _bvc_apply_fallback(venda_sem_bdi, venda_com_bdi, custo_direto_equipe)

    # custo_direto_pool: pool é SEMPRE a base do custo operacional real.
    # Diferença vs venda_sem_bdi = economia (ou sobrepreço) capturado pelo pool.
    return venda_sem_bdi, venda_com_bdi, custo_direto_equipe, custo_materiais, custo_direto_equipe


def _br_append_gap_catalogo_validacao(validacoes: list, venda_sem_bdi: float, custo_direto: float) -> None:
    """Informativo: gap catálogo vs operacional (frentes_equiv_necessarias global)."""
    if venda_sem_bdi > 0 and custo_direto > 0:
        frentes_glob = round(custo_direto / venda_sem_bdi, 3)
        gap_abs = round(custo_direto - venda_sem_bdi, 2)
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-GAP-CATALOGO-OPERACIONAL",
                status="AVISO" if frentes_glob > 1.2 else "OK",
                mensagem=(
                    f"Gap catálogo→operacional: PU×Q = R$ {venda_sem_bdi:,.0f} vs "
                    f"custo direto real = R$ {custo_direto:,.0f} "
                    f"(fator {frentes_glob:.3f}× — gap R$ {gap_abs:,.0f}). "
                    "Todos os overheads são auditáveis no CuboPoolInstancial (ADR-086)."
                ),
            )
        )


# ADR-023 §D1: limiar de materialidade para o AVISO de possível sobreposição AC×ADM.
# Escolha (issue #126): 2% do custo operacional total para CADA lado (AC embutido e
# ADM real). Abaixo disso, qualquer um dos dois valores é pequeno o bastante para ser
# ruído de rateio/arredondamento e não merece interromper a leitura do resultado; acima
# disso, os dois já representam quantia material o suficiente para que uma eventual
# sobreposição conceitual (cobrar "administração" duas vezes) afete a margem de forma
# perceptível — só aí vale a pena pedir confirmação humana (time de orçamento) de que
# AC (overhead corporativo/matriz, via BDI) e ADM (equipe administrativa do canteiro,
# custo indireto real) são conceitos distintos e complementares neste projeto.
_LIMIAR_AC_ADM_PCT = 0.02


def _validate_ac_adm_sobreposicao(
    ac_rate_indireto: float,
    custo_indireto_total: float,
    adm_real: float,
    custo_operacional_real: float,
    validacoes: list,
) -> None:
    """Issue #126: AVISO informativo (nunca ERRO, nunca bloqueia) de possível dupla
    contagem entre o componente `ac` do BDI ("Administração central",
    `ComponentesBdi.ac` — domain/models/financial/bdi/_components.py:34) e o custo real
    de indireto categoria `ADM` (`Indireto.categoria == "ADM"` —
    domain/models/canonical/_financeiro_resultado.py:70-93), que por sua vez também
    recebe o mesmo componente `ac` via `_calc_venda_com_bdi` (acima, `r_indir`).

    IMPORTANTE: isto NÃO decide se há dupla contagem — essa é uma pergunta de negócio
    em aberto (issue #126), só confirmável com o time de orçamento. Esta validação
    apenas torna visível quando ambos os valores são simultaneamente significativos,
    para que alguém avalie se representam conceitos distintos (AC = overhead
    corporativo/matriz vs. ADM = equipe administrativa alocada no canteiro específico)
    ou se merecem revisão. Não remove, reduz nem recalcula nenhum dos dois valores.

    Heurística de detecção (análoga a `_validate_encargos_separacao` /
    VAL-PLAN-ENCARGOS-DUPLA): `ac_rate_indireto × custo_indireto_total` aproxima o
    valor de administração central embutido no BDI que incide sobre os indiretos do
    projeto. Comparado contra o custo real de ADM, ambos expressos como fração do
    custo operacional total (direto + indireto) para julgar materialidade.
    """
    if custo_operacional_real <= 0:
        return
    ac_embutido = round(ac_rate_indireto * custo_indireto_total, 2)
    ac_pct = ac_embutido / custo_operacional_real
    adm_pct = adm_real / custo_operacional_real
    if ac_pct > _LIMIAR_AC_ADM_PCT and adm_pct > _LIMIAR_AC_ADM_PCT:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-BDI-AC-ADM-POSSIVEL-SOBREPOSICAO",
                status="AVISO",
                mensagem=(
                    f"AC embutido no BDI (R$ {ac_embutido:,.0f}, {ac_pct * 100:.1f}% do custo "
                    f"operacional) e custo real de ADM (R$ {adm_real:,.0f}, {adm_pct * 100:.1f}%) "
                    "são ambos significativos neste projeto — confirme que representam conceitos "
                    "distintos (ex: overhead corporativo vs. equipe administrativa do canteiro) "
                    "e não estão cobrando a mesma coisa duas vezes."
                ),
            )
        )


