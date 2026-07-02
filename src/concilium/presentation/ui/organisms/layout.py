"""Main UI layouts and tabs for Streamlit application."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from concilium.domain.models.analytics.diagnostico_pe import DiagnosticoPERelatorio
    from concilium.domain.models.financial.backtracking_pe import BacktrackingPERelatorio

from ..helpers.helpers import (
    build_team_adjustment_rows,
    collect_skill_candidates,
    extract_all_skill_inputs,
    extract_bdi_dict,
    extract_eap_items_for_policy,
    extract_skill_base_inputs,
    safe_count_eap,
    set_path,
)
from ..infra.api import api_call, fetch_artifact_bytes
from ..molecules.common import render_info_row, render_kpi_cards, render_paginated_table
from ..molecules.components import (
    render_download_button,
    render_mapping_table,
    render_numeric_override_editor,
)


def _to_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None


def _format_currency(value: object) -> str:
    parsed = _to_float(value)
    if parsed is None:
        return "-"
    abs_value = abs(parsed)
    if abs_value >= 1_000_000_000:
        return f"R$ {parsed / 1_000_000_000:,.2f} bi"
    if abs_value >= 1_000_000:
        return f"R$ {parsed / 1_000_000:,.2f} mi"
    return f"R$ {parsed:,.2f}"


def _format_percent(value: object) -> str:
    parsed = _to_float(value)
    if parsed is None:
        return "-"
    return f"{parsed * 100:,.2f}%"


def _format_int(value: object) -> str:
    parsed = _to_float(value)
    if parsed is None:
        return "-"
    return f"{int(round(parsed)):,}"


def _emoji_status(gap_rs: float) -> str:
    if gap_rs >= 0:
        return "✅"
    if gap_rs >= -5000:
        return "⚠️"
    return "🔴"


def _render_cube_projection_chart(face: str, chart_hint: str, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    try:
        import pandas as pd
    except Exception:
        st.caption("Pandas indisponível no ambiente; exibindo somente tabela.")
        return

    df = pd.DataFrame(rows)
    if df.empty:
        return

    if chart_hint == "line":
        if face == "s_curve_custo" and {"periodo", "custo_acumulado_rs"}.issubset(df.columns):
            series = df.set_index("periodo")["custo_acumulado_rs"]
            st.line_chart(series)
            return
        if face == "recursos_ativos_tempo" and {"periodo", "n_equipes_totais", "equipamentos_unidades_ativas"}.issubset(
            df.columns
        ):
            multi = df.set_index("periodo")[["n_equipes_totais", "equipamentos_unidades_ativas"]]
            st.line_chart(multi)
            return
        if face == "diesel_temporal" and {"periodo", "consumo_diesel_l"}.issubset(df.columns):
            series = df.groupby("periodo", as_index=True)["consumo_diesel_l"].sum()
            st.line_chart(series)
            return
        if {"periodo", "componente_bdi", "valor_rs"}.issubset(df.columns):
            pivot = df.pivot_table(
                index="periodo",
                columns="componente_bdi",
                values="valor_rs",
                aggfunc="sum",
                fill_value=0,
            ).sort_index()
            st.line_chart(pivot)
            return

    if chart_hint == "bar_stacked" and {"periodo", "natureza", "valor_rs"}.issubset(df.columns):
        pivot = df.pivot_table(
            index="periodo",
            columns="natureza",
            values="valor_rs",
            aggfunc="sum",
            fill_value=0,
        ).sort_index()
        st.bar_chart(pivot)
        return

    if chart_hint == "bar" and {"insumo_id", "custo_total_rs"}.issubset(df.columns):
        series = df.set_index("insumo_id")["custo_total_rs"]
        st.bar_chart(series)
        return

    if chart_hint == "heatmap":
        try:
            import altair as alt
        except Exception:
            st.caption("Altair indisponível no ambiente; exibindo somente tabela.")
            return

        if {"categoria", "componente_bdi", "valor_rs"}.issubset(df.columns):
            heatmap = (
                alt.Chart(df)
                .mark_rect()
                .encode(
                    x=alt.X("componente_bdi:N", title="Componente BDI"),
                    y=alt.Y("categoria:N", title="Categoria"),
                    color=alt.Color("valor_rs:Q", title="Valor (R$)"),
                    tooltip=["categoria", "componente_bdi", alt.Tooltip("valor_rs:Q", format=",.2f")],
                )
            )
            st.altair_chart(heatmap, use_container_width=True)
            return

        if {"atividade_id", "componente_bdi", "valor_rs"}.issubset(df.columns):
            heatmap = (
                alt.Chart(df)
                .mark_rect()
                .encode(
                    x=alt.X("componente_bdi:N", title="Componente BDI"),
                    y=alt.Y("atividade_id:N", title="Atividade"),
                    color=alt.Color("valor_rs:Q", title="Valor (R$)"),
                    tooltip=["atividade_id", "componente_bdi", alt.Tooltip("valor_rs:Q", format=",.2f")],
                )
            )
            st.altair_chart(heatmap, use_container_width=True)
            return


def render_diagnostico_pe(
    base_url: str,
    project_id: str,
    actor: str,
    diagnostico: DiagnosticoPERelatorio | None = None,  # type: ignore[name-defined]
) -> None:
    """Painel de equilíbrio financeiro em linguagem simples (ADR-060)."""
    if diagnostico is None:
        return
    if diagnostico.n_itens_deficit == 0:
        st.success("✅ Todas as atividades estão no equilíbrio financeiro.", icon=None)
        return
    with st.expander(
        f"⚠️ {diagnostico.n_itens_deficit} atividade(s) com custo acima do orçamento — "
        f"custo extra: R$ {abs(diagnostico.gap_total_rs):,.0f}",
        expanded=True,
    ):
        st.markdown("**Por que está custando mais?**")
        causas = diagnostico.resumo_causas
        total_causas = sum(causas.values()) or 1
        for label, valor in causas.items():
            pct = round(valor / total_causas * 100)
            barra = "█" * max(1, pct // 5) + "░" * (20 - max(1, pct // 5))
            st.markdown(f"`{barra}` **{label}** — R$ {valor:,.0f} ({pct}%)")
        if diagnostico.gap_evitavel_rs > 50:
            st.info(
                f"R$ {diagnostico.gap_evitavel_rs:,.0f} deste custo pode ser evitado"
                " com ajustes de cronograma ou mobilização.",
                icon=None,
            )
        if diagnostico.aviso_cross_term:
            st.warning(
                "⚠️ Em pelo menos uma atividade, a mobilização coincidiu com o período de pior clima."
                " Esse custo duplo pode ser evitado mudando a época de início."
            )
        st.markdown("---")
        st.markdown("**Detalhes por atividade:**")
        for item in diagnostico.itens_deficit:
            _render_diagnostico_item(item)


def _render_diagnostico_item(item: object) -> None:
    """Renders one deficit item in the diagnostico expander."""
    from concilium.presentation.ui.atoms.misc import _emoji_status  # noqa: PLC0415 - local import for performance

    with st.expander(
        f"{_emoji_status(item.gap_rs)} {item.descricao[:60]} — custo extra: R$ {abs(item.gap_rs):,.0f}",  # type: ignore[union-attr]
        expanded=False,
    ):
        col1, col2, col3 = st.columns(3)
        col1.metric(
            "Aproveitamento de campo",
            f"{item.aproveitamento_pct:.0f}%",  # type: ignore[union-attr]
            help="Das horas em que a equipe esteve no canteiro, esta fração foi produtiva.",
        )
        col2.metric("Margem atual", f"{item.l_aplicado * 100:.1f}%")  # type: ignore[union-attr]
        col3.metric(
            "Margem mínima necessária",
            f"{item.l_requerido * 100:.1f}%",  # type: ignore[union-attr]
            delta=f"+{item.delta_l * 100:.1f}pp necessário",
            delta_color="inverse",
        )  # type: ignore[union-attr]
        st.caption("Causas identificadas:")
        for f in item.fatores:  # type: ignore[union-attr]
            evit = "✂️ evitável" if f.evitavel else "🔩 estrutural"
            st.markdown(f"- **{f.label}** — R$ {f.gap_rs:,.0f} ({f.pct_gap * 100:.0f}%) · {evit}")
            st.caption(f"  {f.descricao}")
        if not item.validez_aproximacao:  # type: ignore[union-attr]
            st.warning(
                "⚠️ A mobilização desta atividade coincidiu com o período de pior clima. "
                f"Isso criou um custo extra de R$ {abs(item.cov_n_p * item.n_total * 100):,.0f} "  # type: ignore[union-attr]
                "aproximado. Iniciar a mobilização na estação seca pode eliminar este custo.",
            )


def _render_sol_row(i: int, sol: object, cols: list) -> None:
    """Renders one solution row in a backtracking expander."""
    cols[0].markdown(f"**{chr(65 + i)}** — {sol.label}")  # type: ignore[union-attr]
    cols[0].caption(sol.descricao_delta)  # type: ignore[union-attr]
    repasse = f"+{sol.impacto_preco_pct:.1f}%" if sol.impacto_preco_pct > 0.1 else "Nenhum"  # type: ignore[union-attr]
    cols[1].metric("Repasse ao cliente", repasse)
    esforco = f"+{sol.impacto_produtividade_pct:.0f}%" if sol.impacto_produtividade_pct > 0.5 else "—"  # type: ignore[union-attr]
    cols[2].metric("Esforço operacional", esforco)
    if sol.impacto_prazo_semanas != 0:  # type: ignore[union-attr]
        direction = "−" if sol.impacto_prazo_semanas < 0 else "+"  # type: ignore[union-attr]
        cols[3].metric("Prazo", f"{direction}{abs(sol.impacto_prazo_semanas):.0f} sem.")  # type: ignore[union-attr]


def _render_backtrack_item_body(item: object) -> None:
    """Renders the body of one backtracking item expander."""
    validas = [s for s in item.solucoes if s.roundtrip_valido]  # type: ignore[union-attr]
    if not validas:
        st.info("Nenhuma solução foi confirmada automaticamente para esta atividade.")
        return
    st.caption(f"Gap atual: R$ {abs(item.pe_gap_atual):,.0f} | Alvo: equilíbrio (R$ 0)")  # type: ignore[union-attr]
    for i, sol in enumerate(validas):
        cols = st.columns([5, 2, 2, 2])
        _render_sol_row(i, sol, cols)
    if item.solucao_recomendada:  # type: ignore[union-attr]
        rec = item.solucao_recomendada  # type: ignore[union-attr]
        idx = validas.index(rec) if rec in validas else 0
        st.success(f"✨ Opção recomendada: **{chr(65 + idx)} — {rec.label}** ({rec.impacto_cliente_descricao})")


def render_backtracking_pe(
    backtracking: BacktrackingPERelatorio | None = None,  # type: ignore[name-defined]
    on_create_version: callable | None = None,  # type: ignore[valid-type]
) -> None:
    """Painel de soluções para fechar o gap de PE (ADR-061)."""
    if backtracking is None or not backtracking.itens:
        return
    aviso = backtracking.aviso_consistencia
    if aviso:
        st.caption(f"ℹ️ {aviso}")
    for item in backtracking.itens:
        if not item.solucoes:
            continue
        with st.expander(f"💡 Como equilibrar: {item.descricao[:55]}", expanded=False):
            _render_backtrack_item_body(item)


def _wizard_opcao_L(diagnostico: object, opcoes: list) -> None:
    """Appends the L (BDI margin) option if diagnostico is valid."""
    if diagnostico is None:
        return
    delta = diagnostico.l_medio_requerido - (  # type: ignore[union-attr]
        diagnostico.itens_deficit[0].l_aplicado if diagnostico.itens_deficit else 0.09  # type: ignore[union-attr]
    )
    gap_pct = 100 if diagnostico.gap_total_rs else 0  # type: ignore[union-attr]
    opcoes.append(
        (
            "L",
            "Ajustar a margem no orçamento (BDI)",
            f"Estimativa: fecha {gap_pct}% do gap — preço sobe ~{delta * 100:.1f}pp",
        )
    )


def _build_wizard_deficit_opcoes(diagnostico: object, backtracking: object) -> list[tuple[str, str, str]]:
    """Builds the wizard option tuples from backtracking data."""
    opcoes: list[tuple[str, str, str]] = []
    params_disponiveis: dict[str, list[str]] = {}
    bloco_explicacao = getattr(diagnostico, "explicacao_natureza_periodo", {}) if diagnostico else {}
    janelas_prioritarias = []
    if isinstance(bloco_explicacao, dict):
        raw_janelas = bloco_explicacao.get("janelas_prioritarias")
        if isinstance(raw_janelas, list):
            janelas_prioritarias = [j for j in raw_janelas if isinstance(j, dict)]

    for bt_item in backtracking.itens:  # type: ignore[union-attr]
        for sol in bt_item.solucoes:
            if sol.roundtrip_valido:
                params_disponiveis.setdefault(sol.parametro, []).append(bt_item.descricao[:40])
    if "L" in params_disponiveis:
        _wizard_opcao_L(diagnostico, opcoes)
    if "T0_RAMP" in params_disponiveis:
        timing_msg = "Estima eliminar custo de época desfavorável sem repasse ao cliente"
        if janelas_prioritarias:
            top = janelas_prioritarias[0]
            janela = top.get("janela_iso")
            natureza = top.get("natureza")
            if janela and natureza:
                timing_msg = f"Prioriza janela {janela} com causa dominante {natureza}"
        opcoes.append(
            (
                "T0_RAMP",
                "Mudar quando as atividades começam (cronograma)",
                timing_msg,
            )
        )
    if "P" in params_disponiveis:
        opcoes.append(
            ("P", "Melhorar produtividade dos equipamentos", "Requer calibração de CPU ou upgrade de equipamento")
        )
    if "N_MAX" in params_disponiveis:
        opcoes.append(("N_MAX", "Aumentar equipes em paralelo", "Comprime o prazo e reduz overhead fixo"))
    return opcoes


def render_version_wizard(
    base_url: str,
    project: dict,
    actor: str,
    diagnostico: DiagnosticoPERelatorio | None = None,  # type: ignore[name-defined]
    backtracking: BacktrackingPERelatorio | None = None,  # type: ignore[name-defined]
) -> str | None:
    """Wizard de criação de versão com foco no diagnóstico (ADR-060/061 UI).

    Retorna o foco selecionado ("L" | "P" | "N_MAX" | "T0_RAMP" | "LIVRE" | None).
    """
    project_id = project["project_id"]
    st.subheader("✚ Nova versão — O que você quer tentar?")

    tem_deficit = diagnostico and diagnostico.n_itens_deficit > 0
    opcoes: list[tuple[str, str, str]] = []
    if tem_deficit and backtracking and backtracking.itens:
        opcoes = _build_wizard_deficit_opcoes(diagnostico, backtracking)
    opcoes.append(("LIVRE", "Explorar livremente", "Abre o painel de planejamento sem foco específico"))

    labels = [f"{o[1]}\n  ↳ {o[2]}" for o in opcoes]
    escolha = st.radio("", labels, index=len(labels) - 1, key=f"wizard-{project_id}")
    idx = labels.index(escolha)
    foco = opcoes[idx][0]

    col1, col2 = st.columns([3, 1])
    if col2.button("Criar versão →", type="primary", key=f"wizard-create-{project_id}"):
        return foco
    return None


def _collect_last_run(base_url: str, project_id: str, actor: str) -> tuple[dict, dict]:
    """Returns (last_run, summary) from the runs API."""
    try:
        runs = api_call(method="GET", path=f"/api/projects/{project_id}/runs", base_url=base_url, actor=actor).get(
            "items", []
        )
    except Exception:
        runs = []
    last_run = runs[0] if runs else {}
    summary = last_run.get("summary") if isinstance(last_run.get("summary"), dict) else {}
    return last_run, summary


def _collect_override_summary(base_url: str, project_id: str, actor: str) -> list[str]:
    """Returns list of skill IDs with active overrides."""
    try:
        overrides = api_call(method="GET", path=f"/api/projects/{project_id}/overrides", base_url=base_url, actor=actor)
    except Exception:
        overrides = {}
    return [k for k, v in overrides.items() if isinstance(v, dict)] if isinstance(overrides, dict) else []


def _collect_artifact_outputs(base_url: str, project_id: str, current_v: str | None, actor: str) -> list:
    """Returns list of output artifact names for the current version."""
    try:
        artifacts = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/artifacts",
            params={"version": current_v} if current_v else None,
            base_url=base_url,
            actor=actor,
        )
        return list(artifacts.get("outputs") or [])
    except Exception:
        return []


def render_version_summary(base_url: str, project: dict, actor: str) -> None:
    """Resumo da versão atual com KPIs financeiros e operacionais."""
    st.subheader("📊 Resumo da versão")

    project_id = project["project_id"]
    last_run, summary = _collect_last_run(base_url, project_id, actor)
    col_last, col_status, col_dur, col_custo, col_margem, col_pe = st.columns(6)
    _ts_raw = last_run.get("started_at", "-")
    _ts_fmt = _ts_raw[:16].replace("T", " ") if _ts_raw and _ts_raw != "-" else "-"
    col_last.metric("Última execução", _ts_fmt)
    col_status.metric("Status", last_run.get("status", "-"))
    col_dur.metric("Versão da última run", last_run.get("version", "-"))
    col_custo.metric("Custo total", _format_currency(summary.get("custo_total")))  # type: ignore[union-attr]
    col_margem.metric("Margem prevista", _format_percent(summary.get("margem_pct")))  # type: ignore[union-attr]
    col_pe.metric("Ponto de Equilíbrio — itens em déficit", _format_int(summary.get("pe_deficit_items")))  # type: ignore[union-attr]
    col_pe.caption(f"Alertas de P.E.: {_format_int(summary.get('pe_alerta_items'))}")  # type: ignore[union-attr]
    if last_run:
        st.caption(
            "ℹ️ Valores financeiros baseados na última execução e não refletem"
            " o estado definitivo até a versão ser comitada."
        )  # noqa: E501
    override_skills = _collect_override_summary(base_url, project_id, actor)
    if override_skills:
        st.caption(f"Overrides ativos: {len(override_skills)} — skills: {', '.join(sorted(override_skills))}")
    outputs = _collect_artifact_outputs(base_url, project_id, project.get("current_version"), actor)
    col_hist1, col_hist2 = st.columns(2)
    col_hist1.metric("Outputs desta versão", len(outputs))
    _upd = str(project.get("updated_at") or "-")
    col_hist2.metric("Última modificação", _upd[:10] if len(_upd) > 10 else _upd)


def render_version_detail(base_url: str, project: dict, actor: str) -> None:
    """Render descriptive per-version detail panel — runs, KPIs e artefatos da versão selecionada."""
    import pandas as pd

    project_id = project["project_id"]
    versions = list(project.get("versions") or [])
    if not versions:
        st.info("Projeto sem versões registradas.")
        return

    current_v = project.get("current_version") or versions[0]
    selected = st.selectbox(
        "Versão",
        options=versions,
        index=versions.index(current_v) if current_v in versions else 0,
        key=f"detail-version-select-{project_id}",
    )

    st.markdown(f"#### Versão `{selected}`")

    try:
        runs = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/runs",
            base_url=base_url,
            actor=actor,
        ).get("items", [])
    except Exception:
        runs = []

    version_runs = [r for r in runs if r.get("version") == selected]

    if not version_runs:
        st.info(f"Nenhuma execução registrada para a versão **{selected}**.")
    else:
        last = version_runs[0]
        summary = last.get("summary") or {}
        col_status, col_ts, col_custo, col_margem, col_pe = st.columns(5)
        _ts = str(last.get("started_at") or "-")
        col_status.metric("Status", last.get("status", "-"))
        col_ts.metric("Última execução", _ts[:16].replace("T", " ") if len(_ts) > 10 else _ts)
        col_custo.metric("Custo total", _format_currency(summary.get("custo_total")))
        col_margem.metric("Margem prevista", _format_percent(summary.get("margem_pct")))
        col_pe.metric("Itens déficit P.E.", _format_int(summary.get("pe_deficit_items")))
        if summary.get("custo_total") is None and last.get("status") == "OK":
            st.caption(
                "ℹ️ Pipeline concluída sem dados financeiros — a skill de consolidação (resultado) "
                "pode não ter sido executada ou o canônico não atingiu o skill 13."
            )

        rows = [
            {
                "Run ID": str(r.get("run_id") or "-")[:12],
                "Status": r.get("status", "-"),
                "Início": str(r.get("started_at") or "-")[:16].replace("T", " "),
                "Fim": str(r.get("finished_at") or "-")[:16].replace("T", " "),
                "Fork de": r.get("base_version") or "-",
                "Custo": _format_currency((r.get("summary") or {}).get("custo_total")),
                "Margem": _format_percent((r.get("summary") or {}).get("margem_pct")),
            }
            for r in version_runs
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    try:
        artifacts = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/artifacts",
            params={"version": selected},
            base_url=base_url,
            actor=actor,
        )
        outputs = list(artifacts.get("outputs") or [])
        if outputs:
            st.caption(f"**Artefatos gerados ({len(outputs)}):** {', '.join(outputs)}")
        else:
            st.caption("Nenhum artefato gerado para esta versão.")
    except Exception:
        pass


def render_overview_tab(base_url: str, project: dict, actor: str) -> None:
    """Tab: Overview - Dashboard de métricas do projeto."""
    project_id = project["project_id"]

    try:
        reference = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/benchmark-reference",
            base_url=base_url,
            actor=actor,
        )
    except Exception:
        reference = {}

    from concilium.presentation.ui.templates._project_page_helpers_a import _render_context_section, _render_eap_section

    with st.expander("ℹ️ Resumo do Projeto", expanded=True):
        render_kpi_cards(
            [
                {"label": "Tipo", "value": str(project.get("tipo_projeto", "-")).upper()},
                {"label": "Contexto", "value": project.get("contexto_id", "-")},
                {"label": "Benchmark", "value": project.get("benchmark_slug", "-")},
            ]
        )
        render_info_row(
            [
                ("Projeto", str(project.get("nome") or "-")),
                ("ID", str(project_id)),
            ]
        )

        eap_count = safe_count_eap(reference)
        all_base_skills = extract_all_skill_inputs(reference)
        extra_count = len(all_base_skills)
        team_count = len(build_team_adjustment_rows(reference))

        render_kpi_cards(
            [
                {"label": "Itens de EAP", "value": eap_count},
                {"label": "Skills configuradas", "value": extra_count},
                {"label": "Atividades com equipes", "value": team_count},
            ]
        )

    with st.expander("📋 Atividades da EAP", expanded=False):
        _render_eap_section(reference, base_url, project_id, actor)

    with st.expander("🌐 Contexto e Perfil", expanded=False):
        _render_context_section(base_url, project, project_id, actor)


def render_cube_analytics_by_version(base_url: str, project: dict, actor: str) -> None:
    """Painel de cubo analítico com visualização explícita por versão de planejamento."""
    project_id = project["project_id"]
    st.subheader("🧭 Cubo analítico por versão")
    versions = project.get("versions") or []
    version_options = versions if versions else [project.get("current_version") or "v1"]
    selected_version = st.selectbox(
        "Versão de planejamento",
        options=version_options,
        key=f"cube-version-{project_id}",
    )
    st.caption("Exploração analítica vinculada à versão selecionada.")

    face_options = {
        "tempo_natureza": "Tempo × natureza (direto/indireto)",
        "tempo_componente": "Tempo × componente BDI",
        "categoria_componente": "Categoria × componente BDI",
        "atividade_componente": "Atividade × componente BDI",
        "diesel_temporal": "Diesel (litros) × tempo",
        "abc_curva": "Curva ABC por insumo (Pareto)",
        "s_curve_custo": "S-curve de custo acumulado",
        "recursos_ativos_tempo": "Recursos ativos no tempo",
    }
    granularidade_options = ["semana", "mes", "bimestre", "trimestre", "semestre", "ano"]
    contract_faces: dict[str, dict[str, object]] = {}
    try:
        contract = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/cubo-analitico/projecao/contrato",
            base_url=base_url,
            actor=actor,
        )
        raw_faces = contract.get("faces") if isinstance(contract, dict) else None
        if isinstance(raw_faces, dict):
            contract_faces = {k: v for k, v in raw_faces.items() if isinstance(v, dict)}
            face_options = {k: str(v.get("label") or face_options.get(k) or k) for k, v in contract_faces.items()}
        raw_gran = contract.get("granularidades") if isinstance(contract, dict) else None
        if isinstance(raw_gran, list) and raw_gran:
            granularidade_options = [str(g) for g in raw_gran]
    except Exception:
        contract_faces = {}

    categoria_options = ["", "mao_obra", "equipamento", "diesel", "material"]
    componente_options = [
        "",
        "custo_direto",
        "overhead_ac",
        "overhead_df",
        "overhead_r",
        "overhead_cr",
        "margem_l",
        "tributo_cofins",
        "tributo_iss",
        "tributo_pis",
        "tributo_cssl",
        "tributo_ir",
    ]

    # Granularidade só faz sentido em faces com eixo temporal.
    # Lê a seleção atual do session_state (padrão = primeira face) para decidir o
    # layout ANTES de renderizar o selectbox — padrão Streamlit para layouts dependentes.
    _face_key = f"cube-face-{project_id}"
    _face_options_keys = list(face_options.keys())
    _face_current = st.session_state.get(_face_key, _face_options_keys[0])

    face_granularity_support: dict[str, bool] = {
        "tempo_natureza": True,
        "tempo_componente": True,
        "categoria_componente": False,  # cross-tab estático: categoria × componente
        "atividade_componente": False,  # breakdown por atividade, sem eixo temporal
        "diesel_temporal": True,
        "abc_curva": False,  # pareto por insumo, sem tempo
        "s_curve_custo": True,
        "recursos_ativos_tempo": True,
    }
    _show_granularidade = face_granularity_support.get(_face_current, True)

    if _show_granularidade:
        f_col1, f_col2, f_col3 = st.columns([3, 2, 2])
        face_col, gran_col, topn_col = f_col1, f_col2, f_col3
    else:
        f_col1, f_col2 = st.columns([3, 2])
        face_col, topn_col = f_col1, f_col2
        gran_col = None

    face = face_col.selectbox(
        "Face",
        options=_face_options_keys,
        format_func=lambda x: face_options[x],
        key=_face_key,
    )
    granularidade = (
        gran_col.selectbox(
            "Granularidade",
            options=granularidade_options,
            index=1,
            key=f"cube-gran-{project_id}",
        )
        if gran_col is not None
        else granularidade_options[1]  # default "mes" quando oculto
    )
    top_n = int(
        topn_col.number_input(
            "Top N",
            min_value=20,
            max_value=2000,
            value=300,
            step=20,
            key=f"cube-topn-{project_id}",
        )
    )

    face_filter_support: dict[str, dict[str, bool]] = {
        "tempo_natureza": {"categoria": True, "componente": False, "atividade": False},
        "tempo_componente": {"categoria": False, "componente": True, "atividade": False},
        "categoria_componente": {"categoria": True, "componente": True, "atividade": False},
        "atividade_componente": {"categoria": False, "componente": True, "atividade": True},
        "diesel_temporal": {"categoria": False, "componente": False, "atividade": False},
        "abc_curva": {"categoria": True, "componente": False, "atividade": False},
        "s_curve_custo": {"categoria": False, "componente": True, "atividade": False},
        "recursos_ativos_tempo": {"categoria": True, "componente": False, "atividade": True},
    }
    active_filter_cfg = face_filter_support.get(face, {"categoria": True, "componente": True, "atividade": True})

    # Apenas os filtros relevantes à face selecionada ficam visíveis.
    # Calcula larguras proporcionais: categoria/componente = 2, atividade = 3.
    _filter_specs = [
        ("categoria", 2, "cat"),
        ("componente", 2, "comp"),
        ("atividade", 3, "act"),
    ]
    _active = [(dim, w, k) for dim, w, k in _filter_specs if active_filter_cfg.get(dim)]

    categoria = ""
    componente = ""
    atividade_id = ""

    if _active:
        _cols = st.columns([w for _, w, _ in _active])
        for col, (dim, _, _key_suffix) in zip(_cols, _active, strict=False):
            if dim == "categoria":
                categoria = col.selectbox("Categoria", options=categoria_options, key=f"cube-cat-{project_id}")
            elif dim == "componente":
                componente = col.selectbox("Componente BDI", options=componente_options, key=f"cube-comp-{project_id}")
            elif dim == "atividade":
                atividade_id = col.text_input(
                    "Atividade (item_id)",
                    value="",
                    placeholder="ex: eap-1_0",
                    key=f"cube-act-{project_id}",
                ).strip()

    current_face_spec = contract_faces.get(face) if isinstance(contract_faces.get(face), dict) else {}
    face_measure_options = current_face_spec.get("measure_profiles") if isinstance(current_face_spec, dict) else None
    face_agg_options = current_face_spec.get("aggregation_modes") if isinstance(current_face_spec, dict) else None

    with st.expander("Opcional", expanded=False):
        f3_col1, f3_col2, f3_col3 = st.columns([2, 2, 2])
        measure_options = [""] + [
            str(v) for v in (face_measure_options or ["financial_default", "abc_custo_direto", "recursos_ativos"])
        ]
        aggregation_options = [""] + [
            str(v) for v in (face_agg_options or ["sum", "count_distinct", "cumulative", "pareto"])
        ]
        measure_profile = f3_col1.selectbox(
            "Measure profile",
            options=measure_options,
            key=f"cube-measure-{project_id}",
        )
        aggregation_mode = f3_col2.selectbox(
            "Aggregation mode",
            options=aggregation_options,
            key=f"cube-agg-{project_id}",
        )

        abc_threshold_a = 0.80
        abc_threshold_b = 0.95
        if face == "abc_curva":
            abc_threshold_a = float(
                f3_col3.number_input(
                    "ABC threshold A",
                    min_value=0.50,
                    max_value=0.90,
                    value=0.80,
                    step=0.01,
                    key=f"cube-abc-a-{project_id}",
                )
            )
            abc_threshold_b = float(
                st.number_input(
                    "ABC threshold B",
                    min_value=0.85,
                    max_value=0.99,
                    value=0.95,
                    step=0.01,
                    key=f"cube-abc-b-{project_id}",
                )
            )
        else:
            f3_col3.caption("ABC thresholds aplicam-se apenas à face Curva ABC")

    categoria_param = categoria or None
    componente_param = componente or None
    if face == "diesel_temporal":
        categoria_param = "diesel"
        componente_param = "custo_direto"
        st.caption("Face diesel força filtros: categoria=diesel e componente=custo_direto.")

    params = {
        "version": selected_version,
        "face": face,
        "granularidade": granularidade,
        "categoria": categoria_param,
        "componente_bdi": componente_param,
        "atividade_id": atividade_id or None,
        "top_n": top_n,
        "measure_profile": measure_profile or None,
        "aggregation_mode": aggregation_mode or None,
        "abc_threshold_a": abc_threshold_a,
        "abc_threshold_b": abc_threshold_b,
    }
    params = {k: v for k, v in params.items() if v is not None and v != ""}
    try:
        projection = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/cubo-analitico/projecao",
            params=params,
            base_url=base_url,
            actor=actor,
        )
        totals = projection.get("totais") or {}
        rows = projection.get("rows") or []
        columns_meta = projection.get("columns") or []
        chart_hint = str(projection.get("chart_hint") or "")
        operator_meta = projection.get("operator_meta") or {}
        unit_type = str(projection.get("unit_type") or "")

        if face == "diesel_temporal":
            # Métricas de dimensionamento de tanque — consumo em VOLUME (litros)
            consumos = [float(r.get("consumo_diesel_l") or 0.0) for r in rows if isinstance(r, dict)]
            total_l = sum(consumos)
            pico_l = max(consumos) if consumos else 0.0
            media_l = total_l / len(consumos) if consumos else 0.0
            st.caption("⛽ **Volume de diesel** — use o pico para dimensionar tanques em sítio")
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Total consumo", f"{total_l:,.0f} L")
            d2.metric(f"Pico/{granularidade}", f"{pico_l:,.0f} L")
            d3.metric(f"Média/{granularidade}", f"{media_l:,.0f} L")
            # Sugestão de tanque: pico × fator de segurança (1.5 × ciclo de reabastecimento estimado em 2 períodos)
            tanque_sugerido = pico_l * 1.5 * 2
            d4.metric(
                "Tanque sugerido ×3",
                f"{tanque_sugerido:,.0f} L",
                help="Estimativa conservadora: pico × 1,5 (fator segurança) × 2 (ciclo de reabastecimento). "
                "Ajuste conforme frequência de entrega.",
            )
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Preço de venda", f"R$ {float(totals.get('total_preco_venda', 0.0)):,.0f}")
            c2.metric("Custo direto", f"R$ {float(totals.get('total_custo_direto', 0.0)):,.0f}")
            c3.metric("Tributos", f"R$ {float(totals.get('total_tributos', 0.0)):,.0f}")

        if rows:
            _render_cube_projection_chart(face, chart_hint, rows)

            if columns_meta:
                st.caption(
                    "Esquema: "
                    + ", ".join(
                        f"{str(col.get('id'))} ({str(col.get('dtype'))}, {str(col.get('role'))})"
                        for col in columns_meta
                        if isinstance(col, dict)
                    )
                )

            if operator_meta:
                st.caption(f"Operador: {operator_meta}")

            if unit_type:
                st.caption(f"Unidade semântica: {unit_type}")

            render_paginated_table(rows, page_key=f"cube-proj-page-{project_id}", page_size=20, label="cubo")
        else:
            st.info("Sem dados para a combinação de filtros selecionada.")
    except Exception as exc:
        st.warning(f"Falha ao consultar projeção do cubo analítico: {exc}")


def _render_md_with_mermaid(text: str) -> None:
    """Render Markdown com suporte a diagramas Mermaid via componente HTML."""
    import re

    import streamlit.components.v1 as components

    # Pin to a stable Mermaid 11.x that has xychart support without 10.9.6 bugs
    MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"

    # Separa blocos mermaid do resto do markdown
    pattern = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)
    parts = pattern.split(text)

    for i, part in enumerate(parts):
        if i % 2 == 0:
            # Texto/markdown normal
            if part.strip():
                st.markdown(part)
        else:
            # Bloco mermaid — renderiza via HTML
            diagram = part.strip()
            html = f"""
