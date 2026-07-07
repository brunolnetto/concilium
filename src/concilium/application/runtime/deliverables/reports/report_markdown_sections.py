"""Seções base do relatório financeiro em Markdown."""

from __future__ import annotations

from typing import Any, cast


def _brl(value: Any) -> str:
    try:
        return f"R$ {float(value):,.2f}"
    except Exception:
        return str(value)


def _pct(value: Any) -> str:
    try:
        v = float(value)
        # margem_pct is stored as a decimal fraction (0.17 = 17%); multiply to get display %
        if -1.0 <= v <= 1.0:
            v *= 100
        return f"{v:.1f}%"
    except Exception:
        return str(value)


def _exec_summary_parag1(resumo: dict[str, Any]) -> str:
    """Project identity paragraph for the executive summary."""
    nome = resumo.get("projeto") or "Projeto"
    tipo_obra = resumo.get("tipo_obra") or ""
    localizacao = resumo.get("localizacao") or ""
    periodo = resumo.get("periodo") or ""
    status = resumo.get("status") or ""

    tipo_label = {
        "terraplenagem": "obra de terraplenagem",
        "pavimentacao": "obra de pavimentacao",
        "saneamento": "obra de saneamento",
    }.get(tipo_obra, tipo_obra)
    parag1_parts = [f"O orçamento operacional contempla {tipo_label} denominada **{nome}**"]
    if localizacao:
        parag1_parts.append(f"localizada em {localizacao}")
    if periodo:
        parag1_parts.append(f"com execução prevista para o período {periodo}")
    if status:
        parag1_parts.append(f"(status atual: {status})")
    return ", ".join(parag1_parts[:1]) + (", " + ", ".join(parag1_parts[1:]) if len(parag1_parts) > 1 else "") + "."


def _exec_summary_margem_label(status_margem: str) -> str:
    if status_margem == "VERDE":
        return "dentro da faixa objetivo"
    if status_margem == "AMARELO":
        return "próxima ao limite mínimo"
    if status_margem == "VERMELHO":
        return "abaixo do mínimo aceitável"
    return ""


def _exec_summary_parag2(resultado: dict[str, Any]) -> str | None:
    """Financial overview paragraph; returns None when there's no sales price."""
    preco_venda = float(resultado.get("preco_venda_total") or 0)
    if preco_venda <= 0:
        return None
    custo_direto = float(resultado.get("custo_direto") or 0)
    custo_indireto = float(resultado.get("custo_indireto") or 0)
    resultado_bruto = float(resultado.get("resultado_bruto") or 0)
    margem_pct = float(resultado.get("margem_pct") or 0)
    status_margem = str(resultado.get("status_margem") or "")

    margem_label = _exec_summary_margem_label(status_margem)
    parag2 = (
        f"O preço de venda totaliza **{_brl(preco_venda)}**, "
        f"composto por custo direto de {_brl(custo_direto)} e custo indireto de {_brl(custo_indireto)}. "
        f"O resultado bruto apurado é de **{_brl(resultado_bruto)}**, "
        f"correspondendo a uma margem de **{_pct(margem_pct)}**"
    )
    if margem_label:
        parag2 += f", {margem_label}"
    return parag2 + "."


def _exec_summary_parag3(resultado: dict[str, Any]) -> str | None:
    """Cost structure observation paragraph; returns None when not applicable."""
    custo_total = float(resultado.get("custo_total") or 0)
    custo_direto = float(resultado.get("custo_direto") or 0)
    if custo_direto <= 0 or custo_total <= 0:
        return None
    custo_indireto = float(resultado.get("custo_indireto") or 0)
    razao_ind = float(resultado.get("razao_indireto_direto") or 0)

    pct_direto = custo_direto / custo_total * 100
    pct_ind = custo_indireto / custo_total * 100
    parag3 = (
        f"O custo direto representa {_pct(pct_direto)} do custo total, "
        f"enquanto os custos indiretos correspondem a {_pct(pct_ind)}"
    )
    if razao_ind > 0:
        parag3 += f" (razão indireto/direto de {razao_ind:.2f})"
    return parag3 + "."


