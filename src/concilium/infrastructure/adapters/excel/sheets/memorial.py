from __future__ import annotations
from typing import Any
from openpyxl import Workbook
from concilium.domain.models.canonical import CanonicalModel
from ..styles import _fill, _font, _border, _align, _money, _label, _header_row, _title_row, _section_row, _set_col_widths, _auto_fit_columns, _freeze, _C


def _xl_memorial_encargos(ws: Any, row: int, memorial: Any, fills: list, NCOLS: int) -> int:
    """Section 1: social charges A-F; returns updated row."""
    _section_row(ws, row, "1. ENCARGOS SOCIAIS - Grupos A-F + Judicial (vigencia abril/2026)", NCOLS)
    row += 1
    _header_row(ws, row, ["Regime", "Grp A", "Grp B", "Grp C", "Grp D", "Grp E", "Grp F", "Judicial", "TOTAL"])
    row += 1
    enc_pairs = [
        ("Horista CLT", getattr(memorial, "encargos_horista", None) if memorial else None),
        ("Mensalista CLT", getattr(memorial, "encargos_mensalista", None) if memorial else None),
    ]
    for i, (lbl, enc) in enumerate(enc_pairs):
        fill = fills[i % 2]
        ws.cell(row=row, column=1, value=lbl).fill = fill
        vals = (
            [enc.grupo_a, enc.grupo_b, enc.grupo_c, enc.grupo_d, enc.grupo_e, enc.grupo_f, enc.judicial, enc.total]
            if enc
            else [0.0] * 8
        )
        for j, v in enumerate(vals, 2):
            cell = ws.cell(row=row, column=j, value=round(v * 100, 2))
            cell.fill = fill
            cell.border = _border()
            cell.number_format = '0.00"%"'
            cell.alignment = _align("right")
            if j == 9:
                cell.font = _font(bold=True, color=_C["orange"])
        row += 1
    ws.cell(
        row=row, column=1, value="Nota: encargos aplicados ANTES do BDI. Custo MO = Salario x (1 + Encargos)"
    ).font = _font(italic=True, size=9)
    return row + 2


def _xl_memorial_bdi_cats(ws: Any, row: int, bdi_rows: list, memorial: Any, fills: list, NCOLS: int) -> int:
    """Section 2: BDI by category (TCU formula); returns updated row (before blank)."""
    _section_row(ws, row, "2. BDI POR CATEGORIA - Formulacao TCU Ac.2622/2013: BDI=(1+OH)/(1-T)-1", NCOLS)
    row += 1
    _header_row(
        ws,
        row,
        [
            "Categoria",
            "AC(%)",
            "DF(%)",
            "R(%)",
            "CR(%)",
            "L(%)",
            "OH(%)",
            "COFINS",
            "ISS",
            "PIS",
            "CSSL",
            "IR",
            "T(%)",
            "BDI(%)",
        ],
    )
    row += 1
    for i, (nome, cat, comp) in enumerate(bdi_rows):
        fill = fills[i % 2]
        mem_cat = memorial.bdi_por_categoria.get(cat) if memorial else None
        fonte_tag = f" [{mem_cat.fonte_bdi}]" if mem_cat else ""
        _label(ws, row, 1, nome + fonte_tag, fill, bold=True, color=_C["nav_dk"])
        for j, v in enumerate(
            [
                comp.ac * 100,
                comp.df * 100,
                comp.r * 100,
                comp.cr * 100,
                comp.l * 100,
                comp.overhead * 100,
                comp.cofins * 100,
                comp.iss * 100,
                comp.pis * 100,
                comp.cssl * 100,
                comp.ir * 100,
                comp.tributos * 100,
                comp.bdi_total * 100,
            ],
            2,
        ):
            cell = ws.cell(row=row, column=j, value=round(v, 4))
            cell.fill = fill
            cell.border = _border()
            cell.number_format = '0.0000"%"'
            cell.alignment = _align("right")
            if j in (7, 14):
                cell.font = _font(bold=True, color=_C["orange"])
        row += 1
    return row