<div id="mermaid-{i}" class="mermaid" style="background:white">{diagram}</div>
<script>
  (function() {{
    function render() {{
      if (typeof mermaid !== 'undefined') {{
        mermaid.initialize({{startOnLoad: false, theme: 'default', securityLevel: 'loose'}});
        mermaid.run({{nodes: [document.getElementById('mermaid-{i}')]}});
      }}
    }}
    if (typeof mermaid === 'undefined') {{
      var s = document.createElement('script');
      s.src = '{MERMAID_JS}';
      s.onload = render;
      document.head.appendChild(s);
    }} else {{
      render();
    }}
  }})();
</script>
"""
            components.html(html, height=350, scrolling=True)


def _find_md_artifact(outputs: list) -> str | None:
    """Returns the best Markdown artifact name from outputs list."""
    md_candidates = [name for name in outputs if str(name).lower().endswith(".md")]
    preferred = next((name for name in md_candidates if str(name).lower() == "relatorio.md"), None)
    return preferred or (md_candidates[0] if md_candidates else None)


def render_markdown_report_preview(base_url: str, project_id: str, version: str | None, actor: str) -> None:
    """Render Markdown report preview."""
    st.subheader("Pré-visualização do relatório (Markdown)")
    st.caption(
        "⚠️ Gráficos e visualizações analíticas (Curva ABC, S-Curve, Cubo BDI, Campanha de Frota) "
        "estão disponíveis nas abas dedicadas do Excel (`resultado_planejamento.xlsx`). "
        "O relatório Markdown contém texto, tabelas e métricas financeiras."
    )
    try:
        artifacts = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/artifacts",
            base_url=base_url,
            params={"version": version} if version else None,
            actor=actor,
        )
    except Exception as exc:
        st.info(f"Não foi possível carregar lista de artefatos para prévia: {exc}")
        return

    outputs = list(artifacts.get("outputs") or [])
    md_file = _find_md_artifact(outputs)
    if not md_file:
        st.info("Nenhum arquivo Markdown encontrado nos outputs desta versão.")
        return

    try:
        payload = fetch_artifact_bytes(base_url, project_id, "outputs", md_file, version, actor)
        text = payload.decode("utf-8", errors="replace")
        st.caption(f"Arquivo exibido: {md_file}")
        _render_md_with_mermaid(text)
        with st.expander("Ver fonte do Markdown", expanded=False):
            st.code(text, language="markdown")
    except Exception as exc:
        st.warning(f"Falha ao renderizar prévia de {md_file}: {exc}")


def render_planning_tab(base_url: str, project: dict, actor: str, base_version: str | None) -> None:
    """Tab: Planejamento — política de mobilização de equipes."""
    project_id = project["project_id"]

    try:
        reference = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/benchmark-reference",
            base_url=base_url,
            actor=actor,
        )
    except Exception:
        reference = {}

    render_mobilizacao_policy_editor(base_url, project_id, actor, reference, base_version)


def render_bdi_tab(base_url: str, project: dict, actor: str) -> None:
    """Renderiza o editor de BDI isolado (para uso em expander próprio)."""
    project_id = project["project_id"]
    try:
        reference = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/benchmark-reference",
            base_url=base_url,
            actor=actor,
        )
    except Exception:
        reference = {}
    render_bdi_editor(base_url, project_id, actor, reference)


# ── Module-level constants for indirect cost editor ─────────────────────────
_INDIR_REGIMES = ["PJ", "CLT-mensalista", "CLT-horista"]
_INDIR_PERM_CATS = [
    ("ADM", "Administração central (ADM)"),
    ("TOP", "Topografia (TOP)"),
    ("LAB", "Laboratório (LAB)"),
    ("QSMS", "Qualidade, Segurança, Meio Ambiente e Saúde (QSMS)"),
]


def _verbas_from_dict(raw: dict) -> list[tuple[str, float]]:
    """Extracts verbas from a dict mapping name->value."""
    return [(k, float(v)) for k, v in raw.items() if not str(k).startswith("_") and isinstance(v, (int, float))]


def _verbas_from_list_items(raw: list) -> list[tuple[str, float]]:
    """Extracts verbas from a list of dicts or numbers."""
    result: list[tuple[str, float]] = []
    for item in raw:
        if isinstance(item, dict):
            result.append((item.get("descricao") or item.get("nome") or "—", float(item.get("valor_mensal") or 0)))
        elif isinstance(item, (int, float)):
            result.append(("—", float(item)))
    return result


def _indir_verbas_list(raw: object) -> list[tuple[str, float]]:
    """Normaliza verbas_mensais (dict ou list) para [(descricao, valor)]."""
    if isinstance(raw, dict):
        return _verbas_from_dict(raw)
    if isinstance(raw, list):
        return _verbas_from_list_items(raw)
    return []


def _indir_equips_list(raw: object) -> list[dict]:
    """Normaliza equipamentos (list ou dict) para list[dict]."""
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]
    if isinstance(raw, dict):
        return [
            {"tipo": k, **v} if isinstance(v, dict) else {"tipo": k, "aluguel_mensal": float(v or 0)}
            for k, v in raw.items()
            if not str(k).startswith("_")
        ]
    return []


def _render_indir_mo_section(
    mo_pessoas: list, encargos: dict, regimes: list, project_id: str, cat_id: str
) -> tuple[float, list[dict]]:
    """Renders MO table for one indirect category. Returns (total_mo, itens_mo)."""
    import pandas as pd

    total_mo = 0.0
    itens_mo: list[dict] = []
    if not mo_pessoas:
        st.info(f"Sem dados de mão de obra para {cat_id}.")
        return total_mo, itens_mo
    df_rows = []
    for p in mo_pessoas:
        regime = p.get("tipo_contratacao", "PJ") if p.get("tipo_contratacao") in regimes else "PJ"
        enc = encargos.get(regime, 0.0)
        sal = float(p.get("salario_base", 0))
        qtd = int(p.get("quantidade", 1))
        c_unit = sal * (1 + enc)
        df_rows.append(
            {
                "Função": p.get("funcao", "—"),
                "Qtd": qtd,
                "Salário Base (R$)": sal,
                "Regime": regime,
                "Encargos": f"{enc * 100:.0f}%",
                "Custo Unit. (R$)": round(c_unit, 2),
                "Custo Mensal (R$)": round(c_unit * qtd, 2),
            }
        )
    edited_mo = st.data_editor(
        pd.DataFrame(df_rows),
        column_config={
            "Função": st.column_config.TextColumn(width="large"),
            "Qtd": st.column_config.NumberColumn(min_value=0, max_value=999, step=1, width="small"),
            "Salário Base (R$)": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
            "Regime": st.column_config.SelectboxColumn(options=regimes, width="medium"),
            "Encargos": st.column_config.TextColumn(disabled=True, width="small"),
            "Custo Unit. (R$)": st.column_config.NumberColumn(disabled=True, format="%.2f"),
            "Custo Mensal (R$)": st.column_config.NumberColumn(disabled=True, format="%.2f"),
        },
        hide_index=True,
        use_container_width=True,
        key=f"indir-mo-{project_id}-{cat_id}",
        num_rows="dynamic",
    )
    for _, row in edited_mo.iterrows():
        enc = encargos.get(str(row["Regime"]), 0.0)
        c_unit = float(row["Salário Base (R$)"]) * (1 + enc)
        c_mensal = c_unit * int(row["Qtd"])
        total_mo += c_mensal
        itens_mo.append(
            {
                "funcao": row["Função"],
                "quantidade": int(row["Qtd"]),
                "salario_base": float(row["Salário Base (R$)"]),
                "tipo_contratacao": str(row["Regime"]),
                "encargos_pct": enc,
                "custo_unitario": round(c_unit, 2),
                "custo_mensal": round(c_mensal, 2),
            }
        )
    return total_mo, itens_mo


def _build_eq_seed_list(equips: list) -> list[dict]:
    """Builds seed rows for the equipment data_editor."""
    return [
        {
            "Tipo": e.get("tipo") or e.get("descricao") or "",
            "Qtd": int(e.get("quantidade") or 1),
            "Aluguel Unit. (R$/mês)": float(
                e.get("aluguel_mensal") or e.get("valor_mensal") or e.get("custo_mensal") or 0
            ),
        }
        for e in equips
    ]


def _process_eq_edited_rows(edited_list: list) -> tuple[float, list[dict]]:
    """Processes edited equipment rows. Returns (total_eq, equips_out)."""
    total_eq = 0.0
    equips_out: list[dict] = []
    for row in edited_list:
        tipo = str(row.get("Tipo") or "").strip()
        if not tipo:
            continue
        aluguel_u = float(row.get("Aluguel Unit. (R$/mês)") or 0)
        qtd_e = int(row.get("Qtd") or 1)
        total_mes_e = aluguel_u * qtd_e
        total_eq += total_mes_e
        equips_out.append({"tipo": tipo, "quantidade": qtd_e, "aluguel_mensal": aluguel_u, "custo_mensal": total_mes_e})
    return total_eq, equips_out


def _render_indir_equips_section(equips: list, project_id: str, cat_id: str) -> tuple[float, list[dict]]:
    """Renders equipment table for one indirect category. Returns (total_eq, equips_out)."""
    st.caption("**Equipamentos**")
    edited_eq = st.data_editor(
        _build_eq_seed_list(equips),
        column_config={
            "Tipo": st.column_config.TextColumn(width="large"),
            "Qtd": st.column_config.NumberColumn(min_value=0, max_value=999, step=1, width="small"),
            "Aluguel Unit. (R$/mês)": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
        },
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        key=f"indir-eq-{project_id}-{cat_id}",
    )
    edited_list = (
        edited_eq
        if isinstance(edited_eq, list)
        else (edited_eq.to_dict("records") if hasattr(edited_eq, "to_dict") else [])
    )
    return _process_eq_edited_rows(edited_list)


def _render_indir_verbas_section(verbas: list, project_id: str, cat_id: str) -> tuple[float, list[dict]]:
    """Renders verbas table for one indirect category. Returns (total_verbas, verbas_out)."""
    st.caption("**Verbas mensais**")
    verbas_seed = [{"Descrição": n, "R$/mês": v} for n, v in verbas]
    edited_verbas = st.data_editor(
        verbas_seed,
        column_config={
            "Descrição": st.column_config.TextColumn(width="large"),
            "R$/mês": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
        },
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        key=f"indir-verbas-{project_id}-{cat_id}",
    )
    edited_list = (
        edited_verbas
        if isinstance(edited_verbas, list)
        else (edited_verbas.to_dict("records") if hasattr(edited_verbas, "to_dict") else [])
    )
    total_verbas = 0.0
    verbas_out: list[dict] = []
    for row in edited_list:
        desc = str(row.get("Descrição") or "").strip()
        val = float(row.get("R$/mês") or 0)
        if desc:
            total_verbas += val
            verbas_out.append({"descricao": desc, "valor_mensal": val})
    return total_verbas, verbas_out


def _render_indir_cat_equipe(
    cat_id: str, cat_label: str, equipes: dict, encargos: dict, regimes: list, project_id: str
) -> tuple[dict, float]:
    """Renders one indirect support category (ADM/TOP/LAB/QSMS). Returns (entry, total)."""
    eq = equipes.get(cat_id) or {}
    mo_pessoas = eq.get("mao_obra") or []
    equips = _indir_equips_list(eq.get("equipamentos"))
    verbas = _indir_verbas_list(eq.get("verbas_mensais"))
    with st.expander(cat_label, expanded=False):
        total_mo, itens_mo = _render_indir_mo_section(mo_pessoas, encargos, regimes, project_id, cat_id)
        total_eq, equips_out = _render_indir_equips_section(equips, project_id, cat_id)
        total_verbas, verbas_out = _render_indir_verbas_section(verbas, project_id, cat_id)
        total_cat = total_mo + total_eq + total_verbas
        st.metric(f"Total {cat_id}/mês", f"R$ {total_cat:,.0f}")
    entry: dict = {"categoria": cat_id, "driver": "permanencia", "custo_fixo_mensal": round(total_cat, 2)}
    if itens_mo:
        entry["mao_de_obra"] = {"nome": f"MO {cat_id}", "custo_fixo_mensal": round(total_mo, 2), "itens": itens_mo}
    if equips_out:
        entry["equipamentos"] = equips_out
    if verbas_out:
        entry["verbas_mensais"] = verbas_out
    return entry, total_cat


def _render_indir_mob_section(equipes: dict, ind_det: dict, project_id: str) -> dict:
    """Renders the MOB/DESMOB tab content. Returns the entry dict."""
    eq = equipes.get("MOB") or {}
    det = ind_det.get("MOB") or {}
    custo_mob_ref = float(eq.get("custo_total") or det.get("custo_fixo_total") or 0)
    st.caption("Informe os custos de transporte de equipamentos e baixadas de pessoal.")
    col_t, col_b = st.columns(2)
    with col_t:
        st.caption("Transporte de Equipamentos")
        n_veic = st.number_input(
            "Nº de carretas/bi-trens",
            min_value=0,
            step=1,
            value=int(custo_mob_ref / 15000 / 2) or 1,
            key=f"mob-veic-{project_id}",
        )
        custo_por_viagem = st.number_input(
            "Custo por viagem (R$)",
            min_value=0.0,
            step=1000.0,
            value=15000.0,
            format="%.2f",
            key=f"mob-viag-{project_id}",
        )
        n_viagens = st.number_input(
            "Viagens por veículo (ida + volta)", min_value=1, step=1, value=2, key=f"mob-nv-{project_id}"
        )
        custo_transporte = n_veic * custo_por_viagem * n_viagens
    with col_b:
        st.caption("Baixada de Pessoal")
        n_pessoas = st.number_input(
            "Nº de pessoas",
            min_value=0,
            step=1,
            value=int(custo_mob_ref * 0.3 / 2500) or 1,
            key=f"mob-pes-{project_id}",
        )
        custo_por_pessoa = st.number_input(
            "Custo por pessoa (R$)", min_value=0.0, step=100.0, value=2500.0, format="%.2f", key=f"mob-cpp-{project_id}"
        )
        custo_baixada = n_pessoas * custo_por_pessoa
    total_mob = custo_transporte + custo_baixada
    st.metric(
        "Total MOB/DESMOB", f"R$ {total_mob:,.2f}", delta=f"Ref: R$ {custo_mob_ref:,.2f}" if custo_mob_ref else None
    )
    return {"categoria": "MOB", "driver": "one_time", "custo_fixo_total": total_mob}


def _fill_indir_totals_placeholder(placeholder: object, totals_by_cat: dict) -> None:
    """Fills the totals bar at top of equipe tab."""
    if totals_by_cat:
        with placeholder.container():  # type: ignore[union-attr]
            cols_t = st.columns(len(totals_by_cat))
            for col_t, (cat_id_t, total_t) in zip(cols_t, totals_by_cat.items(), strict=False):
                col_t.metric(f"Total {cat_id_t}/mês", f"R$ {total_t:,.0f}")
            st.divider()
    else:
        placeholder.empty()  # type: ignore[union-attr]


def render_indiretos_config(base_url: str, project_id: str, actor: str) -> None:
    """Editor de custos indiretos — composição por categoria com regime trabalhista editável."""
    try:
        reference = api_call(
            method="GET", path=f"/api/projects/{project_id}/benchmark-reference", base_url=base_url, actor=actor
        )
    except Exception:
        reference = {}
    equipes = {str(e.get("categoria", "")).upper(): e for e in (reference.get("equipes_indiretas") or [])}
    ind_det = reference.get("indiretos_detalhamento") or {}
    if not equipes and not ind_det:
        equipes_fb, ind_det_fb = _hydrate_indiretos_from_overrides(base_url, project_id, actor)
        if equipes_fb or ind_det_fb:
            equipes = equipes_fb
            ind_det = ind_det_fb
            st.caption("Base de indiretos carregada de overrides salvos (skill 07).")
    _enc_raw = reference.get("encargos_sociais") or {}
    encargos: dict[str, float] = {
        "PJ": float(_enc_raw.get("pj", 0.0)),
        "CLT-mensalista": float(_enc_raw.get("clt_mensalista", 0.92)),
        "CLT-horista": float(_enc_raw.get("clt_horista", 0.80)),
    }
    if _enc_raw:
        st.caption(
            f"Encargos da jurisdição: PJ={encargos['PJ'] * 100:.0f}% | "
            f"CLT-mensalista={encargos['CLT-mensalista'] * 100:.0f}% | "
            f"CLT-horista={encargos['CLT-horista'] * 100:.0f}%"
        )
    tab_equipe, tab_mob = st.tabs(["👥 Equipe de Apoio", "🚛 Mobilização/desmobilização"])
    cats_config_edited: list[dict] = []
    with tab_equipe:
        st.caption(
            "Salário base: valor contratado. "
            "Custo unitário = salário × (1 + encargos). "
            "Custo mensal = custo unitário × quantidade."
        )
        _totals_placeholder = st.empty()
        totals_by_cat: dict[str, float] = {}
        for cat_id, cat_label in _INDIR_PERM_CATS:
            entry, total = _render_indir_cat_equipe(cat_id, cat_label, equipes, encargos, _INDIR_REGIMES, project_id)
            cats_config_edited.append(entry)
            totals_by_cat[cat_id] = total
        _fill_indir_totals_placeholder(_totals_placeholder, totals_by_cat)
    with tab_mob:
        mob_entry = _render_indir_mob_section(equipes, ind_det, project_id)
        cats_config_edited.append(mob_entry)
    st.divider()
    if st.button("Salvar custos indiretos", key=f"save-indir-{project_id}", use_container_width=True, type="primary"):
        try:
            api_call(
                method="POST",
                path=f"/api/projects/{project_id}/overrides",
                base_url=base_url,
                payload={"skill_id": "06-resultado-financeiro", "inputs": {"categorias_config": cats_config_edited}},
                actor=actor,
            )
            st.success("Salvo. Re-execute o pipeline para refletir as alterações.")
        except Exception as exc:
            st.error(f"Erro ao salvar: {exc}")


def render_run(
    base_url: str, project_id: str, actor: str, base_version: str | None, project: dict | None = None
) -> None:
    """Render pipeline run control."""
    st.subheader("▶️ Run / Re-run")

    # NEP-016: bloqueia pipeline se EAP está vazia ou ainda em rascunho
    status_eap = (project or {}).get("status_eap", "")
    if status_eap == "RASCUNHO":
        st.warning(
            "⚠️ **EAP em rascunho** — adicione ao menos uma atividade à EAP antes de iniciar o pipeline. "
            "Acesse **📋 Atividades da EAP** no painel de Overview para cadastrar os itens.",
            icon=None,
        )
        st.button("Iniciar pipeline", use_container_width=True, type="primary", disabled=True)
        return

    fork = st.checkbox("Criar nova versão (fork)", value=True)

    if st.button("Iniciar pipeline", use_container_width=True, type="primary"):
        payload = {  # type: ignore[var-annotated]
            "base_version": base_version or None,
            "fork_version": fork,
            "skill_inputs_override": {},
            "use_saved_overrides": True,
        }
        result = api_call(
            method="POST",
            path=f"/api/projects/{project_id}/runs/start",
            base_url=base_url,
            payload=payload,
            actor=actor,
        )
        st.session_state["selected_run_id"] = result.get("run_id")
        st.success(f"Run iniciado: {result.get('run_id')}")
        render_mapping_table("Run iniciado", result)


def render_version_management(base_url: str, project: dict, actor: str) -> None:
    """Render version management controls."""
    project_id = project["project_id"]
    st.subheader("🗑️ Excluir versão")
    st.warning(
        "Excluir versão remove seus artefatos/canônico daquela pasta. Runs que apontavam para ela permanecem no histórico e podem ficar órfãos."  # noqa: E501
    )

    versions = list(project.get("versions") or [])
    current_version = project.get("current_version")
    if not versions:
        st.info("Projeto sem versões para remover.")
        return

    col_v1, col_v2 = st.columns([2, 3])
    delete_version = col_v1.selectbox(
        "Versão para excluir",
        options=versions,
        key=f"delete-version-select-{project_id}",
    )
    confirm_text = col_v2.text_input(
        "Confirmação (digite exatamente a versão)",
        value="",
        key=f"delete-version-confirm-{project_id}",
        placeholder=f"Digite {delete_version}",
    )

    if delete_version == current_version:
        st.caption("A versão atual será removida. O sistema promoverá automaticamente a última versão remanescente.")

    if st.button("Excluir versão selecionada", type="primary", key=f"delete-version-btn-{project_id}"):
        if confirm_text.strip() != delete_version:
            st.error("Confirmação inválida. Digite exatamente o nome da versão para excluir.")
            return
        result = api_call(
            method="DELETE",
            path=f"/api/projects/{project_id}/versions/{delete_version}",
            base_url=base_url,
            actor=actor,
        )
        st.success(
            f"Versão {result.get('deleted_version')} removida. Nova atual: {result.get('current_version') or '-'} | Runs órfãs: {result.get('orphaned_runs', 0)}"  # noqa: E501
        )
        st.rerun()


def _render_run_details(run: dict, run_id: str, project_id: str, context: str) -> None:
    """Displays skills progress and error for a run."""
    st.caption(f"Status: {run.get('status')} | Inicio: {run.get('started_at')} | Fim: {run.get('finished_at')}")
    skills_data = run.get("skills_progress") or run.get("skills_log") or []
    if skills_data:
        render_paginated_table(
            skills_data, page_key=f"skills-page-{project_id}-{run_id}-{context}", page_size=15, label="skills"
        )
    else:
        st.info("Aguardando primeiras skills no log de invocacoes.")
    if run.get("error"):
        st.error(run["error"])


def render_pipeline_monitor(base_url: str, project_id: str, actor: str, context: str = "main") -> None:
    """Render pipeline execution monitor."""
    try:
        runs = api_call(method="GET", path=f"/api/projects/{project_id}/runs", base_url=base_url, actor=actor).get(
            "items", []
        )
    except Exception as exc:
        st.warning(
            f"Monitor indisponivel nesta API. Reinicie a API com a versao atual ou use execucao sync. Detalhe: {exc}"
        )
        return
    if not runs:
        st.info("Nenhuma execucao encontrada.")
        return

    run_ids = [item.get("run_id", "") for item in runs]
    default_idx = 0
    selected_run_id = st.session_state.get("selected_run_id")
    if selected_run_id in run_ids:
        default_idx = run_ids.index(selected_run_id)
    run_id = st.selectbox("Run ID", options=run_ids, index=default_idx, key=f"pm-run-id-{project_id}-{context}")
    st.session_state["selected_run_id"] = run_id

    if st.button("Atualizar monitor", key=f"pm-refresh-{project_id}-{context}", type="secondary"):
        pass

    try:
        run = api_call(method="GET", path=f"/api/projects/{project_id}/runs/{run_id}", base_url=base_url, actor=actor)
    except Exception as exc:
        st.error(f"Falha ao consultar run {run_id}: {exc}")
        return
    _render_run_details(run, run_id, project_id, context)


def _build_history_timeline(runs: list) -> list[dict]:
    """Builds the timeline rows list from runs."""
    return [
        {
            "run_id": item.get("run_id", "")[:12],
            "status": item.get("status"),
            "versão": item.get("version"),
            "base": item.get("base_version"),
            "solicitado": (item.get("requested_at") or "")[:16].replace("T", " "),
            "início": (item.get("started_at") or "")[:16].replace("T", " "),
            "fim": (item.get("finished_at") or "")[:16].replace("T", " "),
            "actor": item.get("actor"),
        }
        for item in runs
    ]


def _filter_history(timeline: list[dict], q: str, sel_status: list) -> list[dict]:
    """Applies text and status filters to the timeline list."""
    if q:
        q_l = q.lower()
        timeline = [
            r for r in timeline if q_l in str(r.get("run_id", "")).lower() or q_l in str(r.get("versão", "")).lower()
        ]
    if sel_status:
        timeline = [r for r in timeline if r.get("status") in sel_status]
    return timeline


def render_history(base_url: str, project_id: str, actor: str, context: str = "main") -> None:
    """Render execution history timeline — paginated."""
    try:
        runs = api_call(method="GET", path=f"/api/projects/{project_id}/runs", base_url=base_url, actor=actor).get(
            "items", []
        )
    except Exception as exc:
        st.warning(f"Historico indisponivel nesta API: {exc}")
        return
    if not runs:
        st.info("Sem historico de runs.")
        return

    col_q, col_status = st.columns([4, 2])
    q = col_q.text_input(
        "Buscar run ID ou versão",
        key=f"hist-q-{project_id}-{context}",
        label_visibility="collapsed",
        placeholder="Filtrar runs…",
    )
    status_opts = sorted({r.get("status", "") for r in runs if r.get("status")})
    sel_status = col_status.multiselect(
        "Status",
        options=status_opts,
        key=f"hist-status-{project_id}-{context}",
        label_visibility="collapsed",
        placeholder="Todos os status",
    )

    timeline = _build_history_timeline(runs)
    timeline = _filter_history(timeline, q, sel_status)
    render_paginated_table(timeline, page_key=f"hist-page-{project_id}-{context}", label="runs")


def _render_numeric_override_section(
    project_id: str, reference: dict, current: dict, base_url: str, actor: str
) -> None:
    """Renders the numeric override editor section."""
    st.divider()
    st.subheader("Override numérico rápido")
    skill_options = collect_skill_candidates(reference, current)
    numeric_skill_id = st.selectbox(
        "Skill para edição simplificada", options=skill_options, key=f"numeric-override-skill-{project_id}"
    )
    base_inputs = extract_skill_base_inputs(reference, numeric_skill_id)
    current_inputs = current.get(numeric_skill_id, {}) if isinstance(current.get(numeric_skill_id), dict) else {}
    with st.expander(f"Composição base - {numeric_skill_id}", expanded=False):
        if base_inputs:
            render_mapping_table("Base de referência", base_inputs)
        else:
            st.info("Sem composição base encontrada para este skill na referência.")
    numeric_rows = render_numeric_override_editor(project_id, numeric_skill_id, base_inputs, current_inputs)
    if numeric_rows:
        if st.button("Salvar override numérico", key=f"save-numeric-{project_id}", type="primary"):
            new_inputs = json.loads(json.dumps(base_inputs)) if isinstance(base_inputs, dict) else {}
            for row in numeric_rows:
                dotted = str(row.get("campo") or "")
                if not dotted:
                    continue
                set_path(new_inputs, dotted, float(row.get("novo_valor") or 0.0))
            result = api_call(
                method="POST",
                path=f"/api/projects/{project_id}/overrides",
                base_url=base_url,
                payload={"skill_id": numeric_skill_id, "inputs": new_inputs},
                actor=actor,
            )
            st.success(f"Override numérico salvo para {numeric_skill_id}")
            render_mapping_table("Overrides atualizados", result)


def _render_saved_bdi_section(project_id: str, reference: dict, current: dict, base_url: str, actor: str) -> None:
    """Renders the BDI quick-edit section in saved overrides."""
    st.divider()
    st.subheader("BDI da versão base")
    st.caption("Edite os fatores de BDI e salve como override dos skills financeiros. Ex.: 0.25 = 25%.")
    skill06_base = extract_skill_base_inputs(reference, "06-resultado-financeiro")
    skill08_base = extract_skill_base_inputs(reference, "06-resultado-financeiro")
    skill06_cur = (
        current.get("06-resultado-financeiro", {}) if isinstance(current.get("06-resultado-financeiro"), dict) else {}
    )
    skill08_cur = (
        current.get("06-resultado-financeiro", {}) if isinstance(current.get("06-resultado-financeiro"), dict) else {}
    )
    bdi_base = extract_bdi_dict(skill06_base) or extract_bdi_dict(skill08_base)
    bdi_cur = extract_bdi_dict(skill06_cur) or extract_bdi_dict(skill08_cur)
    bdi_keys = ["mao_obra", "equipamentos", "material", "diesel", "indireto"]
    bdi_defaults = {k: float(bdi_cur.get(k, bdi_base.get(k, 0.0))) for k in bdi_keys}
    st.dataframe(
        [
            {"categoria": k, "fator": round(bdi_defaults[k], 4), "percentual": f"{bdi_defaults[k] * 100:.2f}%"}
            for k in bdi_keys
        ],
        width="stretch",
        hide_index=True,
    )
    bdi_col1, bdi_col2, bdi_col3, bdi_col4, bdi_col5 = st.columns(5)
    edited_bdi = {
        "mao_obra": bdi_col1.number_input(
            "MO",
            min_value=0.0,
            max_value=5.0,
            value=bdi_defaults["mao_obra"],
            step=0.01,
            key=f"ov-bdi-mo-{project_id}",
        ),
        "equipamentos": bdi_col2.number_input(
            "Equip.",
            min_value=0.0,
            max_value=5.0,
            value=bdi_defaults["equipamentos"],
            step=0.01,
            key=f"ov-bdi-eq-{project_id}",
        ),
        "material": bdi_col3.number_input(
            "Material",
            min_value=0.0,
            max_value=5.0,
            value=bdi_defaults["material"],
            step=0.01,
            key=f"ov-bdi-mat-{project_id}",
        ),
        "diesel": bdi_col4.number_input(
            "Diesel",
            min_value=0.0,
            max_value=5.0,
            value=bdi_defaults["diesel"],
            step=0.01,
            key=f"ov-bdi-dsl-{project_id}",
        ),
        "indireto": bdi_col5.number_input(
            "Indireto",
            min_value=0.0,
            max_value=5.0,
            value=bdi_defaults["indireto"],
            step=0.01,
            key=f"ov-bdi-ind-{project_id}",
        ),
    }
    if st.button("Salvar BDI", key=f"save-ov-bdi-{project_id}", use_container_width=True, type="primary"):
        p06 = {"bdi_aplicado": {k: edited_bdi[k] for k in ["mao_obra", "equipamentos", "material", "diesel"]}}
        p08 = {"bdi_aplicado": edited_bdi}
        for skill_id, payload in [("06-resultado-financeiro", {**p06, **p08})]:
            api_call(
                method="POST",
                path=f"/api/projects/{project_id}/overrides",
                base_url=base_url,
                payload={"skill_id": skill_id, "inputs": payload},
                actor=actor,
            )
        st.success("BDI salvo.")


def _render_remove_override_section(project_id: str, current: dict, base_url: str, actor: str) -> None:
    """Renders the quick-remove override section."""
    st.divider()
    st.caption("Remoção rápida de override por skill")
    removable_skills = sorted([k for k, v in current.items() if isinstance(v, dict)])
    if not removable_skills:
        st.info("Nenhum override explícito para remover no momento.")
        return
    remove_skill_id = st.selectbox(
        "Skill para remover override", options=removable_skills, key=f"remove-override-skill-{project_id}"
    )
    if st.button("Remover override da skill selecionada", key=f"remove-override-btn-{project_id}", type="secondary"):
        result = api_call(
            method="DELETE",
            path=f"/api/projects/{project_id}/overrides/{remove_skill_id}",
            base_url=base_url,
            actor=actor,
        )
        st.success("Override removido")
        render_mapping_table("Override atualizado", result)


def render_saved_override(base_url: str, project_id: str, actor: str) -> None:
    """Render saved overrides editor."""
    st.subheader("4) Overrides salvos")
    try:
        current = api_call(method="GET", path=f"/api/projects/{project_id}/overrides", base_url=base_url, actor=actor)
    except Exception as exc:
        st.error(f"Falha ao carregar overrides: {exc}")
        return
    st.caption("Overrides atualmente salvos")
    render_mapping_table("Overrides atuais", current)
    if not any(isinstance(v, dict) for v in current.values()):
        st.info("Sem override explícito salvo. Abaixo você pode editar diretamente a composição base por skill.")
    try:
        reference = api_call(
            method="GET", path=f"/api/projects/{project_id}/benchmark-reference", base_url=base_url, actor=actor
        )
    except Exception:
        reference = {}
    _render_numeric_override_section(project_id, reference, current, base_url, actor)
    _render_saved_bdi_section(project_id, reference, current, base_url, actor)
    _render_remove_override_section(project_id, current, base_url, actor)


def _build_mob_policy_rows(eap_items: list, saved_policies: dict, ramp_up_enabled: bool) -> list[dict]:
    """Builds the policy rows from EAP items and saved policies."""
    rows: list[dict] = []
    for item in eap_items:
        item_id = str(item.get("item_id") or item.get("activity_id") or "")
        saved = saved_policies.get(item_id, {})
        n_max_saved = int(saved.get("n_maximo") or 1)
        n_ini_saved = int(saved.get("n_inicial") or 1) if ramp_up_enabled else n_max_saved
        rows.append(
            {
                "item_id": item_id,
                "descricao": str(item.get("descricao", ""))[:60],
                "cpu_id": str(item.get("cpu_id", "")),
                "quantitativo": float(item.get("quantitativo") or 0),
                "n_maximo": n_max_saved,
                "n_inicial": n_ini_saved,
                "taxa_mobilizacao": float(saved.get("taxa_mobilizacao") or 1.0),
                "_taxa_desmobilizacao": float(saved.get("taxa_desmobilizacao") or 0.0),
                "_semanas_plateau": saved.get("semanas_plateau"),
            }
        )
    return rows


def _extract_cpu_id_from_any_item(item: dict) -> str:
    """Extract cpu_id from canonical EAP contract."""
    if not isinstance(item, dict):
        return ""
    cpu_direct = item.get("cpu_id")
    if isinstance(cpu_direct, str):
        return cpu_direct.strip()
    return ""


def _load_eap_items_for_planning(project_id: str, base_url: str, actor: str) -> list[dict]:
    """Loads EAP items from project endpoint and normalizes cpu_id for planning UIs."""
    try:
        eap_resp = api_call(method="GET", path=f"/api/projects/{project_id}/eap", base_url=base_url, actor=actor)
    except Exception:
        return []
    rows: list[dict] = []
    for item in eap_resp.get("items") or []:
        if not isinstance(item, dict):
            continue
        cpu_id = _extract_cpu_id_from_any_item(item)
        if not cpu_id:
            continue
        normalized = dict(item)
        normalized["cpu_id"] = cpu_id
        rows.append(normalized)
    return rows


def _build_eap_items_from_saved_policies(saved_policies: dict) -> list[dict]:
    """Builds minimal EAP-like rows from saved mobilization policies when EAP is unavailable."""
    items: list[dict] = []
    for item_id in sorted(saved_policies.keys()):
        items.append(
            {
                "item_id": str(item_id),
                "descricao": "(item sem referência de EAP)",
                "cpu_id": "",
                "quantitativo": 0.0,
            }
        )
    return items


def _render_mob_rampdown_expander(rows: list[dict], project_id: str) -> None:
    """Renders the ramp-down controls expander and mutates rows in-place."""
    with st.expander("⚙️ Controles de desmobilização (ramp-down)", expanded=False):
        st.caption("Taxa de saída de equipes após o plateau e duração do plateau antes do ramp-down.")
        for i, row in enumerate(rows):
            adv_col1, adv_col2, adv_label = st.columns([2, 2, 4])
            adv_label.caption(f"{row['item_id']} — {row['descricao'][:40]}")
            rows[i]["_taxa_desmobilizacao"] = adv_col1.number_input(
                "Desmob./sem.",
                min_value=0.0,
                step=0.5,
                value=float(row["_taxa_desmobilizacao"]),
                key=f"desmob-{project_id}-{row['item_id']}",
            )
            plateau_val = adv_col2.number_input(
                "Plateau (sem.)",
                min_value=0,
                step=1,
                value=int(row["_semanas_plateau"] or 0),
                key=f"plateau-{project_id}-{row['item_id']}",
            )
            rows[i]["_semanas_plateau"] = int(plateau_val) if plateau_val > 0 else None


def _display_mob_validate_status(items: list, status_global: str) -> None:
    """Shows validate result status message."""
    if status_global == "OK":
        st.success("✅ Políticas válidas.")
    elif status_global == "AVISO":
        count = sum(1 for i in items if i.get("status") == "AVISO")
        st.warning(f"⚠️ {count} aviso(s).")
    else:
        count = sum(1 for i in items if i.get("status") == "ERRO")
        st.error(f"❌ {count} erro(s).")


def _build_mob_validate_table(items: list) -> list[dict]:
    """Builds the validation result table rows."""
    return [
        {
            "Código": i.get("codigo", ""),
            "Status": i.get("status", ""),
            "Mensagem": i.get("mensagem", ""),
            "Semanas est.": i.get("duration_weeks", "-"),
            "Pico equipes": i.get("peak_teams", "-"),
            "Completa": "✅" if i.get("is_complete") else ("⚠️" if i.get("is_complete") is False else "-"),
        }
        for i in items
    ]


def _handle_mob_validate(base_url: str, project_id: str, actor: str) -> None:
    """Handles the validate policies button logic."""
    try:
        result = api_call(
            method="POST",
            path=f"/api/projects/{project_id}/mobilizacao-policies/validate",
            base_url=base_url,
            actor=actor,
        )
        items = result.get("items", [])
        _display_mob_validate_status(items, result.get("status", "OK"))
        if items:
            st.dataframe(_build_mob_validate_table(items), width="stretch", hide_index=True)
    except Exception as exc:
        st.error(f"Erro na validação: {exc}")


def _build_mob_policy_item(er: dict, adv: dict, ramp_up_enabled: bool, ramp_down_enabled: bool) -> dict:
    """Builds policy_data dict for one mobilizacao item."""
    n_max = max(1, int(er.get("n_maximo") or 1))
    n_ini = min(max(1, int(er.get("n_inicial") or n_max)) if ramp_up_enabled else n_max, n_max)
    taxa_mob = max(0.1, float(er.get("taxa_mobilizacao") or 1.0)) if ramp_up_enabled else float(n_max)
    taxa_desmob = float(adv.get("_taxa_desmobilizacao") or 0.0) if ramp_down_enabled else 0.0
    semanas_plateau = adv.get("_semanas_plateau") if ramp_down_enabled else None
    return {
        "n_inicial": n_ini,
        "n_maximo": n_max,
        "taxa_mobilizacao": taxa_mob,
        "taxa_desmobilizacao": taxa_desmob,
        "semanas_plateau": semanas_plateau,
    }


def _process_mob_save_rows(
    edited_list: list,
    rows: list[dict],
    ramp_up_enabled: bool,
    ramp_down_enabled: bool,
    base_url: str,
    project_id: str,
    actor: str,
) -> tuple[int, list[str]]:
    """Processes all edited rows, POSTing each policy. Returns (count, errors)."""
    errors: list[str] = []
    count = 0
    for i, er in enumerate(edited_list):
        item_id = str(er.get("item_id") or "").strip()
        if not item_id:
            continue
        adv = rows[i] if i < len(rows) else {}
        policy_data = _build_mob_policy_item(er, adv, ramp_up_enabled, ramp_down_enabled)
        try:
            api_call(
                method="POST",
                path=f"/api/projects/{project_id}/mobilizacao-policies",
                base_url=base_url,
                payload={"item_id": item_id, "policy": policy_data},
                actor=actor,
            )
            count += 1
        except Exception as exc:
            errors.append(f"{item_id}: {exc}")
    return count, errors


def _handle_mob_save(
    edited: object,
    rows: list[dict],
    ramp_up_enabled: bool,
    ramp_down_enabled: bool,
    base_url: str,
    project_id: str,
    actor: str,
) -> None:
    """Handles the save policies button logic."""
    edited_list = edited.to_dict("records") if hasattr(edited, "to_dict") else list(edited or [])  # type: ignore[union-attr]
    count, errors = _process_mob_save_rows(
        edited_list, rows, ramp_up_enabled, ramp_down_enabled, base_url, project_id, actor
    )
    if errors:
        st.error(f"Erros ao salvar: {'; '.join(errors)}")
    else:
        st.success(f"✅ {count} política(s) salva(s). Clique em 🚀 Replanejar para aplicar.")


def _build_mob_policy_vis_rows(rows: list[dict], ramp_up_enabled: bool) -> tuple[dict, list[dict]]:
    """Builds column config and visible rows for the mob policy editor."""
    col_cfg: dict = {
        "item_id": st.column_config.TextColumn("Item ID", disabled=True, width="small"),
        "descricao": st.column_config.TextColumn("Descrição", disabled=True, width="large"),
        "cpu_id": st.column_config.TextColumn("CPU", disabled=True, width="small"),
        "quantitativo": st.column_config.NumberColumn("Qtd.", disabled=True, format="%.0f", width="small"),
        "n_maximo": st.column_config.NumberColumn("✏️ Máx. equipes", min_value=1, step=1, format="%.0f", width="small"),
    }
    if ramp_up_enabled:
        col_cfg["n_inicial"] = st.column_config.NumberColumn(
            "✏️ Inicial", min_value=1, step=1, format="%.0f", width="small"
        )
        col_cfg["taxa_mobilizacao"] = st.column_config.NumberColumn(
            "✏️ Mob./sem.", min_value=0.1, step=0.5, format="%.1f", width="small"
        )
    vis_keys = ["item_id", "descricao", "cpu_id", "quantitativo", "n_maximo"] + (
        ["n_inicial", "taxa_mobilizacao"] if ramp_up_enabled else []
    )
    main_rows = [{k: r[k] for k in vis_keys if k in r} for r in rows]
    return col_cfg, main_rows


def render_mobilizacao_policy_editor(
    base_url: str,
    project_id: str,
    actor: str,
    reference: dict,
    base_version: str | None,
) -> None:
    """Editor de políticas de mobilização (ADR-054)."""
    st.caption(
        "Defina a intenção operacional por atividade. O sistema simula a curva de equipes e "
        "deriva o horizonte de execução — não é necessário atingir o máximo se a produção acumulada "
        "cobrir o quantitativo antes."
    )
    try:
        saved_policies: dict = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/mobilizacao-policies",
            base_url=base_url,
            actor=actor,
        ).get("items", {})
    except Exception:
        saved_policies = {}
    eap_items = extract_eap_items_for_policy(reference)
    if not eap_items:
        eap_items = _load_eap_items_for_planning(project_id, base_url, actor)
    if not eap_items and saved_policies:
        eap_items = _build_eap_items_from_saved_policies(saved_policies)
    if not eap_items:
        st.info("Nenhum item de EAP com CPU encontrado na referência para configurar políticas.")
        return
    ramp_col1, ramp_col2, _ = st.columns([2, 2, 4])
    ramp_up_enabled = ramp_col1.checkbox(
        "Ramp-up progressivo",
        value=True,
        key=f"ramp-up-{project_id}",
        help="Mobilização gradual: a equipe aumenta até o máximo ao ritmo definido. "
        "Desabilitado → todas as equipes implantadas na semana 0.",
    )
    ramp_down_enabled = ramp_col2.checkbox(
        "Ramp-down após plateau",
        value=False,
        key=f"ramp-dn-{project_id}",
        help="Desmobilização forçada após o plateau. "
        "Só necessário quando o equipamento/contrato tem data de saída obrigatória.",
    )
    rows = _build_mob_policy_rows(eap_items, saved_policies, ramp_up_enabled)
    col_cfg, main_rows = _build_mob_policy_vis_rows(rows, ramp_up_enabled)
    edited = st.data_editor(
        main_rows,
        width="stretch",
        hide_index=True,
        column_config=col_cfg,
        disabled=["item_id", "descricao", "cpu_id", "quantitativo"],
        key=f"mob-policy-editor-{project_id}",
    )
    if ramp_down_enabled:
        _render_mob_rampdown_expander(rows, project_id)
    col_save, col_validate, col_replan = st.columns([2, 2, 1])
    if col_validate.button("🔍 Validar políticas", key=f"validate-policies-{project_id}"):
        _handle_mob_validate(base_url, project_id, actor)
    if col_save.button("💾 Salvar políticas", key=f"save-policies-{project_id}"):
        _handle_mob_save(edited, rows, ramp_up_enabled, ramp_down_enabled, base_url, project_id, actor)
    col_replan.write("")
    if col_replan.button("🚀 Replanejar", key=f"replan-wmp-{project_id}"):
        result = api_call(
            method="POST",
            path=f"/api/projects/{project_id}/runs/start",
            base_url=base_url,
            payload={"base_version": base_version, "fork_version": True, "use_saved_overrides": True},
            actor=actor,
        )
        st.success(f"✨ Replanejamento iniciado: {result.get('run_id')}")


def render_deliverables_config(base_url: str, project_id: str, actor: str) -> None:
    """Configurable output generation panel — artefatos reais de saída."""
    st.caption("Configure quais **outputs** serão gerados no próximo run.")

    try:
        config = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/deliverables-config",
            base_url=base_url,
            actor=actor,
        )
        outputs: dict = config.get("outputs", {})
    except Exception:
        outputs = {}

    def _get(key: str, default: bool = True) -> bool:
        return bool(outputs.get(key, default))

    edited: dict[str, bool] = {}

    # ── Fundamentais (sempre ativos, não desativáveis) ────────────────────
    st.markdown("**📌 Fundamentais** — sempre incluídos na entrega")
    f1, f2, f3 = st.columns(3)
    edited["resultado_xlsx"] = True
    f1.checkbox(
        "📊 resultado.xlsx",
        value=True,
        disabled=True,
        key=f"deliv-{project_id}-xlsx-fixed",
        help="Planilha principal com RESULTADO, BDI, FLUXO.CAIXA",
    )
    edited["relatorio_md"] = True
    f2.checkbox(
        "📝 relatorio.md",
        value=True,
        disabled=True,
        key=f"deliv-{project_id}-rmd-fixed",
        help="Relatório executivo em Markdown",
    )
    edited["memorial_bdi_pdf"] = True
    f3.checkbox(
        "📄 memorial_bdi.pdf",
        value=True,
        disabled=True,
        key=f"deliv-{project_id}-mbdpdf-fixed",
        help="Memorial de cálculo BDI para entrega",
    )

    st.divider()

    # ── Complementares (toggleáveis) ──────────────────────────────────────
    st.markdown("**🔬 Analíticos complementares** — opcionais")
    c1, c2, c3 = st.columns(3)
    edited["aba_memorial_bdi"] = c1.checkbox(
        "MEMORIAL.BDI",
        value=_get("aba_memorial_bdi", True),
        key=f"deliv-{project_id}-aba-bdi",
        help="Aba de auditoria de cálculo BDI no Excel",
    )
    edited["aba_curva_abc"] = c2.checkbox(
        "CURVA.ABC.ATIVIDADES",
        value=_get("aba_curva_abc", True),
        key=f"deliv-{project_id}-aba-abc",
        help="Pareto por atividade (curva ABC atual)",
    )
    edited["aba_curva_abc_composicao"] = c3.checkbox(
        "CURVA.ABC.COMPOSIÇÃO",
        value=_get("aba_curva_abc_composicao", False),
        key=f"deliv-{project_id}-aba-abc-comp",
        help="Pareto por componente de custo (MO, EQ, MAT, DIESEL) — nova aba",
    )
    c4, c5, c6 = st.columns(3)
    edited["aba_s_curve"] = c4.checkbox(
        "S-CURVE",
        value=_get("aba_s_curve", True),
        key=f"deliv-{project_id}-aba-sc",
        help="Curva de desembolso acumulado",
    )
    edited["aba_campanha_frota"] = c5.checkbox(
        "CAMPANHA.FROTA",
        value=_get("aba_campanha_frota", True),
        key=f"deliv-{project_id}-aba-frota",
        help="Permanência de equipamentos",
    )
    edited["relatorio_pdf"] = c6.checkbox(
        "relatorio.pdf",
        value=_get("relatorio_pdf", True),
        key=f"deliv-{project_id}-rpdf",
        help="PDF nativo financeiro (ReportLab)",
    )

    if st.button(
        "Salvar configuração de saídas", key=f"save-deliv-{project_id}", use_container_width=True, type="primary"
    ):
        try:
            api_call(
                method="PUT",
                path=f"/api/projects/{project_id}/deliverables-config",
                base_url=base_url,
                payload={"outputs": edited},
                actor=actor,
            )
            st.success("Salvo.")
        except Exception as exc:
            st.error(f"Erro ao salvar: {exc}")


def _hydrate_indiretos_from_overrides(base_url: str, project_id: str, actor: str) -> tuple[dict, dict]:
    """Fallback: use saved skill 07 overrides when benchmark reference has no indirect baseline."""
    try:
        ov = api_call(method="GET", path=f"/api/projects/{project_id}/overrides", base_url=base_url, actor=actor)
    except Exception:
        return {}, {}
    s07 = ov.get("06-resultado-financeiro") if isinstance(ov, dict) else None
    if not isinstance(s07, dict):
        return {}, {}
    cats = s07.get("categorias_config") or []
    if not isinstance(cats, list):
        return {}, {}
    equipes_fallback: dict[str, dict] = {}
    ind_det_fallback: dict[str, dict] = {}
    for cat in cats:
        if not isinstance(cat, dict):
            continue
        cid = str(cat.get("categoria") or "").upper().strip()
        if not cid:
            continue
        if cid == "MOB":
            ind_det_fallback["MOB"] = {
                "custo_fixo_total": float(cat.get("custo_fixo_total") or cat.get("custo_total") or 0.0)
            }
            continue
        mo = ((cat.get("mao_de_obra") or {}).get("itens") or []) if isinstance(cat.get("mao_de_obra"), dict) else []
        equips = cat.get("equipamentos") or []
        verbas = cat.get("verbas_mensais") or []
        if not mo and not equips and not verbas:
            total_month = float(cat.get("custo_fixo_mensal") or 0.0)
            if total_month > 0:
                verbas = [{"descricao": "custo consolidado", "valor_mensal": total_month}]
        equipes_fallback[cid] = {
            "categoria": cid,
            "mao_obra": mo,
            "equipamentos": equips,
            "verbas_mensais": verbas,
        }
    return equipes_fallback, ind_det_fallback


def _bdi_tcu_cv(saved_comp: dict, key: str, dom_val: float) -> float:
    """Returns component value from saved or default, scaled to percentage."""
    return float(saved_comp.get(key, dom_val)) * 100


def _compute_bdi_from_tabela(tabela_bdi: dict, bdi_base: dict) -> None:
    """Computes BDI values from tabela_bdi components into bdi_base in-place."""
    for cat, comps in tabela_bdi.items():
        if not isinstance(comps, dict) or "ac" not in comps:
            continue
        ac = float(comps.get("ac", 0))
        df_ = float(comps.get("df", 0))
        r_ = float(comps.get("r", 0))
        cr_ = float(comps.get("cr", 0))
        l_ = float(comps.get("l") or comps.get("lucro") or 0)
        t_ = sum(float(comps.get(k, 0)) for k in ("cofins", "iss", "pis", "cssl", "ir"))
        bdi_val = ((1 + ac + df_ + r_ + cr_ + l_) / (1 - t_) - 1) if t_ < 1 else 0.0
        bdi_base[cat] = round(bdi_val, 6)
    if "equipamentos" not in bdi_base:
        # ADR-023 §D3 revisado: bucket equipamentos = locação (SV-31/STF: sem ISS) → taxa de material
        bdi_base["equipamentos"] = bdi_base.get("material", 0.0)


def _render_tcu_cat_expander(
    cat: str, cat_label: str, dom_comp: object, saved_comp: dict, project_id: str, tcu_edited: dict
) -> None:
    """Renders the TCU decomposition expander for one BDI category."""
    with st.expander(cat_label, expanded=False):
        st.markdown("**Overhead (numerador)**")
        oh_c1, oh_c2, oh_c3, oh_c4, oh_c5 = st.columns(5)
        ac_v = (
            oh_c1.number_input(
                "AC %",
                0.0,
                20.0,
                _bdi_tcu_cv(saved_comp, "ac", dom_comp.ac),
                step=0.1,
                key=f"tcu-{project_id}-{cat}-ac",
            )
            / 100
        )  # type: ignore[union-attr]
        df_v = (
            oh_c2.number_input(
                "DF %",
                0.0,
                10.0,
                _bdi_tcu_cv(saved_comp, "df", dom_comp.df),
                step=0.1,
                key=f"tcu-{project_id}-{cat}-df",
            )
            / 100
        )  # type: ignore[union-attr]
        r_v = (
            oh_c3.number_input(
                "R %", 0.0, 10.0, _bdi_tcu_cv(saved_comp, "r", dom_comp.r), step=0.1, key=f"tcu-{project_id}-{cat}-r"
            )
            / 100
        )  # type: ignore[union-attr]
        cr_v = (
            oh_c4.number_input(
                "CR %",
                0.0,
                10.0,
                _bdi_tcu_cv(saved_comp, "cr", dom_comp.cr),
                step=0.1,
                key=f"tcu-{project_id}-{cat}-cr",
            )
            / 100
        )  # type: ignore[union-attr]
        l_v = (
            oh_c5.number_input(
                "L %", 0.0, 30.0, _bdi_tcu_cv(saved_comp, "l", dom_comp.l), step=0.1, key=f"tcu-{project_id}-{cat}-l"
            )
            / 100
        )  # type: ignore[union-attr]
        st.markdown("**Tributos (denominador)**")
        tr_c1, tr_c2, tr_c3, tr_c4, tr_c5 = st.columns(5)
        cofins_v = (
            tr_c1.number_input(
                "COFINS %",
                0.0,
                10.0,
                _bdi_tcu_cv(saved_comp, "cofins", dom_comp.cofins),
                step=0.1,
                key=f"tcu-{project_id}-{cat}-cofins",
            )
            / 100
        )  # type: ignore[union-attr]
        iss_v = (
            tr_c2.number_input(
                "ISS %",
                0.0,
                10.0,
                _bdi_tcu_cv(saved_comp, "iss", dom_comp.iss),
                step=0.1,
                key=f"tcu-{project_id}-{cat}-iss",
            )
            / 100
        )  # type: ignore[union-attr]
        pis_v = (
            tr_c3.number_input(
                "PIS %",
                0.0,
                5.0,
                _bdi_tcu_cv(saved_comp, "pis", dom_comp.pis),
                step=0.05,
                key=f"tcu-{project_id}-{cat}-pis",
            )
            / 100
        )  # type: ignore[union-attr]
        cssl_v = (
            tr_c4.number_input(
                "CSLL %",
                0.0,
                5.0,
                _bdi_tcu_cv(saved_comp, "cssl", dom_comp.cssl),
                step=0.1,
                key=f"tcu-{project_id}-{cat}-cssl",
            )
            / 100
        )  # type: ignore[union-attr]
        ir_v = (
            tr_c5.number_input(
                "IR %", 0.0, 5.0, _bdi_tcu_cv(saved_comp, "ir", dom_comp.ir), step=0.1, key=f"tcu-{project_id}-{cat}-ir"
            )
            / 100
        )  # type: ignore[union-attr]
        t_total = cofins_v + iss_v + pis_v + cssl_v + ir_v
        oh_total = ac_v + df_v + r_v + cr_v + l_v
        bdi_calc = (1 + oh_total) / (1 - t_total) - 1 if t_total < 1 else 0.0
        st.metric(f"BDI {cat_label}", f"{bdi_calc * 100:.2f}%", help="Calculado em tempo real pela fórmula TCU")
        tcu_edited[cat] = {
            "ac": ac_v,
            "df": df_v,
            "r": r_v,
            "cr": cr_v,
            "l": l_v,
            "cofins": cofins_v,
            "iss": iss_v,
            "pis": pis_v,
            "cssl": cssl_v,
            "ir": ir_v,
        }


def _resolve_bdi_pre_reforma_defaults(
    reference: dict, current: dict, skill06_current: dict, DEFAULT_BDI_TABELA: object
) -> tuple[dict, list[str]]:
    """Resolves bdi_defaults and bdi_keys for pre-reforma editor."""
    skill06_base = extract_skill_base_inputs(reference, "06-resultado-financeiro")
    skill08_base = extract_skill_base_inputs(reference, "06-resultado-financeiro")
    skill08_current = (
        current.get("06-resultado-financeiro", {}) if isinstance(current.get("06-resultado-financeiro"), dict) else {}
    )
    bdi_base = extract_bdi_dict(skill06_base) or extract_bdi_dict(skill08_base)
    if not bdi_base:
        tabela_bdi = skill06_base.get("tabela_bdi") or {}
        if tabela_bdi and isinstance(tabela_bdi, dict):
            _compute_bdi_from_tabela(tabela_bdi, bdi_base)
    bdi_cur = extract_bdi_dict(skill06_current) or extract_bdi_dict(skill08_current)
    bdi_keys_l = ["mao_obra", "equipamentos", "material", "diesel", "indireto"]
    _dft = {
        "mao_obra": float(DEFAULT_BDI_TABELA.mao_obra.bdi_total),  # type: ignore[union-attr]
        "equipamentos": float(DEFAULT_BDI_TABELA.servicos.bdi_total),  # type: ignore[union-attr]
        "material": float(DEFAULT_BDI_TABELA.material.bdi_total),  # type: ignore[union-attr]
        "diesel": float(DEFAULT_BDI_TABELA.diesel.bdi_total),  # type: ignore[union-attr]
        "indireto": float(DEFAULT_BDI_TABELA.indireto.bdi_total),  # type: ignore[union-attr]
    }
    bdi_defaults = {k: float(bdi_cur.get(k, bdi_base.get(k, _dft.get(k, 0.0)))) for k in bdi_keys_l}
    return bdi_defaults, bdi_keys_l


def _render_bdi_simple_save(project_id: str, edited_bdi: dict, bdi_keys: list, base_url: str, actor: str) -> None:
    """Handles saving the simplified BDI values."""
    api_call(
        method="POST",
        path=f"/api/projects/{project_id}/overrides",
        base_url=base_url,
        payload={
            "skill_id": "06-resultado-financeiro",
            "inputs": {"bdi_aplicado": {k: edited_bdi[k] for k in bdi_keys if k != "indireto"}},
        },
        actor=actor,
    )
    api_call(
        method="POST",
        path=f"/api/projects/{project_id}/overrides",
        base_url=base_url,
        payload={"skill_id": "06-resultado-financeiro", "inputs": {"bdi_aplicado": edited_bdi}},
        actor=actor,
    )
    st.success("BDI salvo.")


def _render_tcu_expander_section(
    project_id: str,
    skill06_current: dict,
    tcu_cats: list,
    tcu_labels: dict,
    dom_map: dict,
    base_url: str,
    actor: str,
) -> None:
    """Renders the TCU decomposition expander section."""
    saved_tabela = skill06_current.get("tabela_bdi") or {}
    with st.expander("▶ Ver decomposição TCU por categoria", expanded=False):
        st.caption(
            "Edite os componentes individuais (AC, DF, R, CR, L, tributos). "
            "O BDI total é recalculado pela fórmula TCU: `(1 + AC + DF + R + CR + L) / (1 − T) − 1`."
        )
        tcu_edited: dict[str, dict] = {}
        for cat in tcu_cats:
            _render_tcu_cat_expander(
                cat, tcu_labels[cat], dom_map[cat], saved_tabela.get(cat) or {}, project_id, tcu_edited
            )
        if st.button("Salvar decomposição TCU", key=f"save-tcu-{project_id}", type="primary", use_container_width=True):
            api_call(
                method="POST",
                path=f"/api/projects/{project_id}/overrides",
                base_url=base_url,
                payload={"skill_id": "06-resultado-financeiro", "inputs": {"tabela_bdi": tcu_edited}},
                actor=actor,
            )
            st.success("Decomposição TCU salva. Recalcule o BDI total com 'Salvar BDI' acima.")


def _render_bdi_pre_reforma(
    project_id: str,
    reference: dict,
    current: dict,
    skill06_current: dict,
    base_url: str,
    actor: str,
    DEFAULT_BDI_TABELA: object,
) -> None:
    """Renders the pre-reforma BDI editor section."""
    st.caption("Modo legado — edite os fatores BDI diretamente. Ex.: 0.35 = 35%.")
    bdi_defaults, bdi_keys_l = _resolve_bdi_pre_reforma_defaults(
        reference, current, skill06_current, DEFAULT_BDI_TABELA
    )
    st.dataframe(
        [
            {"categoria": k, "fator": round(bdi_defaults[k], 4), "percentual": f"{bdi_defaults[k] * 100:.2f}%"}
            for k in bdi_keys_l
        ],
        width="stretch",
        hide_index=True,
    )
    c1, c2, c3, c4, c5 = st.columns(5)
    edited_bdi = {
        "mao_obra": c1.number_input(
            "MO", min_value=0.0, max_value=5.0, value=bdi_defaults["mao_obra"], step=0.01, key=f"bdi-mo-{project_id}"
        ),
        "equipamentos": c2.number_input(
            "Equip.",
            min_value=0.0,
            max_value=5.0,
            value=bdi_defaults["equipamentos"],
            step=0.01,
            key=f"bdi-eq-{project_id}",
        ),
        "material": c3.number_input(
            "Material",
            min_value=0.0,
            max_value=5.0,
            value=bdi_defaults["material"],
            step=0.01,
            key=f"bdi-mat-{project_id}",
        ),
        "diesel": c4.number_input(
            "Diesel", min_value=0.0, max_value=5.0, value=bdi_defaults["diesel"], step=0.01, key=f"bdi-dsl-{project_id}"
        ),
        "indireto": c5.number_input(
            "Indireto",
            min_value=0.0,
            max_value=5.0,
            value=bdi_defaults["indireto"],
            step=0.01,
            key=f"bdi-ind-{project_id}",
        ),
    }
    if st.button("Salvar BDI", key=f"save-bdi-{project_id}", use_container_width=True, type="primary"):
        _render_bdi_simple_save(project_id, edited_bdi, bdi_keys_l, base_url, actor)
    _tcu_cats = ["mao_obra", "equipamentos", "material", "diesel", "indireto"]
    _tcu_labels = {
        "mao_obra": "Mão de Obra",
        "equipamentos": "Equipamentos",
        "material": "Material",
        "diesel": "Diesel",
        "indireto": "Indireto",
    }
    _dom_map = {
        "mao_obra": DEFAULT_BDI_TABELA.mao_obra,
        "equipamentos": DEFAULT_BDI_TABELA.servicos,  # type: ignore[union-attr]
        "material": DEFAULT_BDI_TABELA.material,
        "diesel": DEFAULT_BDI_TABELA.diesel,
        "indireto": DEFAULT_BDI_TABELA.indireto,  # type: ignore[union-attr]
    }
    _render_tcu_expander_section(project_id, skill06_current, _tcu_cats, _tcu_labels, _dom_map, base_url, actor)


def _render_bdi_cbs_ibs(
    project_id: str,
    saved_tax_scenario: dict,
    selected_regime: object,
    selected_regime_key: str,
    cenario_base: object,
    default_bdi_tabela: object,
    resolver_bdi_cbs_ibs_fn: object,
    tax_sim_scenario_cls: type,
    regime_labels: dict,
    base_url: str,
    actor: str,
) -> None:
    """Renders the CBS/IBS BDI editor section."""
    st.caption(
        "Modo CBS/IBS — defina as premissas de crédito por categoria. "
        "O BDI é derivado automaticamente pela fórmula TCU com T_efetivo = CBS_IBS×(1−ratio)+CSSL+IR."
    )
    if cenario_base.split_payment:  # type: ignore[union-attr]
        st.info(
            "ℹ️ **Split payment** ativo neste regime — o tomador retém o imposto na fonte. "
            "Não altera o BDI, mas impacta o fluxo de caixa.",
            icon="💡",
        )

    def _f(key: str, default: float) -> float:
        return (
            float(saved_tax_scenario.get(key, default))
            if saved_tax_scenario.get("regime_version") == selected_regime_key
            else default
        )

    st.markdown("**Alíquota CBS+IBS combinada (bruta sobre o preço de venda)**")
    cbs_ibs_rate = (
        st.slider(
            "CBS+IBS combinado (%)",
            min_value=0.0,
            max_value=35.0,
            value=round(_f("cbs_ibs_combined_rate", cenario_base.cbs_ibs_combined_rate) * 100, 1),  # type: ignore[union-attr]
            step=0.1,
            key=f"bdi-cbs-rate-{project_id}",
        )
        / 100.0
    )
    st.markdown("**Crédito recuperável por categoria (premissa do planejador)**")
    cr_col1, cr_col2, cr_col3, cr_col4 = st.columns(4)
    cr_mo = (
        cr_col1.number_input(
            "MO (%)",
            0.0,
            100.0,
            round(_f("credit_ratio_mao_obra", cenario_base.credit_ratio_mao_obra) * 100, 1),
            step=1.0,
            key=f"bdi-cr-mo-{project_id}",
        )
        / 100.0
    )  # type: ignore[union-attr]
    cr_mat = (
        cr_col2.number_input(
            "Material (%)",
            0.0,
            100.0,
            round(_f("credit_ratio_material", cenario_base.credit_ratio_material) * 100, 1),
            step=1.0,
            key=f"bdi-cr-mat-{project_id}",
        )
        / 100.0
    )  # type: ignore[union-attr]
    cr_srv = (
        cr_col3.number_input(
            "Serviços (%)",
            0.0,
            100.0,
            round(_f("credit_ratio_servicos", cenario_base.credit_ratio_servicos) * 100, 1),
            step=1.0,
            key=f"bdi-cr-srv-{project_id}",
        )
        / 100.0
    )  # type: ignore[union-attr]
    cr_dsl = (
        cr_col4.number_input(
            "Diesel (%)",
            0.0,
            100.0,
            round(_f("credit_ratio_diesel", cenario_base.credit_ratio_diesel) * 100, 1),
            step=1.0,
            key=f"bdi-cr-dsl-{project_id}",
        )
        / 100.0
    )  # type: ignore[union-attr]
    with st.expander("⚙️ Parâmetros avançados (lag e taxa financeira)", expanded=False):
        lag_col, taxa_col, sp_col = st.columns(3)
        lag = int(
            lag_col.number_input(
                "Lag recuperação (sem.)",
                0,
                26,
                int(_f("credit_lag_semanas", cenario_base.credit_lag_semanas)),
                step=1,
                key=f"bdi-lag-{project_id}",
            )
        )  # type: ignore[union-attr]
        taxa = (
            taxa_col.number_input(
                "Taxa financ. anual (%)",
                0.0,
                50.0,
                round(_f("taxa_financ_anual", cenario_base.taxa_financ_anual) * 100, 1),
                step=0.5,
                key=f"bdi-taxa-{project_id}",
            )
            / 100.0
        )  # type: ignore[union-attr]
        sp = sp_col.checkbox(
            "Split payment",
            value=bool(saved_tax_scenario.get("split_payment", cenario_base.split_payment)),
            key=f"bdi-sp-{project_id}",
        )  # type: ignore[union-attr]
        cssl = float(saved_tax_scenario.get("cssl_rate", cenario_base.cssl_rate))  # type: ignore[union-attr]
        ir = float(saved_tax_scenario.get("ir_rate", cenario_base.ir_rate))  # type: ignore[union-attr]
    scenario_preview = tax_sim_scenario_cls(  # type: ignore[operator]
        regime_version=selected_regime,
        cbs_ibs_combined_rate=cbs_ibs_rate,
        credit_ratio_mao_obra=cr_mo,
        credit_ratio_material=cr_mat,
        credit_ratio_servicos=cr_srv,
        credit_ratio_diesel=cr_dsl,
        credit_lag_semanas=lag,
        taxa_financ_anual=taxa,
        split_payment=sp,
        cssl_rate=cssl,
        ir_rate=ir,
    )
    tabela_preview = resolver_bdi_cbs_ibs_fn(default_bdi_tabela, scenario_preview)  # type: ignore[operator]
    t_ef = scenario_preview.tributos_efetivos_por_categoria()
    preview_rows = [
        {
            "Categoria": cat,
            "T_bruto (%)": f"{cbs_ibs_rate * 100:.1f}%",
            "Crédito (%)": f"{ratio * 100:.0f}%",
            "T_efetivo (%)": f"{t_ef[cat2] * 100:.2f}%",
            "BDI derivado (%)": f"{getattr(tabela_preview, cat2).bdi_total * 100:.2f}%",
        }
        for cat, ratio, cat2 in [
            ("Mão de Obra", cr_mo, "mao_obra"),
            ("Material", cr_mat, "material"),
            ("Serviços/Equip.", cr_srv, "servicos"),
            ("Diesel", cr_dsl, "diesel"),
            ("Indireto", cr_srv, "indireto"),
        ]
    ]
    st.markdown("**BDI derivado — fórmula TCU Ac. 2622/2013**")
    st.caption(
        "**T_bruto**: alíquota CBS+IBS sobre o preço de venda. **Crédito (%)**: fração recuperável. "
        "**T_efetivo**: carga líquida após crédito + CSSL + IR."
        " **BDI**: markup total = (1 + overhead) / (1 − T_efetivo) − 1."
    )
    st.dataframe(preview_rows, width="stretch", hide_index=True)
    if st.button("Salvar cenário CBS/IBS", key=f"save-tax-scenario-{project_id}", type="primary"):
        payload_ts = scenario_preview.to_dict()
        for skill_id in ["06-resultado-financeiro"]:
            api_call(
                method="POST",
                path=f"/api/projects/{project_id}/overrides",
                base_url=base_url,
                payload={"skill_id": skill_id, "inputs": {"tax_scenario": payload_ts}},
                actor=actor,
            )
        st.success(f"Cenário {regime_labels[selected_regime_key]} salvo nos skills 06 e 08.")


def render_bdi_editor(base_url: str, project_id: str, actor: str, reference: dict) -> None:
    """Editor de BDI — Modo Legado (PRE_REFORMA) ou CBS/IBS (ADR-055)."""
    from concilium.domain.models.financial.bdi import (
        CENARIOS_TRIBUTARIOS,
        DEFAULT_BDI_TABELA,
        TaxRegimeVersion,
        TaxSimulationScenario,
        resolver_bdi_cbs_ibs,
    )

    try:
        current = api_call(method="GET", path=f"/api/projects/{project_id}/overrides", base_url=base_url, actor=actor)
    except Exception:
        current = {}
    skill06_current = (
        current.get("06-resultado-financeiro", {}) if isinstance(current.get("06-resultado-financeiro"), dict) else {}
    )
    saved_tax_scenario: dict = skill06_current.get("tax_scenario", {}) if isinstance(skill06_current, dict) else {}
    REGIME_LABELS = {
        "pre_reforma": "Pré-Reforma (PIS/COFINS/ISS vigente)",
        "transicao": "Transição 2026–2032 (CBS/IBS parcial)",
        "pleno_cbs_ibs": "Pleno CBS/IBS (2033+ / cenário prospectivo)",
    }
    regime_keys = list(REGIME_LABELS.keys())
    current_regime_val = saved_tax_scenario.get("regime_version", "pre_reforma")
    default_idx = regime_keys.index(current_regime_val) if current_regime_val in regime_keys else 0
    selected_regime_key = st.selectbox(
        "Regime tributário",
        options=regime_keys,
        format_func=lambda k: REGIME_LABELS[k],
        index=default_idx,
        key=f"bdi-regime-{project_id}",
    )
    selected_regime = TaxRegimeVersion(selected_regime_key)
    if selected_regime == TaxRegimeVersion.PRE_REFORMA:
        _render_bdi_pre_reforma(project_id, reference, current, skill06_current, base_url, actor, DEFAULT_BDI_TABELA)
        return
    cenario_base = CENARIOS_TRIBUTARIOS[selected_regime]
    _render_bdi_cbs_ibs(
        project_id,
        saved_tax_scenario,
        selected_regime,
        selected_regime_key,
        cenario_base,
        DEFAULT_BDI_TABELA,
        resolver_bdi_cbs_ibs,
        TaxSimulationScenario,
        REGIME_LABELS,
        base_url,
        actor,
    )


def _extract_cpu_ids(reference: dict) -> set[str]:
    cpu_ids: set[str] = set()
    if not isinstance(reference, dict):
        return cpu_ids

    def _add_cpu(value: object) -> None:
        if isinstance(value, str) and value.strip():
            cpu_ids.add(value.strip())

    cpus_block = reference.get("cpus")
    if isinstance(cpus_block, dict):
        for item in cpus_block.get("itens_eap", []):
            if isinstance(item, dict):
                _add_cpu(item.get("cpu_id"))

    return cpu_ids


def _cpu_prod_resolve(cpu: dict, prod_lookup: dict) -> float:
    """Resolves producao_horaria for a CPU."""
    prod_id = cpu.get("producao_id_ref")
    if prod_id and prod_id in prod_lookup:
        return prod_lookup[prod_id]
    return float(cpu.get("producao_horaria") or 0.0)


def _build_cpu_prod_lookup(cat: dict) -> dict[str, float]:
    """Builds producao_id -> valor_horario lookup from catalog."""
    lookup: dict[str, float] = {}
    for _p in cat.get("producoes") or cat.get("produtividades") or []:
        if isinstance(_p, dict):
            pid = _p.get("id") or _p.get("codigo")
            val = _p.get("valor_horario") or _p.get("producao_horaria")
            if pid and val is not None:
                lookup[str(pid)] = float(val)
    return lookup


def _build_resolved_cpus(
    cpu_ids: list | set, catalog_cpus_prod: dict, base_url: str, project_id: str, actor: str
) -> dict[str, dict]:
    """Resolves CPU dicts from snapshot or API fallback."""
    resolved: dict[str, dict] = {}
    for cpu_id in sorted(cpu_ids):
        if cpu_id in catalog_cpus_prod:
            resolved[cpu_id] = dict(catalog_cpus_prod[cpu_id])
        else:
            try:
                resolved[cpu_id] = api_call(
                    method="GET",
                    path=f"/api/projects/{project_id}/catalog/cpus/{cpu_id}",
                    base_url=base_url,
                    actor=actor,
                ) or {"codigo": cpu_id}
            except Exception:
                resolved[cpu_id] = {"codigo": cpu_id}
    return resolved


def _find_changed_cpus(edited_rows: list) -> list[dict]:
    """Returns rows where producao_horaria changed."""
    return [
        r
        for r in edited_rows
        if abs(float(r.get("producao_horaria_nova") or 0.0) - float(r.get("producao_horaria_base") or 0.0)) > 1e-9
    ]


def _save_cpu_productivity(edited: object, base_url: str, project_id: str, actor: str) -> None:
    """Handles saving changed CPU productivity values."""
    edited_rows = edited.to_dict("records") if hasattr(edited, "to_dict") else list(edited or [])  # type: ignore[union-attr]
    changed = _find_changed_cpus(edited_rows)
    if not changed:
        st.info("Nenhuma alteração detectada.")
        return
    errors: list[str] = []
    for row in changed:
        cpu_id = str(row["cpu_id"])
        try:
            api_call(
                method="POST",
                path=f"/api/projects/{project_id}/catalog/cpus/{cpu_id}",
                base_url=base_url,
                payload={"producao_horaria": float(row["producao_horaria_nova"])},
                actor=actor,
            )
        except Exception as exc:
            errors.append(f"{cpu_id}: {exc}")
    if errors:
        st.error(f"Erros ao salvar: {'; '.join(errors)}")
    else:
        st.success(f"Produtividade salva para {len(changed)} CPU(s). Re-execute o pipeline para aplicar.")


def _resolve_cpu_ids_with_fallback(reference: dict, base_url: str, project_id: str, actor: str) -> list:
    """Resolves cpu_ids from reference or EAP fallback."""
    cpu_ids = list(_extract_cpu_ids(reference))
    if not cpu_ids:
        eap_rows = _load_eap_items_for_planning(project_id, base_url, actor)
        cpu_ids = list({_extract_cpu_id_from_any_item(it) for it in eap_rows if _extract_cpu_id_from_any_item(it)})
    return cpu_ids


def _catalog_cpus_by_codigo(cat: dict) -> dict[str, dict]:
    """Returns a codigo->cpu dict from the catalog cpus list."""
    return {str(c.get("codigo") or ""): c for c in (cat.get("cpus") or []) if isinstance(c, dict) and c.get("codigo")}


def _process_comp_row(
    row: dict,
    orig_funcoes: dict,
    orig_equips: dict,
    orig_itens: dict,
    new_funcoes: list,
    new_equipamentos: list,
    new_composicao: list,
) -> None:
    """Classifies one edited composition row and appends to appropriate list."""
    tipo = str(row.get("tipo", ""))
    rid = str(row.get("id", ""))
    qty = float(row.get("quantidade") or 0.0)
    if tipo == "MÃO_OBRA":
        entry = dict(orig_funcoes.get(rid, {"funcao_id": rid}))
        entry["num_pessoas"] = max(0, int(round(qty)))
        new_funcoes.append(entry)
    elif tipo == "EQUIPAMENTO":
        entry = dict(orig_equips.get(rid, {"equip_id": rid}))
        entry["num_unidades"] = max(0, int(round(qty)))
        new_equipamentos.append(entry)
    else:
        entry = dict(orig_itens.get(rid, {"insumo_id": rid, "categoria_custo": tipo}))
        entry["coeficiente"] = qty
        new_composicao.append(entry)


def render_cpu_productivity_override(base_url: str, project_id: str, actor: str) -> None:
    """Override de produtividade das CPUs — edita apenas producao_horaria."""
    st.caption("Edite apenas a produção horária de cada CPU. Demais atributos são somente leitura.")
    try:
        reference = api_call(
            method="GET", path=f"/api/projects/{project_id}/benchmark-reference", base_url=base_url, actor=actor
        )
    except Exception:
        reference = {}
    cpu_ids = _resolve_cpu_ids_with_fallback(reference, base_url, project_id, actor)
    if not cpu_ids:
        st.info("Nenhuma CPU encontrada. Execute o pipeline ou adicione itens à EAP.")
        return
    _cat = reference.get("catalog") or {}
    catalog_cpus_prod = _catalog_cpus_by_codigo(_cat)
    prod_lookup = _build_cpu_prod_lookup(_cat)
    resolved = _build_resolved_cpus(cpu_ids, catalog_cpus_prod, base_url, project_id, actor)
    rows = [
        {
            "cpu_id": cpu_id,
            "descricao": resolved[cpu_id].get("descricao", ""),
            "unidade": resolved[cpu_id].get("unidade", ""),
            "producao_id_ref": resolved[cpu_id].get("producao_id_ref", "—"),
            "producao_horaria_base": _cpu_prod_resolve(resolved[cpu_id], prod_lookup),
            "producao_horaria_nova": _cpu_prod_resolve(resolved[cpu_id], prod_lookup),
        }
        for cpu_id in sorted(resolved)
    ]
    edited = st.data_editor(
        rows,
        width="stretch",
        hide_index=True,
        column_config={
            "cpu_id": st.column_config.TextColumn("CPU", disabled=True, width="medium"),
            "descricao": st.column_config.TextColumn("Descrição", disabled=True, width="large"),
            "unidade": st.column_config.TextColumn("Un.", disabled=True, width="small"),
            "producao_id_ref": st.column_config.TextColumn("Prod. ID", disabled=True, width="medium"),
            "producao_horaria_base": st.column_config.NumberColumn("Base (un/h)", disabled=True, format="%.2f"),
            "producao_horaria_nova": st.column_config.NumberColumn(
                "✏️ Nova prod./hora", format="%.2f", step=0.5, min_value=0.0
            ),
        },
        disabled=["cpu_id", "descricao", "unidade", "producao_id_ref", "producao_horaria_base"],
        key=f"cpu-prod-editor-{project_id}",
    )
    if st.button("Salvar produtividade das CPUs", key=f"save-cpu-prod-{project_id}", type="primary"):
        _save_cpu_productivity(edited, base_url, project_id, actor)


def _cpu_insumo_info(insumo_id: str, insumos_cat: dict) -> tuple[str, float]:
    """Returns (descricao, preco_unitario) for an insumo ID."""
    i = insumos_cat.get(str(insumo_id), {})
    return (i.get("descricao") or insumo_id, float(i.get("preco_unitario") or 0))


def _insumos_dict_from_list(items: list) -> dict:
    """Builds codigo->insumo dict from a list of insumo dicts."""
    return {str(i.get("codigo") or i.get("id") or ""): i for i in items if isinstance(i, dict)}


def _fetch_insumos_from_catalog_api(project_id: str, base_url: str, actor: str) -> list:
    """Fetches insumos from the catalog API. Returns list or [] on failure."""
    try:
        _proj_meta = api_call("GET", f"/api/projects/{project_id}", base_url=base_url, actor=actor)
        _ctx_id = _proj_meta.get("contexto_id", "")
        _ctx = api_call("GET", f"/api/contextos/{_ctx_id}/versions", base_url=base_url, actor=actor)
        _current_v = _ctx.get("versions", [{}])[-1] if _ctx.get("versions") else {}
        _cat_id = _current_v.get("catalogo_id") or _ctx_id
        _ins_resp = api_call(
            "GET", f"/api/catalogs/{_cat_id}/insumos", params={"limit": 500}, base_url=base_url, actor=actor
        )
        return _ins_resp.get("items") or []
    except Exception:
        return []


def _load_cpu_insumos_catalog(reference: dict, base_url: str, project_id: str, actor: str) -> dict:
    """Loads insumos catalog dict from snapshot or API fallback."""
    raw = (reference.get("catalog") or {}).get("insumos") or []
    insumos_cat = _insumos_dict_from_list(raw)
    if not insumos_cat:
        insumos_cat = _insumos_dict_from_list(_fetch_insumos_from_catalog_api(project_id, base_url, actor))
    return insumos_cat


def _resolve_catalog_id_for_project(project_id: str, base_url: str, actor: str) -> str:
    """Resolve catalog_id currently associated to the project's context."""
    try:
        project_meta = api_call("GET", f"/api/projects/{project_id}", base_url=base_url, actor=actor)
        contexto_id = str(project_meta.get("contexto_id") or "").strip()
        if not contexto_id:
            return ""
        ctx = api_call("GET", f"/api/contextos/{contexto_id}/versions", base_url=base_url, actor=actor)
        versions = ctx.get("versions") or []
        if isinstance(versions, list) and versions:
            return str((versions[-1] or {}).get("catalogo_id") or contexto_id)
        return contexto_id
    except Exception:
        return ""


