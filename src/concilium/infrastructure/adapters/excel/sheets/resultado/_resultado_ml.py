"""Excel sheets — resultado (parte extraída de resultado.py, grupo _resultado_ml)."""

from __future__ import annotations

import math
import re as _re
from typing import Any

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from concilium.domain.models.canonical import CanonicalModel

from ...cash_flow import _cash_flow
from ...helpers import _project_months
from ...styles import (
    _C,
    _align,
    _auto_fit_columns,
    _border,
    _fill,
    _font,
    _freeze,
    _label,
    _section_row,
    _set_col_widths,
    _title_row,
)


def _xl_resultado_ref(sheet: str, col: int, ref_row: int | None, fallback: Any) -> Any:
    """Cross-sheet formula reference when ref_row is known."""
    if ref_row is not None:
        sheet_ref = f"'{sheet}'" if not _re.fullmatch(r"[A-Za-z0-9_]+", sheet) else sheet
        return f"={sheet_ref}!${get_column_letter(col)}${ref_row}"
    return fallback


def _xl_resultado_indirect_cats(res: Any, indiretos_refs: dict | None, linha_fn: Any) -> None:
    """Write each indirect cost category row (for cat, attr in [...])."""
    for cat, attr in [
        ("ADM", "indireto_adm"),
        ("TOP", "indireto_top"),
        ("LAB", "indireto_lab"),
        ("QSMS", "indireto_qsms"),
        ("MOB", "indireto_mob"),
    ]:
        fallback = getattr(res.custo, attr, 0.0) if hasattr(res.custo, attr) else 0.0
        cat_row = (indiretos_refs or {}).get(cat)
        linha_fn(f"  {cat}", _xl_resultado_ref("INDIRETOS.DET", 8, cat_row, fallback))


def _xl_resultado_custo_composicao(res: Any, planejamento_total_row: int | None, linha_fn: Any) -> float:
    """COMPOSIÇÃO DE CUSTO block — returns cd (direto base value)."""
    if not res:
        return 0.0
    cd = res.custo.direto_equipes
    ci_total = res.custo.total - cd
    pvt = res.venda.total_com_bdi
    razao = ci_total / cd if cd > 0 else 0.0
    ci_pvt = ci_total / pvt if pvt > 0 else 0.0
    linha_fn(
        "Total Direto (equipes)",
        _xl_resultado_ref("PLANEJAMENTO", 13, planejamento_total_row, res.venda.total_sem_bdi),
    )
    linha_fn("Total Direto (c/BDI)", res.venda.total_com_bdi)
    linha_fn("RAZÃO CI / CD (%)", round(razao * 100, 2), pct=True, is_money=False)
    linha_fn("CI / PVT (%)", round(ci_pvt * 100, 2), pct=True, is_money=False)
    return cd


def _xl_resultado_cap_giro_rows(n_exec: int, canonical: Any, linha_fn: Any) -> None:
    """Parcela and residuo rows for capital de giro — only when n_exec > 0."""
    if n_exec > 0 and canonical.resultado:
        M = canonical.resultado.venda.total_com_bdi
        linha_fn("Parcela mensal (meses 2 a n)", math.floor(M / n_exec))
        linha_fn("Resíduo (mês n+1)", M - math.floor(M / n_exec) * (n_exec - 1))


def _compute_resultado_alavancas(canonical: Any) -> tuple:
    """Compute alavancas metrics for RESULTADO sheet."""
    custo_equipes_total = sum(eq.custo_total for eq in canonical.equipes_diretas)
    custo_fixo_mensal_total = sum(eq.custo_fixo_mensal for eq in canonical.equipes_diretas)
    permanencia_media = (
        sum(eq.permanencia_meses for eq in canonical.equipes_diretas) / len(canonical.equipes_diretas)
        if canonical.equipes_diretas
        else 0.0
    )
    pico_equipes = max((eq.num_equipes_base for eq in canonical.equipes_diretas), default=0)
    pratic_media = 0.0
    if canonical.praticabilidade and canonical.praticabilidade.percentual_produtivo_semanal:
        vals = list(canonical.praticabilidade.percentual_produtivo_semanal.values())
        pratic_media = sum(vals) / len(vals) if vals else 0.0
    return custo_equipes_total, custo_fixo_mensal_total, permanencia_media, pico_equipes, pratic_media


