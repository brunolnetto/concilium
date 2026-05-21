"""Skill 06 — Consolidação Financeira (Consolidada).

Consolida:
1. Consolidação de Resultado (antiga 06)
2. Reconciliação de Custos de Recurso (antiga 06A)
3. Análise de Compensação Estrutural — The Bridge (ADR-039)

Objetivo: Produzir o balanço final de venda, custo e margem, já considerando impactos de aquisição
e separando os desvios estruturais (escala + clima) do delta real de gestão.
"""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.constants import SEMANAS_POR_MES
from concilium.domain.models.bdi import (
    DEFAULT_BDI_TABELA,
    PerfilBdiProjeto,
    TabelaBdi,
    TaxSimulationScenario,
    resolver_bdi_cbs_ibs,
    resolver_componentes_bdi,
)
from concilium.domain.models.canonical import (
    AtividadeCustoCompleto,
    AtividadeInsumo,
    CanonicalModel,
    CustoTotal,
    IndiretoAlocacao,
    InsumoComponenteAtividade,
    PontoEquilibrio,
    Resultado,
    ResultadoReconciliado,
    ValidacaoItem,
    Venda,
)
from concilium.domain.services.bridge_analyzer import BridgeAnalyzer


def _get_bdi_value(manual: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key in manual and manual.get(key) is not None:
            try:
                return float(manual.get(key) or 0.0)
            except Exception:
                continue
    return float(default)


def _resolve_bdi_full(
    inputs: dict[str, Any], validacoes: list[ValidacaoItem]
) -> tuple[dict[str, float], TabelaBdi, str, str, bool]:
    """ADR-057: resolve BDI retornando também (tabela, fonte, regime_version, override_aplicado).

    Retorna: (rates_dict, tabela_usada, fonte_bdi, regime_version, override_aplicado)
    """
    # ADR-055: TaxSimulationScenario CBS/IBS — deriva BDI por categoria incluindo indireto
    tax_scenario_raw = inputs.get("tax_scenario")
    if tax_scenario_raw and isinstance(tax_scenario_raw, dict):
        try:
            scenario = TaxSimulationScenario.from_dict(tax_scenario_raw)
            tabela_cbs_ibs = resolver_bdi_cbs_ibs(DEFAULT_BDI_TABELA, scenario)
            rates = {
                "mao_obra": float(tabela_cbs_ibs.mao_obra.bdi_total),
                "equipamentos": float(tabela_cbs_ibs.servicos.bdi_total),
                "material": float(tabela_cbs_ibs.material.bdi_total),
                "diesel": float(tabela_cbs_ibs.diesel.bdi_total),
                "indireto": float(tabela_cbs_ibs.indireto.bdi_total),
            }
            t_ef = scenario.tributos_efetivos_por_categoria()
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-CONSOL-BDI-REGIME",
                    status="OK",
                    mensagem=(
                        f"Consolidação via TaxSimulationScenario ADR-055 "
                        f"(regime={scenario.regime_version.value}): "
                        f"MO={rates['mao_obra'] * 100:.2f}% | IND={rates['indireto'] * 100:.2f}% | "
                        f"T_ef_MO={t_ef['mao_obra'] * 100:.2f}% | T_ef_MAT={t_ef['material'] * 100:.2f}%"
                    ),
                )
            )
            return rates, tabela_cbs_ibs, "inputs.tax_scenario", scenario.regime_version.value, True
        except Exception as exc:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-CONSOL-BDI-REGIME",
                    status="AVISO",
                    mensagem=f"Falha ao aplicar tax_scenario: {exc}. Usando path legado.",
                )
            )

    manual = inputs.get("bdi_aplicado")
    if isinstance(manual, dict):
        mo = _get_bdi_value(manual, "mao_obra", "mo")
        mat = _get_bdi_value(manual, "material", "mat")
        diesel = _get_bdi_value(manual, "diesel", "combustivel", "comb")
        serv = _get_bdi_value(manual, "servicos", "serv", default=mo)
        eq = _get_bdi_value(manual, "equipamentos", "eq", default=serv)
        indireto = _get_bdi_value(manual, "indireto", "ind", default=0.0)
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CONSOL-BDI-FONTE",
                status="AVISO",
                mensagem=(
                    "Consolidação financeira usando inputs.bdi_aplicado "
                    f"(MO={mo * 100:.2f}%, EQ={eq * 100:.2f}%, MAT={mat * 100:.2f}%, "
                    f"COMB={diesel * 100:.2f}%, SERV={serv * 100:.2f}%, IND={indireto * 100:.2f}%)."
                ),
            )
        )
        return {
            "mao_obra": mo,
            "equipamentos": eq,
            "material": mat,
            "diesel": diesel,
            "indireto": indireto,
        }
        # For memorial: reconstruct a minimal TabelaBdi from the manual override
        from concilium.domain.models.bdi import ComponentesBdi as _CB

        def _mk(v):
            return _CB(ac=0, df=0, r=0, cr=0, l=0, cofins=0, iss=0, pis=0, cssl=0, ir=v)

        _manual_tabela = DEFAULT_BDI_TABELA  # best-effort; exact shape not reconstructable from flat dict
        return (
            {
                "mao_obra": mo,
                "equipamentos": eq,
                "material": mat,
                "diesel": diesel,
                "indireto": indireto,
            },
            _manual_tabela,
            "inputs.bdi_aplicado",
            "pre_reforma",
            True,
        )

    tabela_raw = inputs.get("tabela_bdi")
    tabela: TabelaBdi | None = None
    fonte = "DEFAULT_BDI_TABELA"
    override = False
    if tabela_raw is not None:
        try:
            tabela = TabelaBdi.model_validate(tabela_raw) if isinstance(tabela_raw, dict) else tabela_raw
            fonte = "inputs.tabela_bdi"
            override = True
        except Exception as e:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-CONSOL-BDI-PARSE",
                    status="AVISO",
                    mensagem=f"Falha ao parsear tabela_bdi: {e}. Usando DEFAULT_BDI_TABELA.",
                )
            )
            tabela = None

    if tabela is None:
        tabela = DEFAULT_BDI_TABELA

    perfil_bdi_raw = inputs.get("bdi_perfil") or inputs.get("perfil_bdi")
    if perfil_bdi_raw is not None:
        try:
            perfil_bdi = (
                PerfilBdiProjeto.model_validate(perfil_bdi_raw) if isinstance(perfil_bdi_raw, dict) else perfil_bdi_raw
            )
            tabela = resolver_componentes_bdi(tabela, perfil_bdi)
            fonte += " + PerfilBdiProjeto"
            override = True
            regime_v = getattr(perfil_bdi, "regime_version", None)
            regime_str = regime_v.value if regime_v else "pre_reforma"
        except Exception as e:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-CONSOL-BDI-PERFIL",
                    status="AVISO",
                    mensagem=f"Falha ao aplicar perfil_bdi: {e}. Mantendo tabela base.",
                )
            )
            regime_str = "pre_reforma"
    else:
        regime_str = "pre_reforma"

    rates = {
        "mao_obra": float(tabela.mao_obra.bdi_total),
        # EQ é tratado como SERVIÇOS para venda final por composição.
        "equipamentos": float(tabela.servicos.bdi_total),
        "material": float(tabela.material.bdi_total),
        "diesel": float(tabela.diesel.bdi_total),
        "indireto": float(tabela.indireto.bdi_total),
    }
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-CONSOL-BDI-FONTE",
            status="OK",
            mensagem=(
                f"Consolidação financeira por composição ({fonte}): "
                f"MO={rates['mao_obra'] * 100:.2f}% | EQ={rates['equipamentos'] * 100:.2f}% | "
                f"MAT={rates['material'] * 100:.2f}% | DIESEL={rates['diesel'] * 100:.2f}% | "
                f"IND={rates['indireto'] * 100:.2f}%"
            ),
        )
    )
    return rates, tabela, fonte, regime_str, override