def render_executive_summary(resumo: dict[str, Any], resultado: dict[str, Any]) -> list[str]:
    """Generates a brief executive prose summary from the relatorio structured data."""
    if not isinstance(resumo, dict) or not isinstance(resultado, dict):
        return []

    # Compose contextual paragraphs
    lines: list[str] = ["## Sumário Executivo", ""]

    lines.append(_exec_summary_parag1(resumo))
    lines.append("")

    parag2 = _exec_summary_parag2(resultado)
    if parag2 is not None:
        lines.append(parag2)
        lines.append("")

    parag3 = _exec_summary_parag3(resultado)
    if parag3 is not None:
        lines.append(parag3)
        lines.append("")

    lines += ["---", ""]
    return lines


def render_header(meta: dict[str, Any], resumo: dict[str, Any]) -> list[str]:
    nome = resumo.get("projeto") or meta.get("framework", "Projeto")
    gerado = str(meta.get("gerado_em", ""))[:19].replace("T", " ")
    return [
        f"# Relatório Técnico-Financeiro -- {nome}",
        "",
        f"**Gerado em:** {gerado}  ",
        f"**Framework:** {meta.get('framework', '')}  ",
        "",
        "---",
        "",
    ]


def render_resultado(resultado: dict[str, Any]) -> list[str]:
    if not isinstance(resultado, dict) or not resultado:
        return []
    lines = [
        "## Dimensionamento Financeiro",
        "",
        "| Indicador | Valor |",
        "|-----------|-------|",
        f"| Preço de venda (c/ BDI) | {_brl(resultado.get('preco_venda_total', 0))} |",
        f"| Custo direto | {_brl(resultado.get('custo_direto', 0))} |",
        f"| Custo indireto | {_brl(resultado.get('custo_indireto', 0))} |",
        f"| **Custo total** | **{_brl(resultado.get('custo_total', 0))}** |",
        f"| **Resultado bruto** | **{_brl(resultado.get('resultado_bruto', 0))}** |",
        "",
        "---",
        "",
    ]
    return lines


def render_planejamento_table(plan: list[dict[str, Any]]) -> list[str]:
    if not isinstance(plan, list) or not plan:
        return []
    lines = [
        "## Quantitativos e Composição de Custos",
        "",
        "| Item | Descricao | c/BDI (R$) |",
        "|------|-----------|-----------:|",
    ]
    for item in plan:
        item_id = item.get("item_id", "-")
        desc = str(item.get("descricao") or "")[:72]
        total = _brl(item.get("subtotal_com_bdi", 0))
        lines.append(f"| {item_id} | {desc} | {total} |")
    lines += ["", "---", ""]
    return lines


def _cronograma_resumo_exec(
    makespan_base: int, makespan_otimo: int, delta_max: int, poupanca_max: float, n_viaveis: int, c_semana: float
) -> list[str]:
    """Resumo executivo da análise de compressão de cronograma."""
    if delta_max > 0:
        return [
            f"**Potencial identificado:** {makespan_base}w → **{makespan_otimo}w** "
            f"({delta_max}w de compressao, poupanca de **{_brl(poupanca_max)}**) "
            f"com {n_viaveis} atividade(s) candidata(s).",
            "",
            f"Custo semanal de referencia: {_brl(c_semana)}/semana.",
            "",
        ]
    return [
        "Nenhuma atividade apresenta compressao de makespan via k-scaling com os recursos atuais.",
        "O schedule e limitado pelas precedencias — aumento de pool nao reduz o prazo.",
        "",
    ]


_CRONOGRAMA_CLS_ICON = {
    "PC": "CP",
    "RC": "RC",
    "GW": "Gateway",
    "Bloqueada": "Bloqueada",
    "Livre": "Livre",
}


def _cronograma_mksp_str(k_ot: Any, delta: int, makespan_base: int) -> str:
    return str(makespan_base - delta) if (k_ot and delta > 0) else "—"