def render_resultado_ml(
    wb: Workbook,
    canonical: CanonicalModel,
    diretos_total_row: int | None = None,
    indiretos_refs: dict[str, int] | None = None,
    planejamento_total_row: int | None = None,
) -> None:
    """RESULTADO — resumo financeiro consolidado.

    Quando diretos_total_row / indiretos_refs / planejamento_total_row são
    fornecidos, as células de custo e receita contém fórmulas de referência
    cruzada (=DIRETOS!$I$N etc.) em vez de valores estáticos, tornando a
    planilha autoajustável sem precisa ser regenerada após ajustes manuais
    nas abas de origem.
    """
    ws = wb.create_sheet("RESULTADO")

    _set_col_widths(ws, [38, 22, 10])
    _freeze(ws, "A3")

    row = 1
    _title_row(ws, row, "RESULTADO FINANCEIRO — MENDESLOBO CONSTRUTORA", 3)
    row += 2

    res = canonical.resultado
    if res is None:
        ws.cell(row=row, column=1, value="Resultado não disponível.")
        return

    proj = canonical.projeto
    cf = _cash_flow(canonical)
    max_exp = max((r["exposicao_acumulada"] for r in cf), default=0.0)

    STATUS_COLOR = {
        "VERDE": (_C["verde"], _C["verde_lt"]),
        "AMARELO": (_C["amarelo"], _C["amar_lt"]),
        "VERMELHO": (_C["vermelho"], _C["verm_lt"]),
    }
    s_color, s_bg = STATUS_COLOR.get(res.status_margem, (_C["preto"], _C["cinza_lt"]))

    def bloco(titulo: str) -> None:
        nonlocal row
        _section_row(ws, row, titulo, 3)
        row += 1

    def linha(
        label: str,
        valor: Any,
        destaque: bool = False,
        is_money: bool = True,
        pct: bool = False,
        color_override: str | None = None,
    ) -> None:
        nonlocal row
        fill = _fill(_C["white"]) if row % 2 == 0 else _fill(_C["row_alt"])
        _label(ws, row, 1, label, fill, bold=destaque)
        cell = ws.cell(row=row, column=2, value=valor)
        cell.fill = fill
        cell.border = _border()
        cell.font = _font(bold=destaque, color=color_override or _C["preto"])
        is_formula = isinstance(valor, str) and valor.startswith("=")
        if is_money and (isinstance(valor, (int, float)) or is_formula):
            cell.number_format = "R$ #,##0.00"
            cell.alignment = _align("right")
        elif pct and (isinstance(valor, (int, float)) or is_formula):
            cell.number_format = '0.00"%"'
            cell.alignment = _align("right")
        else:
            cell.alignment = _align("left")
        ws.cell(row=row, column=3).fill = fill
        ws.cell(row=row, column=3).border = _border()
        row += 1

    def linha_alavanca(label: str, valor: Any, nota: str, *, is_money: bool = True, pct: bool = False) -> None:
        nonlocal row
        fill = _fill(_C["white"]) if row % 2 == 0 else _fill(_C["row_alt"])
        _label(ws, row, 1, label, fill, bold=False)
        cell = ws.cell(row=row, column=2, value=valor)
        cell.fill = fill
        cell.border = _border()
        cell.alignment = _align("right" if (is_money or pct or isinstance(valor, (int, float))) else "left")
        if is_money and (isinstance(valor, (int, float)) or (isinstance(valor, str) and valor.startswith("="))):
            cell.number_format = "R$ #,##0.00"
        elif pct and isinstance(valor, (int, float)):
            cell.number_format = '0.00"%"'
        _label(ws, row, 3, nota, fill, color=_C["nav_md"])
        row += 1

    # Identificação do projeto
    bloco("PROJETO")
    linha("Nome", proj.nome, is_money=False)
    linha("Tipo de obra", proj.tipo_obra, is_money=False)
    linha("Localização", str(proj.localizacao) if proj.localizacao is not None else "", is_money=False)
    linha("Período", f"{proj.data_inicio} -> {proj.data_termino}", is_money=False)
    linha(
        "Regime",
        f"{proj.regime_trabalho.dias_semana} dias/sem · {proj.regime_trabalho.horas_dia} h/dia",
        is_money=False,
    )
    row += 1

    # Receita
    bloco("RECEITA CONTRATUAL (COM BDI)")
    linha(
        "Preço de venda s/ BDI", _xl_resultado_ref("PLANEJAMENTO", 13, planejamento_total_row, res.venda.total_sem_bdi)
    )
    linha("Preço de venda c/ BDI", res.venda.total_com_bdi, destaque=True)
    row += 1

    # Custos — com referências cruzadas para DIRETOS e INDIRETOS
    bloco("CUSTOS")
    row_custo_direto = row
    linha(
        "Custo direto (equipes)",
        _xl_resultado_ref("PLANEJAMENTO", 13, planejamento_total_row, res.custo.direto_equipes),
    )
    _xl_resultado_indirect_cats(res, indiretos_refs, linha)
    custo_ind = res.custo.total - res.custo.direto_equipes
    row_custo_indireto = row
    linha(
        "Custo indireto (subtotal)",
        _xl_resultado_ref("INDIRETOS.DET", 8, (indiretos_refs or {}).get("total"), custo_ind),
    )
    row_custo_total = row
    linha("CUSTO TOTAL", f"=B{row_custo_direto}+B{row_custo_indireto}", destaque=True)
    row += 1

    # Resultado
    # ADR-183 (achado pendente): "Resultado bruto"/"Margem bruta" precisam da venda
    # OPERACIONAL (custo instancial × BDI, total_custo_plus) — não da venda de catálogo
    # (total_com_bdi, row_venda acima), que é a base certa só para o bloco "RECEITA
    # CONTRATUAL" e para os consumidores de capital de giro/alavanca mais abaixo.
    # Linha dedicada evita misturar bases sem alterar o que row_venda já alimenta.
    bloco("RESULTADO")
    row_venda_operacional = row
    linha("Preço de venda operacional (custo instancial × BDI)", res.venda.total_custo_plus)
    row_resultado_bruto = row
    linha(
        "Resultado bruto (R$)",
        f"=B{row_venda_operacional}-B{row_custo_total}",
        destaque=True,
        color_override=_C["verde"] if res.resultado_financeiro >= 0 else _C["vermelho"],
    )
    linha(
        "Margem bruta (%)",
        f"=IF(B{row_venda_operacional}>0, B{row_resultado_bruto}/B{row_venda_operacional}, 0)",
        destaque=True,
        is_money=False,
        pct=True,
        color_override=s_color,
    )
    row += 1

    # Status em caixa colorido
    fill_status = _fill(s_bg)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
    cell_st = ws.cell(row=row, column=1, value=f"STATUS: {res.status_margem}")
    cell_st.fill = fill_status
    cell_st.font = _font(bold=True, color=s_color, size=14)
    cell_st.alignment = _align("center")
    cell_st.border = _border()
    row += 2

    # Composicao de custo
    bloco("COMPOSIÇÃO DE CUSTO")
    cd = _xl_resultado_custo_composicao(res, planejamento_total_row, linha)
    row += 1

    # Capital de giro
    bloco("CAPITAL DE GIRO")
    linha("Exposição máxima", max_exp, color_override=_C["vermelho"] if max_exp > 0 else _C["verde"])
    n_exec = len(_project_months(canonical))
    _xl_resultado_cap_giro_rows(n_exec, canonical, linha)
    linha("Duração da execução (meses)", n_exec, is_money=False)

    # Alavancas de reajuste para iteração manual
    bloco("ALAVANCAS DE REAJUSTE")
    custo_equipes_total, custo_fixo_mensal_total, permanencia_media, pico_equipes, pratic_media = (
        _compute_resultado_alavancas(canonical)
    )
    linha_alavanca("Preço de venda total", res.venda.total_com_bdi, "Depende de MO/EQ/MAT/DIESEL + BDI indireto")
    linha_alavanca("Base catálogo s/BDI", cd, "Knob de partida para precificação", is_money=True)
    linha_alavanca(
        "Markup efetivo",
        # ADR-183: bdi_equivalente_proj (base operacional consistente), não
        # bdi_lucro_impostos (mistura venda de catálogo com custo operacional).
        res.venda.bdi_equivalente_proj,
        "Resultado consolidado, não a fórmula de composição",
        pct=True,
        is_money=False,
    )
    linha_alavanca(
        "Custo direto de equipes", custo_equipes_total, "Sensível a permanência, produtividade e nº de frentes"
    )
    linha_alavanca("Custo fixo mensal de equipes", custo_fixo_mensal_total, "Multiplica diretamente pela permanência")
    linha_alavanca(
        "Permanência média (meses)", permanencia_media, "Reduzir prazo reduz custo fixo e mobilização", is_money=False
    )
    linha_alavanca("Pico de equipes", pico_equipes, "Se subir, pressiona custo fixo e mobilização", is_money=False)
    linha_alavanca(
        "Praticabilidade média", pratic_media, "Baixa praticabilidade aumenta permanência", pct=True, is_money=False
    )
    _auto_fit_columns(ws)