def _fetch_cpu_from_master_catalog(cpu_id: str, catalog_id: str, base_url: str, actor: str) -> dict:
    """Fetch CPU from master catalog API. Returns {} on failure."""
    if not catalog_id:
        return {}
    try:
        payload = api_call(
            method="GET",
            path=f"/api/catalogs/{catalog_id}/cpus/{cpu_id}",
            base_url=base_url,
            actor=actor,
        )
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _cpu_equipe_parts(cpu: dict) -> tuple[list, list, list]:
    """Extracts (funcoes, equipamentos, composicao_itens) from a CPU dict."""
    equipe_block = cpu.get("equipe")
    if not isinstance(equipe_block, dict):
        equipe_block = (
            cpu.get("composicao_padrao_equipe") if isinstance(cpu.get("composicao_padrao_equipe"), dict) else {}
        )
    funcoes = list((equipe_block or {}).get("funcoes") or [])
    equipamentos = list((equipe_block or {}).get("equipamentos") or [])
    composicao_itens = list(cpu.get("composicao_itens") or cpu.get("composicao_completa") or [])
    return funcoes, equipamentos, composicao_itens


def _build_cpu_comp_rows(cpu: dict, insumos_cat: dict) -> list[dict]:
    """Builds the composition rows list for a CPU."""
    funcoes, equipamentos, composicao_itens = _cpu_equipe_parts(cpu)
    rows: list[dict] = []
    for f in funcoes:
        fid = f.get("funcao_id", "")
        desc, preco = _cpu_insumo_info(fid, insumos_cat)
        rows.append(
            {
                "remover": False,
                "tipo": "MÃO_OBRA",
                "id": fid,
                "descricao": desc,
                "quantidade": float(f.get("num_pessoas") or 0),
                "custo_unit (R$/mês)": preco,
                "custo_total (R$/mês)": round(preco * float(f.get("num_pessoas") or 0), 2),
            }
        )
    for e in equipamentos:
        eid = e.get("equip_id", "")
        desc, preco = _cpu_insumo_info(eid, insumos_cat)
        rows.append(
            {
                "remover": False,
                "tipo": "EQUIPAMENTO",
                "id": eid,
                "descricao": desc,
                "quantidade": float(e.get("num_unidades") or 0),
                "custo_unit (R$/mês)": preco,
                "custo_total (R$/mês)": round(preco * float(e.get("num_unidades") or 0), 2),
            }
        )
    for item in composicao_itens:
        iid = item.get("insumo_id", "")
        desc, preco = _cpu_insumo_info(iid, insumos_cat)
        coef = float(item.get("coeficiente") or 0)
        rows.append(
            {
                "remover": False,
                "tipo": item.get("categoria_custo", "MATERIAL"),
                "id": iid,
                "descricao": desc,
                "quantidade": coef,
                "custo_unit (R$/mês)": preco,
                "custo_total (R$/mês)": round(preco * coef, 2),
            }
        )
    return rows