def _xl_memorial_decomp(ws: Any, row: int, bdi_rows: list, fills: list, NCOLS: int) -> int:
    """Section 3: price decomposition per category; returns updated row (before blank)."""
    _section_row(ws, row, "3. DECOMPOSICAO NO PRECO DE VENDA - De cada R$1,00 cobrado", NCOLS)
    row += 1
    _header_row(
        ws,
        row,
        [
            "Categoria",
            "Custo Dir.",
            "OH-AC",
            "OH-DF",
            "OH-R",
            "OH-CR",
            "Margem L",
            "COFINS",
            "ISS",
            "PIS",
            "CSSL",
            "IR",
            "T Total",
            "SOMA",
        ],
    )
    row += 1
    for i, (nome, _cat, comp) in enumerate(bdi_rows):
        fill = fills[i % 2]
        d = comp.decomposicao_no_preco()
        soma = round(sum(d.values()), 4)
        t_total = d["tributo_cofins"] + d["tributo_iss"] + d["tributo_pis"] + d["tributo_cssl"] + d["tributo_ir"]
        _label(ws, row, 1, nome, fill, bold=True, color=_C["nav_dk"])
        for j, v in enumerate(
            [
                d["custo_direto"],
                d["overhead_ac"],
                d["overhead_df"],
                d["overhead_r"],
                d["overhead_cr"],
                d["margem_l"],
                d["tributo_cofins"],
                d["tributo_iss"],
                d["tributo_pis"],
                d["tributo_cssl"],
                d["tributo_ir"],
                t_total,
                soma,
            ],
            2,
        ):
            cell = ws.cell(row=row, column=j, value=round(v * 100, 2))
            cell.fill = fill
            cell.border = _border()
            cell.number_format = '0.00"%"'
            cell.alignment = _align("right")
            if j == 7:
                cell.font = _font(bold=True, color=_C["verde"])
            if j == 14:
                ok_color = _C["verde"] if abs(soma - 1.0) < 0.001 else _C["vermelho"]
                cell.font = _font(bold=True, color=ok_color)
        row += 1
    return row


def _xl_memorial_aplicacao(ws: Any, row: int, memorial: Any, fills: list, NCOLS: int) -> None:
    """Section 4: BDI application per EAP item."""
    _section_row(ws, row, "4. APLICACAO POR ITEM DA EAP - BDI efetivo x preco unitario", NCOLS)
    row += 1
    _header_row(
        ws,
        row,
        [
            "Item",
            "Descricao",
            "CPU",
            "Un.",
            "Qtd.",
            "PU s/BDI",
            "BDI(%)",
            "PU c/BDI",
            "Sub. s/BDI",
            "Sub. c/BDI",
            "MO (R$)",
            "EQ (R$)",
            "MAT (R$)",
            "DIESEL (R$)",
        ],
    )
    row += 1
    aplicacao = getattr(memorial, "aplicacao_por_item", None) or []
    for i, item in enumerate(aplicacao):
        fill = fills[i % 2]
        vals = [
            item.item_id,
            item.descricao,
            item.cpu_id,
            item.unidade,
            item.quantitativo,
            item.preco_unit_sem_bdi,
            round(item.bdi_aplicado * 100, 2),
            item.preco_unit_com_bdi,
            item.subtotal_sem_bdi,
            item.subtotal_com_bdi,
            item.custo_mao_obra,
            item.custo_equipamentos,
            item.custo_material,
            item.custo_diesel,
        ]
        for j, v in enumerate(vals, 1):
            cell = ws.cell(row=row, column=j, value=v)
            cell.fill = fill
            cell.border = _border()
            if j >= 5:
                cell.alignment = _align("right")
            if j in (6, 8, 9, 10, 11, 12, 13, 14):
                cell.number_format = "R$ #,##0.00"
            if j == 7:
                cell.number_format = '0.00"%"'
        row += 1


