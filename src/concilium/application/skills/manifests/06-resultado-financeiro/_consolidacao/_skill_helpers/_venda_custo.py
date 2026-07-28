"""Skill 06 (_consolidacao) — Consolidação Financeira (parte extraída de _skill_helpers_a.py)."""

from __future__ import annotations

import logging

from concilium.domain.models.canonical import (
    AtividadeCustoCompleto,
    CanonicalModel,
    ValidacaoItem,
)

from ._categorial import _build_custo_categorial_bottom_up  # ty: ignore[unresolved-import]

logger = logging.getLogger(__name__)



def _calc_venda_com_bdi(
    canonical_in: CanonicalModel,
    bdi_rates: dict[str, float],
    bdi_indireto_efetivo: float | None = None,
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

    # Direto: combina consumivel e combustivel em material (ambos BDI_material = 4%)
    custo_material_total = cat.get("material", 0.0)  # inclui consumivel + combustivel
    venda_direto_eq = (
        cat["mao_obra"] * (1 + _bdi("mao_obra"))
        + cat["eq_aluguel"] * (1 + _bdi("equipamentos"))
        + custo_material_total * (1 + _bdi("material"))
    )

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

    return round(venda_direto_eq, 2), round(venda_indireto, 2), round(custo_indireto_total, 2)


def _cpu_familia(cpu_id: str) -> str:
    if not cpu_id:
        return ""
    if "-" in cpu_id:
        return cpu_id.split("-")[0]
    if "_" in cpu_id:
        return cpu_id.split("_")[0]
    return cpu_id


def _catv_from_scheduled(acts: list, eap_by_id: dict) -> list[AtividadeCustoCompleto]:
    out: list[AtividadeCustoCompleto] = []
    for act in acts:
        eap_item = eap_by_id.get(act.activity_id)
        nome = (eap_item.descricao or act.activity_id) if eap_item else act.activity_id
        out.append(
            AtividadeCustoCompleto(
                atividade_id=act.activity_id,
                nome=nome,
                semana_inicio=max(0, int(getattr(act, "start_week", 0) or 0)),
                semana_fim=max(0, int(getattr(act, "end_week", 0) or 0)),
                custos_diretos=[],
                custo_indireto_atribuido=0.0,
            )
        )
    return out


def _catv_from_equipes(equipes_diretas: list, eap_by_id: dict) -> list[AtividadeCustoCompleto]:
    out: list[AtividadeCustoCompleto] = []
    for eq in equipes_diretas:
        if not eq.item_id:
            continue
        eap_item = eap_by_id.get(eq.item_id)
        nome = (eap_item.descricao or eq.item_id) if eap_item else eq.item_id
        out.append(
            AtividadeCustoCompleto(
                atividade_id=eq.item_id,
                nome=nome,
                semana_inicio=0,
                semana_fim=0,
                custos_diretos=[],
                custo_indireto_atribuido=0.0,
            )
        )
    return out


def _build_custos_atividades(canonical_in: CanonicalModel) -> list[AtividadeCustoCompleto]:
    eap_by_id = {e.item_id: e for e in canonical_in.eap}
    acts = canonical_in.cronograma.scheduled_activities if canonical_in.cronograma else []
    out = _catv_from_scheduled(acts, eap_by_id)
    if not out:
        out = _catv_from_equipes(canonical_in.equipes_diretas, eap_by_id)
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

    # ADR-091: custo_total já armazena o custo total de todas as frentes (normalizado
    # em skill-05 por divisão por num_equipes_paralelas antes de armazenar).
    # Não multiplicar por num_equipes_base — evitar dupla contagem.
    custo_direto_equipe = sum(float(e.custo_total or 0.0) for e in canonical_in.equipes_diretas)

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