def _save_cpu_comp(
    edited: object,
    cpu: dict,
    project_id: str,
    cpu_id: str,
    base_url: str,
    actor: str,
) -> None:
    """Handles saving the edited CPU composition."""
    edited_rows = edited.to_dict("records") if hasattr(edited, "to_dict") else list(edited or [])  # type: ignore[union-attr]
    funcoes, equipamentos, composicao_itens = _cpu_equipe_parts(cpu)
    orig_funcoes = {f.get("funcao_id"): f for f in funcoes}
    orig_equips = {e.get("equip_id"): e for e in equipamentos}
    orig_itens = {i.get("insumo_id"): i for i in composicao_itens}
    new_funcoes: list[dict] = []
    new_equipamentos: list[dict] = []
    new_composicao: list[dict] = []
    for row in edited_rows:
        if row.get("remover"):
            continue
        _process_comp_row(row, orig_funcoes, orig_equips, orig_itens, new_funcoes, new_equipamentos, new_composicao)
    payload = {"equipe": {"funcoes": new_funcoes, "equipamentos": new_equipamentos}, "composicao_itens": new_composicao}
    try:
        api_call(
            method="POST",
            path=f"/api/projects/{project_id}/catalog/cpus/{cpu_id}",
            base_url=base_url,
            payload=payload,
            actor=actor,
        )
        st.success(f"Composição salva para {cpu_id}.")
    except Exception as exc:
        st.error(f"Erro ao salvar {cpu_id}: {exc}")


