"""Camada de apresentação — layout Streamlit (parte extraída de layout.py)."""

from __future__ import annotations

import streamlit as st

from ...infra.api import api_call
from ...molecules.common import render_paginated_table
from ._charts import _render_cube_projection_chart


def _cube_face_label(v: dict, face_options: dict[str, str], key: str) -> str:
    """Resolve o rótulo de exibição de uma face do cubo: label do contrato > opção existente > chave."""
    return str(v.get("label") or face_options.get(key) or key)


def _parse_cube_face_contract(
    contract: dict, face_options: dict[str, str], granularidade_options: list[str]
) -> tuple[dict[str, str], dict[str, dict[str, object]], list[str]]:
    """Extrai face_options/contract_faces/granularidade_options de um contrato de cubo já obtido."""
    contract_faces: dict[str, dict[str, object]] = {}
    raw_faces = contract.get("faces") if isinstance(contract, dict) else None
    if isinstance(raw_faces, dict):
        contract_faces = {k: v for k, v in raw_faces.items() if isinstance(v, dict)}
        face_options = {k: _cube_face_label(v, face_options, k) for k, v in contract_faces.items()}
    raw_gran = contract.get("granularidades") if isinstance(contract, dict) else None
    if isinstance(raw_gran, list) and raw_gran:
        granularidade_options = [str(g) for g in raw_gran]
    return face_options, contract_faces, granularidade_options


def _fetch_cube_face_contract(
    base_url: str, project_id: str, actor: str, face_options: dict[str, str]
) -> tuple[dict[str, str], dict[str, dict[str, object]], list[str]]:
    """Busca o contrato de faces/granularidades do cubo analítico, com fallback silencioso."""
    granularidade_options = ["semana", "mes", "bimestre", "trimestre", "semestre", "ano"]
    contract_faces: dict[str, dict[str, object]] = {}
    try:
        contract = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/cubo-analitico/projecao/contrato",
            base_url=base_url,
            actor=actor,
        )
        face_options, contract_faces, granularidade_options = _parse_cube_face_contract(
            contract, face_options, granularidade_options
        )
    except Exception:
        contract_faces = {}
    return face_options, contract_faces, granularidade_options


def _render_cube_face_and_gran_widgets(
    project_id: str, face_options: dict[str, str], granularidade_options: list[str]
) -> tuple[str, str, int]:
    """Renderiza os widgets de face/granularidade/top-N com layout dependente da face atual."""
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
    return face, granularidade, top_n


def _render_cube_filter_widgets(project_id: str, face: str) -> tuple[str, str, str]:
    """Renderiza apenas os filtros (categoria/componente/atividade) relevantes à face selecionada."""
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
    return categoria, componente, atividade_id


def _render_cube_optional_expander(
    project_id: str, face: str, current_face_spec: dict[str, object]
) -> tuple[str, str, float, float]:
    """Renderiza o expander 'Opcional' com measure profile, aggregation mode e thresholds ABC."""
    raw_measure_options = current_face_spec.get("measure_profiles")
    raw_agg_options = current_face_spec.get("aggregation_modes")
    face_measure_options = raw_measure_options if isinstance(raw_measure_options, list) else None
    face_agg_options = raw_agg_options if isinstance(raw_agg_options, list) else None

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
    return measure_profile, aggregation_mode, abc_threshold_a, abc_threshold_b


def _build_cube_projection_params(
    selected_version: str,
    face: str,
    granularidade: str,
    categoria: str,
    componente: str,
    atividade_id: str,
    top_n: int,
    measure_profile: str,
    aggregation_mode: str,
    abc_threshold_a: float,
    abc_threshold_b: float,
) -> dict[str, object]:
    """Monta os params da requisição de projeção do cubo, aplicando overrides da face diesel."""
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
    return {k: v for k, v in params.items() if v is not None and v != ""}


def _render_cube_diesel_metrics(rows: list, granularidade: str) -> None:
    """Renderiza métricas de dimensionamento de tanque para a face diesel_temporal."""
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


def _render_cube_totals_metrics(totals: dict) -> None:
    """Renderiza as métricas de totais (preço de venda, custo direto, tributos)."""
    c1, c2, c3 = st.columns(3)
    c1.metric("Preço de venda", f"R$ {float(totals.get('total_preco_venda', 0.0)):,.0f}")
    c2.metric("Custo direto", f"R$ {float(totals.get('total_custo_direto', 0.0)):,.0f}")
    c3.metric("Tributos", f"R$ {float(totals.get('total_tributos', 0.0)):,.0f}")


def _render_cube_rows_output(
    face: str,
    chart_hint: str,
    rows: list,
    columns_meta: list,
    operator_meta: dict,
    unit_type: str,
    project_id: str,
) -> None:
    """Renderiza gráfico, esquema, metadados e tabela paginada para as rows da projeção."""
    if not rows:
        st.info("Sem dados para a combinação de filtros selecionada.")
        return

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
    face_options, contract_faces, granularidade_options = _fetch_cube_face_contract(
        base_url, project_id, actor, face_options
    )

    face, granularidade, top_n = _render_cube_face_and_gran_widgets(project_id, face_options, granularidade_options)
    categoria, componente, atividade_id = _render_cube_filter_widgets(project_id, face)

    raw_face_spec = contract_faces.get(face)
    current_face_spec = raw_face_spec if isinstance(raw_face_spec, dict) else {}
    measure_profile, aggregation_mode, abc_threshold_a, abc_threshold_b = _render_cube_optional_expander(
        project_id, face, current_face_spec
    )

    params = _build_cube_projection_params(
        selected_version,
        face,
        granularidade,
        categoria,
        componente,
        atividade_id,
        top_n,
        measure_profile,
        aggregation_mode,
        abc_threshold_a,
        abc_threshold_b,
    )
    _fetch_and_render_cube_projection(base_url, project_id, actor, params, face, granularidade)


def _fetch_and_render_cube_projection(
    base_url: str, project_id: str, actor: str, params: dict[str, object], face: str, granularidade: str
) -> None:
    """Consulta a projeção do cubo e renderiza métricas/gráfico/tabela, com fallback de erro."""
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
            _render_cube_diesel_metrics(rows, granularidade)
        else:
            _render_cube_totals_metrics(totals)

        _render_cube_rows_output(face, chart_hint, rows, columns_meta, operator_meta, unit_type, project_id)
    except Exception as exc:
        st.warning(f"Falha ao consultar projeção do cubo analítico: {exc}")