def _cronograma_roi_str(k_ot: Any, roi: Any) -> str:
    if roi is not None:
        return f"{roi:.0f}x"
    return "—" if not k_ot else "inf"


def _cronograma_decisao_str(k_ot: Any, roi: Any) -> str:
    if k_ot and roi and roi > 1:
        return f"**k={k_ot}** compensa"
    return "avaliar" if k_ot else "—"


def _cronograma_item_row(item: Any, makespan_base: int) -> str:
    """Formata uma linha da tabela principal de compressão de cronograma."""
    aid = str(item.get("activity_id") or "")
    tipo = str(item.get("tipo_recurso") or "")
    d = int(item.get("duration_base") or 0)
    tf = float(item.get("float_rcpsp") or 0)
    cls = str(item.get("criticality_class") or "")
    k_ot = item.get("k_otimo")
    gamma = item.get("gamma_otimo")
    delta = int(item.get("delta_makespan") or 0)
    roi = item.get("roi")

    k_str = str(k_ot) if k_ot else "—"
    mksp_str = _cronograma_mksp_str(k_ot, delta, makespan_base)
    g_str = f"{gamma:.2f}" if gamma is not None else "—"
    roi_str = _cronograma_roi_str(k_ot, roi)
    dec = _cronograma_decisao_str(k_ot, roi)
    cls_str = _CRONOGRAMA_CLS_ICON.get(cls, cls)

    return f"| {aid} | {tipo} | {d} | {tf:.0f} | {cls_str} | {k_str} | {mksp_str} | {g_str} | {roi_str} | {dec} |"


def _cronograma_tabela_principal(itens: list[Any], makespan_base: int) -> list[str]:
    lines = [
        "| Atividade | Recurso | d (sem) | Float RCPSP | Classe | k* | Mksp(k*) | gamma | ROI | Decisao |",
        "|-----------|---------|:-------:|:-----------:|:------:|:--:|:--------:|:-----:|:---:|---------|",
    ]
    for item in itens:
        lines.append(_cronograma_item_row(item, makespan_base))
    lines += [""]
    return lines


def _cronograma_detalhe_item(item: Any) -> list[str]:
    """Bloco de detalhamento de uma atividade candidata viável."""
    aid = item.get("activity_id", "")
    tipo = item.get("tipo_recurso", "")
    n = int(item.get("n_base") or 1)
    k_ot = int(item.get("k_otimo"))
    delta = int(item.get("delta_makespan") or 0)
    poup = float(item.get("poupanca") or 0)
    roi = float(item.get("roi") or 0)
    gamma = float(item.get("gamma_otimo") or 0)

    return [
        f"**{aid}** — `{tipo}` (base: {n} unidade(s))",
        f"- Recomendacao: aumentar para **{n * k_ot} unidades** (k={k_ot})",
        f"- Duracao: {item.get('duration_base')}w → {item.get('duration_base') // k_ot}w",
        f"- Reducao de makespan: **{delta} semana(s)** | gamma={gamma:.2f}",
        f"- Poupanca: **{_brl(poup)}** | ROI: **{roi:.1f}x**",
        "",
    ]


def _cronograma_detalhamento_viaveis(itens: list[Any]) -> list[str]:
    """Seção de detalhamento das atividades viáveis (roi > 1)."""
    viáveis = [i for i in itens if i.get("k_otimo") and i.get("roi") and float(i.get("roi") or 0) > 1]
    if not viáveis:
        return []
    lines = ["### Detalhamento das Atividades Candidatas à Compressão", ""]
    for item in viáveis:
        lines += _cronograma_detalhe_item(item)
    return lines


