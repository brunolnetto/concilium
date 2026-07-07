"""Side effects de skills: persistência de artefatos, relatórios, gráficos e helpers de insumos."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .helpers.insumos import dedup_insumos, ingest_insumos, load_insumos_subdir
from .helpers.serialization import json_default
from .reports.executive_summary import render_resumo_executivo
from .reports.financial_report_markdown import render_financial_report_markdown
from .reports.financial_report_pdf import render_financial_report_pdf
from .reports.memorial_bdi_markdown import render_memorial_bdi_markdown
from .reports.pdf_renderer import render_markdown_pdf
from .visualizations.png_bundle import build_visualization_png_files

if TYPE_CHECKING:
    from concilium.application.services.project.project_repository import ProjectHandle
    from concilium.application.skills.base import SkillResult


def _json_default(obj: object) -> object:
    return json_default(obj)


def _ingest_insumos(data: object, insumos: list) -> None:
    ingest_insumos(data, insumos)


def _load_insumos_subdir(sub: Path, insumos: list) -> None:
    load_insumos_subdir(sub, insumos)


def _dedup_insumos(insumos: list) -> list:
    return dedup_insumos(insumos)


def _save_memorial_bdi_files(
    result: SkillResult, project: ProjectHandle, v: str, gerar_md: bool, gerar_pdf: bool
) -> None:
    memorial_bdi_json = getattr(result, "memorial_bdi_json", None)
    if not memorial_bdi_json:
        return
    try:
        project.save_intermediate_file("memorial_bdi.json", memorial_bdi_json, v)
        if gerar_md or gerar_pdf:
            memorial_dict = json.loads(memorial_bdi_json.decode("utf-8"))
            md_memorial = render_memorial_bdi_markdown(memorial_dict)
            if gerar_md:
                project.save_output_file(md_memorial.encode("utf-8"), v, "memorial_bdi.md")
            if gerar_pdf:
                proj_nome = (memorial_dict.get("meta") or {}).get("projeto", "")
                pdf_bytes = render_markdown_pdf(
                    md_memorial,
                    f"Memorial BDI - {proj_nome}",
                    image_provider=lambda file_name: _load_output_image_bytes(project, v, file_name),
                )
                if pdf_bytes:
                    project.save_output_file(pdf_bytes, v, "memorial_bdi.pdf")
    except Exception:
        pass


def _save_relatorio_graficos_files(
    rel_dict: dict,
    canonical: object | None,
    project: ProjectHandle,
    v: str,
    gerar_md: bool,
    gerar_pdf: bool,
    gerar_pngs: bool = True,
) -> list[str]:
    if not (gerar_md or gerar_pdf) or not gerar_pngs:
        return []
    graficos = rel_dict.get("GRAFICOS", {}) if isinstance(rel_dict.get("GRAFICOS", {}), dict) else {}
    if not graficos and canonical is None:
        return []

    try:
        png_docs = build_visualization_png_files(rel_dict, canonical=canonical)
    except Exception:
        return []
    if png_docs:
        for fname, png_bytes in png_docs.items():
            project.save_output_file(png_bytes, v, fname)
        return sorted(png_docs.keys())

    # Não gerar mais fallback grafico_*.md/.pdf: o contrato de saída é PNG.
    return []


def _append_png_gallery(md_content: str, png_files: list[str]) -> str:
    if not png_files:
        return md_content
    lines = [md_content.rstrip(), "", "## Graficos Gerados", ""]
    for file_name in sorted(png_files):
        lines.append(f"### {file_name}")
        lines.append(f"![{file_name}]({file_name})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _load_output_image_bytes(project: ProjectHandle, v: str, file_name: str) -> bytes | None:
    try:
        return project.load_output_file(v, file_name)
    except Exception:
        return None


def _resolve_relatorio_canonical(result: SkillResult, project: ProjectHandle, v: str) -> Any:
    """Resolve o canônico do resultado, ou carrega do project como fallback."""
    canonical = getattr(result, "canonical", None)
    if canonical is not None:
        return canonical
    try:
        return project.load_canonical(v)
    except Exception:
        return None


def _save_relatorio_md_outputs(rel_dict: dict, canonical: Any, project: ProjectHandle, v: str, md_content: str) -> None:
    """Salva relatorio.md e resumo_executivo.md (ADR-093 D5)."""
    project.save_output_file(md_content.encode("utf-8"), v, "relatorio.md")
    try:
        resumo_md = render_resumo_executivo(rel_dict, canonical=canonical)
        project.save_output_file(resumo_md.encode("utf-8"), v, "resumo_executivo.md")
    except Exception:  # pragma: no cover
        pass


def _resolve_relatorio_proj_nome(rel_dict: dict) -> str:
    """Prioridade: meta.projeto → resumo.projeto → fallback genérico."""
    return (
        (rel_dict.get("meta") or {}).get("projeto")
        or (rel_dict.get("resumo") or {}).get("projeto")
        or "Relatório Financeiro"
    )


def _save_relatorio_pdf_output(rel_dict: dict, project: ProjectHandle, v: str) -> None:
    """Renderiza e salva relatorio.pdf, com imagens resolvidas via project."""
    proj_nome = _resolve_relatorio_proj_nome(rel_dict)

    def provider(file_name):
        return _load_output_image_bytes(project, v, file_name)

    pdf_bytes = render_financial_report_pdf(rel_dict, proj_nome, image_provider=provider)
    if pdf_bytes:
        project.save_output_file(pdf_bytes, v, "relatorio.pdf")


def _save_relatorio_files(
    result: SkillResult, project: ProjectHandle, v: str, gerar_md: bool, gerar_pdf: bool, gerar_pngs: bool = True
) -> None:
    relatorio = getattr(result, "relatorio", None)
    if not relatorio or not (gerar_md or gerar_pdf):
        return
    try:
        rel_dict = json.loads(json.dumps(relatorio, default=_json_default))
        canonical = _resolve_relatorio_canonical(result, project, v)
        md_content = render_financial_report_markdown(rel_dict, canonical=canonical)
        png_files = _save_relatorio_graficos_files(
            rel_dict, canonical, project, v, gerar_md, gerar_pdf, gerar_pngs=gerar_pngs
        )
        md_content = _append_png_gallery(md_content, png_files)
        if gerar_md:
            _save_relatorio_md_outputs(rel_dict, canonical, project, v, md_content)
        if gerar_pdf:
            _save_relatorio_pdf_output(rel_dict, project, v)
    except Exception:  # pragma: no cover
        pass


def _handle_skill_09_side_effects(result: SkillResult, project: ProjectHandle, v: str, outputs_cfg: dict) -> None:
    # Entrega oficial: somente PDFs para memorial e relatório final.
    gerar_md = False
    gerar_rpdf = True
    gerar_mem_md = False
    gerar_mem_pdf = outputs_cfg.get("memorial_bdi_pdf", outputs_cfg.get("memorial_bdi", True))
    gerar_xlsx = outputs_cfg.get("resultado_xlsx", outputs_cfg.get("cronograma_xlsx", True))
    gerar_pngs = outputs_cfg.get("graficos_png", True)  # False desabilita PNGs pesados (analytic cube)
    relatorio = getattr(result, "relatorio", None)
    if relatorio:
        project.save_intermediate_file(
            "relatorio.json", json.dumps(relatorio, indent=2, ensure_ascii=False, default=_json_default), v
        )

    excel_bytes = getattr(result, "excel_bytes", None)
    if excel_bytes and gerar_xlsx:
        project.save_output_file(excel_bytes, v, "resultado_planejamento.xlsx")

    _save_memorial_bdi_files(result, project, v, gerar_mem_md, gerar_mem_pdf)
    _save_relatorio_files(result, project, v, gerar_md, gerar_rpdf, gerar_pngs=gerar_pngs)


def _handle_skill_04_side_effects(result: SkillResult, project: ProjectHandle, v: str) -> None:
    cronograma = getattr(result.canonical, "cronograma", None)
    if not cronograma or cronograma.algorithm == "manual_allocation":
        return
    schedules_data = {
        "algorithm": cronograma.algorithm,
        "quality_score": cronograma.quality_score,
        "makespan_weeks": cronograma.makespan_weeks,
        "is_feasible": cronograma.is_feasible,
        "was_relaxed": cronograma.was_relaxed,
        "activities": [
            {
                "activity_id": sa.activity_id,
                "start_week": sa.start_week,
                "end_week": sa.end_week,
                "duration_weeks": sa.duration_weeks,
                "data_inicio": sa.data_inicio.isoformat() if sa.data_inicio else None,
                "data_fim": sa.data_fim.isoformat() if sa.data_fim else None,
            }
            for sa in cronograma.scheduled_activities
        ],
    }
    project.save_intermediate_file(
        "schedules_weekly.json", json.dumps(schedules_data, indent=2, ensure_ascii=False, default=_json_default), v
    )


def _persist_typed_artifacts(result: SkillResult, project: ProjectHandle, v: str) -> None:
    """Persiste ArtifactEnvelope(s) produzidos por uma skill (ADR-018 §D2).

    Usa project.write_json() em vez de pathlib.Path direto — funciona tanto
    no backend local quanto no de storage (SharePoint/S3/Azure/GDrive), onde
    project.version_path() não é um diretório real gravável.
    """
    artifacts = getattr(result, "artifacts", None)
    if not artifacts:
        return

    import logging

    _log = logging.getLogger(__name__)

    for artifact in artifacts:
        meta = getattr(artifact, "meta", None)
        artifact_id = getattr(meta, "artifact_id", None)
        if meta is None or not artifact_id:
            _log.warning("Artefato tipado sem meta/artifact_id válido — pulando: %r", artifact)
            continue
        try:
            payload = getattr(artifact, "payload", None)
            payload_data = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
            project.write_json(f"{v}/artifacts/{artifact_id}.json", payload_data)
            project.write_json(f"{v}/artifacts/{artifact_id}.meta.json", meta.model_dump(mode="json"))
        except Exception:
            _log.warning("Falha ao persistir artefato tipado '%s'", artifact_id, exc_info=True)
