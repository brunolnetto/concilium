"""Skill 06 — Consolidação Financeira (Consolidada).

Consolida:
1. Consolidação de Resultado (antiga 06)
2. Reconciliação de Custos de Recurso (antiga 06A)
3. Análise de Compensação Estrutural — The Bridge (ADR-039)

Objetivo: Produzir o balanço final de venda, custo e margem, já considerando impactos de aquisição
e separando os desvios estruturais (escala + clima) do delta real de gestão.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from concilium.domain.models.canonical import (
    AtividadeCustoCompleto,
    CanonicalModel,
    CustoTotal,
    PontoEquilibrio,
    Resultado,
    ValidacaoItem,
    Venda,
)
from concilium.domain.services.bridge_analyzer import BridgeAnalyzer

try:
    from ._skill_helpers_b import _classificar_margem, _resolve_bdi_full
except ImportError:
    import importlib.util
    from pathlib import Path

    _here = Path(__file__).resolve().parent
    _spec_b = importlib.util.spec_from_file_location("skill08_helpers_b_for_a", _here / "_skill_helpers_b.py")
    _mod_b = importlib.util.module_from_spec(_spec_b)  # type: ignore[arg-type]
    _spec_b.loader.exec_module(_mod_b)  # type: ignore[union-attr]
    _classificar_margem = _mod_b._classificar_margem
    _resolve_bdi_full = _mod_b._resolve_bdi_full


def _calc_venda_com_bdi(canonical_in: CanonicalModel, bdi_rates: dict[str, float]) -> tuple[float, float, float]:
    venda_direto_eq = 0.0
    for eq in canonical_in.equipes_diretas:
        venda_direto_eq += float(eq.custo_mao_obra_mensal or 0.0) * (1 + float(bdi_rates.get("mao_obra", 0.0)))
        venda_direto_eq += float(eq.custo_equipamentos_mensal or 0.0) * (1 + float(bdi_rates.get("equipamentos", 0.0)))
        venda_direto_eq += float(eq.custo_material_mensal or 0.0) * (1 + float(bdi_rates.get("material", 0.0)))
        venda_direto_eq += float(eq.custo_combustivel_total_mensal or 0.0) * (1 + float(bdi_rates.get("diesel", 0.0)))

    custo_indireto_total = sum(float(ind.custo_total or 0.0) for ind in canonical_in.indiretos)
    venda_indireto = custo_indireto_total * (1 + float(bdi_rates.get("indireto", 0.0)))
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
        nome = eap_by_id.get(act.activity_id).descricao if eap_by_id.get(act.activity_id) else act.activity_id
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
            nome = eap_by_id.get(eq.item_id).descricao if eap_by_id.get(eq.item_id) else eq.item_id
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
    """Returns (venda_sem_bdi, venda_com_bdi, custo_direto_equipe, custo_materiais, custo_direto)."""
    venda_sem_bdi = sum(p.subtotal.sem_bdi.total for p in canonical_in.planejamento)
    venda_com_bdi = sum(p.subtotal.com_bdi.total for p in canonical_in.planejamento)
    custo_direto_equipe = sum(e.custo_total for e in canonical_in.equipes_diretas)
    custo_materiais = sum(p.subtotal.sem_bdi.material for p in canonical_in.planejamento)
    return venda_sem_bdi, venda_com_bdi, custo_direto_equipe, custo_materiais, custo_direto_equipe + custo_materiais


def _build_resultado(
    canonical_in: CanonicalModel, inputs: dict, validacoes: list, perfil: dict
) -> tuple[Resultado, dict, str, str, bool, float, float, float]:
    """Computa resultado financeiro e retorna.

    Returns: (res, bdi_rates, bdi_fonte, bdi_regime, bdi_override,
    venda_sem_bdi, venda_catalogo_plus, margem).
    """
    venda_sem_bdi, venda_com_bdi, custo_direto_equipe, _custo_mat, custo_direto = _br_build_venda_custo(canonical_in)
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
    status_val = "OK" if status_margem != "VERMELHO" else "AVISO"
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-CONSOL-MARGEM",
            status=status_val,
            mensagem=f"Margem consolidada {margem * 100:.2f}% | status={status_margem}",
        )
    )
    indir_kwargs = {f"indireto_{k.lower()}": v for k, v in custos_indiretos.items() if k != "MOB"}
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
                mensagem=(
                    f"Item '{pe.item_id}': PE DEFICITÁRIO com confiança"
                    f" {pe.confianca_pe.upper()} na PU ({pe.validacao_pu_status})."
                    f" {pe.diagnostico_pu or ''}"
                ),
            )
        )


def _validate_pe_particao(pe: PontoEquilibrio, validacoes: list) -> None:
    if pe.frentes_equivalentes > 1.05 and pe.custo_realizado and pe.custo_realizado > 0:
        delta_op = pe.custo_venda_cpu - pe.custo_operacional_real
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


def _bpe_process_equipe(equipe: Any, venda_por_item: dict, validacoes: list) -> PontoEquilibrio | None:
    """Builds and validates PE for a single equipe; returns None if skipped."""
    if not equipe.item_id:
        return None
    pe = _build_pe_for_equipe(equipe, venda_por_item)
    if pe is None:
        return None
    _validate_pe_duplo_risco(pe, validacoes)
    if pe.custo_operacional_real > 0:
        _validate_pe_particao(pe, validacoes)
    return pe


def _build_ponto_equilibrio(canonical_in: CanonicalModel, validacoes: list) -> list[PontoEquilibrio]:
    """Calcula ponto de equilíbrio para todas as equipes diretas."""
    venda_por_item = {
        p.item_id: p.subtotal.com_bdi.total for p in canonical_in.planejamento if p.item_id and p.subtotal
    }
    equipe_by_item = {e.item_id: e for e in canonical_in.equipes_diretas if e.item_id}
    pe_items = [
        pe
        for e in canonical_in.equipes_diretas
        for pe in [_bpe_process_equipe(e, venda_por_item, validacoes)]
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
                mensagem=(
                    f"Bridge calculada: N1={bridge.nivel_1_catalogo_base:.0f}"
                    f" -> N3={bridge.nivel_3_catalogo_normalizado:.0f}"
                    f" | alerta={bridge.status_alerta}"
                ),
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
