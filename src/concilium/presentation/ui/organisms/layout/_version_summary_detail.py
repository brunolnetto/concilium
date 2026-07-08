"""Camada de apresentação — layout Streamlit (parte extraída de layout.py)."""

from __future__ import annotations

import streamlit as st

from ...infra.api import api_call
from ._charts import _format_currency, _format_int, _format_percent


def _collect_last_run(base_url: str, project_id: str, actor: str) -> tuple[dict, dict]:
    """Returns (last_run, summary) from the runs API."""
    try:
        runs = api_call(method="GET", path=f"/api/projects/{project_id}/runs", base_url=base_url, actor=actor).get(
            "items", []
        )
    except Exception:
        runs = []
    raw_last = runs[0] if runs else {}
    last_run = raw_last if isinstance(raw_last, dict) else {}
    raw_summary = last_run.get("summary")
    summary = raw_summary if isinstance(raw_summary, dict) else {}
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


def _fetch_version_runs(base_url: str, project_id: str, actor: str, selected: str) -> list:
    """Busca as runs da API e filtra apenas as pertencentes à versão selecionada."""
    try:
        runs = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/runs",
            base_url=base_url,
            actor=actor,
        ).get("items", [])
    except Exception:
        runs = []
    return [r for r in runs if r.get("version") == selected]


def _render_version_last_run_metrics(last: dict) -> None:
    """Renderiza as métricas (status, timestamp, custo, margem, déficit P.E.) da última run."""
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


def _render_version_runs_table(version_runs: list) -> None:
    """Renderiza a tabela de runs da versão selecionada."""
    import pandas as pd

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


def _render_version_runs_section(version_runs: list, selected: str) -> None:
    """Renderiza o bloco de runs da versão: mensagem vazia, métricas da última run e tabela."""
    if not version_runs:
        st.info(f"Nenhuma execução registrada para a versão **{selected}**.")
        return
    _render_version_last_run_metrics(version_runs[0])
    _render_version_runs_table(version_runs)


def _render_version_artifacts_caption(base_url: str, project_id: str, actor: str, selected: str) -> None:
    """Busca e renderiza a legenda de artefatos gerados para a versão selecionada."""
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


def render_version_detail(base_url: str, project: dict, actor: str) -> None:
    """Render descriptive per-version detail panel — runs, KPIs e artefatos da versão selecionada."""
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

    version_runs = _fetch_version_runs(base_url, project_id, actor, selected)
    _render_version_runs_section(version_runs, selected)
    _render_version_artifacts_caption(base_url, project_id, actor, selected)