def render_compressao_cronograma(compressao: dict | None) -> list[str]:
    """NEP-038 — Seção de oportunidades de compressão de cronograma por k-scaling.

    Exibe a tabela de atividades com γ, ROI e recomendação de k ótimo.
    Retorna lista vazia quando não há análise ou nenhuma atividade viável.
    """
    if not isinstance(compressao, dict):
        return []

    itens = compressao.get("itens") or []
    if not itens:
        return []

    makespan_base = int(compressao.get("makespan_base") or 0)
    makespan_otimo = int(compressao.get("makespan_otimo") or makespan_base)
    delta_max = int(compressao.get("delta_makespan_max") or 0)
    poupanca_max = float(compressao.get("poupanca_total_max") or 0)
    n_viaveis = int(compressao.get("n_viáveis") or 0)
    c_semana = float(compressao.get("custo_semana") or 0)

    lines: list[str] = [
        "## Oportunidades de Aceleração do Cronograma (k-scaling)",
        "",
        "> NEP-038 — k-scaling de equipes: dobrar os recursos de uma atividade reduz"
        " sua duracao produtiva pela metade sem alterar o custo direto (invariante"
        " `custo_direto = k * c * (d/k) = c*d`). O beneficio vem da reducao do"
        " overhead semanal do projeto (`gamma * delta_d * C_semana`).",
        "",
    ]

    lines += _cronograma_resumo_exec(makespan_base, makespan_otimo, delta_max, poupanca_max, n_viaveis, c_semana)
    lines += _cronograma_tabela_principal(itens, makespan_base)
    lines += _cronograma_detalhamento_viaveis(itens)

    lines += ["---", ""]
    return lines


def _opp_get(obj: object, key: str, default: Any = None) -> Any:
    """Acesso uniforme a campo de oportunidade (aceita dict ou objeto Pydantic)."""
    if isinstance(obj, dict):
        # cast: isinstance(x, dict) sobre object vira dict[Unknown, Unknown] no ty,
        # que não unifica a chave str com _KT — limitação conhecida do checker.
        return cast("dict[str, Any]", obj).get(key, default)
    return getattr(obj, key, default)


def _oportunidades_gap_max_section(gap_max_dict: dict[str, Any]) -> list[str]:
    if not gap_max_dict:
        return []
    lines = [
        "### gap_r^max por Tipo de Recurso",
        "",
        "| Tipo | gap_max (sem.) | Interpretação |",
        "|------|:--------------:|---------------|",
    ]
    for tipo, gmax in sorted(gap_max_dict.items()):
        interp = "∞ — sem custo idle" if gmax >= 9999 else f"Perpetuar ≤ {gmax}w é viável"
        lines.append(f"| {tipo} | {gmax if gmax < 9999 else '∞'} | {interp} |")
    lines += [""]
    return lines


def _oportunidades_viavel_str(o: object, gap_max: Any) -> str:
    viavel = _opp_get(o, "economicamente_viavel", True)
    return "✅" if viavel else f"❌ >{gap_max}w"


def _oportunidades_par_row(o: object) -> str:
    """Formata a linha da tabela de uma oportunidade de compartilhamento par a par."""
    ai = _opp_get(o, "atividade_i", "?") or "?"
    aj = _opp_get(o, "atividade_j", "?") or "?"
    tipo = _opp_get(o, "tipo_id", "?") or "?"
    gap = _opp_get(o, "gap_semanas", 0) or 0
    gap_max = _opp_get(o, "gap_max_semanas", 9999) or 9999
    eta = _opp_get(o, "eta", 0.0) or 0.0
    omega = _opp_get(o, "omega_bundle", 0.0) or 0.0
    delta = _opp_get(o, "delta_c_pot", 0.0) or 0.0
    l0 = _opp_get(o, "lambda0", 0.0) or 0.0
    viavel_str = _oportunidades_viavel_str(o, gap_max)
    return f"| {ai} | {aj} | {tipo} | {gap}w | {eta:.3f} | {omega:.2f} | {_brl(delta)} | {_brl(l0)} | {viavel_str} |"