def render_memorial_bdi(wb, canonical) -> None:
    """MEMORIAL.BDI - Memorial de calculo BDI auditavel ponta a ponta (ADR-057).

    4 secoes: (1) Encargos A-F, (2) BDI por categoria,
    (3) Decomposicao no preco de venda, (4) Aplicacao por item EAP.
    """
    from concilium.domain.models.financial.bdi import DEFAULT_BDI_TABELA
    from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

    memorial = getattr(canonical, "memorial_calculo_bdi", None)
    if memorial is None:
        try:
            memorial = MemorialBDIBuilder().build(
                canonical_in=canonical, bdi_fonte="DEFAULT_BDI_TABELA", regime_version="pre_reforma"
            )
        except Exception:
            pass

    ws = wb.create_sheet("MEMORIAL.BDI")
    NCOLS = 14
    _set_col_widths(ws, [22, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 18])
    tbl = DEFAULT_BDI_TABELA
    fills = [_fill(_C["white"]), _fill(_C["row_alt"])]
    row = 1

    _title_row(ws, row, "MEMORIAL DE CALCULO BDI - AUDITORIA PONTA A PONTA (ADR-057)", NCOLS)
    row += 1
    if memorial:
        meta = memorial.meta
        ws.cell(
            row=row,
            column=1,
            value=f"Projeto: {meta.projeto_id} | Gerado: {meta.gerado_em[:19]} | "
            f"Regime: {meta.regime_tributario} | Vigencia: {meta.vigencia_bdi}",
        ).font = _font(italic=True, size=9)
        row += 2

    # Secao 1: Encargos
    row = _xl_memorial_encargos(ws, row, memorial, fills, NCOLS)

    # Secao 2: BDI por categoria
    bdi_rows = [
        ("MAO DE OBRA", "mao_obra", tbl.mao_obra),
        ("MATERIAL", "material", tbl.material),
        ("SERVICOS", "servicos", tbl.servicos),
        ("INDIRETO", "indireto", tbl.indireto),
        ("DIESEL", "diesel", tbl.diesel),
    ]
    row = _xl_memorial_bdi_cats(ws, row, bdi_rows, memorial, fills, NCOLS)
    row += 1

    # Secao 3: Decomposicao no preco de venda
    row = _xl_memorial_decomp(ws, row, bdi_rows, fills, NCOLS)
    row += 1

    # Secao 4: Aplicacao por item
    _xl_memorial_aplicacao(ws, row, memorial, fills, NCOLS)
    ws.freeze_panes = "B4"


