"""Skill 06 (_consolidacao) — Consolidação Financeira (parte extraída de _skill_helpers_a.py)."""

from __future__ import annotations

from typing import Any

from concilium.domain.models.canonical import (
    CanonicalModel,
    LimitacaoClimaN4,
    ValidacaoItem,
)


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


def _bridge_compute_n4(inputs: dict, custo_direto_equipe: float, benchmark_mode: bool) -> float | None:
    if benchmark_mode:
        return None
    raw_n4 = inputs.get("custo_operacional_equipes") or (custo_direto_equipe if custo_direto_equipe > 0 else None)
    return round(float(raw_n4), 2) if raw_n4 else None


def _bridge_compute_delta_status(n3: float, n4: float | None) -> tuple[float | None, float | None, str]:
    delta_abs = round(n4 - n3, 2) if n4 is not None else None
    delta_pct = round(delta_abs / n4 * 100, 2) if delta_abs is not None and n4 else None
    abs_pct = abs(delta_pct) if delta_pct is not None else None
    status = (
        "VERDE"
        if abs_pct is not None and abs_pct <= 10
        else (
            "AMARELO" if abs_pct is not None and abs_pct <= 25 else ("VERMELHO" if abs_pct is not None else "SEM_DADOS")
        )
    )
    return delta_abs, delta_pct, status


def _bridge_compute_n123(venda_sem_bdi: float, pe_items: list) -> tuple[float, float, float, float, float]:
    N1 = round(venda_sem_bdi, 2)
    gap_escala = sum(float(getattr(pe, "gap_escala_abs", 0.0) or 0.0) for pe in pe_items)
    gap_prat = sum(float(getattr(pe, "gap_praticabilidade_abs", 0.0) or 0.0) for pe in pe_items)
    N2 = round(N1 + gap_escala, 2)
    N3 = round(N2 + gap_prat, 2)
    return N1, N2, N3, gap_escala, gap_prat


def _bridge_build_dict(
    n1: float,
    n2: float,
    n3: float,
    n4: float | None,
    n_pool: float,
    fq: float,
    praticabilidade: float,
    gap_escala: float,
    gap_prat: float,
    delta_abs: float | None,
    delta_pct: float | None,
    status: str,
) -> dict:
    return {
        "nivel_1_catalogo_base": n1,
        "nivel_2_catalogo_escalado": n2,
        "nivel_3_catalogo_normalizado": n3,
        "nivel_4_operacional": n4,
        # NEP-042: custo pool instancial explícito (Camada 3)
        "nivel_pool_instancial": n_pool if n_pool > 0 else None,
        "fator_quantizacao": fq,
        "fator_praticabilidade": praticabilidade,
        "desvio_escala_abs": round(gap_escala, 2),
        "desvio_clima_abs": round(gap_prat, 2),
        "delta_real_abs": delta_abs,
        "delta_real_percentual": delta_pct,
        "delta_estrutural_abs": round(n3 - n1, 2),
        "necessidades_fracionadas": [],
        "status_alerta": status,
    }


def _bridge_build_limitacao_clima_n4(gap_prat: float) -> LimitacaoClimaN4 | None:
    """Issue #124: materializa `gap_praticabilidade_abs` como campo de 1ª classe.

    Retorna None quando não há gap climático diagnosticado neste run (gap_prat <= 0),
    espelhando o mesmo critério de `_pe_lever_gap_praticabilidade` — evita ruído em
    projetos sem lesão de praticabilidade.
    """
    if gap_prat <= 0:
        return None
    return LimitacaoClimaN4(gap_praticabilidade_abs=round(gap_prat, 2))


def _bridge_append_clima_n4_validacao(validacoes: list, limitacao: LimitacaoClimaN4 | None) -> None:
    if limitacao is None:
        return
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-BRIDGE-CLIMA-N4",
            status="INFO",
            mensagem=(
                f"Gap climático diagnosticado (N3): R$ {limitacao.gap_praticabilidade_abs:,.0f} — "
                "NÃO cobrado no custo operacional real (N4); ver Resultado.limitacao_clima_n4 "
                "(ADR-148 D2-bis / ADR-082-cons, issue #124)."
            ),
        )
    )