def _oportunidades_pares_section(
    relatorio: object, total: int, podadas: int, total_econ: float, lambda0_total: float
) -> list[str]:
    lines = [
        "### Oportunidades de Compartilhamento por Par de Atividades",
        "",
        f"Total: **{total}** oportunidades avaliadas · "
        f"**{total - podadas}** viáveis · **{podadas}** podadas · "
        f"Economia pot.: **{_brl(total_econ)}** · λ_0 total: **{_brl(lambda0_total)}**",
        "",
        "| Atividade i | Atividade j | Tipo | Gap | η | Ω | ΔC Potencial (R$) | λ_0 (R$) | Viável? |",
        "|-------------|-------------|------|:---:|:-:|:-:|------------------:|---------:|:-------:|",
    ]

    opps = _opp_get(relatorio, "oportunidades", []) or []
    for o in opps if isinstance(opps, list) else []:
        lines.append(_oportunidades_par_row(o))

    return lines


def render_oportunidades(relatorio: object | None) -> list[str]:
    """ADR-078 — Seção do grafo de oportunidades de compartilhamento de recursos.

    Aceita um ``RelatorioOportunidades`` (Pydantic) ou o dict equivalente.
    Retorna lista vazia quando não há relatório ou nenhuma oportunidade.
    """
    if relatorio is None:
        return []

    total = _opp_get(relatorio, "total_oportunidades", 0) or 0
    if total == 0:
        return []

    total_econ = _opp_get(relatorio, "total_economia_pot", 0.0) or 0.0
    podadas = _opp_get(relatorio, "oportunidades_podadas", 0) or 0
    lambda0_total = _opp_get(relatorio, "lambda0_total", 0.0) or 0.0
    gap_max_dict = _opp_get(relatorio, "gap_max_por_tipo", {}) or {}

    lines: list[str] = [
        "## Oportunidades de Compartilhamento de Recursos",
        "",
        "> ADR-078 — Pré-processamento estrutural: pares de atividades com potencial de"
        " economia via perpetuação de recursos. `η` = eficiência (desconta custo idle);"
        " `Ω` = sobreposição do bundle; `ΔC pot` = economia potencial; `λ_0` = penalidade"
        " inicial para Scheduling Modo B.",
        "",
    ]

    lines += _oportunidades_gap_max_section(gap_max_dict)
    lines += _oportunidades_pares_section(relatorio, total, podadas, total_econ, lambda0_total)

    lines += ["", "---", ""]
    return lines