def _resolve_bdi_rates(inputs: dict[str, Any], validacoes: list[ValidacaoItem]) -> dict[str, float]:
    """Backward-compat wrapper — retorna apenas os rates."""
    rates, _, _, _, _ = _resolve_bdi_full(inputs, validacoes)
    return rates


def _classificar_margem(margem, alvo, aceitavel):
    if alvo["min"] <= margem <= alvo["max"]:
        return "VERDE"
    if aceitavel["min"] <= margem <= aceitavel["max"]:
        return "AMARELO"
    return "VERMELHO"


def _cpu_familia(cpu_id: str) -> str:
    """Normaliza CPU para uma família operacional (ex.: remove sufixos DMT)."""
    if not cpu_id:
        return ""
    return re.sub(r"-DMT\d+$", "", cpu_id)


def _build_custos_atividades(canonical_in: CanonicalModel) -> list[AtividadeCustoCompleto]:
    """ADR-056 §T2: Breakdown de custo completo por atividade da EAP.

    Agrega equipes_diretas (MO + EQ + DIESEL + MAT), planejamento (custo unitário × qtd)
    e indiretos (alocados proporcionalmente por duração) em AtividadeCustoCompleto.
    Requer cronograma já populado (Skill 04 deve ter rodado).
    """
    if not canonical_in.cronograma or not canonical_in.eap:
        return []

    sched_lookup = {sa.activity_id: sa for sa in canonical_in.cronograma.scheduled_activities}
    equipe_lookup = {e.item_id: e for e in (canonical_in.equipes_diretas or [])}
    plan_lookup = {p.item_id: p for p in (canonical_in.planejamento or [])}

    # Total de semanas do projeto para alocação proporcional de indiretos
    total_semanas = canonical_in.cronograma.makespan_weeks or 1
    custo_indireto_total = sum(ind.custo_sem_bdi for ind in (canonical_in.indiretos_com_bdi or []))

    custos: list[AtividadeCustoCompleto] = []
    for item in canonical_in.eap:
        sa = sched_lookup.get(item.item_id)
        equipe = equipe_lookup.get(item.item_id)
        plan_lookup.get(item.item_id)

        semana_inicio = sa.start_week if sa else 0
        semana_fim = sa.end_week if sa else 0
        duracao = max(1, semana_fim - semana_inicio + 1) if sa else 1

        # Custo direto via equipe (MO + EQ + COMB + MAT)
        custos_diretos: list[AtividadeInsumo] = []
        if equipe:
            meses = equipe.permanencia_meses or (duracao / SEMANAS_POR_MES)
            custos_diretos.append(
                AtividadeInsumo(
                    categoria="equipe_direta",
                    mao_de_obra=InsumoComponenteAtividade(
                        nome="Mão de Obra",
                        itens=[],
                        custo_total=round(equipe.custo_mao_obra_mensal * meses, 2),
                    ),
                    equipamentos=InsumoComponenteAtividade(
                        nome="Equipamentos",
                        itens=[],
                        custo_total=round(equipe.custo_equipamentos_mensal * meses, 2),
                    ),
                    material=InsumoComponenteAtividade(
                        nome="Combustível + Material",
                        itens=[],
                        custo_total=round(
                            (equipe.custo_combustivel_total_mensal + equipe.custo_material_mensal) * meses, 2
                        ),
                    ),
                )
            )

        # Indireto proporcional por duração
        custo_ind = round(custo_indireto_total * duracao / total_semanas, 2) if custo_indireto_total > 0 else 0.0
        ind_alocacao = IndiretoAlocacao(
            estrategia="duracao",
            semanas_atividade=duracao,
            semanas_projeto=total_semanas,
        )

        custos.append(
            AtividadeCustoCompleto(
                atividade_id=item.item_id,
                nome=item.descricao if hasattr(item, "descricao") else item.item_id,
                semana_inicio=semana_inicio,
                semana_fim=semana_fim,
                custos_diretos=custos_diretos,
                indireto_alocacao=ind_alocacao,
                custo_indireto_atribuido=custo_ind,
            )
        )

    return custos