def _render_cpu_comp_expander(
    cpu_id: str,
    cpu: dict,
    insumos_cat: dict,
    project_id: str,
    base_url: str,
    actor: str,
) -> None:
    """Renders the composition editor expander for one CPU."""
    descricao = cpu.get("descricao", "")
    funcoes, equipamentos, composicao_itens = _cpu_equipe_parts(cpu)
    _comp_cats = sorted({it.get("categoria_custo", "?") for it in composicao_itens})
    _parts: list[str] = []
    if funcoes:
        _parts.append(f"MO:{len(funcoes)}")
    if equipamentos:
        _parts.append(f"EQ:{len(equipamentos)}")
    if composicao_itens:
        _parts.append(f"INS:{len(composicao_itens)}")
    if _comp_cats:
        _parts.extend(_comp_cats)
    _badge = " · ".join(_parts) if _parts else "sem composição"
    with st.expander(f"{cpu_id} — {descricao[:60]}  `{_badge}`", expanded=False):
        rows = _build_cpu_comp_rows(cpu, insumos_cat)
        if not rows:
            st.caption(
                "Esta CPU não possui composição de insumos registrada no catálogo. "
                "Para adicionar, edite o arquivo `config/catalogos/{id}/cpus/{cpu_id}.json` "
                "ou use a página **Catálogo** → aba CPUs → Editar composição."
            )
            return
        edited = st.data_editor(
            rows,
            width="stretch",
            hide_index=True,
            column_config={
                "remover": st.column_config.CheckboxColumn("🗑️", width="small"),
                "tipo": st.column_config.TextColumn("Categoria", disabled=True, width="medium"),
                "id": st.column_config.TextColumn("ID", disabled=True, width="medium"),
                "descricao": st.column_config.TextColumn("Descrição", disabled=True, width="large"),
                "quantidade": st.column_config.NumberColumn("✏️ Qtd", format="%.2f", step=0.5, min_value=0.0),
                "custo_unit (R$/mês)": st.column_config.NumberColumn("Custo Unit. (R$)", disabled=True, format="%.2f"),
                "custo_total (R$/mês)": st.column_config.NumberColumn(
                    "Custo Total (R$/mês)", disabled=True, format="%.2f"
                ),
            },
            disabled=["tipo", "id", "descricao", "custo_unit (R$/mês)", "custo_total (R$/mês)"],
            key=f"cpu-comp-editor-{project_id}-{cpu_id}",
        )
        if st.button(f"Salvar composição — {cpu_id}", key=f"save-comp-{project_id}-{cpu_id}", type="primary"):
            _save_cpu_comp(edited, cpu, project_id, cpu_id, base_url, actor)