def _bridge_append_ok_validacao(
    validacoes: list, n1: float, n2: float, n3: float, n4: float | None, n_pool: float, status: str
) -> None:
    n4_str = f"{n4:.0f}" if n4 is not None else "N/A"
    pool_str = f" | pool={n_pool:.0f}" if n_pool > 0 else ""
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-BRIDGE-OK",
            status="OK",
            mensagem=f"Bridge: N1={n1:.0f} → N2={n2:.0f} → N3={n3:.0f} → N4={n4_str}{pool_str} | alerta={status}",
        )
    )


def _build_bridge_from_pe(
    pe_items: list,
    venda_sem_bdi: float,
    custo_direto_equipe: float,
    inputs: dict,
    validacoes: list,
) -> tuple[dict | None, LimitacaoClimaN4 | None]:
    """Deriva bridge N1→N2→N3→N4 das três camadas de PontoEquilibrio (NEP-042 D5).

    N1 = Σ(PU_cat × Q)     — catálogo puro
    N2 = N1 + Σ gap_escala  — corrigido por escala de frentes (quantização)
    N3 = N2 + Σ gap_prat    — corrigido por praticabilidade climática
    N4 = custo operacional real (pool instancial)

    Returns:
        (bridge_dict, limitacao_clima_n4) — o segundo elemento (issue #124) expõe
        `gap_praticabilidade_abs` como campo de 1ª classe para `Resultado.limitacao_clima_n4`,
        None quando não há gap climático diagnosticado neste run.
    """
    try:
        benchmark_mode = _as_bool(inputs.get("benchmark_mode")) or _as_bool(inputs.get("modo_benchmark"))

        N1, N2, N3, gap_escala, gap_prat = _bridge_compute_n123(venda_sem_bdi, pe_items)

        N4 = _bridge_compute_n4(inputs, custo_direto_equipe, benchmark_mode)
        delta_abs, delta_pct, status = _bridge_compute_delta_status(N3, N4)

        fq = round(N2 / N1, 4) if N1 > 0 else 1.0
        praticabilidade = round(N2 / N3, 4) if N3 > 0 else 1.0

        # NEP-042 D5: N_pool = custo pool instancial total (Camada 3)
        N_pool = round(sum(float(getattr(pe, "custo_pool_total", 0.0) or 0.0) for pe in pe_items), 2)

        bridge = _bridge_build_dict(
            N1, N2, N3, N4, N_pool, fq, praticabilidade, gap_escala, gap_prat, delta_abs, delta_pct, status
        )
        _bridge_append_ok_validacao(validacoes, N1, N2, N3, N4, N_pool, status)
        limitacao_clima_n4 = _bridge_build_limitacao_clima_n4(gap_prat)
        _bridge_append_clima_n4_validacao(validacoes, limitacao_clima_n4)
        return bridge, limitacao_clima_n4
    except Exception as exc:  # pragma: no cover
        validacoes.append(
            ValidacaoItem(codigo="VAL-BRIDGE-WARN", status="AVISO", mensagem=f"Bridge não calculada: {exc}")
        )
        return None, None


def _build_diagnostico_pe(
    canonical_in: CanonicalModel,
    custos_atividades: list,
    pe_items: list,
    validacoes: list,
    bdi_tabela: Any = None,
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
        # Repassa a alíquota de tributos da tabela de BDI efetivamente aplicada
        # neste run, em vez do fallback 0.1338 (ver diagnostico_pe_builder/backtracking_pe_builder).
        bdi_rates = {"tributos_efetivo": bdi_tabela.mao_obra.tributos} if bdi_tabela is not None else None
        diag = DiagnosticoPEBuilder().build(_cp, bdi_rates=bdi_rates)
        back = BacktrackingPEBuilder(tabela_bdi=bdi_tabela).build(diag, _cp)
        return diag, back
    except Exception as exc:  # pragma: no cover
        import logging

        logging.getLogger(__name__).warning("DiagnosticoPE falhou (best-effort): %s", exc)
        return None, None


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