def _pool_economia_causa_by_item(causa_proj: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Mapa atividade_id -> componentes de causa de custo (produtivo/ocioso/mob-demob)."""
    causa_by_item: dict[str, dict[str, float]] = {}
    for row in causa_proj.get("rows") or []:
        item = str(row.get("atividade_id", "") or "")
        if not item:
            continue
        causa_by_item[item] = {
            "produtivo_compartilhado": float(row.get("produtivo_compartilhado", 0.0) or 0.0),
            "ocioso_imputado": float(row.get("ocioso_imputado", 0.0) or 0.0),
            "mob_demob_imputado": float(row.get("mob_demob_imputado", 0.0) or 0.0),
        }
    return causa_by_item


def _pool_economia_top_pos_row(row: dict[str, Any], causa_by_item: dict[str, dict[str, float]]) -> str:
    item = str(row.get("atividade_id", "") or "-")
    eco = float(row.get("economia", 0.0) or 0.0)
    eco_pct = float(row.get("economia_pct", 0.0) or 0.0)
    causa = causa_by_item.get(item, {})
    part = float(causa.get("produtivo_compartilhado", 0.0) or 0.0)
    oc = float(causa.get("ocioso_imputado", 0.0) or 0.0)
    md = float(causa.get("mob_demob_imputado", 0.0) or 0.0)
    leitura = f"compartilhado={_brl(part)}, ocioso={_brl(oc)}, mob/demob={_brl(md)}"
    return f"| {item} | {_brl(eco)} | {eco_pct:.1f}% | {leitura} |"


def _pool_economia_top_pos_section(
    top_pos: list[dict[str, Any]], causa_by_item: dict[str, dict[str, float]]
) -> list[str]:
    if not top_pos:
        return []
    lines = [
        "### Principais Economias de Pool",
        "",
        "| Atividade | Economia (R$) | Economia (%) | Leitura causal |",
        "|-----------|--------------:|-------------:|----------------|",
    ]
    for row in top_pos:
        lines.append(_pool_economia_top_pos_row(row, causa_by_item))
    lines += [""]
    return lines


def _pool_economia_top_neg_row(row: dict[str, Any], causa_by_item: dict[str, dict[str, float]]) -> str:
    item = str(row.get("atividade_id", "") or "-")
    eco = float(row.get("economia", 0.0) or 0.0)
    causa = causa_by_item.get(item, {})
    oc = float(causa.get("ocioso_imputado", 0.0) or 0.0)
    md = float(causa.get("mob_demob_imputado", 0.0) or 0.0)
    if oc >= md:
        motivo = f"ocioso imputado ({_brl(oc)})"
    else:
        motivo = f"mobilização/desmobilização ({_brl(md)})"
    return f"| {item} | {_brl(eco)} | {motivo} |"


def _pool_economia_top_neg_section(
    top_neg: list[dict[str, Any]], causa_by_item: dict[str, dict[str, float]]
) -> list[str]:
    if not top_neg:
        return []
    lines = [
        "### Atividades com Sobrecusto de Pool (Ociosidade)",
        "",
        "| Atividade | Economia (R$) | Motivo dominante |",
        "|-----------|--------------:|------------------|",
    ]
    for row in top_neg:
        lines.append(_pool_economia_top_neg_row(row, causa_by_item))
    lines += [""]
    return lines


def _pool_economia_resolve_projections(canonical: object) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Resolve as projeções economia_pool e causa_custo; retorna None em caso de erro."""
    try:
        from concilium.application.services.analytics.cubo_pool_projection import resolve_cubo_pool_projection

        eco_proj = resolve_cubo_pool_projection(canonical, face="economia_pool", top_n=300)
        causa_proj = resolve_cubo_pool_projection(canonical, face="causa_custo", top_n=300)
    except Exception:
        return None
    return eco_proj, causa_proj


def _pool_economia_top_pos(eco_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        r
        for r in sorted(eco_rows, key=lambda x: -float(x.get("economia", 0.0) or 0.0))
        if float(r.get("economia", 0.0) or 0.0) > 0
    ][:5]


def _pool_economia_top_neg(eco_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        r
        for r in sorted(eco_rows, key=lambda x: float(x.get("economia", 0.0) or 0.0))
        if float(r.get("economia", 0.0) or 0.0) < 0
    ][:3]


def _pool_economia_header_lines(eco_proj: dict[str, Any]) -> list[str]:
    meta = eco_proj.get("operator_meta") or {}
    tot_aut = float(meta.get("custo_autonomo_total", 0.0) or 0.0)
    tot_inst = float(meta.get("custo_instancial_total", 0.0) or 0.0)
    tot_eco = float(meta.get("economia_total", 0.0) or 0.0)
    return [
        "## Economia por Compartilhamento de Frente",
        "",
        f"Baseline homogênea (planejamento sem BDI): **{_brl(tot_aut)}** | Instancial (pool): **{_brl(tot_inst)}** | "
        f"Economia líquida: **{_brl(tot_eco)}**.",
        "",
    ]


def render_pool_economia_origem(canonical: object | None) -> list[str]:
    """Resumo textual da origem da economia do pool por atividade."""
    if canonical is None:
        return []
    projections = _pool_economia_resolve_projections(canonical)
    if projections is None:
        return []
    eco_proj, causa_proj = projections

    eco_rows = [r for r in (eco_proj.get("rows") or []) if float(r.get("custo_autonomo", 0.0) or 0.0) > 0.0]
    if not eco_rows:
        return []

    causa_by_item = _pool_economia_causa_by_item(causa_proj)
    top_pos = _pool_economia_top_pos(eco_rows)
    top_neg = _pool_economia_top_neg(eco_rows)

    lines: list[str] = _pool_economia_header_lines(eco_proj)
    lines += _pool_economia_top_pos_section(top_pos, causa_by_item)
    lines += _pool_economia_top_neg_section(top_neg, causa_by_item)

    lines += ["---", ""]
    return lines