def _calc_venda_com_bdi(canonical_in: CanonicalModel, bdi_rates: dict[str, float]) -> tuple[float, float, float]:
    """Retorna (venda_direto_eq_com_bdi, venda_indireto_com_bdi, custo_indireto_total)."""
    custo_indireto_total = sum(ind.custo_total for ind in canonical_in.indiretos)
    mo_eq = sum((e.custo_mao_obra_mensal or 0.0) * (e.permanencia_meses or 0.0) for e in canonical_in.equipes_diretas)
    eq_eq = sum(
        (e.custo_equipamentos_mensal or 0.0) * (e.permanencia_meses or 0.0) for e in canonical_in.equipes_diretas
    )
    diesel_eq = sum(
        (e.custo_combustivel_total_mensal or 0.0) * (e.permanencia_meses or 0.0) for e in canonical_in.equipes_diretas
    )
    mat_eq = sum((e.custo_material_mensal or 0.0) * (e.permanencia_meses or 0.0) for e in canonical_in.equipes_diretas)
    venda_direto = (
        mo_eq * (1 + bdi_rates["mao_obra"])
        + eq_eq * (1 + bdi_rates["equipamentos"])
        + diesel_eq * (1 + bdi_rates["diesel"])
        + mat_eq * (1 + bdi_rates["material"])
    )
    venda_indireto = custo_indireto_total * (1 + bdi_rates["indireto"])
    return venda_direto, venda_indireto, custo_indireto_total


