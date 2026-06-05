"""Renderizacao do memorial de calculo de BDI em Markdown estruturado."""

from __future__ import annotations


def _pct(v: float) -> str:
    return f"{v:.2%}"


def _brl(v: float) -> str:
    return f"R$ {v:,.2f}"


def render_memorial_bdi_markdown(memorial: dict) -> str:
    """Renderiza memorial BDI como Markdown estruturado com secoes e tabelas."""
    lines: list[str] = []

    # ---- Cabecalho / Meta ------------------------------------------------
    meta = memorial.get("meta") or {}
    gerado_em = str(meta.get("gerado_em", ""))[:19].replace("T", " ")
    lines += [
        "# Memorial de Calculo BDI",
        "",
        f"**Projeto:** {meta.get('projeto_id', '')}",
        f"**Versao:** {meta.get('version', '?')}",
        f"**Gerado em:** {gerado_em}",
        f"**Vigencia encargos:** {meta.get('vigencia_encargos', '')}",
        f"**Vigencia BDI:** {meta.get('vigencia_bdi', '')}",
        f"**Regime tributario:** {meta.get('regime_tributario', '')}",
        "",
        "---",
        "",
    ]

    # ---- Encargos Sociais ------------------------------------------------
    enc_h = memorial.get("encargos_horista") or {}
    enc_m = memorial.get("encargos_mensalista") or {}
    lines += [
        "## Encargos Sociais",
        "",
        "| Grupo | Horista CLT | Mensalista CLT |",
        "|-------|------------:|---------------:|",
    ]
    for grupo in ["grupo_a", "grupo_b", "grupo_c", "grupo_d", "grupo_e", "grupo_f", "judicial"]:
        label = grupo.upper().replace("_", " ")
        lines.append(f"| {label} | {_pct(enc_h.get(grupo, 0))} | {_pct(enc_m.get(grupo, 0))} |")
    lines += [
        f"| **TOTAL** | **{_pct(enc_h.get('total', 0))}** | **{_pct(enc_m.get('total', 0))}** |",
        "",
        f"*Fonte: {enc_h.get('fonte', '')}*",
        "",
        "---",
        "",
    ]

    # ---- BDI por Categoria -----------------------------------------------
    bdi_cat = memorial.get("bdi_por_categoria") or {}
    lines += [
        "## BDI por Categoria",
        "",
        "| Categoria | AC | DF | R | Lucro | Overhead | Tributos | BDI Total |",
        "|-----------|---:|---:|---:|------:|---------:|---------:|----------:|",
    ]
    for cat, bdi in bdi_cat.items():
        override_flag = " *" if bdi.get("override_aplicado") else ""
        lines.append(
            f"| {cat}{override_flag} | {_pct(bdi.get('ac', 0))} | {_pct(bdi.get('df', 0))} | "
            f"{_pct(bdi.get('r', 0))} | {_pct(bdi.get('l', 0))} | "
            f"{_pct(bdi.get('overhead_total', 0))} | {_pct(bdi.get('tributos_total', 0))} | "
            f"**{_pct(bdi.get('bdi_total', 0))}** |"
        )
    lines += [
        "",
        "*Categorias marcadas com * tiveram override aplicado.*",
        "",
        "---",
        "",
    ]

    # ---- Decomposicao Percentual por Categoria ---------------------------
    decomp = memorial.get("decomposicao_por_categoria") or {}
    if decomp:
        lines += [
            "## Decomposicao Percentual do Preco de Venda",
            "",
            "| Categoria | Custo Direto | AC | DF | R | Lucro | ISS | CSSL | IR |",
            "|-----------|-------------:|---:|---:|---:|------:|----:|-----:|---:|",
        ]
        for cat, d in decomp.items():
            lines.append(
                f"| {cat} | {_pct(d.get('custo_direto_pct', 0))} | "
                f"{_pct(d.get('overhead_ac_pct', 0))} | {_pct(d.get('overhead_df_pct', 0))} | "
                f"{_pct(d.get('overhead_r_pct', 0))} | {_pct(d.get('margem_l_pct', 0))} | "
                f"{_pct(d.get('tributo_iss_pct', 0))} | {_pct(d.get('tributo_cssl_pct', 0))} | "
                f"{_pct(d.get('tributo_ir_pct', 0))} |"
            )
        lines += ["", "---", ""]

    # ---- Aplicacao por Item ---------------------------------------------
    aplicacao = memorial.get("aplicacao_por_item") or []
    if aplicacao:
        lines += [
            "## Aplicacao por Item",
            "",
            "| Item | Descricao | Qtd | Un | PU s/BDI | BDI | PU c/BDI | Subtotal c/BDI |",
            "|------|-----------|----:|----|----------:|----:|----------:|---------------:|",
        ]
        for item in aplicacao:
            qty = item.get("quantitativo", 0)
            qty_str = f"{qty:,.0f}" if qty >= 1 else f"{qty:.4f}"
            lines.append(
                f"| {item.get('item_id', '')} | {item.get('descricao', '')} | "
                f"{qty_str} | {item.get('unidade', '')} | "
                f"R$ {item.get('preco_unit_sem_bdi', 0):,.4f} | {_pct(item.get('bdi_aplicado', 0))} | "
                f"R$ {item.get('preco_unit_com_bdi', 0):,.4f} | {_brl(item.get('subtotal_com_bdi', 0))} |"
            )
        lines += ["", "---", ""]

    # ---- Resumo Financeiro ----------------------------------------------
    lines += [
        "## Resumo Financeiro",
        "",
        "| Componente | Valor |",
        "|------------|------:|",
        f"| Custo Direto Total | {_brl(memorial.get('custo_direto_total', 0))} |",
        f"| Overhead Total | {_brl(memorial.get('overhead_total', 0))} |",
        f"| Tributos Total | {_brl(memorial.get('tributos_total', 0))} |",
        f"| Margem Total | {_brl(memorial.get('margem_total', 0))} |",
        f"| **Venda Total c/ BDI** | **{_brl(memorial.get('venda_total_com_bdi', 0))}** |",
        f"| Margem % | {_pct(memorial.get('margem_pct', 0))} |",
        "",
    ]

    return "\n".join(lines)


__all__ = ["render_memorial_bdi_markdown"]