def render_cpu_composition_override(base_url: str, project_id: str, actor: str) -> None:
    """Override da composição das CPUs — mão de obra, equipamentos e materiais."""
    st.caption(
        "Edite as quantidades de mão de obra, equipamentos e materiais por CPU. "
        "CPUs deduplicadas — alterações aqui aplicam-se a **todas** as atividades que usam essa CPU. IDs são somente leitura."  # noqa: E501
    )
    try:
        reference = api_call(
            method="GET", path=f"/api/projects/{project_id}/benchmark-reference", base_url=base_url, actor=actor
        )
    except Exception:
        reference = {}
    cpu_ids = _resolve_cpu_ids_with_fallback(reference, base_url, project_id, actor)
    if not cpu_ids:
        st.info("Nenhuma CPU encontrada. Execute o pipeline ou adicione itens à EAP.")
        return
    insumos_cat = _load_cpu_insumos_catalog(reference, base_url, project_id, actor)
    catalog_cpus = _catalog_cpus_by_codigo(reference.get("catalog") or {})
    catalog_id = _resolve_catalog_id_for_project(project_id, base_url, actor)
    master_cache: dict[str, dict] = {}
    for cpu_id in sorted(cpu_ids):
        cpu: dict = dict(catalog_cpus.get(cpu_id) or {})

        # Snapshot de referência pode trazer apenas INS (sem equipe/equipamentos).
        # Nesses casos, reidrata via endpoint resolvido do projeto.
        funcoes, equipamentos, _ = _cpu_equipe_parts(cpu)
        needs_hydration = (not cpu) or (not funcoes and not equipamentos)
        if needs_hydration:
            try:
                resolved = (
                    api_call(
                        method="GET",
                        path=f"/api/projects/{project_id}/catalog/cpus/{cpu_id}",
                        base_url=base_url,
                        actor=actor,
                    )
                    or {}
                )
                if isinstance(resolved, dict):
                    cpu = {**cpu, **resolved} if cpu else resolved
            except Exception:
                if not cpu:
                    cpu = {"codigo": cpu_id}

        # Se ainda faltar equipe, consulta catálogo mestre do contexto explicitamente.
        funcoes, equipamentos, _ = _cpu_equipe_parts(cpu)
        if not funcoes and not equipamentos:
            if cpu_id not in master_cache:
                master_cache[cpu_id] = _fetch_cpu_from_master_catalog(cpu_id, catalog_id, base_url, actor)
            master_cpu = master_cache.get(cpu_id) or {}
            if master_cpu:
                cpu = {**cpu, **master_cpu}

        if not cpu:
            st.warning(f"CPU '{cpu_id}' não encontrada.")
            continue
        _render_cpu_comp_expander(cpu_id, cpu, insumos_cat, project_id, base_url, actor)