def _build_resultado(
    canonical_in: CanonicalModel, inputs: dict, validacoes: list, perfil: dict
) -> tuple[Resultado, dict, str, str, bool, float, float, float]:
    """Computa resultado financeiro e retorna (res, bdi_rates, bdi_fonte, bdi_regime, bdi_override, venda_sem_bdi, venda_catalogo_plus, margem)."""
    venda_sem_bdi = sum(p.subtotal.sem_bdi.total for p in canonical_in.planejamento)
    venda_com_bdi = sum(p.subtotal.com_bdi.total for p in canonical_in.planejamento)
    custo_direto_equipe = sum(e.custo_total for e in canonical_in.equipes_diretas)
    custo_materiais = sum(p.subtotal.sem_bdi.material for p in canonical_in.planejamento)
    custo_direto = custo_direto_equipe + custo_materiais

    bdi_rates, _bdi_tabela, _bdi_fonte, _bdi_regime, _bdi_override = _resolve_bdi_full(inputs, validacoes)
    venda_direto_eq, venda_indireto, custo_indireto_total = _calc_venda_com_bdi(canonical_in, bdi_rates)
    custos_indiretos = {ind.categoria: ind.custo_total for ind in canonical_in.indiretos}

    venda_catalogo_plus = round(venda_com_bdi + venda_indireto, 2)
    venda_plus = round(venda_direto_eq + venda_indireto, 2)
    custo_total = custo_direto + custo_indireto_total
    bdi_lucro = (venda_catalogo_plus / custo_total - 1) if custo_total > 0 else 0.0
    custo_total_catalogo = venda_sem_bdi + custo_indireto_total
    resultado_fin = venda_catalogo_plus - custo_total_catalogo
    margem = resultado_fin / venda_catalogo_plus if venda_catalogo_plus > 0 else 0.0
    status_margem = _classificar_margem(margem, perfil["faixa_margem_alvo"], perfil["faixa_margem_aceitavel"])
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-CONSOL-MARGEM",
            status="OK" if status_margem != "VERMELHO" else "AVISO",
            mensagem=f"Margem consolidada {margem * 100:.2f}% | status={status_margem}",
        )
    )
    res = Resultado(
        venda=Venda(
            total_sem_bdi=venda_sem_bdi,
            total_com_bdi=venda_catalogo_plus,
            total_custo_plus=venda_plus,
            total_custo_plus_catalogo=venda_catalogo_plus,
            bdi_lucro_impostos=bdi_lucro,
        ),
        custo=CustoTotal(
            direto_equipes=custo_direto,
            direto_catalogo=venda_sem_bdi,
            total=custo_total_catalogo,
            **{f"indireto_{k.lower()}": v for k, v in custos_indiretos.items() if k != "MOB"},
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
        custo_total,
        custo_total_catalogo,
    )


def _build_pe_for_equipe(equipe: Any, venda_por_item: dict) -> PontoEquilibrio | None:
    """Constrói PontoEquilibrio para uma equipe. Retorna None se custo_fixo ≤ 0."""
    custo_fixo_total = equipe.custo_fixo_mensal * (equipe.permanencia_meses or 1.0)
    if custo_fixo_total <= 0:
        return None
    custo_venda_total = venda_por_item.get(equipe.item_id, 0.0)
    delta = custo_venda_total - custo_fixo_total
    custo_operacional_real = float(equipe.custo_total or 0.0)
    frentes = custo_operacional_real / custo_fixo_total if custo_fixo_total > 0 else 1.0
    return PontoEquilibrio(
        item_id=equipe.item_id,
        custo_fixo_equipe=round(custo_fixo_total, 2),
        custo_venda_cpu=round(custo_venda_total, 2),
        delta=round(delta, 2),
        delta_pct=round(delta / custo_fixo_total, 5),
        status_validacao="OK" if delta >= 0 else "ERRO",
        custo_operacional_real=round(custo_operacional_real, 2),
        frentes_equivalentes=round(frentes, 2),
    )


def _validate_pe_duplo_risco(pe: PontoEquilibrio, validacoes: list) -> None:
    if pe.confianca_pe and pe.confianca_pe in ("MEDIA", "BAIXA") and pe.status_validacao == "ERRO":
        severidade = "AVISO" if pe.confianca_pe == "MEDIA" else "ERRO"
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PE-PU-DUPLO-RISCO",
                status=severidade,
                mensagem=f"Item '{pe.item_id}': PE DEFICITÁRIO com confiança {pe.confianca_pe.upper()} na PU ({pe.validacao_pu_status}). {pe.diagnostico_pu or ''}",
            )
        )