def render_memorial_mao_obra(wb: Workbook, canonical: CanonicalModel) -> None:
    """MEMORIAL.MAO_OBRA — base de mão de obra efetivamente usada no projeto."""
    ws = wb.create_sheet("MEMORIAL.MAO_OBRA")
    _set_col_widths(ws, [22, 32, 12, 14, 16])
    row = 1
    _title_row(ws, row, "MEMORIAL.MAO_OBRA — INSUMOS UTILIZADOS", 5)
    row += 1
    ws.cell(row=row, column=1, value="Fonte: composições de EQUIPE.DIRETO e indiretos por categoria.").font = _font(
        italic=True, size=9
    )
    row += 2
    _header_row(ws, row, ["Funcao ID", "Descricao", "Papel", "Qtd Base", "Custo Mensal Unit."])
    row += 1

    agg: dict[str, dict[str, Any]] = {}
    for eq in canonical.equipes_diretas or []:
        for f in eq.funcoes or []:
            key = str(f.funcao_id)
            rec = agg.setdefault(
                key,
                {
                    "descricao": f.descricao or key,
                    "papel": getattr(f, "papel", "direto") or "direto",
                    "qtd": 0.0,
                    "custo": float(getattr(f, "custo_mensal_unitario", 0.0) or 0.0),
                },
            )
            rec["qtd"] += float(getattr(f, "num_pessoas", 0.0) or 0.0) * float(
                getattr(eq, "num_equipes_base", 0.0) or 0.0
            )

    fills = [_fill(_C["white"]), _fill(_C["row_alt"])]
    if not agg:
        ws.cell(row=row, column=1, value="Sem dados de mão de obra para memorial.").font = _font(italic=True, size=9)
    for i, (func_id, rec) in enumerate(sorted(agg.items())):
        fill = fills[i % 2]
        vals = [func_id, rec["descricao"], str(rec["papel"]).upper(), rec["qtd"], rec["custo"]]
        for col, val in enumerate(vals, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.fill = fill
            cell.border = _border()
            if col == 5:
                cell.number_format = "R$ #,##0.00"
            if col == 4:
                cell.number_format = "0.00"
                cell.alignment = _align("right")
        row += 1
    _auto_fit_columns(ws)


def render_memorial_equipamentos(wb: Workbook, canonical: CanonicalModel) -> None:
    """MEMORIAL.EQUIPAMENTOS — base de equipamentos efetivamente usada no projeto."""
    ws = wb.create_sheet("MEMORIAL.EQUIPAMENTOS")
    _set_col_widths(ws, [22, 32, 12, 16, 16, 16])
    row = 1
    _title_row(ws, row, "MEMORIAL.EQUIPAMENTOS — INSUMOS UTILIZADOS", 6)
    row += 1
    ws.cell(row=row, column=1, value="Fonte: composições de EQUIPE.DIRETO.").font = _font(italic=True, size=9)
    row += 2
    _header_row(ws, row, ["Equip ID", "Descricao", "Qtd Base", "Custo Mensal", "Comb. Mensal", "Total Mensal"])
    row += 1

    agg: dict[str, dict[str, Any]] = {}
    for eq in canonical.equipes_diretas or []:
        for e in eq.equipamentos or []:
            key = str(e.equip_id or "")
            if not key:
                continue
            rec = agg.setdefault(
                key,
                {
                    "descricao": e.descricao or key,
                    "qtd": 0.0,
                    "custo": 0.0,
                    "comb": 0.0,
                },
            )
            n = float(getattr(e, "num_unidades", 0.0) or 0.0) * float(getattr(eq, "num_equipes_base", 0.0) or 0.0)
            rec["qtd"] += n
            rec["custo"] += float(getattr(e, "custo_mensal", 0.0) or 0.0) * n
            rec["comb"] += float(getattr(e, "custo_combustivel_mensal", 0.0) or 0.0) * n

    fills = [_fill(_C["white"]), _fill(_C["row_alt"])]
    if not agg:
        ws.cell(row=row, column=1, value="Sem dados de equipamentos para memorial.").font = _font(italic=True, size=9)
    for i, (equip_id, rec) in enumerate(sorted(agg.items())):
        fill = fills[i % 2]
        total = float(rec["custo"]) + float(rec["comb"])
        vals = [equip_id, rec["descricao"], rec["qtd"], rec["custo"], rec["comb"], total]
        for col, val in enumerate(vals, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.fill = fill
            cell.border = _border()
            if col >= 4:
                cell.number_format = "R$ #,##0.00"
            if col == 3:
                cell.number_format = "0.00"
                cell.alignment = _align("right")
        row += 1
    _auto_fit_columns(ws)


def render_memorial_materiais(wb: Workbook, canonical: CanonicalModel) -> None:
    """MEMORIAL.MATERIAIS — materiais e valores vindos do planejamento/catálogo."""
    ws = wb.create_sheet("MEMORIAL.MATERIAIS")
    _set_col_widths(ws, [14, 36, 12, 16, 16, 16])
    row = 1
    _title_row(ws, row, "MEMORIAL.MATERIAIS — ITENS COM MATERIAL", 6)
    row += 1
    ws.cell(
        row=row,
        column=1,
        value="Fonte: PLANEJAMENTO (preco_unitario.material e subtotal sem/com BDI).",
    ).font = _font(italic=True, size=9)
    row += 2
    _header_row(ws, row, ["Item ID", "CPU ID", "Qtd", "PU Mat. s/BDI", "Subtotal Mat. s/BDI", "Subtotal Mat. c/BDI"])
    row += 1

    fills = [_fill(_C["white"]), _fill(_C["row_alt"])]
    has_rows = False
    for i, p in enumerate(canonical.planejamento or []):
        pu_mat = float(getattr(getattr(p, "preco_unitario", None), "material", 0.0) or 0.0)
        if pu_mat <= 0.0:
            continue
        fill = fills[i % 2]
        qtd = float(getattr(p, "quantitativo", 0.0) or 0.0)
        sem_bdi = float(getattr(getattr(getattr(p, "subtotal", None), "sem_bdi", None), "material", 0.0) or 0.0)
        com_bdi = float(getattr(getattr(getattr(p, "subtotal", None), "com_bdi", None), "material", 0.0) or 0.0)
        vals = [getattr(p, "item_id", "-"), getattr(p, "cpu_id", "-"), qtd, pu_mat, sem_bdi, com_bdi]
        for col, val in enumerate(vals, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.fill = fill
            cell.border = _border()
            if col >= 4:
                cell.number_format = "R$ #,##0.00"
            if col == 3:
                cell.number_format = "0.00"
                cell.alignment = _align("right")
        row += 1
        has_rows = True

    if not has_rows:
        ws.cell(row=row, column=1, value="Sem materiais com custo explícito neste planejamento.").font = _font(
            italic=True, size=9
        )

    _auto_fit_columns(ws)


# ── MEMORIAL.CATALOGO ────────────────────────────────────────────────────────


def render_memorial_catalogo(wb, canonical) -> None:
    """MEMORIAL.CATALOGO — parâmetros de catálogo por item EAP (formulação referencial).

    Porta a essência das abas PARÂMETROS e RECURSOS do live_model:
    produtividade, preços unitários, composição de equipe (funcoes + equipamentos)
    para cada item da EAP. Permite auditar como os valores do canonical foram
    construídos a partir do catálogo.
    """
    ws = wb.create_sheet("MEMORIAL.CATALOGO")
    NCOLS = 14
    _set_col_widths(ws, [18, 16, 30, 6, 14, 10, 12, 12, 12, 12, 12, 10, 12, 14])

    plan_map = {p.item_id: p for p in (canonical.planejamento or [])}
    equipe_map = {e.item_id: e for e in (canonical.equipes_diretas or [])}
    eap = canonical.eap or []

    fills = [_fill(_C["white"]), _fill(_C["row_alt"])]
    row = 1

    _title_row(ws, row, "MEMORIAL DO CATÁLOGO — PARÂMETROS DE PRODUTIVIDADE E COMPOSIÇÃO POR ITEM EAP", NCOLS)
    row += 2

    # ── Seção 1: Parâmetros por item ─────────────────────────────────────────
    _section_row(ws, row, "1. PARÂMETROS DE CATÁLOGO — POR ITEM EAP", NCOLS)
    row += 1
    _header_row(ws, row, [
        "Item ID", "CPU ID", "Descrição", "Un.", "Qtd.",
        "P_i (un/h)", "PU MO s/BDI", "PU EQ s/BDI", "PU Diesel s/BDI",
        "PU Total s/BDI", "PU Total c/BDI", "nEq",
        "Custo Fixo/Mês", "Perm. Efet. (m)",
    ])
    row += 1

    for i, item in enumerate(eap):
        fill = fills[i % 2]
        p = plan_map.get(item.item_id)
        eq = equipe_map.get(item.item_id)
        pu = getattr(p, "preco_unitario", None) if p else None
        pu_bdi = getattr(p, "preco_unitario_com_bdi", None) if p else None

        def _fv(obj, field, default=0.0):
            try:
                return float(getattr(obj, field, None) or default)
            except Exception:
                return default

        vals = [
            item.item_id,
            item.cpu_id,
            getattr(item, "descricao", "") or item.cpu_id,
            getattr(item, "unidade", ""),
            _fv(item, "quantitativo"),
            _fv(eq, "producao_horaria") if eq else 0.0,
            _fv(pu, "mao_obra"),
            _fv(pu, "equipamentos"),
            _fv(pu, "diesel"),
            _fv(pu, "total"),
            _fv(pu_bdi, "total"),
            int(_fv(eq, "num_equipes_base", 1)) if eq else 1,
            _fv(eq, "custo_fixo_mensal"),
            _fv(eq, "permanencia_efetiva_meses"),
        ]
        fmts = [None, None, None, None, "#,##0.##", "0.0000", "#,##0.0000", "#,##0.0000",
                "#,##0.0000", "#,##0.0000", "#,##0.0000", "0", "#,##0.00", "0.00"]

        for col, (v, fmt) in enumerate(zip(vals, fmts), 1):
            cell = ws.cell(row=row, column=col, value=v)
            cell.fill = fill
            cell.border = _border()
            cell.alignment = _align("right" if col > 4 else "left")
            cell.font = _font(size=9)
            if fmt:
                cell.number_format = fmt
        row += 1

    row += 1

    # ── Seção 2: Composição de equipes (funcoes) ──────────────────────────────
    _section_row(ws, row, "2. COMPOSIÇÃO DE EQUIPES — FUNÇÕES (MÃO DE OBRA)", NCOLS)
    row += 1
    _header_row(ws, row, [
        "Item ID", "CPU ID", "Função ID", "Descrição", "Num. Pessoas",
        "Custo Unit. Mensal (R$)", "Custo Total Mensal (R$)",
        "Encargos Separados", "Cat. Sindical", "", "", "", "", "",
    ])
    row += 1

    for i, item in enumerate(eap):
        eq = equipe_map.get(item.item_id)
        if not eq:
            continue
        for j, func in enumerate(eq.funcoes or []):
            fill = fills[(i + j) % 2]
            n_pessoas = int(getattr(func, "num_pessoas", 1) or 1)
            custo_unit = float(getattr(func, "custo_mensal_unitario", 0) or 0)
            custo_enc = float(getattr(func, "custo_encargos_mensal", 0) or 0)
            cat = getattr(func, "categoria_sindical", "") or ""
            vals = [
                item.item_id if j == 0 else "",
                item.cpu_id if j == 0 else "",
                getattr(func, "funcao_id", ""),
                getattr(func, "descricao", "") or getattr(func, "funcao_id", ""),
                n_pessoas,
                custo_unit,
                round(n_pessoas * custo_unit, 2),
                custo_enc,
                cat,
            ]
            fmts = [None, None, None, None, "0", "#,##0.00", "#,##0.00", "#,##0.00", None]
            for col, (v, fmt) in enumerate(zip(vals, fmts), 1):
                cell = ws.cell(row=row, column=col, value=v)
                cell.fill = fill
                cell.border = _border()
                cell.alignment = _align("right" if col >= 5 else "left")
                cell.font = _font(size=9)
                if fmt:
                    cell.number_format = fmt
            row += 1

    row += 1

    # ── Seção 3: Composição de equipes (equipamentos) ─────────────────────────
    _section_row(ws, row, "3. COMPOSIÇÃO DE EQUIPES — EQUIPAMENTOS", NCOLS)
    row += 1
    _header_row(ws, row, [
        "Item ID", "CPU ID", "Equip. ID", "Descrição", "Num. Unidades",
        "Aluguel Mensal/Unid. (R$)", "Manutenção Mensal/Unid. (R$)", "Comb. Mensal/Unid. (R$)",
        "Total Mensal (R$)", "", "", "", "", "",
    ])
    row += 1

    for i, item in enumerate(eap):
        eq = equipe_map.get(item.item_id)
        if not eq:
            continue
        for j, equip in enumerate(eq.equipamentos or []):
            fill = fills[(i + j) % 2]
            n_unid = int(getattr(equip, "num_unidades", 1) or 1)
            alug = float(getattr(equip, "custo_locacao_mensal", 0) or 0)
            manut = float(getattr(equip, "custo_manutencao_mensal", 0) or 0)
            comb = float(getattr(equip, "custo_combustivel_mensal", 0) or 0)
            total = n_unid * (alug + manut + comb)
            vals = [
                item.item_id if j == 0 else "",
                item.cpu_id if j == 0 else "",
                getattr(equip, "equip_id", ""),
                getattr(equip, "descricao", "") or getattr(equip, "equip_id", ""),
                n_unid,
                alug,
                manut,
                comb,
                round(total, 2),
            ]
            fmts = [None, None, None, None, "0", "#,##0.00", "#,##0.00", "#,##0.00", "#,##0.00"]
            for col, (v, fmt) in enumerate(zip(vals, fmts), 1):
                cell = ws.cell(row=row, column=col, value=v)
                cell.fill = fill
                cell.border = _border()
                cell.alignment = _align("right" if col >= 5 else "left")
                cell.font = _font(size=9)
                if fmt:
                    cell.number_format = fmt
            row += 1

    ws.freeze_panes = "A4"
