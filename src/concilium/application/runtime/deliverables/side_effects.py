"""Side effects de skills: persistência de artefatos, relatórios, gráficos e helpers de insumos."""

from __future__ import annotations

import json
from pathlib import Path

from .helpers.insumos import dedup_insumos, ingest_insumos, load_insumos_subdir
from .helpers.serialization import json_default
from .reports.executive_summary import render_resumo_executivo
from .reports.financial_report_markdown import render_financial_report_markdown
from .reports.financial_report_pdf import render_financial_report_pdf
from .reports.memorial_bdi_markdown import render_memorial_bdi_markdown
from .reports.pdf_renderer import render_markdown_pdf
from .visualizations.png_bundle import build_visualization_png_files


def _json_default(obj: object) -> object:
    return json_default(obj)


def _ingest_insumos(data: object, insumos: list) -> None:
    ingest_insumos(data, insumos)


def _load_insumos_subdir(sub: Path, insumos: list) -> None:
    load_insumos_subdir(sub, insumos)


def _dedup_insumos(insumos: list) -> list:
    return dedup_insumos(insumos)


def _save_memorial_bdi_files(result: object, project: object, v: str, gerar_md: bool, gerar_pdf: bool) -> None:
    memorial_bdi_json = getattr(result, "memorial_bdi_json", None)
    if not memorial_bdi_json:
        return
    try:
        project.save_intermediate_file("memorial_bdi.json", memorial_bdi_json, v)  # type: ignore[union-attr]
        if gerar_md or gerar_pdf:
            memorial_dict = json.loads(memorial_bdi_json.decode("utf-8"))
            md_memorial = render_memorial_bdi_markdown(memorial_dict)
            if gerar_md:
                project.save_output_file(md_memorial.encode("utf-8"), v, "memorial_bdi.md")  # type: ignore[union-attr]
            if gerar_pdf:
                proj_nome = (memorial_dict.get("meta") or {}).get("projeto", "")
                pdf_bytes = render_markdown_pdf(
                    md_memorial,
                    f"Memorial BDI - {proj_nome}",
                    image_provider=lambda file_name: _load_output_image_bytes(project, v, file_name),
                )
                if pdf_bytes:
                    project.save_output_file(pdf_bytes, v, "memorial_bdi.pdf")  # type: ignore[union-attr]
    except Exception:
        pass


def _save_relatorio_graficos_files(
    rel_dict: dict,
    canonical: object | None,
    project: object,
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
            project.save_output_file(png_bytes, v, fname)  # type: ignore[union-attr]
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


def _load_output_image_bytes(project: object, v: str, file_name: str) -> bytes | None:
    try:
        return project.load_output_file(v, file_name)  # type: ignore[union-attr]
    except Exception:
        return None


def _save_relatorio_files(
    result: object, project: object, v: str, gerar_md: bool, gerar_pdf: bool, gerar_pngs: bool = True
) -> None:
    relatorio = getattr(result, "relatorio", None)
    if not relatorio or not (gerar_md or gerar_pdf):
        return
    try:
        rel_dict = json.loads(json.dumps(relatorio, default=_json_default))
        canonical = getattr(result, "canonical", None)
        if canonical is None:
            try:
                canonical = project.load_canonical(v)  # type: ignore[union-attr]
            except Exception:
                canonical = None
        md_content = render_financial_report_markdown(rel_dict, canonical=canonical)
        png_files = _save_relatorio_graficos_files(
            rel_dict, canonical, project, v, gerar_md, gerar_pdf, gerar_pngs=gerar_pngs
        )
        md_content = _append_png_gallery(md_content, png_files)
        if gerar_md:
            project.save_output_file(md_content.encode("utf-8"), v, "relatorio.md")  # type: ignore[union-attr]
            # ADR-093 D5: resumo executivo de 1 página para decisores
            try:
                resumo_md = render_resumo_executivo(rel_dict, canonical=canonical)
                project.save_output_file(resumo_md.encode("utf-8"), v, "resumo_executivo.md")  # type: ignore[union-attr]
            except Exception:  # pragma: no cover
                pass
        if gerar_pdf:
            # Prioridade: meta.projeto → resumo.projeto → fallback genérico
            proj_nome = (
                (rel_dict.get("meta") or {}).get("projeto")
                or (rel_dict.get("resumo") or {}).get("projeto")
                or "Relatório Financeiro"
            )
            def provider(file_name):
                return _load_output_image_bytes(project, v, file_name)
            pdf_bytes = render_financial_report_pdf(rel_dict, proj_nome, image_provider=provider)
            if pdf_bytes:
                project.save_output_file(pdf_bytes, v, "relatorio.pdf")  # type: ignore[union-attr]
    except Exception:  # pragma: no cover
        pass


def _handle_skill_09_side_effects(result: object, project: object, v: str, outputs_cfg: dict) -> None:
    # Entrega oficial: somente PDFs para memorial e relatório final.
    gerar_md = False
    gerar_rpdf = True
    gerar_mem_md = False
    gerar_mem_pdf = outputs_cfg.get("memorial_bdi_pdf", outputs_cfg.get("memorial_bdi", True))
    gerar_xlsx = outputs_cfg.get("resultado_xlsx", outputs_cfg.get("cronograma_xlsx", True))
    gerar_pngs = outputs_cfg.get("graficos_png", True)  # False desabilita PNGs pesados (analytic cube)
    relatorio = getattr(result, "relatorio", None)
    if relatorio:
        project.save_intermediate_file(  # type: ignore[union-attr]
            "relatorio.json", json.dumps(relatorio, indent=2, ensure_ascii=False, default=_json_default), v
        )

    excel_bytes = getattr(result, "excel_bytes", None)
    if excel_bytes and gerar_xlsx:
        project.save_output_file(excel_bytes, v, "resultado_planejamento.xlsx")  # type: ignore[union-attr]

    _save_memorial_bdi_files(result, project, v, gerar_mem_md, gerar_mem_pdf)
    _save_relatorio_files(result, project, v, gerar_md, gerar_rpdf, gerar_pngs=gerar_pngs)


def _handle_skill_04_side_effects(result: object, project: object, v: str) -> None:
    cronograma = getattr(result.canonical, "cronograma", None)  # type: ignore[union-attr]
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
    project.save_intermediate_file(  # type: ignore[union-attr]
        "schedules_weekly.json", json.dumps(schedules_data, indent=2, ensure_ascii=False, default=_json_default), v
    )


def _persist_typed_artifacts(result: object, project: object, v: str) -> None:
    artifacts = getattr(result, "artifacts", None)
    if not artifacts:
        return

    try:
        from concilium.infrastructure.storage.artifact_store import FileSystemArtifactStore

        store = FileSystemArtifactStore(project.version_path(v) / "artifacts")  # type: ignore[union-attr]
        for artifact in artifacts:
            payload = getattr(artifact, "payload", None)
            payload_path = store.root / f"{artifact.meta.artifact_id}.json"
            if hasattr(payload, "model_dump_json"):
                payload_json = payload.model_dump_json(indent=2)
            else:
                payload_json = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
            payload_path.write_text(payload_json, encoding="utf-8")
            store.save_meta_sidecar(payload_path, artifact.meta)
    except Exception:
        pass