def _validate_pe_particao(pe: PontoEquilibrio, validacoes: list) -> None:
    if pe.frentes_equivalentes > 1.05 and pe.custo_realizado and pe.custo_realizado > 0:
        delta_op = pe.custo_venda_cpu - pe.custo_operacional_real
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PONTO-EQUILIBRIO-PARTICAO",
                status="AVISO",
                mensagem=f"Item '{pe.item_id}': ~{pe.frentes_equivalentes:.2f} frentes equivalentes. Delta operacional: R$ {delta_op:,.2f}.",
            )
        )


def _apply_pe_mitigacao(pe_items: list[PontoEquilibrio], equipe_by_item: dict, validacoes: list) -> None:
    pe_por_item = {p.item_id: p for p in pe_items}
    familia_rows: dict[str, list[tuple[str, PontoEquilibrio]]] = {}
    for item_id, pe_item in pe_por_item.items():
        eq = equipe_by_item.get(item_id)
        fam = _cpu_familia(eq.cpu_id if eq else "")
        if fam:
            familia_rows.setdefault(fam, []).append((item_id, pe_item))
    for fam, rows in familia_rows.items():
        if len(rows) < 2:
            continue
        delta_fam = sum(r[1].delta for r in rows)
        erros_fam = [r for r in rows if r[1].status_validacao == "ERRO"]
        if erros_fam and delta_fam >= 0:
            for _, pe_item in erros_fam:
                pe_item.status_validacao = "AVISO"
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-PONTO-EQUILIBRIO-MITIGACAO",
                    status="AVISO",
                    mensagem=f"Família '{fam}' com itens originalmente em ERRO ({', '.join(i for i, _ in erros_fam)}) mas saldo agregado positivo (Δfam = R$ {delta_fam:,.2f}). Criticidade rebaixada para AVISO.",
                )
            )


def _build_ponto_equilibrio(canonical_in: CanonicalModel, validacoes: list) -> list[PontoEquilibrio]:
    """Calcula ponto de equilíbrio para todas as equipes diretas."""
    venda_por_item = {
        p.item_id: p.subtotal.com_bdi.total for p in canonical_in.planejamento if p.item_id and p.subtotal
    }
    equipe_by_item = {e.item_id: e for e in canonical_in.equipes_diretas if e.item_id}
    pe_items: list[PontoEquilibrio] = []
    for equipe in canonical_in.equipes_diretas:
        if not equipe.item_id:
            continue
        pe = _build_pe_for_equipe(equipe, venda_por_item)
        if pe is None:
            continue
        pe_items.append(pe)
        _validate_pe_duplo_risco(pe, validacoes)
        if pe.custo_operacional_real > 0:
            _validate_pe_particao(pe, validacoes)
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


def _build_bridge(inputs: dict, venda_sem_bdi: float, custo_direto_equipe: float, validacoes: list) -> dict | None:
    try:
        praticabilidade = inputs.get("praticabilidade", 1.0)
        if isinstance(praticabilidade, dict):
            praticabilidade = praticabilidade.get("fator", 1.0)
        praticabilidade = max(0.01, min(1.0, float(praticabilidade or 1.0)))
        nivel_4 = inputs.get("custo_operacional_equipes") or (custo_direto_equipe if custo_direto_equipe > 0 else None)
        bridge = BridgeAnalyzer.calcular(
            nivel_1=venda_sem_bdi,
            necessidades_fracionadas=inputs.get("necessidades_fracionadas", []),
            praticabilidade=praticabilidade,
            nivel_4=float(nivel_4) if nivel_4 else None,
        )
        bridge_dict = asdict(bridge)
        bridge_dict["status_alerta"] = bridge.status_alerta
        bridge_dict["delta_estrutural_abs"] = bridge.delta_estrutural_abs
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-BRIDGE-OK",
                status="OK",
                mensagem=f"Bridge calculada: N1={bridge.nivel_1_catalogo_base:.0f} -> N3={bridge.nivel_3_catalogo_normalizado:.0f} | alerta={bridge.status_alerta}",
            )
        )
        return bridge_dict
    except Exception as exc:
        validacoes.append(
            ValidacaoItem(codigo="VAL-BRIDGE-WARN", status="AVISO", mensagem=f"Bridge não calculada: {exc}")
        )
        return None


