"""Skill 06 — Consolidação Financeira (Consolidada).

Consolida:
1. Consolidação de Resultado (antiga 06)
2. Reconciliação de Custos de Recurso (antiga 06A)
3. Análise de Compensação Estrutural — The Bridge (ADR-039)

Objetivo: Produzir o balanço final de venda, custo e margem, já considerando impactos de aquisição
e separando os desvios estruturais (escala + clima) do delta real de gestão.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from concilium.domain.models.canonical import (
    AtividadeCustoCompleto,
    CanonicalModel,
    CustoParticionadoItem,
    CustoTotal,
    LeverEquilibrio,
    PontoEquilibrio,
    Resultado,
    ValidacaoItem,
    Venda,
)

if TYPE_CHECKING:
    from concilium.domain.models.financial.bdi import TabelaBdi

try:
    # Hyphenated manifest dir: only loaded at runtime via a synthetic package
    # (see concilium/application/skills/__init__.py); ty cannot resolve this
    # statically.
    from ._skill_helpers_b import _classificar_margem, _resolve_bdi_full  # ty: ignore[unresolved-import]
except ImportError:
    import importlib.util
    from pathlib import Path

    _here = Path(__file__).resolve().parent
    _path_b = _here / "_skill_helpers_b.py"
    _spec_b = importlib.util.spec_from_file_location("skill08_helpers_b_for_a", _path_b)
    if _spec_b is None or _spec_b.loader is None:
        raise ImportError(f"Não foi possível carregar spec para: {_path_b}") from None
    _mod_b = importlib.util.module_from_spec(_spec_b)
    _spec_b.loader.exec_module(_mod_b)
    _classificar_margem = _mod_b._classificar_margem
    _resolve_bdi_full = _mod_b._resolve_bdi_full

logger = logging.getLogger(__name__)


def _build_custo_categorial_bottom_up(canonical_in: CanonicalModel) -> dict[str, float]:
    """ADR-085 D4/D5 / ADR-089: custo instancial por sub-propriedade (base bottom-up para BDI).

    Retorna ``{"mao_obra", "eq_aluguel", "eq_combustivel", "material"}`` em R$ (sem BDI).
    "eq_aluguel" = aluguel + manutenção (BDI_servicos); "eq_combustivel" = diesel (BDI_diesel).
    Compatibilidade com consumidores legados via chaves "equipamentos" e "diesel".
    """
    cat = {
        "mao_obra": 0.0,
        "eq_aluguel": 0.0,  # aluguel + manutencao → BDI_servicos
        "material": 0.0,  # consumivel + combustivel → BDI_material (ADR-090)
        # Aliases legados (retrocompat)
        "equipamentos": 0.0,  # = eq_aluguel
        "diesel": 0.0,  # = parcela de material.combustivel
        # Mantido para granularidade de diagnóstico (não usado no BDI)
        "eq_combustivel": 0.0,
    }

    # ADR-091: custo_total já é o custo total de todas as frentes — não multiplicar por
    # num_equipes_base para evitar dupla contagem (mesma correção de _br_build_venda_custo).
    nfrentes_por_item: dict[str, int] = {
        eq.item_id: 1  # custo_inst_* já incluem todas as frentes
        for eq in canonical_in.equipes_diretas
    }

    # 1. Itens com partição instancial categorial (pool, ADR-085 ativo)
    part_by_item: dict[str, Any] = {}
    for contrato in canonical_in.contratos_recurso:
        for part in contrato.particao_por_item:
            if part.custo_inst_mo or part.custo_inst_eq or part.custo_inst_comb or part.custo_inst_mat:
                part_by_item[part.item_id] = part

    contados: set[str] = set()
    for item_id, part in part_by_item.items():
        _nf = nfrentes_por_item.get(item_id, 1)
        _mo = float(part.custo_inst_mo or 0.0) * _nf
        _eq = float(part.custo_inst_eq or 0.0) * _nf
        _comb = float(part.custo_inst_comb or 0.0) * _nf
        _mat = float(part.custo_inst_mat or 0.0) * _nf
        # Mob+demob+idle: custo contratual além do produtivo — vai para eq_aluguel (BDI_servicos)
        _mob = float(getattr(part, "custo_mob_imputado", 0.0) or 0.0) * _nf
        _demob = float(getattr(part, "custo_demob_imputado", 0.0) or 0.0) * _nf
        _idle = float(getattr(part, "custo_ocioso_imputado", 0.0) or 0.0) * _nf
        cat["mao_obra"] += _mo
        cat["eq_aluguel"] += _eq + _mob + _demob + _idle
        cat["material"] += _mat + _comb  # ADR-090: combustivel funde em material
        cat["eq_combustivel"] += _comb  # diagnóstico granular
        contados.add(item_id)

    # 2. Demais itens: prioriza custo_inst_* se disponível (ADR-106 F7), senão heurística proporcional
    # NEP-043: custo_inst_* armazena custo de 1 frente — multiplicar por num_equipes_base
    # (mesma correção de _br_build_venda_custo, que usa custo_total × n_frentes).
    for eq in canonical_in.equipes_diretas:
        if eq.item_id in contados:
            continue
        # ADR-091: custo_total já armazena o custo total de todas as frentes.
        ct = float(eq.custo_total or 0.0)

        # ADR-106 F7: usar custo_inst_* diretamente quando preenchidos (F3 garantiu isso)
        if getattr(eq, "custo_inst_mo", None) is not None:
            _ct_mo = float(eq.custo_inst_mo or 0.0)
            _ct_eq = float(getattr(eq, "custo_inst_eq", 0.0) or 0.0)
            _ct_comb = float(getattr(eq, "custo_inst_comb", 0.0) or 0.0)
            _ct_mat = float(getattr(eq, "custo_inst_mat", 0.0) or 0.0)
            cat["mao_obra"] += _ct_mo
            cat["eq_aluguel"] += _ct_eq
            cat["material"] += _ct_mat + _ct_comb  # ADR-090: combustivel funde em material
            cat["eq_combustivel"] += _ct_comb
            continue

        # Fallback heurístico (legado) para equipes sem custo_inst_* preenchido
        # NEP-037: incluir encargos na fração de MO para decomposição (encargos ficam em mao_obra)
        _mo_mais_enc = float(eq.custo_mao_obra_mensal or 0.0) + float(getattr(eq, "custo_encargos_mensal", 0.0) or 0.0)
        base = (
            _mo_mais_enc
            + float(eq.custo_equipamentos_mensal or 0.0)
            + float(eq.custo_combustivel_total_mensal or 0.0)
            + float(eq.custo_material_mensal or 0.0)
        )
        if base <= 0:
            cat["mao_obra"] += ct
            continue
        _ct_mo = ct * _mo_mais_enc / base
        _ct_eq = ct * float(eq.custo_equipamentos_mensal or 0.0) / base
        _ct_comb = ct * float(eq.custo_combustivel_total_mensal or 0.0) / base
        _ct_mat = ct * float(eq.custo_material_mensal or 0.0) / base
        cat["mao_obra"] += _ct_mo
        cat["eq_aluguel"] += _ct_eq
        cat["material"] += _ct_mat + _ct_comb  # ADR-090: combustivel funde em material
        cat["eq_combustivel"] += _ct_comb

    # Aliases legados (retrocompat)
    cat["equipamentos"] = cat["eq_aluguel"]
    cat["diesel"] = cat["eq_combustivel"]
    return {k: round(v, 2) for k, v in cat.items()}


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


def _build_custos_atividades(canonical_in: CanonicalModel) -> list[AtividadeCustoCompleto]:
    eap_by_id = {e.item_id: e for e in canonical_in.eap}
    out: list[AtividadeCustoCompleto] = []
    acts = canonical_in.cronograma.scheduled_activities if canonical_in.cronograma else []
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

    if not out:
        for eq in canonical_in.equipes_diretas:
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


def _br_build_venda_custo(canonical_in: CanonicalModel) -> tuple[float, float, float, float, float]:
    """Returns (venda_sem_bdi, venda_com_bdi, custo_direto_equipe, custo_materiais, custo_direto_pool).

    custo_direto_pool = custo real das equipes via pool (mob/demob/ociosidade incluídos).
    venda_sem_bdi     = PU×Q de catálogo (referência de mercado para confronto).
    Usar sempre o pool como base do custo operacional — o trunfo do pool é exatamente
    executar abaixo do PU×Q de catálogo, e isso deve aparecer no resultado financeiro.
    """
    venda_sem_bdi = sum(p.subtotal.sem_bdi.total for p in canonical_in.planejamento if p.subtotal is not None)
    venda_com_bdi = sum(p.subtotal.com_bdi.total for p in canonical_in.planejamento if p.subtotal is not None)

    # ADR-091: custo_total já armazena o custo total de todas as frentes (normalizado
    # em skill-05 por divisão por num_equipes_paralelas antes de armazenar).
    # Não multiplicar por num_equipes_base — evitar dupla contagem.
    custo_direto_equipe = sum(float(e.custo_total or 0.0) for e in canonical_in.equipes_diretas)
    custo_materiais = sum(p.subtotal.sem_bdi.material for p in canonical_in.planejamento if p.subtotal is not None)

    # Fallback: se planejamento vazio, venda_sem_bdi = custo_direto_equipe
    if not venda_sem_bdi and custo_direto_equipe > 0:
        venda_sem_bdi = custo_direto_equipe
    if not venda_com_bdi and custo_direto_equipe > 0:
        venda_com_bdi = custo_direto_equipe

    # custo_direto_pool: pool é SEMPRE a base do custo operacional real.
    # Diferença vs venda_sem_bdi = economia (ou sobrepreço) capturado pelo pool.
    return venda_sem_bdi, venda_com_bdi, custo_direto_equipe, custo_materiais, custo_direto_equipe


def _build_resultado(
    canonical_in: CanonicalModel, inputs: dict, validacoes: list, perfil: dict
) -> tuple[
    Resultado,
    dict[str, float],
    TabelaBdi,
    str,
    str,
    bool,
    float,
    float,
    float,
    float,
    str,
    float,
    float,
    float,
]:
    """Computa resultado financeiro e retorna.

    Returns: (res, bdi_rates, bdi_tabela, bdi_fonte, bdi_regime, bdi_override,
    venda_sem_bdi, venda_catalogo_plus, margem, custo_direto_equipe, status_margem,
    venda_plus, custo_operacional_real, custo_total_catalogo).
    """
    venda_sem_bdi, venda_com_bdi, custo_direto_equipe, _custo_mat, custo_direto = _br_build_venda_custo(canonical_in)
    bdi_rates, _bdi_tabela, _bdi_fonte, _bdi_regime, _bdi_override = _resolve_bdi_full(inputs, validacoes)
    bdi_indireto_efetivo = inputs.get("bdi_indireto_efetivo")
    if not isinstance(bdi_indireto_efetivo, (int, float)):
        bdi_indireto_efetivo = None
    venda_direto_eq, venda_indireto, custo_indireto_total = _calc_venda_com_bdi(
        canonical_in,
        bdi_rates,
        bdi_indireto_efetivo,
    )
    custos_indiretos = {ind.categoria: ind.custo_total for ind in canonical_in.indiretos}

    venda_catalogo_plus = round(venda_com_bdi + venda_indireto, 2)  # N1×BDI — usado só na bridge
    venda_plus = round(venda_direto_eq + venda_indireto, 2)  # preço operacional (base do resultado)

    # ── Pricing consolidado ───────────────────────────────────────────────────────
    # custo_operacional_real: pool (produtivo + idle + mob/demob) + indiretos.
    # venda_plus: BDI aplicado sobre custo operacional real por componente.
    # Margem sempre sobre venda_plus — venda_catalogo_plus é referência de mercado (bridge/N1).
    custo_operacional_real = round(custo_direto + custo_indireto_total, 2)
    resultado_fin = round(venda_plus - custo_operacional_real, 2)
    margem = resultado_fin / venda_plus if venda_plus > 0 else 0.0

    # markup efetivo: venda_catalogo_plus / custo_real (para auditoria do consolidado)
    bdi_lucro = (venda_catalogo_plus / custo_operacional_real - 1) if custo_operacional_real > 0 else 0.0

    # custo_total_catalogo preservado para o confronto de benchmark (PU×Q + indireto)
    custo_total_catalogo = venda_sem_bdi + custo_indireto_total

    status_margem = _classificar_margem(margem, perfil["faixa_margem_alvo"], perfil["faixa_margem_aceitavel"])
    status_val = "OK" if status_margem != "VERMELHO" else "AVISO"
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-CONSOL-MARGEM",
            status=status_val,
            mensagem=(
                f"Margem operacional {margem * 100:.2f}% | status={status_margem} "
                f"| preço R$ {venda_plus:,.0f} (operacional) vs R$ {venda_catalogo_plus:,.0f} (catálogo)"
            ),
        )
    )
    # Informativo: gap catálogo vs operacional (frentes_equiv_necessarias global)
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
    indir_kwargs = {f"indireto_{k.lower()}": v for k, v in custos_indiretos.items() if k != "MOB"}
    res = Resultado(
        venda=Venda(
            total_sem_bdi=venda_sem_bdi,
            # total_com_bdi mantém contrato histórico de benchmark (PU×Q×BDI + indiretos).
            # A visão operacional (custo instancial × BDI) segue em total_custo_plus.
            total_com_bdi=venda_catalogo_plus,
            total_custo_plus=venda_plus,
            # total_custo_plus_catalogo: benchmark de mercado (PU×Q×BDI).
            # Lido por projection.py para o gate do confronto — benchmark estável.
            total_custo_plus_catalogo=venda_catalogo_plus,
            bdi_lucro_impostos=bdi_lucro,
        ),
        custo=CustoTotal(
            direto_equipes=custo_direto,
            # total agora é o custo operacional real (não o catálogo+indireto)
            total=custo_operacional_real,
            **indir_kwargs,
            indireto_mob=custos_indiretos.get("MOB", 0),
        ),
        resultado_financeiro=resultado_fin,
        margem_pct=margem,
        status_margem=status_margem,
        validacoes=[],
    )
    return (
        res,
        bdi_rates,
        _bdi_tabela,
        _bdi_fonte,
        _bdi_regime,
        _bdi_override,
        venda_sem_bdi,
        venda_catalogo_plus,
        margem,
        custo_direto_equipe,
        status_margem,
        venda_plus,
        custo_operacional_real,
        custo_total_catalogo,
    )


def _lesao_from_sched(sched: Any) -> dict:
    """Extrai fatores de lesão de produtividade de uma ScheduledActivityCanonical."""
    dist = getattr(sched, "distribuicao_semanal", None) or {}
    if not dist:
        return {}
    team_weeks = sum(d.num_equipes for d in dist.values())
    active_weeks = sum(1 for d in dist.values() if d.num_equipes > 0)
    if team_weeks == 0:
        return {}
    soma_clima = sum(getattr(d, "fator_clima", 1.0) * d.num_equipes for d in dist.values())
    soma_cal = sum(getattr(d, "fator_calendario", 1.0) * d.num_equipes for d in dist.values())
    semanas_lesadas = sum(1 for d in dist.values() if getattr(d, "fator_clima", 1.0) < 0.90)
    # NEP-042 TD-3: eMW_i = Σ_j(m_{ij} × η_j) usando fator_total (= η_s·η_p·η_w)
    # Preferir fator_total quando disponível; fallback para fator_clima × fator_calendario
    emw = sum(
        d.num_equipes
        * float(
            getattr(d, "fator_total", None) or (getattr(d, "fator_clima", 1.0) * getattr(d, "fator_calendario", 1.0))
        )
        for d in dist.values()
    )
    return {
        "team_weeks": team_weeks,
        "active_weeks": active_weeks,
        "effective_machine_weeks": round(emw, 4),
        "fator_clima": round(soma_clima / team_weeks, 4),
        "fator_cal": round(soma_cal / team_weeks, 4),
        "semanas_lesadas_clima": semanas_lesadas,
    }


def _build_diagnostico_lesao(
    n_equipes: float,
    fator_clima: float,
    semanas_lesadas: int,
    semanas_ativas: int,
    gap_escala: float,
    gap_pool: float,
) -> str:
    """Gera texto de justificativa de lesão para o campo diagnostico_lesao."""
    partes: list[str] = []

    # Lesão por escala de equipes
    if n_equipes > 1.05:
        partes.append(
            f"{n_equipes:.1f} equipes simultaneas (compressao de prazo): "
            f"+{(n_equipes - 1.0) * 100:.0f}% custo sobre 1 equipe."
        )

    # Lesão climática
    lesao_clima_pct = (1.0 - fator_clima) * 100
    if lesao_clima_pct > 0.5 and semanas_lesadas > 0:
        partes.append(
            f"{semanas_lesadas} sem. de {semanas_ativas} com clima < 90% "
            f"(f_clima={fator_clima:.3f}, lesao {lesao_clima_pct:.1f}% da produtividade horaria)."
        )

    # Pool overhead
    if gap_pool > 1_000:
        partes.append(f"Overhead de pool: R$ {gap_pool:,.0f} (ociosidade do contrato compartilhado).")

    if not partes:
        return "Sem desvio significativo identificado."
    return " | ".join(partes)


def _build_pe_for_equipe(
    equipe: Any,
    venda_por_item: dict,
    planejamento_por_item: dict | None = None,
    sched_por_item: dict | None = None,
    particao_por_item: dict | None = None,
    idle_por_item: dict | None = None,
    pool_total_por_item: dict | None = None,
) -> PontoEquilibrio | None:
    """Constrói PontoEquilibrio para uma equipe. Retorna None se custo_fixo ≤ 0.

    ADR-076:
    - planejamento_por_item: frentes_equivalentes_necessarias (Opção C) e calibração PU (Opção D).
    - sched_por_item: fatores de lesão de produtividade (fator_clima, n_equipes, semanas_lesadas).
    ADR-083:
    - particao_por_item: {item_id: CustoParticionadoItem} — decomposição causal do gap_pool.
    """
    permanencia_base = float(
        getattr(equipe, "permanencia_efetiva_meses", 0.0) or getattr(equipe, "permanencia_meses", 0.0) or 1.0
    )
    custo_fixo_total = equipe.custo_fixo_mensal * permanencia_base
    if custo_fixo_total <= 0:
        return None
    custo_venda_total = venda_por_item.get(equipe.item_id, 0.0)
    delta = custo_venda_total - custo_fixo_total
    custo_operacional_real = float(equipe.custo_total or 0.0)
    frentes = custo_operacional_real / custo_fixo_total if custo_fixo_total > 0 else 1.0

    # ADR-091: custo_total já armazena o custo total de todas as frentes (normalizado em
    # skill-05). _n_frentes mantido apenas para gap_escala e diagnóstico.
    _n_frentes = max(1, int(getattr(equipe, "num_equipes_base", 1) or 1))

    # ── ADR-076 campos quantitativos ──────────────────────────────────────────
    # custo_total_autonomo: por ADR-091, custo_total_autonomo no canônico representa
    # o custo de 1 frente autônoma → multiplicar por n_frentes para total.
    _custo_1fr_autonomo = float(getattr(equipe, "custo_total_autonomo", 0.0) or 0.0)
    if _custo_1fr_autonomo <= 0 and custo_operacional_real > 0:
        _custo_1fr_autonomo = custo_operacional_real
    custo_total_autonomo = _custo_1fr_autonomo * _n_frentes

    # gap_pool_overhead: quando idle_por_item está disponível (pool ativo), usa idle real.
    # Caso contrário, fallback para diferença entre custo operacional e custo autônomo.
    idle_item = (idle_por_item or {}).get(equipe.item_id, 0.0)
    if idle_por_item is not None:
        gap_pool_overhead = round(float(idle_item), 2)
    else:
        gap_pool_overhead = round(float(max(0.0, custo_operacional_real - custo_total_autonomo)), 2)

    # fe_nec = custo_total_autonomo / (PU_sbdi × Q) = 1/η_p
    # NOTA: PU_sbdi JÁ inclui encargos no numerador (nota NEP-029: B_base×(1+enc)).
    # Portanto fe_nec usa custo_total (com encargos) — não remover encargos aqui.
    # custo_encargos_mensal serve para decomposição interna (ADR-104, cubo, memorial),
    # não para calibração de fe_nec. Ver investigação de invariantes 2026-06-09.

    pu_catalogo_unitario: float = 0.0
    pu_calibrado_unitario: float = 0.0
    ajuste_minimo_pct: float = 0.0
    frentes_nec: float = 1.0
    gap_praticabilidade_abs: float = 0.0
    gap_escala_abs: float = 0.0

    plan = (planejamento_por_item or {}).get(equipe.item_id)
    if plan is not None and plan.subtotal and plan.quantitativo and plan.quantitativo > 0:
        Q = float(plan.quantitativo)
        venda_sem_bdi = float(plan.subtotal.sem_bdi.total if (plan.subtotal and plan.subtotal.sem_bdi) else 0.0)
        pu_catalogo_unitario = round(venda_sem_bdi / Q, 4) if Q > 0 else 0.0

        if venda_sem_bdi > 0 and custo_total_autonomo > 0:
            frentes_nec = round(custo_total_autonomo / venda_sem_bdi, 4)
        elif custo_total_autonomo <= 0 and custo_venda_total > 0:
            frentes_nec = round(custo_operacional_real / custo_venda_total, 4)

        # ADR-076 Fallback: se frentes_nec >> 10 (absurdo), usar 1 como conservador
        if frentes_nec > 10.0:
            frentes_nec = 1.0

        pu_aut_unit = custo_total_autonomo / Q if custo_total_autonomo > 0 else 0.0
        pu_calibrado_unitario = round(max(pu_catalogo_unitario, pu_aut_unit), 4)
        if pu_catalogo_unitario > 0:
            ajuste_minimo_pct = round((pu_calibrado_unitario - pu_catalogo_unitario) / pu_catalogo_unitario * 100, 2)

        # gap_praticabilidade é calculado após lesao ser resolvida (fator_clima_v necessário)

    # ── ADR-076 Lesão de Produtividade (via distribuicao_semanal) ─────────────
    lesao: dict = {}
    sched = (sched_por_item or {}).get(equipe.item_id)
    if sched is not None:
        lesao = _lesao_from_sched(sched)

    n_equipes_ef = (
        round(lesao["team_weeks"] / lesao["active_weeks"], 2)
        if lesao and lesao.get("active_weeks", 0) > 0
        else round(permanencia_base / float(getattr(equipe, "permanencia_meses", 1.0) or 1.0), 2)
    )
    semanas_ativas_v = lesao.get("active_weeks", 0)
    fator_clima_v = lesao.get("fator_clima", 1.0)
    fator_cal_v = lesao.get("fator_cal", 1.0)
    semanas_lesadas_v = lesao.get("semanas_lesadas_clima", 0)

    # NEP-042: Camada 2 — PU operacional autônomo, machine-weeks, η_real
    _Q = float((plan.quantitativo if plan else 0) or 0)
    pu_operacional_autonomo = round(custo_total_autonomo / _Q, 4) if _Q > 0 and custo_total_autonomo > 0 else 0.0
    machine_weeks_brutas = float(lesao.get("team_weeks", 0)) if lesao else 0.0
    # TD-3: usar eMW exacto (Σ m_{ij}·η_j) de fator_total quando disponível
    machine_weeks_efetivas = float(lesao.get("effective_machine_weeks", 0)) if lesao else 0.0
    if machine_weeks_efetivas == 0 and machine_weeks_brutas > 0:
        # fallback para produto das médias se effective_machine_weeks não computado
        _feta = float(lesao.get("fator_clima", 1.0)) * float(lesao.get("fator_cal", 1.0)) if lesao else 1.0
        machine_weeks_efetivas = round(machine_weeks_brutas * _feta, 4)
    eta_real = round(machine_weeks_efetivas / machine_weeks_brutas, 4) if machine_weeks_brutas > 0 else 1.0

    # NEP-042 / ADR-091: Camada 3 — custo pool instancial agregado e PU pool.
    # pool_total_por_item (particao_por_item) já armazena o custo total de todas as
    # frentes — não multiplicar por n_frentes (evitar dupla contagem).
    _raw_pool = float((pool_total_por_item or {}).get(equipe.item_id, 0.0))
    custo_pool_total = round(_raw_pool, 2) if _raw_pool > 0 else 0.0
    custo_pool_por_unidade = round(custo_pool_total / _Q, 4) if _Q > 0 and custo_pool_total > 0 else 0.0
    economia_pool_abs = round(custo_total_autonomo - custo_pool_total, 2)

    # ADR-083 §4: gap_praticabilidade — custo excedente C_eps por η̄ < 1 (clima/terreno)
    # NEP-043: C_eps = (PU_mo + PU_eq) × Q × (1/η - 1) × n_frentes
    # Diesel NÃO integra C_eps: ocorre por produção (não por calendário), é constante em Q.
    # Apenas MO e EQ acumulam custo em intervalos não produtivos (extensão do prazo).
    # fator_clima_v é a média ponderada de η por team-weeks; gap = 0 quando η = 1.
    if fator_clima_v < 0.9999 and plan is not None and _Q > 0:
        _pu = plan.preco_unitario if plan and plan.preco_unitario else None
        _pu_mo_eq = (
            float((getattr(_pu, "mao_obra", 0.0) or 0.0) + (getattr(_pu, "equipamentos", 0.0) or 0.0)) if _pu else 0.0
        )
        if _pu_mo_eq > 0:
            # PU_mo_eq × Q já representa o custo total de MO+EQ para a atividade completa;
            # não multiplicar por n_frentes (PU×Q é total, não por frente).
            gap_praticabilidade_abs = round(_pu_mo_eq * _Q * (1.0 / fator_clima_v - 1.0), 2)

    # gap_escala_abs: custo adicional por usar N>1 equipes vs 1 equipe × perm.nominal
    perm_nom = float(getattr(equipe, "permanencia_meses", 0.0) or 0.0)
    custo_base_cat = equipe.custo_fixo_mensal * perm_nom if perm_nom > 0 else custo_fixo_total / max(n_equipes_ef, 1.0)
    gap_escala_abs = round(custo_base_cat * max(0.0, n_equipes_ef - 1.0), 2)

    diag = _build_diagnostico_lesao(
        n_equipes=n_equipes_ef,
        fator_clima=fator_clima_v,
        semanas_lesadas=semanas_lesadas_v,
        semanas_ativas=semanas_ativas_v,
        gap_escala=gap_escala_abs,
        gap_pool=gap_pool_overhead,
    )

    # Threshold status_frentes: OK ≤ 1.25, AVISO ≤ 1.5, CRITICO > 1.5
    status_frentes: Literal["OK", "AVISO", "CRITICO"]
    if frentes_nec <= 1.25:
        status_frentes = "OK"
    elif frentes_nec <= 1.5:
        status_frentes = "AVISO"
    else:
        status_frentes = "CRITICO"

    # ── ADR-082: Levers de ajuste do ponto de equilíbrio ─────────────────────
    levers: list = []
    _cv = custo_venda_total  # alias para legibilidade
    if gap_escala_abs > 0:
        levers.append(
            LeverEquilibrio(
                id="fechar_gap_escala",
                tipo="custo",
                descricao=f"Paralelismo: {n_equipes_ef:.1f}x frentes (quantizacao de equipes)",
                delta_margin=round(gap_escala_abs, 2),
                delta_margin_pct=round(gap_escala_abs / _cv, 6) if _cv > 0 else 0.0,
                viavel=n_equipes_ef > 1.05,
                restricoes=[f"Sequencializar estende prazo +{(n_equipes_ef - 1.0) * 100:.0f}%"]
                if n_equipes_ef > 1.5
                else [],
            )
        )
    if gap_praticabilidade_abs > 0:
        levers.append(
            LeverEquilibrio(
                id="fechar_gap_praticabilidade",
                tipo="custo",
                descricao=f"Praticabilidade: eta={fator_clima_v:.1%} aproveitamento efetivo",
                delta_margin=round(gap_praticabilidade_abs, 2),
                delta_margin_pct=round(gap_praticabilidade_abs / _cv, 6) if _cv > 0 else 0.0,
                viavel=True,
                restricoes=[],
            )
        )
    if gap_pool_overhead > 0:
        # ADR-083: decompor gap_pool em overhead de ociosidade e economia de mob/demob
        _particao = (particao_por_item or {}).get(equipe.item_id)
        _pool_restricoes: list[str] = []
        if _particao is not None:
            if _particao.overhead_ocioso > 0:
                _pool_restricoes.append(f"Ociosidade de gap: R$ {_particao.overhead_ocioso:,.0f}")
            if _particao.economia_mob > 0:
                _pool_restricoes.append(f"Economia mob/demob: −R$ {_particao.economia_mob:,.0f}")
            _saldo = _particao.overhead_ocioso - _particao.economia_mob
            _pool_restricoes.append(
                f"Saldo pool ({'+overhead' if _saldo > 0 else 'economia líquida'}): R$ {abs(_saldo):,.0f}"
            )
            # ADR-084 Fase 4: exibir predecessor_critico_id e overlap_semanas quando disponíveis
            if getattr(_particao, "predecessor_critico_id", None):
                _pool_restricoes.append(f"Predecessor critico: {_particao.predecessor_critico_id}")
            if getattr(_particao, "overlap_semanas", 0.0) > 0:
                _pool_restricoes.append(f"Sobreposicao: {_particao.overlap_semanas:.1f} semanas")
        levers.append(
            LeverEquilibrio(
                id="fechar_gap_pool",
                tipo="custo",
                descricao="ResourcePool: overhead mob/demob e ociosidade de contrato",
                delta_margin=round(gap_pool_overhead, 2),
                delta_margin_pct=round(gap_pool_overhead / _cv, 6) if _cv > 0 else 0.0,
                viavel=True,
                restricoes=_pool_restricoes,
            )
        )
    if delta < 0:
        levers.append(
            LeverEquilibrio(
                id="revisao_bdi_minima",
                tipo="preco",
                descricao=(
                    f"BDI: +{ajuste_minimo_pct:.1f}% no PU catalogo para PE nulo"
                    if ajuste_minimo_pct > 0
                    else "BDI: revisao minima de preco para cobrir ineficiencia"
                ),
                delta_margin=round(-delta, 2),
                delta_margin_pct=round(-delta / _cv, 6) if _cv > 0 else 0.0,
                viavel=True,
                restricoes=["Lever de precificacao — fora do alcance do planejador"],
            )
        )

    return PontoEquilibrio(
        item_id=equipe.item_id,
        custo_fixo_equipe=round(custo_fixo_total, 2),
        custo_venda_cpu=round(custo_venda_total, 2),
        delta=round(delta, 2),
        delta_pct=round(delta / custo_fixo_total, 5),
        status_validacao="OK" if delta >= 0 else "ERRO",
        custo_operacional_real=round(custo_operacional_real, 2),
        frentes_equivalentes=round(frentes, 2),
        # ADR-076 Opção C
        frentes_equivalentes_necessarias=frentes_nec,
        gap_pool_overhead=gap_pool_overhead,
        status_frentes=status_frentes,
        # ADR-076 Opção D
        pu_catalogo_unitario=pu_catalogo_unitario,
        pu_calibrado_unitario=pu_calibrado_unitario,
        ajuste_minimo_pct=ajuste_minimo_pct,
        gap_praticabilidade_abs=gap_praticabilidade_abs,
        gap_pool_abs=round(-economia_pool_abs, 2) if economia_pool_abs != 0 else gap_pool_overhead,
        # ADR-076 Justificativa de Lesão
        n_equipes_efetivo=n_equipes_ef,
        semanas_ativas=semanas_ativas_v,
        fator_clima_medio=fator_clima_v,
        fator_calendario_medio=fator_cal_v,
        semanas_lesadas_clima=semanas_lesadas_v,
        gap_escala_abs=gap_escala_abs,
        diagnostico_lesao=diag,
        # ADR-082
        levers_equilibrio=levers,
        # NEP-042: três camadas de precificação
        pu_operacional_autonomo=pu_operacional_autonomo,
        machine_weeks_brutas=machine_weeks_brutas,
        machine_weeks_efetivas=machine_weeks_efetivas,
        eta_real=eta_real,
        custo_pool_total=custo_pool_total,
        custo_pool_por_unidade=custo_pool_por_unidade,
        economia_pool_abs=economia_pool_abs,
    )


def _validate_pe_duplo_risco(pe: PontoEquilibrio, validacoes: list) -> None:
    if pe.confianca_pe and pe.confianca_pe in ("MEDIA", "BAIXA") and pe.status_validacao == "ERRO":
        severidade = "AVISO" if pe.confianca_pe == "MEDIA" else "ERRO"
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PE-PU-DUPLO-RISCO",
                status=severidade,
                mensagem=(
                    f"Item '{pe.item_id}': PE DEFICITÁRIO com confiança"
                    f" {pe.confianca_pe.upper()} na PU ({pe.validacao_pu_status})."
                    f" {pe.diagnostico_pu or ''}"
                ),
            )
        )


def _validate_prod_vs_pu(pe: PontoEquilibrio, validacoes: list) -> None:
    """VAL-PROD-VS-PU (ADR-082-cons): divergência de produtividade engine ↔ catálogo.

    O custo operacional excede o de catálogo por um fator ``fe_nec``. Parte é
    explicável por clima (fator_clima_medio). O **resíduo** não-climático isola o
    desencontro entre a produtividade do engine (valor_horario, skill-04) e a
    embutida no PU planilha-first (skill-06):

        residuo = fe_nec × fator_clima_medio
        residuo ≈ 1 → gap puramente climático (P consistente)
        residuo ≠ 1 → P_engine diverge de P_catálogo (calibração a reconciliar)

    Emite AVISO quando |residuo − 1| > 10% — o número que fecha a base de cálculo.
    """
    fe_nec = pe.frentes_equivalentes_necessarias
    clima = pe.fator_clima_medio or 1.0
    if fe_nec <= 0 or clima <= 0:
        return
    residuo = fe_nec * clima
    if abs(residuo - 1.0) <= 0.10:
        return
    sentido = (
        "P_engine < P_catálogo (operacional mais barato)"
        if residuo < 1.0
        else ("P_engine > P_catálogo (operacional mais caro)")
    )
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-PROD-VS-PU",
            status="AVISO",
            mensagem=(
                f"Item '{pe.item_id}': divergência de produtividade {(residuo - 1.0) * 100:+.1f}% "
                f"não explicada por clima (fe_nec={fe_nec:.2f} × clima={clima:.2f} = {residuo:.2f}). "
                f"{sentido}. Reconciliar valor_horario (producao) com o PU de catálogo "
                f"(cat={pe.pu_catalogo_unitario:.3f} vs calibrado={pe.pu_calibrado_unitario:.3f})."
            ),
        )
    )


def _validate_frentes_necessarias(pe: PontoEquilibrio, validacoes: list) -> None:
    """VAL-FRENTES-NECESSARIAS-ALTA (ADR-076): execução autônoma supera o PU de catálogo.

    Threshold: OK ≤ 1.25, AVISO ≤ 1.5, CRITICO > 1.5.
    Emite AVISO ou ERRO dependendo do grau de desvio.
    """
    if pe.frentes_equivalentes_necessarias <= 1.25:
        return
    status_val = "ERRO" if pe.frentes_equivalentes_necessarias > 1.5 else "AVISO"
    desvio_pct = (pe.frentes_equivalentes_necessarias - 1.0) * 100
    ajuste_info = f" PU calibrado: +{pe.ajuste_minimo_pct:.1f}%." if pe.ajuste_minimo_pct > 0 else ""
    pool_info = f" Pool overhead: R$ {pe.gap_pool_abs:,.2f}." if pe.gap_pool_abs > 0 else ""
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-FRENTES-NECESSARIAS-ALTA",
            status=status_val,
            mensagem=(
                f"Item '{pe.item_id}': custo autônomo {desvio_pct:.1f}% acima do PU de catálogo"
                f" ({pe.frentes_equivalentes_necessarias:.2f}× frentes necessárias)."
                f"{ajuste_info}{pool_info}"
            ),
        )
    )


def _validate_pe_particao(pe: PontoEquilibrio, validacoes: list) -> None:
    # Compat: custo_realizado foi substituído por custo_operacional_real no modelo canônico.
    custo_realizado = float(getattr(pe, "custo_realizado", 0.0) or getattr(pe, "custo_operacional_real", 0.0) or 0.0)
    if pe.frentes_equivalentes > 1.05 and custo_realizado > 0:
        delta_op = pe.custo_venda_cpu - pe.custo_operacional_real
        if delta_op >= 0:
            return
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PONTO-EQUILIBRIO-PARTICAO",
                status="AVISO",
                mensagem=(
                    f"Item '{pe.item_id}': ~{pe.frentes_equivalentes:.2f} frentes equivalentes."
                    f" Delta operacional: R$ {delta_op:,.2f}."
                ),
            )
        )


def _apm_build_familia_rows(pe_por_item: dict, equipe_by_item: dict) -> dict:
    """Groups PE items by CPU family."""
    familia_rows: dict = {}
    for item_id, pe_item in pe_por_item.items():
        eq = equipe_by_item.get(item_id)
        fam = _cpu_familia(eq.cpu_id if eq else "")
        if fam:
            familia_rows.setdefault(fam, []).append((item_id, pe_item))
    return familia_rows


def _apm_process_familia(fam: str, rows: list, validacoes: list) -> None:
    """Downgrades ERRO to AVISO for PE items in a family with positive aggregate delta."""
    if len(rows) < 2:
        return
    delta_fam = sum(r[1].delta for r in rows)
    erros_fam = [r for r in rows if r[1].status_validacao == "ERRO"]
    if not (erros_fam and delta_fam >= 0):
        return
    for _, pe_item in erros_fam:
        pe_item.status_validacao = "AVISO"
    ids = ", ".join(i for i, _ in erros_fam)
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-PONTO-EQUILIBRIO-MITIGACAO",
            status="AVISO",
            mensagem=(
                f"Família '{fam}' com itens originalmente em ERRO ({ids})"
                f" mas saldo agregado positivo (Δfam = R$ {delta_fam:,.2f})."
                " Criticidade rebaixada para AVISO."
            ),
        )
    )


def _apply_pe_mitigacao(pe_items: list[PontoEquilibrio], equipe_by_item: dict, validacoes: list) -> None:
    pe_por_item = {p.item_id: p for p in pe_items}
    familia_rows = _apm_build_familia_rows(pe_por_item, equipe_by_item)
    for fam, rows in familia_rows.items():
        _apm_process_familia(fam, rows, validacoes)


def _bpe_process_equipe(
    equipe: Any,
    venda_por_item: dict,
    validacoes: list,
    planejamento_por_item: dict | None = None,
    sched_por_item: dict | None = None,
    particao_por_item: dict | None = None,
    idle_por_item: dict | None = None,
    pool_total_por_item: dict | None = None,
) -> PontoEquilibrio | None:
    """Builds and validates PE for a single equipe; returns None if skipped."""
    if not equipe.item_id:
        return None
    pe = _build_pe_for_equipe(
        equipe,
        venda_por_item,
        planejamento_por_item,
        sched_por_item,
        particao_por_item,
        idle_por_item,
        pool_total_por_item,
    )
    if pe is None:
        return None
    _validate_pe_duplo_risco(pe, validacoes)
    if pe.custo_operacional_real > 0:
        _validate_pe_particao(pe, validacoes)
    _validate_frentes_necessarias(pe, validacoes)
    _validate_prod_vs_pu(pe, validacoes)
    return pe


def _build_ponto_equilibrio(canonical_in: CanonicalModel, validacoes: list) -> list[PontoEquilibrio]:
    """Calcula ponto de equilíbrio para todas as equipes diretas."""
    venda_por_item = {
        p.item_id: p.subtotal.com_bdi.total for p in canonical_in.planejamento if p.item_id and p.subtotal
    }
    planejamento_por_item = {p.item_id: p for p in canonical_in.planejamento if p.item_id}
    equipe_by_item = {e.item_id: e for e in canonical_in.equipes_diretas if e.item_id}
    # Mapa activity_id → ScheduledActivityCanonical para extrair fatores de lesão climática
    sched_por_item: dict = {}
    if canonical_in.cronograma and canonical_in.cronograma.scheduled_activities:
        for sa in canonical_in.cronograma.scheduled_activities:
            sched_por_item[sa.activity_id] = sa
    # ADR-083: particao causal de custo por item (hub: item_id → CustoParticionadoItem)
    particao_por_item: dict[str, CustoParticionadoItem] = {}
    for contrato in canonical_in.contratos_recurso:
        for part in contrato.particao_por_item:
            particao_por_item[part.item_id] = part

    # NEP-042 D3: custo pool total por item — soma custo_total_particionado sobre TODOS os contratos
    pool_total_por_item: dict[str, float] = {}
    for contrato in canonical_in.contratos_recurso:
        for part in contrato.particao_por_item:
            pool_total_por_item[part.item_id] = pool_total_por_item.get(part.item_id, 0.0) + float(
                getattr(part, "custo_total_particionado", 0.0) or 0.0
            )

    # Idle real por item: Σ(custo_idle_mo + custo_idle_eq) das instâncias do pool.
    # Quando a política de late hire / early dismissal está ativa e não há standby,
    # esse valor é 0 — e o lever ResourcePool no painel_equilibrio desaparece.
    idle_por_item: dict[str, float] = {}
    for inst in canonical_in.instancias_recurso or []:
        idle = float(getattr(inst, "custo_idle_mo", 0.0) or 0.0) + float(getattr(inst, "custo_idle_eq", 0.0) or 0.0)
        if idle > 0:
            for ativ in getattr(inst, "atividades_cobertas", []) or []:
                idle_por_item[str(ativ)] = idle_por_item.get(str(ativ), 0.0) + idle

    pe_items = [
        pe
        for e in canonical_in.equipes_diretas
        for pe in [
            _bpe_process_equipe(
                e,
                venda_por_item,
                validacoes,
                planejamento_por_item,
                sched_por_item,
                particao_por_item,
                idle_por_item,
                pool_total_por_item,
            )
        ]
        if pe is not None
    ]
    if pe_items:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PONTO-EQUILIBRIO",
                status="OK",
                mensagem=f"Ponto de equilíbrio calculado para {len(pe_items)} equipes.",
            )
        )
        _apply_pe_mitigacao(pe_items, equipe_by_item, validacoes)
    return pe_items


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "f", "no", "n", "off", ""}:
            return False
    return False


def _build_bridge_from_pe(
    pe_items: list,
    venda_sem_bdi: float,
    custo_direto_equipe: float,
    inputs: dict,
    validacoes: list,
) -> dict | None:
    """Deriva bridge N1→N2→N3→N4 das três camadas de PontoEquilibrio (NEP-042 D5).

    N1 = Σ(PU_cat × Q)     — catálogo puro
    N2 = N1 + Σ gap_escala  — corrigido por escala de frentes (quantização)
    N3 = N2 + Σ gap_prat    — corrigido por praticabilidade climática
    N4 = custo operacional real (pool instancial)
    """
    try:
        benchmark_mode = _as_bool(inputs.get("benchmark_mode")) or _as_bool(inputs.get("modo_benchmark"))

        N1 = round(venda_sem_bdi, 2)
        gap_escala = sum(float(getattr(pe, "gap_escala_abs", 0.0) or 0.0) for pe in pe_items)
        gap_prat = sum(float(getattr(pe, "gap_praticabilidade_abs", 0.0) or 0.0) for pe in pe_items)
        N2 = round(N1 + gap_escala, 2)
        N3 = round(N2 + gap_prat, 2)

        if benchmark_mode:
            N4 = None
        else:
            raw_n4 = inputs.get("custo_operacional_equipes") or (
                custo_direto_equipe if custo_direto_equipe > 0 else None
            )
            N4 = round(float(raw_n4), 2) if raw_n4 else None

        delta_abs = round(N4 - N3, 2) if N4 is not None else None
        delta_pct = round(delta_abs / N4 * 100, 2) if delta_abs is not None and N4 else None
        abs_pct = abs(delta_pct) if delta_pct is not None else None
        status = (
            "VERDE"
            if abs_pct is not None and abs_pct <= 10
            else (
                "AMARELO"
                if abs_pct is not None and abs_pct <= 25
                else ("VERMELHO" if abs_pct is not None else "SEM_DADOS")
            )
        )
        fq = round(N2 / N1, 4) if N1 > 0 else 1.0
        praticabilidade = round(N2 / N3, 4) if N3 > 0 else 1.0

        # NEP-042 D5: N_pool = custo pool instancial total (Camada 3)
        N_pool = round(sum(float(getattr(pe, "custo_pool_total", 0.0) or 0.0) for pe in pe_items), 2)

        bridge = {
            "nivel_1_catalogo_base": N1,
            "nivel_2_catalogo_escalado": N2,
            "nivel_3_catalogo_normalizado": N3,
            "nivel_4_operacional": N4,
            # NEP-042: custo pool instancial explícito (Camada 3)
            "nivel_pool_instancial": N_pool if N_pool > 0 else None,
            "fator_quantizacao": fq,
            "fator_praticabilidade": praticabilidade,
            "desvio_escala_abs": round(gap_escala, 2),
            "desvio_clima_abs": round(gap_prat, 2),
            "delta_real_abs": delta_abs,
            "delta_real_percentual": delta_pct,
            "delta_estrutural_abs": round(N3 - N1, 2),
            "necessidades_fracionadas": [],
            "status_alerta": status,
        }
        n4_str = f"{N4:.0f}" if N4 is not None else "N/A"
        pool_str = f" | pool={N_pool:.0f}" if N_pool > 0 else ""
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-BRIDGE-OK",
                status="OK",
                mensagem=f"Bridge: N1={N1:.0f} → N2={N2:.0f} → N3={N3:.0f} → N4={n4_str}{pool_str} | alerta={status}",
            )
        )
        return bridge
    except Exception as exc:  # pragma: no cover
        validacoes.append(
            ValidacaoItem(codigo="VAL-BRIDGE-WARN", status="AVISO", mensagem=f"Bridge não calculada: {exc}")
        )
        return None


def _build_diagnostico_pe(
    canonical_in: CanonicalModel,
    custos_atividades: list,
    pe_items: list,
    validacoes: list,
) -> tuple:
    try:
        from concilium.domain.services.analytics.backtracking_pe_builder import BacktrackingPEBuilder
        from concilium.domain.services.analytics.diagnostico_pe_builder import DiagnosticoPEBuilder

        # Injeta ponto_equilibrio da run atual para que _compute_f1_quantizacao
        # leia gap_escala_abs correto em vez de bridge_analysis do run anterior.
        _cp = canonical_in.model_copy(
            update={
                "custos_atividades": custos_atividades,
                "ponto_equilibrio": pe_items,
            }
        )
        diag = DiagnosticoPEBuilder().build(_cp)
        back = BacktrackingPEBuilder().build(diag, _cp)
        return diag, back
    except Exception as exc:  # pragma: no cover
        import logging

        logging.getLogger(__name__).warning("DiagnosticoPE falhou (best-effort): %s", exc)
        return None, None


# ---------------------------------------------------------------------------
# ADR-106 F8 — Pool occupancy face builder (stub)
# ---------------------------------------------------------------------------


def _build_cubo_pool_face(
    equipes_diretas: list,
    cronograma: list,
    projeto_id: str = "",
) -> Any:
    """Constrói a face de ocupação do pool por semana e tipo de recurso (ADR-106 F8 stub).

    Esta função é um stub para a implementação futura (ADR-106 F8).
    Retorna um ``CuboPoolFace`` com as células de ocupação derivadas das equipes
    diretas e do cronograma.

    Dimensões da face:
      - ``item_id``: atividade EAP que gerou a demanda
      - ``semana``: semana ISO ou sequencial
      - ``tipo_recurso``: tipo de recurso (EQUIP-* ou FUNC-*)

    Medidas:
      - ``horas_ativas``: horas produtivas do recurso na semana
      - ``horas_idle``: horas ociosas (mobilizado, sem atividade)
      - ``custo_ativo``: custo do componente produtivo (MO + EQ em prod)
      - ``custo_idle``: custo ocioso (MO integral + EQ reduzida em idle)
      - ``estado``: "mobilizando" | "ativo" | "idle" | "desmobilizando" | "off"

    Args:
        equipes_diretas: lista de EquipeDireta com custo_inst_* preenchidos.
        cronograma: lista de itens do cronograma (atividades com datas/semanas).
        projeto_id: identificador do projeto (para rastreabilidade).

    Returns:
        CuboPoolFace com células de ocupação. Retorna face vazia se inputs
        insuficientes (equipes sem dados de pool ou cronograma vazio).

    Note:
        ADR-106 F8 está marcado como pendente — aguarda ADR-086 extensão.
        Esta stub retorna apenas estrutura vazia, garantindo que o contrato
        de tipo está correto e os consumidores podem ser escritos e testados.
    """
    import datetime

    from concilium.domain.models.analytics.cubo_pool import CuboPoolFace

    gerado_em = datetime.datetime.now(datetime.UTC).isoformat()
    return CuboPoolFace(
        projeto_id=projeto_id,
        gerado_em=gerado_em,
        celulas=(),
    )
