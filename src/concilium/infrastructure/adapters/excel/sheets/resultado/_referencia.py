"""Excel sheets — resultado (parte extraída de resultado.py, grupo _referencia)."""

from __future__ import annotations

from ...styles import (
    _C,
    _align,
    _border,
    _fill,
    _font,
    _header_row,
    _section_row,
    _set_col_widths,
    _title_row,
)


def _ref_sv(obj, field, default=0.0):
    """Lê um campo numérico com fallback seguro, para uso nas tabelas da aba REFERÊNCIA."""
    try:
        return float(getattr(obj, field, None) or default)
    except Exception:
        return default


def _build_referencia_items(canonical) -> list[tuple[str, float, str, bool]]:
    """Monta as linhas (label, value, formula_note, is_pct) dos resultados financeiros calculados."""
    res = canonical.resultado
    venda = getattr(res, "venda", None) if res else None
    custo = getattr(res, "custo", None) if res else None

    indireto_total = sum(float(getattr(ind, "custo_total", 0) or 0) for ind in (canonical.indiretos or []))

    return [
        # (label, value, formula_note, is_pct)
        (
            "Custo Direto — Equipes (catálogo)",
            _ref_sv(custo, "direto_equipes"),
            "Σ(custo_fixo_mensal × permanência_efetiva_meses × nEq) por atividade",
            False,
        ),
        (
            "Custo Direto — Pool instancial (N3)",
            _ref_sv(custo, "direto_pool") or _ref_sv(custo, "direto_equipes"),
            "Σ(custo_pool_imputado × nEq) via contratos de pool (ADR-071)",
            False,
        ),
        (
            "Custo Indireto",
            indireto_total if indireto_total > 0 else _ref_sv(custo, "indireto_total"),
            "Σ(custo_fixo_mensal × permanência) por categoria indireta",
            False,
        ),
        (
            "Custo Total (direto + indireto)",
            _ref_sv(custo, "total"),
            "custo_direto + custo_indireto (sem BDI)",
            False,
        ),
        (
            "Preço de Venda — sem BDI",
            _ref_sv(venda, "total_sem_bdi"),
            "Σ(quantitativo × PU_cat) por item EAP + indiretos s/BDI",
            False,
        ),
        (
            "Preço de Venda — com BDI",
            _ref_sv(venda, "total_com_bdi"),
            "Σ(quantitativo × PU_cat × (1+BDI_cat)) por categoria + indiretos×(1+BDI_ind)",
            False,
        ),
        (
            "Margem Bruta",
            _ref_sv(res, "margem_pct"),
            # ADR-183: base operacional (total_custo_plus), não catálogo (total_com_bdi) —
            # nota corrigida para bater com a fórmula real em _resultado.py.
            "(preco_venda_operacional - custo_total) / preco_venda_operacional",
            True,
        ),
    ]


def _render_referencia_items_rows(ws, row: int, fills: list, items: list[tuple[str, float, str, bool]]) -> int:
    """Renderiza as linhas de resultados financeiros calculados e retorna a próxima linha livre."""
    for i, (label, value, note, is_pct) in enumerate(items):
        fill = fills[i % 2]
        fmt = "0.00%" if is_pct else "#,##0.00"

        ws.cell(row=row, column=1, value=label).fill = fill
        ws.cell(row=row, column=1).border = _border()
        ws.cell(row=row, column=1).alignment = _align("left")
        ws.cell(row=row, column=1).font = _font(size=10)

        cell_val = ws.cell(row=row, column=2, value=value)
        cell_val.fill = fill
        cell_val.border = _border()
        cell_val.alignment = _align("right")
        cell_val.number_format = fmt
        cell_val.font = _font(bold=True, size=10)

        ws.cell(row=row, column=3, value=note).fill = fill
        ws.cell(row=row, column=3).border = _border()
        ws.cell(row=row, column=3).alignment = _align("left")
        ws.cell(row=row, column=3).font = _font(italic=True, size=9)
        row += 1
    return row