def _build_diagnostico_pe(canonical_in: CanonicalModel, custos_atividades: list, validacoes: list) -> tuple:
    try:
        from concilium.domain.services.backtracking_pe_builder import BacktrackingPEBuilder
        from concilium.domain.services.diagnostico_pe_builder import DiagnosticoPEBuilder

        _cp = canonical_in.model_copy(update={"custos_atividades": custos_atividades})
        diag = DiagnosticoPEBuilder().build(_cp)
        back = BacktrackingPEBuilder().build(diag, _cp)
        return diag, back
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("DiagnosticoPE falhou (best-effort): %s", exc)
        return None, None


def _build_abc_analytics(
    canonical_in: CanonicalModel, inputs: dict, bdi_tabela: Any, bdi_regime: str, validacoes: list
) -> tuple:
    try:
        from concilium.domain.services.cubo_analitico_builder import CuboAnaliticoBuilder
        from concilium.domain.services.curva_abc_builder import CurvaABCBuilder
        from concilium.domain.services.s_curve_builder import SCurveBuilder

        curva_abc = CurvaABCBuilder().build(canonical_in)
        s_curve = SCurveBuilder().build(canonical_in)
        _regime = (
            inputs.get("tax_scenario", {}).get("regime_version", "pre_reforma")
            if isinstance(inputs.get("tax_scenario"), dict)
            else bdi_regime
        )
        cubo_analitico = CuboAnaliticoBuilder(tabela_bdi=bdi_tabela, regime_version=_regime).build(canonical_in)
        return curva_abc, s_curve, cubo_analitico
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("CurvaABC/SCurve/Cubo falhou (best-effort): %s", exc)
        return None, None, None


def _build_memorial_bdi(
    canonical_in: CanonicalModel, bdi_fonte: str, bdi_regime: str, bdi_tabela: Any, bdi_override: bool
) -> Any:
    try:
        from concilium.domain.services.memorial_bdi_builder import MemorialBDIBuilder

        return MemorialBDIBuilder().build(
            canonical_in=canonical_in,
            bdi_fonte=bdi_fonte,
            regime_version=bdi_regime,
            tabela_usada=bdi_tabela,
            override_aplicado=bdi_override,
        )
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("Memorial BDI falhou (best-effort): %s", exc)
        return None


def run_consolidacao_financeira(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    perfil: dict[str, Any],
) -> SkillResult:
    validacoes: list[ValidacaoItem] = []

    if not canonical_in.equipes_diretas or not canonical_in.planejamento:
        validacoes.append(
            ValidacaoItem(codigo="VAL-CONSOL-PRE", status="ERRO", mensagem="Equipes e Planejamento necessários.")
        )
        return SkillResult(canonical_in, validacoes)

    (
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
        custo_total,
        custo_total_catalogo,
    ) = _build_resultado(canonical_in, inputs, validacoes, perfil)

    ponto_equilibrio_items = _build_ponto_equilibrio(canonical_in, validacoes)
    recon = ResultadoReconciliado(
        itens_aquisicao=[],
        delta_custo_total=0.0,
        venda_total_com_bdi=venda_plus,
        custo_total_reconciliado=custo_total,
        margem_reconciliada_pct=margem,
        status_margem_reconciliado=status_margem,
    )
    bridge_dict = _build_bridge(inputs, venda_sem_bdi, custo_direto_equipe, validacoes)
    custos_atividades = _build_custos_atividades(canonical_in)
    _diag_pe, _back_pe = _build_diagnostico_pe(canonical_in, custos_atividades, validacoes)
    curva_abc, s_curve, cubo_analitico = _build_abc_analytics(
        canonical_in, inputs, _bdi_tabela, _bdi_regime, validacoes
    )
    memorial = _build_memorial_bdi(canonical_in, _bdi_fonte, _bdi_regime, _bdi_tabela, _bdi_override)

    novo = canonical_in.model_copy(
        update={
            "resultado": res,
            "resultado_reconciliado": recon,
            "bridge_analysis": bridge_dict,
            "ponto_equilibrio": ponto_equilibrio_items,
            "custos_atividades": custos_atividades,
            "memorial_calculo_bdi": memorial,
            "curva_abc_insumo": curva_abc,
            "s_curve": s_curve,
            "cubo_analitico": cubo_analitico,
            "diagnostico_pe": _diag_pe,
            "backtracking_pe": _back_pe,
        }
    )
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-CONSOL-OK", status="OK", mensagem=f"Consolidação concluída. Margem: {margem * 100:.2f}%"
        )
    )
    return SkillResult(novo, validacoes)