def render_ops_audit_tab(base_url: str, project_id: str, actor: str) -> None:
    """Tab: Ops Audit - Pipeline monitor + history + audit trail."""
    with st.expander("📡 Monitor de Execuções", expanded=False):
        render_pipeline_monitor(base_url, project_id, actor, context="audit")
    with st.expander("📋 Histórico de execuções", expanded=False):
        render_history(base_url, project_id, actor, context="audit")
    with st.expander("🔍 Audit Trail", expanded=False):
        render_audit(base_url, project_id, actor)


def _render_version_tree_lines(
    node: str | None, version_meta: dict, children: dict, prefix: str = "", is_last: bool = True
) -> list[str]:
    """Recursively builds version tree display lines."""
    kids = sorted(children.get(node, []))
    lines: list[str] = []
    if node is not None:
        run = version_meta.get(node, {})
        ts = str(run.get("started_at") or "")[:16].replace("T", " ")
        status = run.get("status", "")
        status_icon = "[OK]" if status == "OK" else ("[ERRO]" if status == "ERRO" else "[--]")
        connector = "└─" if is_last else "├─"
        lines.append(f"{prefix}{connector} {status_icon} {node} — {ts or '–'}")
        child_prefix = prefix + ("   " if is_last else "│  ")
    else:
        child_prefix = ""
    for i, kid in enumerate(kids):
        lines.extend(_render_version_tree_lines(kid, version_meta, children, child_prefix, i == len(kids) - 1))
    return lines