def _build_referencia_bridge_rows(canonical) -> list[tuple[str, float, str]]:
    """Monta as linhas (label, value, interpretação) do bridge de precificação N1 → N2 → N3."""
    pe_items = canonical.ponto_equilibrio or []
    n1 = sum(float(getattr(pe, "preco_venda_cpu", 0) or 0) for pe in pe_items)
    gap_escala = sum(float(getattr(pe, "gap_escala_abs", 0) or 0) for pe in pe_items)
    gap_prat = sum(float(getattr(pe, "gap_praticabilidade_abs", 0) or 0) for pe in pe_items)
    n2 = n1 + gap_escala
    n3 = n2 + gap_prat

    return [
        ("N1 — Catálogo puro (Σ PU_cat × Q)", n1, "Base de mercado: preço de referência sem considerar execução real"),
        (
            f"  Δ Gap de Escala (+ R$ {gap_escala:,.0f})",
            gap_escala,
            "Custo de paralelismo: frentes adicionais com produtividade marginal",
        ),
        ("N2 — Autônomo escalado", n2, "Custo se equipes fossem dedicadas (sem compartilhamento de pool)"),
        (
            f"  Δ Gap de Praticabilidade (+ R$ {gap_prat:,.0f})",
            gap_prat,
            "Perdas climáticas e de eficiência absorvidas pelo pool",
        ),
        ("N3 — Pool instancial", n3, "Custo real projetado com pool compartilhado (= N2 ± economia/custo pool)"),
    ]


def _build_referencia_clima_n4_nota(canonical) -> str | None:
    """Issue #124: nota explicando que o gap de praticabilidade (N1→N2→N3) não é
    cobrado no custo operacional real (N4) — retorna None quando não há gap
    climático diagnosticado neste run (mesmo critério de LimitacaoClimaN4).
    """
    limitacao = getattr(canonical.resultado, "limitacao_clima_n4", None) if canonical.resultado else None
    if limitacao is None:
        return None
    return limitacao.mensagem


def _render_referencia_bridge_rows(ws, row: int, fills: list, bridge_rows: list[tuple[str, float, str]]) -> int:
    """Renderiza as linhas do bridge de precificação e retorna a próxima linha livre."""
    for i, (label, value, note) in enumerate(bridge_rows):
        fill = fills[i % 2]
        is_bold = "N1" in label or "N2" in label or "N3" in label
        ws.cell(row=row, column=1, value=label).fill = fill
        ws.cell(row=row, column=1).border = _border()
        ws.cell(row=row, column=1).alignment = _align("left")
        ws.cell(row=row, column=1).font = _font(bold=is_bold, size=10)

        cell_val = ws.cell(row=row, column=2, value=value)
        cell_val.fill = fill
        cell_val.border = _border()
        cell_val.alignment = _align("right")
        cell_val.number_format = "#,##0.00"
        cell_val.font = _font(bold=is_bold, size=10)

        ws.cell(row=row, column=3, value=note).fill = fill
        ws.cell(row=row, column=3).border = _border()
        ws.cell(row=row, column=3).alignment = _align("left")
        ws.cell(row=row, column=3).font = _font(italic=True, size=9)
        row += 1
    return row


def render_referencia(wb, canonical) -> None:
    """REFERÊNCIA — valores calculados pelo Concilium com base de cálculo auditável.

    Porta a aba REFERÊNCIA do live_model: mostra os valores financeiros-chave
    do canonical com a explicação de como cada um é derivado, permitindo
    auditoria da formulação usada pelo sistema.
    """
    ws = wb.create_sheet("REFERÊNCIA")
    _set_col_widths(ws, [42, 20, 50])
    NCOLS = 3

    fills = [_fill(_C["white"]), _fill(_C["row_alt"])]
    row = 1

    _title_row(ws, row, "REFERÊNCIA — VALORES CALCULADOS PELO CONCILIUM (FORMULAÇÃO REFERENCIAL)", NCOLS)
    row += 2

    _section_row(ws, row, "RESULTADOS FINANCEIROS CALCULADOS", NCOLS)
    row += 1
    _header_row(ws, row, ["Indicador", "Valor Calculado (R$)", "Base de Cálculo / Formulação"])
    row += 1

    items = _build_referencia_items(canonical)
    row = _render_referencia_items_rows(ws, row, fills, items)

    row += 1

    # ── Seção 2: Bridge N1 → N2 → N3 ────────────────────────────────────────
    _section_row(ws, row, "BRIDGE DE PRECIFICAÇÃO N1 → N2 → N3 (NEP-042)", NCOLS)
    row += 1
    _header_row(ws, row, ["Camada", "Valor (R$)", "Interpretação"])
    row += 1

    bridge_rows = _build_referencia_bridge_rows(canonical)
    row = _render_referencia_bridge_rows(ws, row, fills, bridge_rows)

    # Issue #124: nota — o gap de praticabilidade acima é diagnosticado, mas nunca
    # é cobrado no custo operacional real (N4). Renderizada só quando há gap > 0.
    nota_clima_n4 = _build_referencia_clima_n4_nota(canonical)
    if nota_clima_n4:
        row += 1
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=NCOLS)
        cell_nota = ws.cell(row=row, column=1, value=f"⚠ {nota_clima_n4}")
        cell_nota.alignment = _align("left")
        cell_nota.font = _font(italic=True, size=9)
        row += 1

    ws.freeze_panes = "A4"