def _render_compare_tree(project_id: str, versions: list, base_url: str, actor: str) -> None:
    """Renders version lineage tree inside an expander."""
    try:
        runs = api_call(method="GET", path=f"/api/projects/{project_id}/runs", base_url=base_url, actor=actor).get(
            "items", []
        )
        version_meta = {r.get("version"): r for r in runs if r.get("version")}
        children: dict[str | None, list[str]] = {}
        for v in versions:
            run = version_meta.get(v, {})
            parent = run.get("base_version") or None
            children.setdefault(parent, []).append(v)
        tree_lines = _render_version_tree_lines(None, version_meta, children)
        if tree_lines:
            with st.expander("📜 Linhagem de versões", expanded=False):
                st.code("\n".join(tree_lines), language=None)
    except Exception:
        pass


def _do_compare(project_id: str, left: str, right: str, base_url: str, actor: str) -> None:
    """Executes comparison and shows delta metrics."""
    if not st.button("Comparar", type="secondary"):
        return
    try:
        result = api_call(
            method="POST",
            path=f"/api/projects/{project_id}/compare",
            base_url=base_url,
            payload={"left_version": left, "right_version": right},
            actor=actor,
        )
    except RuntimeError as exc:
        err = str(exc)
        if "sem canônico" in err or "400" in err:
            st.warning(
                "Uma das versões selecionadas ainda não possui dados de pipeline executados. "
                "Execute o pipeline nessa versão antes de comparar."
            )
        else:
            st.error(f"Erro ao comparar versões: {exc}")
        return
    deltas = result.get("deltas", {})
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Delta custo total",
        f"{deltas.get('custo_total', 0.0):,.2f}",
        delta=f"{deltas.get('custo_total', 0.0):,.2f}",
        delta_color="inverse",
    )
    col2.metric(
        "Delta margem %", f"{deltas.get('margem_pct', 0.0):,.2f}", delta=f"{deltas.get('margem_pct', 0.0):,.2f}"
    )
    col3.metric(
        "Delta PE deficit",
        f"{deltas.get('pe_deficit_items', 0.0):,.0f}",
        delta=f"{deltas.get('pe_deficit_items', 0.0):,.0f}",
        delta_color="inverse",
    )
    st.subheader("Deltas detalhados")
    st.dataframe([{"indicador": k, "delta": v} for k, v in deltas.items()], width="stretch")
    render_mapping_table("Comparação de versões", result)


def render_compare(base_url: str, project: dict, actor: str) -> None:
    """Render version comparison."""
    st.subheader("🔀 Comparar versões")
    project_id = project["project_id"]
    try:
        versions = api_call(
            method="GET", path=f"/api/projects/{project_id}/versions", base_url=base_url, actor=actor
        ).get("items", [])
    except Exception as exc:
        st.error(f"Falha ao carregar versões: {exc}")
        return
    if len(versions) < 2:
        st.info("São necessárias ao menos duas versões para comparar.")
        return
    _render_compare_tree(project_id, versions, base_url, actor)
    left = st.selectbox("Versão base (esquerda)", options=versions, index=0)
    right = st.selectbox("Versão comparada (direita)", options=versions, index=len(versions) - 1)
    _do_compare(project_id, left, right, base_url, actor)


def render_audit(base_url: str, project_id: str, actor: str) -> None:
    """Render audit trail — paginated."""
    cache_key = f"audit-rows-{project_id}"
    col_q, col_reload = st.columns([5, 1])
    q = col_q.text_input(
        "Buscar evento ou actor",
        key=f"audit-q-{project_id}",
        label_visibility="collapsed",
        placeholder="Filtrar auditoria…",
    )
    if col_reload.button("↺", key=f"audit-reload-{project_id}"):
        st.session_state.pop(cache_key, None)

    if cache_key not in st.session_state:
        try:
            st.session_state[cache_key] = api_call(
                method="GET",
                path=f"/api/projects/{project_id}/audit",
                base_url=base_url,
                params={"limit": 1000},
                actor=actor,
            ).get("items", [])
        except Exception as exc:
            msg = str(exc)
            if "404" in msg or "Not Found" in msg:
                st.info("Audit trail indisponivel para este ambiente/API.")
            else:
                st.warning(f"Audit trail indisponivel nesta API: {exc}")
            return

    rows = st.session_state[cache_key]
    if not rows:
        st.info("Sem eventos de auditoria para este projeto.")
        return

    if q:
        q_l = q.lower()
        rows = [r for r in rows if q_l in str(r).lower()]

    render_paginated_table(rows, page_key=f"audit-page-{project_id}", label="eventos")


def _render_md_preview_for(
    base_url: str,
    project_id: str,
    version: str | None,
    actor: str,
    md_filename: str,
    pdf_filename: str,
) -> None:
    """Renderiza preview de um arquivo .md com botões de download .md e .pdf."""
    try:
        artifacts = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/artifacts",
            base_url=base_url,
            params={"version": version} if version else None,
            actor=actor,
        )
    except Exception as exc:
        st.info(f"Artefatos não disponíveis: {exc}")
        return

    outputs = list(artifacts.get("outputs") or [])
    if md_filename not in outputs:
        st.info(f"`{md_filename}` não encontrado nos outputs desta versão.")
        return

    try:
        payload = fetch_artifact_bytes(base_url, project_id, "outputs", md_filename, version, actor)
        text = payload.decode("utf-8", errors="replace")
    except Exception as exc:
        st.warning(f"Falha ao carregar {md_filename}: {exc}")
        return

    col_md, col_pdf = st.columns(2)
    with col_md:
        render_download_button(
            base_url,
            project_id,
            "outputs",
            md_filename,
            version,
            actor,
            f"⬇️ {md_filename}",
            key=f"prev-dl-md-{project_id}-{md_filename}",
            use_container_width=True,
        )
    with col_pdf:
        if pdf_filename in outputs:
            render_download_button(
                base_url,
                project_id,
                "outputs",
                pdf_filename,
                version,
                actor,
                f"⬇️ {pdf_filename}",
                key=f"prev-dl-pdf-{project_id}-{pdf_filename}",
                use_container_width=True,
            )
        else:
            st.caption(f"`{pdf_filename}` não gerado nesta versão.")

    _render_md_with_mermaid(text)
    with st.expander("Ver fonte Markdown", expanded=False):
        st.code(text, language="markdown")


def render_artifacts_tab(base_url: str, project_id: str, project: dict, actor: str) -> None:
    """Tab: Artifacts - Version artifacts downloader."""
    st.subheader("📦 Artefatos por Versão")
    versions = project.get("versions") or []
    try:
        live_versions = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/versions",
            base_url=base_url,
            actor=actor,
        ).get("items", [])
        if isinstance(live_versions, list) and live_versions:
            versions = live_versions
    except Exception:
        pass
    version_selected = st.selectbox(
        "Versão",
        options=versions if versions else [project.get("current_version") or "v1"],
        key="artifacts-version-select",
    )
    try:
        artifacts = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/artifacts",
            base_url=base_url,
            params={"version": version_selected},
            actor=actor,
        )
        outputs = artifacts.get("outputs", [])
        intermediate = artifacts.get("intermediate", [])

        col_artifact_output, col_artifact_intermediate = st.columns(2)
        with col_artifact_output:
            st.caption(f"**Outputs** ({len(outputs)})")
            if outputs:
                for filename in outputs:
                    render_download_button(
                        base_url,
                        project_id,
                        "outputs",
                        filename,
                        version_selected,
                        actor,
                        f"📥 {filename}",
                        use_container_width=True,
                    )
            else:
                st.caption("Sem outputs")

        with col_artifact_intermediate:
            st.caption(f"**Intermediários** ({len(intermediate)})")
            if intermediate:
                for filename in intermediate:
                    render_download_button(
                        base_url,
                        project_id,
                        "intermediate",
                        filename,
                        version_selected,
                        actor,
                        f"📥 {filename}",
                        use_container_width=True,
                    )
            else:
                st.caption("Sem intermediários")
    except Exception as exc:
        st.error(f"Falha ao carregar artefatos: {exc}")
    st.divider()
    # ── Pré-visualizações colapsáveis ─────────────────────────────────────
    with st.expander("📝 Relatório Analítico", expanded=False):
        _render_md_preview_for(base_url, project_id, version_selected, actor, "relatorio.md", "relatorio.pdf")
    with st.expander("🔢 Memorial BDI", expanded=False):
        _render_md_preview_for(base_url, project_id, version_selected, actor, "memorial_bdi.md", "memorial_bdi.pdf")
