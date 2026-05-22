"""Runtime do Concilium: carrega config, valida dependencias e executa skills."""

from __future__ import annotations

import functools
import inspect
import json
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from concilium.application.skills import MANIFEST_META, SKILLS
from concilium.application.skills.base import SkillResult
from concilium.application.skills.executor import ExecutionRecord, SkillExecutor
from concilium.domain.models.canonical import CanonicalModel
from concilium.domain.models.contexto import ContextoObra
from concilium.infrastructure.storage.project import ProjectStore

# ADR-022: skills GATE cujas falhas contaminam (taint) o canônico.
# Downstream do conjunto bloqueado não executa — pipeline_integridade = CORROMPIDO.
# Derivado dos manifests TOML (gate = true) para evitar duplicação.
_GATE_SKILLS: frozenset[str] = frozenset(sid for sid, meta in MANIFEST_META.items() if meta.get("gate", False))


def _save_memorial_bdi_files(result: object, project: object, v: str, gerar_md: bool, gerar_pdf: bool) -> None:
    memorial_bdi_json = getattr(result, "memorial_bdi_json", None)
    if not memorial_bdi_json:
        return
    try:
        project.save_intermediate_file("memorial_bdi.json", memorial_bdi_json, v)  # type: ignore[union-attr]
        if gerar_md or gerar_pdf:
            memorial_dict = json.loads(memorial_bdi_json.decode("utf-8"))
            md_memorial = _memorial_bdi_to_md(memorial_dict)
            if gerar_md:
                project.save_output_file(md_memorial.encode("utf-8"), v, "memorial_bdi.md")  # type: ignore[union-attr]
            if gerar_pdf:
                proj_nome = (memorial_dict.get("meta") or {}).get("projeto", "")
                pdf_bytes = _md_to_pdf_bytes(md_memorial, f"Memorial BDI — {proj_nome}")
                if pdf_bytes:
                    project.save_output_file(pdf_bytes, v, "memorial_bdi.pdf")  # type: ignore[union-attr]
    except Exception:
        pass


def _save_relatorio_files(result: object, project: object, v: str, gerar_md: bool, gerar_pdf: bool) -> None:
    relatorio = getattr(result, "relatorio", None)
    if not relatorio or not (gerar_md or gerar_pdf):
        return
    try:
        rel_dict = json.loads(json.dumps(relatorio, default=_json_default))
        md_content = _relatorio_to_md(rel_dict)
        if gerar_md:
            project.save_output_file(md_content.encode("utf-8"), v, "relatorio.md")  # type: ignore[union-attr]
        if gerar_pdf:
            proj_nome = (rel_dict.get("meta") or {}).get("projeto", "Relatório")
            pdf_bytes = _md_to_pdf_bytes(md_content, proj_nome)
            if pdf_bytes:
                project.save_output_file(pdf_bytes, v, "relatorio.pdf")  # type: ignore[union-attr]
    except Exception:
        pass


def _handle_skill_09_side_effects(result: object, project: object, v: str, outputs_cfg: dict) -> None:
    gerar_md = outputs_cfg.get("relatorio_md", True)
    gerar_rpdf = outputs_cfg.get("relatorio_pdf", True)
    gerar_mem_md = outputs_cfg.get(
        "memorial_bdi_md", outputs_cfg.get("memorial_bdi", outputs_cfg.get("memoria_calculo", True))
    )
    gerar_mem_pdf = outputs_cfg.get("memorial_bdi_pdf", outputs_cfg.get("memorial_bdi", True))
    gerar_xlsx = outputs_cfg.get("resultado_xlsx", outputs_cfg.get("cronograma_xlsx", True))
    gerar_modelo_vivo = outputs_cfg.get("modelo_vivo_xlsx", False)

    relatorio = getattr(result, "relatorio", None)
    if relatorio:
        project.save_intermediate_file(
            "relatorio.json", json.dumps(relatorio, indent=2, ensure_ascii=False, default=_json_default), v
        )  # type: ignore[union-attr]

    excel_bytes = getattr(result, "excel_bytes", None)
    if excel_bytes and gerar_xlsx:
        project.save_output_file(excel_bytes, v, "resultado_planejamento.xlsx")  # type: ignore[union-attr]

    excel_live_bytes = getattr(result, "excel_live_bytes", None)
    if excel_live_bytes and gerar_modelo_vivo:
        project.save_output_file(excel_live_bytes, v, "modelo_vivo.xlsx")  # type: ignore[union-attr]

    _save_memorial_bdi_files(result, project, v, gerar_mem_md, gerar_mem_pdf)
    _save_relatorio_files(result, project, v, gerar_md, gerar_rpdf)


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
    project.save_intermediate_file(
        "schedules_weekly.json", json.dumps(schedules_data, indent=2, ensure_ascii=False, default=_json_default), v
    )  # type: ignore[union-attr]


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
        # Best-effort: artifacts tipados não podem quebrar a persistência principal do canônico.
        pass


class RuntimeError(Exception):
    """Erro de orquestracao do pipeline."""


class RuntimeDomainError(RuntimeError):
    """Erro de dominio (pre-condicao, regra de negocio, contrato)."""


class RuntimeTechnicalError(RuntimeError):
    """Erro tecnico inesperado durante execucao."""


@dataclass(frozen=True)
class SkillExecutionContract:
    """Contrato unico de execucao de uma skill."""

    skill_id: str
    signature: list[str]
    required_inputs: list[str]
    optional_inputs: list[str]
    depends_on_skills: list[str]
    produces_section: str | None
    output_schema: dict[str, Any]


def _md_to_pdf_bytes(md_text: str, title: str = "") -> bytes | None:
    """Converte Markdown para PDF usando fpdf2. Retorna None se fpdf2 não estiver disponível."""
    try:
        from fpdf import FPDF

        class _PDF(FPDF):
            def header(self):
                if title:
                    self.set_font("Helvetica", "B", 9)
                    self.set_text_color(26, 58, 92)
                    self.cell(0, 8, title, align="R", new_x="LMARGIN", new_y="NEXT")
                    self.set_text_color(0, 0, 0)

        pdf = _PDF(orientation="P", unit="mm", format="A4")
        pdf.set_margins(20, 20, 20)
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()
        pdf.set_font("Helvetica", size=10)

        def _cell(h: float, text: str) -> None:
            # Always reset to left margin before multi_cell to avoid fpdf2 2.8.x
            # cursor-position bug where w=0 computes negative available width.
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(pdf.epw, h, text)

        for line in md_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# "):
                pdf.set_font("Helvetica", "B", 14)
                pdf.set_text_color(26, 58, 92)
                _cell(8, stripped[2:])
                pdf.set_font("Helvetica", size=10)
                pdf.set_text_color(0, 0, 0)
            elif stripped.startswith("## "):
                pdf.set_font("Helvetica", "B", 12)
                pdf.set_text_color(26, 58, 92)
                _cell(7, stripped[3:])
                pdf.set_font("Helvetica", size=10)
                pdf.set_text_color(0, 0, 0)
            elif stripped.startswith("### "):
                pdf.set_font("Helvetica", "BI", 10)
                _cell(6, stripped[4:])
                pdf.set_font("Helvetica", size=10)
            elif stripped.startswith("|"):
                pdf.set_font("Courier", size=8)
                _cell(5, stripped[:120])
                pdf.set_font("Helvetica", size=10)
            elif stripped.startswith("---"):
                pdf.set_draw_color(192, 92, 24)
                pdf.set_x(pdf.l_margin)
                pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + pdf.epw, pdf.get_y())
                pdf.ln(2)
            elif stripped == "":
                pdf.ln(3)
            else:
                text = stripped.replace("**", "")
                _cell(6, text)

        return bytes(pdf.output())
    except ImportError:
        return None
    except Exception:
        return None


def _mbm_pct(v: object) -> str:
    return f"{float(v or 0) * 100:.2f}%"


def _mbm_brl(v: object) -> str:
    return f"R$ {float(v or 0):,.2f}"


def _mbm_encargos_sociais(memorial: dict) -> list[str]:
    lines: list[str] = []
    for regime_key, label in [("encargos_horista", "CLT-Horista"), ("encargos_mensalista", "CLT-Mensalista")]:
        enc = memorial.get(regime_key) or {}
        if not enc:
            continue
        lines += [f"### {label}", ""]
        lines += ["| Grupo | Descrição | Fator |", "|-------|-----------|------:|"]
        for grupo, desc in [
            ("grupo_a", "Básicos (INSS, FGTS, RAT, Sal.Ed., Terceiros)"),
            ("grupo_b", "Com incidência A (Férias, 13º, DSR)"),
            ("grupo_c", "Sem incidência A (Aviso prévio, indenizações)"),
            ("grupo_d", "Reincidências B sobre C"),
            ("grupo_e", "Seguros e benefícios (saúde, EPI)"),
            ("grupo_f", "Vale-transporte + Vale-refeição"),
            ("judicial", "Provisão trabalhista"),
        ]:
            v = enc.get(grupo)
            if v is not None:
                lines.append(f"| {grupo.upper().replace('_', ' ')} | {desc} | {_mbm_pct(v)} |")
        lines.append(f"| **TOTAL** | | **{_mbm_pct(enc.get('total'))}** |")
        lines += [""]
    return lines


def _mbm_bdi_categorias(memorial: dict) -> list[str]:
    lines: list[str] = []
    bdi_cats = memorial.get("bdi_por_categoria") or {}
    if not bdi_cats:
        return lines
    lines += [
        "## BDI por Categoria",
        "",
        "| Categoria | AC | DF | R | CR | L | T | BDI Total |",
        "|-----------|---:|---:|--:|---:|--:|--:|----------:|",
    ]
    for cat, bdi in bdi_cats.items():
        if not isinstance(bdi, dict):
            continue
        lines.append(
            f"| {cat} | {_mbm_pct(bdi.get('ac'))} | {_mbm_pct(bdi.get('df'))} | "
            f"{_mbm_pct(bdi.get('r'))} | {_mbm_pct(bdi.get('cr'))} | {_mbm_pct(bdi.get('l'))} | "
            f"{_mbm_pct(bdi.get('t'))} | **{_mbm_pct(bdi.get('bdi_total'))}** |"
        )
    lines += [""]
    return lines


def _mbm_aplicacao_eap(memorial: dict) -> list[str]:
    lines: list[str] = []
    aplicacao = memorial.get("aplicacao_por_item") or []
    if not aplicacao:
        return lines
    lines += [
        "## Aplicação por Item (EAP)",
        "",
        "| Item | Custo s/BDI | BDI Pond. | Preço c/BDI | Margem% |",
        "|------|------------:|----------:|------------:|--------:|",
    ]
    for item in aplicacao:
        if not isinstance(item, dict):
            continue
        iid = item.get("item_id") or item.get("cpu_id") or "—"
        custo = item.get("custo_sem_bdi", 0)
        venda = item.get("preco_com_bdi", 0)
        bdi_pond = item.get("bdi_ponderado", 0)
        margem = (venda - custo) / venda * 100 if venda else 0
        lines.append(f"| {iid} | {_mbm_brl(custo)} | {_mbm_pct(bdi_pond)} | {_mbm_brl(venda)} | {margem:.2f}% |")
    lines += [""]
    return lines


def _memorial_bdi_to_md(memorial: dict) -> str:
    """Converte memorial_bdi dict para Markdown auditável."""
    meta = memorial.get("meta") or {}
    proj = meta.get("projeto", "")
    gerado = str(meta.get("gerado_em", ""))[:19].replace("T", " ")
    lines: list[str] = [
        "# Memorial de Cálculo BDI",
        "",
        f"**Projeto:** {proj}  ",
        f"**Gerado em:** {gerado}",
        "",
        "## Resultado Financeiro",
        "",
        "| Indicador | Valor |",
        "|-----------|------:|",
        f"| Preço de Venda (c/BDI) | {_mbm_brl(memorial.get('venda_total_com_bdi'))} |",
        f"| Custo Direto | {_mbm_brl(memorial.get('custo_direto_total'))} |",
        f"| Overhead | {_mbm_brl(memorial.get('overhead_total'))} |",
        f"| Tributos | {_mbm_brl(memorial.get('tributos_total'))} |",
        f"| Margem Líquida | {_mbm_brl(memorial.get('margem_total'))} ({_mbm_pct(memorial.get('margem_pct'))}) |",
        "",
        "---",
        "",
        "## Encargos Sociais",
        "",
    ]
    lines += _mbm_encargos_sociais(memorial)
    lines += ["---", ""]
    lines += _mbm_bdi_categorias(memorial)
    lines += ["---", ""]
    lines += _mbm_aplicacao_eap(memorial)
    return "\n".join(lines)


def _brl(v: Any) -> str:
    try:
        return f"R$ {float(v):,.2f}"
    except Exception:
        return str(v)


def _is_nullish(v: Any) -> bool:
    return v is None or v == "" or v == [] or v == {}


def _drop_nulls(v: Any) -> Any:
    if isinstance(v, dict):
        cleaned = {k: _drop_nulls(val) for k, val in v.items()}
        return {k: val for k, val in cleaned.items() if not _is_nullish(val)}
    if isinstance(v, list):
        cleaned = [_drop_nulls(i) for i in v]  # type: ignore[assignment]
        return [i for i in cleaned if not _is_nullish(i)]
    return v


_MONTH_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _weekly_to_monthly_labels(labels: list[str]) -> list[str]:
    import datetime

    result = []
    seen_months: set[str] = set()
    for lbl in labels:
        try:
            parts = lbl.split("-W")
            if len(parts) == 2:
                year, week = int(parts[0]), int(parts[1])
                d = datetime.datetime.strptime(f"{year}-W{week:02d}-1", "%G-W%V-%u")
                m_key = f"{d.month}-{d.year}"
                if m_key not in seen_months:
                    seen_months.add(m_key)
                    result.append(f"{_MONTH_PT[d.month - 1]}/{str(d.year)[2:]}")
                else:
                    result.append(".")
            else:
                result.append(lbl)
        except Exception:
            result.append(lbl)
    return result


def _xychart(
    title: str, labels: list[str], values: list[Any], y_label: str, monthly_ticks: bool = False
) -> list[str] | None:
    if not labels or not values:
        return None
    numeric_values: list[float] = []
    for value in values:
        try:
            numeric_values.append(float(value))
        except Exception:
            numeric_values.append(0.0)
    max_abs = max((abs(v) for v in numeric_values), default=0.0)
    y_top = max(1.0, max_abs * 1.2)
    display_labels = _weekly_to_monthly_labels(labels) if monthly_ticks else labels
    return [
        "```mermaid",
        "xychart-beta",
        f'    title "{title}"',
        f"    x-axis {json.dumps(display_labels, ensure_ascii=False)}",
        f'    y-axis "{y_label}" 0 --> {y_top:.2f}',
        f"    bar {json.dumps([round(v, 2) for v in numeric_values], ensure_ascii=False)}",
        "```",
    ]


def _xychart_bar_line(
    title: str, lbls: list[str], bars: list[Any], line_vals: list[Any], y_label: str
) -> list[str] | None:
    if not lbls:
        return None

    def _nums(vals: list[Any]) -> list[float]:
        out = []
        for v in vals:
            try:
                out.append(float(v))
            except Exception:
                out.append(0.0)
        return out

    b = _nums(bars)
    line_data = _nums(line_vals)
    max_abs = max((abs(v) for v in b + line_data), default=0.0)
    y_top = max(1.0, max_abs * 1.2)
    return [
        "```mermaid",
        "xychart-beta",
        f'    title "{title}"',
        f"    x-axis {json.dumps(lbls, ensure_ascii=False)}",
        f'    y-axis "{y_label}" 0 --> {y_top:.2f}',
        f"    bar {json.dumps([round(v, 2) for v in b], ensure_ascii=False)}",
        f"    line {json.dumps([round(v, 2) for v in line_data], ensure_ascii=False)}",
        "```",
    ]


def _gantt_block(title: str, tasks: list[dict[str, Any]]) -> list[str] | None:
    if not tasks:
        return None
    block = [
        "```mermaid",
        "gantt",
        f'    title "{title}"',
        "    dateFormat  YYYY-MM-DD",
        "    axisFormat  %d/%m",
        "    section Cronograma",
    ]
    for idx, task in enumerate(tasks, 1):
        name = str(task.get("name") or task.get("item_id") or f"Atividade {idx}")
        start = task.get("start")
        duration_days = task.get("duration_days")
        if not start or not duration_days:
            continue
        block.append(f"    {name} :task{idx}, {start}, {int(duration_days)}d")
    block.append("```")
    return block


def _md_header(meta: dict, resumo: dict) -> list[str]:
    nome = resumo.get("projeto") or meta.get("framework", "Projeto")
    gerado = str(meta.get("gerado_em", ""))[:19].replace("T", " ")
    return [
        f"# Relatorio Analitico -- {nome}",
        "",
        f"**Gerado em:** {gerado}  ",
        f"**Framework:** {meta.get('framework', '')}  ",
        "",
        "---",
        "",
        "## Resumo do Projeto",
        "",
        "| Campo | Valor |",
        "|-------|-------|",
        *[f"| {k.replace('_', ' ').title()} | {v} |" for k, v in resumo.items()],
        "",
        "---",
        "",
    ]


def _md_resultado(result: dict) -> list[str]:
    if not result:
        return []
    lines = ["## Resultado Financeiro", "", "| Indicador | Valor |", "|-----------|-------|"]
    lines.append(f"| Preco de venda (c/ BDI) | {_brl(result.get('preco_venda_total', 0))} |")
    lines.append(f"| Custo direto | {_brl(result.get('custo_direto', 0))} |")
    lines.append(f"| Custo indireto | {_brl(result.get('custo_indireto', 0))} |")
    lines.append(f"| **Custo total** | **{_brl(result.get('custo_total', 0))}** |")
    lines.append(f"| **Resultado bruto** | **{_brl(result.get('resultado_bruto', 0))}** |")
    margem = result.get("margem_pct", 0)
    try:
        pct = float(margem)
        margem_fmt = f"{pct * 100:.2f}%" if pct < 1 else f"{pct:.2f}%"
    except Exception:
        margem_fmt = str(margem)
    lines.append(f"| Margem bruta | {margem_fmt} |")
    lines.append(f"| Status | **{result.get('status_margem', '--')}** |")
    lines += ["", "---", ""]
    return lines


def _md_planejamento(plan: list) -> list[str]:
    lines = ["## Planejamento por EAP", ""]
    if not plan:
        return lines
    lines += [
        "| Item | Descricao | Un. | Qtd | MO (R$) | EQ (R$) | Diesel (R$) |"
        " Mat (R$) | s/BDI (R$) | c/BDI (R$) | Criticidade |",
        "|------|-----------|-----|----:|--------:|--------:|------------:|---------:|-----------:|-----------:|:-----------:|",
    ]
    for p in plan:
        desc = str(p.get("descricao") or "")[:60]
        crit = p.get("criticidade", "--")
        try:
            lines.append(
                f"| {p.get('item_id')} | {desc} | {p.get('unidade', '')} "
                f"| {float(p.get('quantitativo', 0)):,.0f} | {float(p.get('subtotal_mo', 0)):,.2f} "
                f"| {float(p.get('subtotal_eq', 0)):,.2f} | {float(p.get('subtotal_diesel', 0)):,.2f} "
                f"| {float(p.get('subtotal_mat', 0)):,.2f} | {float(p.get('subtotal_sem_bdi', 0)):,.2f} "
                f"| {float(p.get('subtotal_com_bdi', 0)):,.2f} | {crit} |"
            )
        except Exception:
            lines.append(f"| {p.get('item_id')} | {desc} | -- | -- | -- | -- | -- | -- | -- | -- | {crit} |")
    lines += ["", "---", ""]
    return lines


def _mifv_funcoes_rows(funcoes: list) -> list[str]:
    lines = ["| Funcao | Qtd | Custo Mensal (R$) | Tipo |", "|--------|----:|------------------:|:-----|"]
    for f in funcoes:
        lines.append(
            f"| {f.get('funcao') or f.get('funcao_id') or '—'}"
            f" | {int(f.get('quantidade', 1))}"
            f" | {float(f.get('custo_mensal', 0)):,.2f}"
            f" | {f.get('tipo_contratacao') or '—'} |"
        )
    lines.append("")
    return lines


def _mifv_verbas_rows(verbas: list) -> list[str]:
    lines = ["**Verbas mensais:**", "", "| Descricao | Valor Mensal (R$) |", "|-----------|------------------:|"]
    for v in verbas:
        lines.append(f"| {v.get('descricao') or '—'} | {float(v.get('valor_mensal', 0)):,.2f} |")
    lines.append("")
    return lines


def _mifv_funcoes_rows(funcoes: list) -> list[str]:
    lines = ["| Funcao | Qtd | Custo Mensal (R$) | Tipo |", "|--------|----:|------------------:|:-----|"]
    for f in funcoes:
        lines.append(
            f"| {f.get('funcao') or f.get('funcao_id') or '—'}"
            f" | {int(f.get('quantidade', 1))}"
            f" | {float(f.get('custo_mensal', 0)):,.2f}"
            f" | {f.get('tipo_contratacao') or '—'} |"
        )
    lines.append("")
    return lines


def _mifv_verbas_rows(verbas: list) -> list[str]:
    lines = ["**Verbas mensais:**", "", "| Descricao | Valor Mensal (R$) |", "|-----------|------------------:|"]
    for v in verbas:
        lines.append(f"| {v.get('descricao') or '—'} | {float(v.get('valor_mensal', 0)):,.2f} |")
    lines.append("")
    return lines


def _md_indir_funcoes_verbas(ind: dict) -> list[str]:
    funcoes = ind.get("funcoes") or []
    verbas = ind.get("verbas_mensais") or []
    if not funcoes and not verbas:
        return []
    cat = ind.get("categoria", "")
    desc = ind.get("descricao", cat)
    lines: list[str] = [f"### {cat} — {desc}", ""]
    if funcoes:
        lines += _mifv_funcoes_rows(funcoes)
    if verbas:
        lines += _mifv_verbas_rows(verbas)
    return lines


def _md_indiretos(indirs: list) -> list[str]:
    if not isinstance(indirs, list) or not indirs:
        return []
    total_ind = sum(float(i.get("custo_total", 0)) for i in indirs)
    lines = [
        "## Custos Indiretos",
        "",
        "| Categoria | Descricao | Permanencia (meses) | Custo Total (R$) |",
        "|-----------|-----------|--------------------:|-----------------:|",
    ]
    for ind in indirs:
        perm = ind.get("permanencia_meses")
        perm_str = f"{float(perm):.2f}" if perm else "—"
        lines.append(
            f"| {ind.get('categoria', '--')} | {ind.get('descricao', '--')} "
            f"| {perm_str} | {_brl(ind.get('custo_total', 0))} |"
        )
    lines.append(f"| **TOTAL** | | | **{_brl(total_ind)}** |")
    lines += [""]
    for ind in indirs:
        lines += _md_indir_funcoes_verbas(ind)
    lines += ["---", ""]
    return lines


def _md_ponto_equilibrio(ponto_equilibrio: list) -> list[str]:
    if not isinstance(ponto_equilibrio, list) or not ponto_equilibrio:
        return []
    lines = [
        "## Ponto de Equilibrio: Estrutural vs Operacional",
        "",
        "| Item | PE Estrutural (R$) | PE Operacional (R$) | Venda (R$) | Frentes Eq. | Criticidade |",
        "|------|--------------------:|---------------------:|-----------:|:-----------:|:-----------:|",
    ]
    for pe in ponto_equilibrio:
        frentes = pe.get("frentes_equivalentes", 1)
        try:
            frentes_fmt = f"{float(frentes):.2f}"
        except Exception:
            frentes_fmt = str(frentes)
        lines.append(
            f"| {pe.get('item_id', '-')} | {_brl(pe.get('custo_fixo_equipe', 0))} "
            f"| {_brl(pe.get('custo_operacional_real', 0))} | {_brl(pe.get('custo_venda_cpu', 0))} "
            f"| {frentes_fmt} | {pe.get('status_validacao', '-')} |"
        )
    lines += ["", "---", ""]
    return lines


def _md_analise_composicional(analise: list) -> list[str]:
    if not isinstance(analise, list) or not analise:
        return []
    lines = [
        "## Analise Composicional de Custo",
        "",
        "| Item | Venda (R$) | Operacional (R$) | Gap (R$) | Gap % | Dominante | Acao Sugerida |",
        "|------|-----------:|-----------------:|---------:|------:|-----------|---------------|",
    ]
    for row in analise:
        gap_pct = row.get("gap_pct", 0)
        try:
            gap_pct_fmt = f"{float(gap_pct) * 100:.2f}%"
        except Exception:
            gap_pct_fmt = str(gap_pct)
        lines.append(
            f"| {row.get('item_id', '-')} | {_brl(row.get('custo_venda_cpu', 0))} "
            f"| {_brl(row.get('custo_operacional_real', 0))} | {_brl(row.get('gap_operacional', 0))} "
            f"| {gap_pct_fmt} | {row.get('dominante', '-')} | {row.get('acao_sugerida', '-')} |"
        )
    lines += ["", "---", ""]
    return lines


def _mdgf_exposicao_block(labels: list, expos: list) -> list[str]:
    expos_n = [float(v) if _is_nullish(v) is False else 0.0 for v in expos]
    max_abs_e = max((abs(v) for v in expos_n), default=0.0)
    y_top_e = max(1.0, max_abs_e * 1.2)
    return (
        ["### Exposicao Acumulada", ""]
        + [
            "```mermaid",
            "xychart-beta",
            '    title "Exposicao Acumulada (Receita - Despesa acum.)"',
            f"    x-axis {json.dumps(labels, ensure_ascii=False)}",
            f'    y-axis "R$" 0 --> {y_top_e:.2f}',
            f"    line {json.dumps([round(v, 2) for v in expos_n], ensure_ascii=False)}",
            "```",
        ]
        + [""]
    )


def _md_graficos_financeiro(graficos: dict) -> list[str]:
    financeiro = graficos.get("financeiro") or {}
    if not isinstance(financeiro, dict):
        return []
    labels = [str(label) for label in financeiro.get("labels", [])]
    rec = list(financeiro.get("receita", []))
    saldo = list(financeiro.get("saldo", []))
    expos = list(financeiro.get("exposicao", []))
    lines: list[str] = []
    if saldo and rec:
        chart = _xychart_bar_line("Fluxo de Caixa (barras=Saldo Rec-Desp, linha=Receita)", labels, saldo, rec, "R$")
        if chart:
            lines += ["### Fluxo de Caixa", ""] + chart + [""]
    if expos:
        lines += _mdgf_exposicao_block(labels, expos)
    return lines


def _mdg_add_histogram(lines: list, graficos: dict, key: str, title: str, ylabel: str) -> None:
    """Appends histogram section to lines if data is available."""
    section = graficos.get(key) or {}
    if not isinstance(section, dict):
        return
    chart = _xychart(
        title,
        [str(lbl) for lbl in section.get("labels", [])],
        list(section.get("values", [])),
        ylabel,
        monthly_ticks=True,
    )
    if chart:
        lines += [f"### {title}", ""] + chart + [""]


def _mdg_add_histogram(lines: list, graficos: dict, key: str, title: str, ylabel: str) -> None:
    """Appends histogram section to lines if data is available."""
    section = graficos.get(key) or {}
    if not isinstance(section, dict):
        return
    chart = _xychart(
        title,
        [str(lbl) for lbl in section.get("labels", [])],
        list(section.get("values", [])),
        ylabel,
        monthly_ticks=True,
    )
    if chart:
        lines += [f"### {title}", ""] + chart + [""]


def _md_graficos(graficos: dict) -> list[str]:
    if not graficos:
        return []
    lines: list[str] = ["## Graficos", ""]
    _mdg_add_histogram(lines, graficos, "equipamentos", "Histograma de Equipamentos", "Unidades")
    _mdg_add_histogram(lines, graficos, "mao_obra", "Histograma de Mao de Obra", "Pessoas")
    gantt = graficos.get("cronograma") or {}
    chart = _gantt_block("Cronograma de Execucao", list(gantt.get("tasks", []))) if isinstance(gantt, dict) else None
    if chart:
        lines += ["### Cronograma", ""] + chart + [""]
    lines += _md_graficos_financeiro(graficos)
    lines += ["", "---", ""]
    return lines


def _mip_criticidade(valor: dict) -> str:
    a_plus = valor.get("total_A_mais", 0)
    a, b, cv = valor.get("total_A", 0), valor.get("total_B", 0), valor.get("total_C", 0)
    total = valor.get("total_atividades", 0)
    return f"- **criticidade**: total={total}, A+={a_plus}, A={a}, B={b}, C={cv}"


def _mip_sensibilidade(valor: dict) -> str:
    status = valor.get("status_margem", "--")
    repair_steps = len(valor.get("passos_repair", []))
    oportunidades = len(valor.get("oportunidades", []))
    extra = []
    for field, label in [("margem_entrada", "margem_entrada"), ("margem_pos_repair", "margem_pos_repair")]:
        v = valor.get(field)
        if v is not None:
            try:
                extra.append(f"{label}={float(v) * 100:.2f}%")
            except Exception:
                pass
    extra_txt = ", " + ", ".join(extra) if extra else ""
    return (
        f"- **sensibilidade**: status={status}, repair_steps={repair_steps}, oportunidades={oportunidades}{extra_txt}"
    )


def _mip_intervencao(valor: dict) -> str:
    recomendacao = valor.get("recomendacao_primaria") or {}
    rec_nome = recomendacao.get("nome", "Nenhuma") if isinstance(recomendacao, dict) else str(recomendacao)
    eixos = valor.get("eixos_intervencao", [])
    return f"- **intervencao**: recomendacao={rec_nome}, eixos={len(eixos)}"


def _md_insight_pair(nome: str, valor: Any) -> str | None:
    """Formata um par (nome, valor) de insight."""
    valor = _drop_nulls(valor)
    if _is_nullish(valor):
        return None
    if nome == "criticidade" and isinstance(valor, dict):
        return _mip_criticidade(valor)
    if nome == "sensibilidade" and isinstance(valor, dict):
        return _mip_sensibilidade(valor)
    if nome == "intervencao" and isinstance(valor, dict):
        return _mip_intervencao(valor)
    if isinstance(valor, dict):
        return f"- **{nome}**: {json.dumps(valor, ensure_ascii=False)}"
    return f"- **{nome}**: {valor}"


def _mi_format_item(ins: Any) -> str | None:
    """Formats a single insight item to markdown line."""
    if isinstance(ins, dict):
        titulo = ins.get("titulo") or ins.get("title") or ins.get("insight", "")
        descr = ins.get("descricao") or ins.get("description") or ""
        return f"- **{titulo}**: {descr}"
    if isinstance(ins, (list, tuple)) and len(ins) == 2:
        return _md_insight_pair(str(ins[0]), ins[1])
    return f"- {ins}"


def _md_insights(insights: Any) -> list[str]:
    if not insights:
        return []
    items = insights if isinstance(insights, list) else list(insights.items()) if isinstance(insights, dict) else []
    lines: list[str] = ["## Insights Acionaveis", ""]
    for ins in items:
        row = _mi_format_item(ins)
        if row:
            lines.append(row)
    lines += ["", "---", ""]
    return lines


def _relatorio_to_md(relatorio: dict) -> str:
    """Converte dict relatorio para markdown analitico."""
    meta = relatorio.get("meta", {})
    resumo = relatorio.get("resumo", {})
    result = relatorio.get("RESULTADO", {})
    plan = relatorio.get("PLANEJAMENTO", [])
    indirs = relatorio.get("INDIRETOS", [])
    insights = relatorio.get("ACTIONABLE_INSIGHTS", [])
    graficos = relatorio.get("GRAFICOS", {}) if isinstance(relatorio.get("GRAFICOS", {}), dict) else {}

    lines: list[str] = []
    lines += _md_header(meta, resumo)
    lines += _md_resultado(result)
    lines += _md_planejamento(plan)
    lines += _md_indiretos(indirs)
    lines += _md_ponto_equilibrio(relatorio.get("ponto_equilibrio") or relatorio.get("PONTO_EQUILIBRIO") or [])
    lines += _md_analise_composicional(relatorio.get("analise_composicional") or [])
    lines += _md_graficos(graficos)
    lines += _md_insights(insights)
    return chr(10).join(lines) + chr(10)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _rt_ingest_insumos(data: Any, insumos: list) -> None:
    if isinstance(data, list):
        insumos.extend(data)
    elif isinstance(data, dict) and "insumos" in data:
        insumos.extend(data["insumos"])
    elif isinstance(data, dict):
        insumos.append(data)


def _rt_load_insumos_subdir(sub: Any, insumos: list) -> None:
    for f in sub.glob("*.json"):
        try:
            _rt_ingest_insumos(json.loads(f.read_text(encoding="utf-8")), insumos)
        except Exception:
            pass


def _rt_dedup_insumos(insumos: list) -> list:
    seen: set = set()
    unique = []
    for i in insumos:
        iid = i.get("id") or i.get("codigo")
        if iid and iid not in seen:
            seen.add(iid)
            unique.append(i)
    return unique


def _rt_parse_executed_skills(log_path: Any) -> set:
    """Parses invocations log and returns set of executed skill IDs."""
    executed: set = set()
    if not log_path.exists():
        return executed
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            import json as _json

            entry = _json.loads(line)
            if entry.get("status") in ("OK", "ERRO") and "skill" in entry:
                executed.add(entry["skill"])
        except Exception:
            pass
    return executed


def _rsop_execute_skill(skill_fn, kwargs, skill_id, execution_id, ts_inicio, plano_store):
    """Run skill_fn; on exception logs and re-raises appropriately."""
    try:
        return skill_fn(**kwargs)
    except Exception as exc:
        plano_store.log_invocation(
            {
                "ts": ts_inicio.isoformat(),
                "execution_id": execution_id,
                "skill": skill_id,
                "status": "ERRO",
                "erro": str(exc),
            }
        )
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeTechnicalError(f"Falha técnica na skill '{skill_id}': {exc}") from exc


def _rp_apply_dv(new_canonical: Any, dv_raw: Any) -> Any:
    """Apply decision variables to canonical model if valid."""
    try:
        from concilium.domain.models.decision_variables import DecisionVariables

        dv_obj = DecisionVariables.model_validate(dv_raw) if isinstance(dv_raw, dict) else dv_raw
        if new_canonical.decision_variables != dv_obj:
            return new_canonical.model_copy(update={"decision_variables": dv_obj})
    except Exception:
        pass
    return new_canonical


def _rp_resolve_state(skill_id: str, result: Any, skill_inputs: dict) -> Any:
    """State resolution for run_pipeline: taint propagation + decision variables."""
    new_canonical = result.canonical
    if result.has_errors and skill_id in _GATE_SKILLS:
        blocked = list(set(new_canonical.pipeline_blocked_from) | {skill_id})
        new_canonical = new_canonical.model_copy(
            update={
                "pipeline_blocked_from": blocked,
                "pipeline_integridade": "CORROMPIDO",
            }
        )
    elif not result.has_errors and skill_id in _GATE_SKILLS:
        current_blocked = set(new_canonical.pipeline_blocked_from)
        if skill_id in current_blocked:
            new_blocked = sorted(current_blocked - {skill_id})
            new_canonical = new_canonical.model_copy(
                update={
                    "pipeline_blocked_from": new_blocked,
                    "pipeline_integridade": "CORROMPIDO" if new_blocked else None,
                }
            )
    dv_raw = skill_inputs.get(skill_id, {}).get("decision_variables")
    if dv_raw is not None and not result.has_errors:
        new_canonical = _rp_apply_dv(new_canonical, dv_raw)
    return new_canonical


def _rp_oas_log_invocation(runtime, store, version, invocation_context, skill_id, result, record):
    """Log skill invocation to store. Errors are silently swallowed."""
    try:
        from datetime import UTC as _UTC
        from datetime import datetime

        contract = runtime.get_skill_contract(skill_id)
        error_kind = "DOMINIO" if record.status == "ERRO" else ("TECNICO" if record.status == "EXCEPTION" else None)
        store.log_invocation(
            version,
            {
                "ts": datetime.now(_UTC).isoformat(),
                "skill": skill_id,
                **invocation_context,
                "contract": {
                    "required_inputs": contract.required_inputs,
                    "optional_inputs": contract.optional.inputs,  # type: ignore[attr-defined]
                    "depends_on_skills": contract.depends_on_skills,
                    "produces_section": contract.produces_section,
                },
                "status": record.status,
                "duration_ms": record.duration_ms,
                "error_kind": error_kind,
                "avisos": record.warnings,
                "validacoes": [
                    {"codigo": val.codigo, "status": val.status} for val in getattr(result, "validacoes", [])
                ],
            },
        )
    except Exception:
        pass


def _rp_oas_save_state(store, version, skill_id, result, new_state, record):
    """Persist canonical state after skill execution (taint-aware)."""
    should_save = not (skill_id == "00-escopo" and record.status == "ERRO")
    if new_state is not None and should_save and record.status != "EXCEPTION":
        store.save_canonical(new_state, version, created_by=skill_id)
    elif result is None and skill_id in _GATE_SKILLS and new_state is not None:
        blocked = list(set(new_state.pipeline_blocked_from) | {skill_id})
        tainted = new_state.model_copy(
            update={
                "pipeline_blocked_from": blocked,
                "pipeline_integridade": "CORROMPIDO",
            }
        )
        store.save_canonical(tainted, version, created_by=f"taint:{skill_id}")


def _rp_on_after_skill(runtime, store, version, invocation_context, skill_id, result, new_state, record):
    """on_after_skill callback: persistence + side effects + logging."""
    _rp_oas_save_state(store, version, skill_id, result, new_state, record)
    if result is not None:
        runtime._process_side_effects(skill_id, result, store, version)
    msg = f"[{record.status}] {record.duration_ms}ms"
    if record.errors:
        msg += f"  {'; '.join(record.errors)}"
    print(msg)
    if record.status == "EXCEPTION" and runtime._meta_is_gate(skill_id):
        print(f"  [STOP] Interrompendo pipeline: skill portão '{skill_id}' falhou.")
    _rp_oas_log_invocation(runtime, store, version, invocation_context, skill_id, result, record)


def _rp_print_skill_start(skill_id: str) -> None:
    print(f"  > {skill_id}...", end=" ", flush=True)


def _rp_format_records(records: list) -> list[dict]:
    """Format execution records to pipeline return format."""
    result = []
    for r in records:
        entry: dict = {
            "skill": r.skill_id,
            "status": r.status,
            "duration_ms": r.duration_ms,
            "avisos": r.warnings,
        }
        if r.errors:
            entry["erros"] = r.errors
        if r.status == "EXCEPTION" and r.errors:
            entry["erro"] = r.errors[0]
        result.append(entry)
    return result


class Runtime:
    """Camada de orquestracao: composicao de stores + dispatch declarativo."""

    def __init__(self, config_root: Path | str):
        self.config_root = Path(config_root)
        self._config_cache: dict[str, Any] = {}

    def _load_json_config(self, folder: str, file_id: str, label: str) -> dict[str, Any]:
        path = self.config_root / folder / f"{file_id}.json"
        if not path.exists():
            raise RuntimeDomainError(f"{label} '{file_id}' não encontrado em {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def load_tema(self, tema_id: str | None = None):  # returns TemaVisual (lazy import)
        """Carrega TemaVisual pelo ID (ADR-065). None → fallback 'default'."""
        from concilium.domain.models.tema import TEMA_DEFAULT, TemaVisual

        tid = tema_id or "default"
        key = f"tema:{tid}"
        if key in self._config_cache:
            return self._config_cache[key]  # type: ignore[return-value]

        path = self.config_root / "temas" / tid / "tema.json"
        if not path.exists():
            self._config_cache[key] = TEMA_DEFAULT
            return TEMA_DEFAULT

        try:
            tema = TemaVisual.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            tema = TEMA_DEFAULT
        self._config_cache[key] = tema
        return tema

    def load_contexto(self, contexto_id: str) -> ContextoObra:
        key = f"ctx:{contexto_id}"
        if key not in self._config_cache:
            data = self._load_json_config("contextos", contexto_id, "Contexto")
            self._config_cache[key] = ContextoObra.model_validate(data)
        return self._config_cache[key]

    def load_jurisdicao(self, codigo: str) -> dict[str, Any]:
        data = self._load_json_config("jurisdicoes", codigo, "Jurisdição")

        # Lógica de herança (ADR-035)
        parent_id = data.get("parent_id")
        if parent_id:
            parent_data = self.load_jurisdicao(parent_id)
            # Deep merge simples: o filho sobrescreve o pai
            merged = self._deep_merge(parent_data, data)
            return merged

        return data

    def _deep_merge(self, base: dict, overlay: dict) -> dict:
        """Realiza a fusão profunda de dois dicionários."""
        result = dict(base)
        for key, value in overlay.items():
            if isinstance(value, dict) and key in result and isinstance(result[key], dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def load_perfil(self, perfil_id: str) -> dict[str, Any]:
        key = f"perfil:{perfil_id}"
        if key not in self._config_cache:
            self._config_cache[key] = self._load_json_config("perfis", perfil_id, "Perfil")
        return self._config_cache[key]

    def load_referencia(self, ref_id: str) -> dict[str, Any]:
        return self._load_json_config("referencias", ref_id, "Referência")

    def load_catalogo(self, catalogo_id: str) -> dict[str, Any]:
        import copy

        key = f"catalogo:{catalogo_id}"
        if key not in self._config_cache:
            self._config_cache[key] = self._load_catalogo_from_disk(catalogo_id)
        # Cópia profunda: skills podem adicionar campos calculados ao catalogo sem
        # contaminar o objeto em cache para chamadas subsequentes.
        return copy.deepcopy(self._config_cache[key])

    def _load_resolved_catalogo(
        self,
        catalogo_id: str,
        jurisdicao_id: str | None,
        project: Any,
    ) -> dict[str, Any]:
        """ADR-066: load master catalog then apply jurisdiction + project overlays."""

        from concilium.application.services.catalog_resolver import CatalogResolver

        master = self.load_catalogo(catalogo_id)  # cached deep copy
        resolver = CatalogResolver(self.config_root)
        resolved, _trace = resolver.apply_overlays(master, project, jurisdicao_id)
        return resolved

    def _catalog_bundle_valid(self, cat_dir: Path, bundle_path: Path) -> bool:
        """Verifica se o bundle é mais novo que os arquivos JSON de origem.

        A verificação por mtime de diretório não detecta edição de conteúdo em
        todos os filesystems. Aqui validamos pelo mtime dos arquivos `.json`
        para garantir recarga após qualquer alteração de catálogo.
        """
        if not bundle_path.exists():
            return False
        try:
            bundle_mtime = bundle_path.stat().st_mtime
            for json_file in cat_dir.rglob("*.json"):
                if json_file.name == ".catalog_bundle.json":
                    continue
                if json_file.stat().st_mtime > bundle_mtime:
                    return False
            return True
        except Exception:
            return False

    @staticmethod
    def _load_cpus_from_cpu_dir(cpu_dir: Path) -> list:
        cpus: list = []
        if not (cpu_dir.exists() and cpu_dir.is_dir()):
            return cpus
        for f in cpu_dir.glob("*.json"):
            try:
                cpu_data = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(cpu_data, list):
                    cpus.extend(cpu_data)
                elif isinstance(cpu_data, dict) and "cpus" in cpu_data:
                    cpus.extend(cpu_data["cpus"])
                else:
                    cpus.append(cpu_data)
            except Exception:
                continue
        return cpus

    @staticmethod
    def _load_cpus_from_json(cpus_file: Path) -> list:
        try:
            cpu_data = json.loads(cpus_file.read_text(encoding="utf-8"))
            if isinstance(cpu_data, list):
                return cpu_data
            if isinstance(cpu_data, dict) and "cpus" in cpu_data:
                return cpu_data["cpus"]
            return []
        except Exception:
            return []

    @staticmethod
    def _load_producoes_from_cat_dirs(cat_dir: Path) -> list:
        producoes: list = []
        for dname in ["producoes", "produtividades"]:
            p_dir = cat_dir / dname
            if p_dir.exists() and p_dir.is_dir():
                for f in p_dir.glob("*.json"):
                    try:
                        p_data = json.loads(f.read_text(encoding="utf-8"))
                        if isinstance(p_data, list):
                            producoes.extend(p_data)
                        elif isinstance(p_data, dict):
                            producoes.append(p_data)
                    except Exception:
                        continue
        return producoes

    @staticmethod
    def _synthesize_missing_producoes(cpus: list, seen_prod_ids: set) -> list:
        result: list = []
        for cpu in cpus:
            prod_id_ref = cpu.get("producao_id_ref")
            producao_horaria = cpu.get("producao_horaria")
            if prod_id_ref and producao_horaria and prod_id_ref not in seen_prod_ids:
                result.append(
                    {
                        "id": prod_id_ref,
                        "valor_horario": float(producao_horaria),
                        "composicao_padrao_equipe": cpu.get("composicao_padrao_equipe"),
                    }
                )
                seen_prod_ids.add(prod_id_ref)
        return result

    @staticmethod
    def _merge_global_producoes(producoes: list, global_prods: list) -> list:
        seen_ids = {p["id"] for p in producoes if "id" in p}
        for gp in global_prods:
            if gp.get("id") not in seen_ids:
                producoes.append(gp)
        return producoes

    def _load_and_synthesize_producoes(self, cpus: list[dict[str, Any]], cat_dir: Path) -> list[dict[str, Any]]:
        producoes = self._load_producoes_from_cat_dirs(cat_dir)
        seen_prod_ids = {p.get("id") for p in producoes if "id" in p}
        synth = self._synthesize_missing_producoes(cpus, seen_prod_ids)
        producoes.extend(synth)
        global_prods = self._load_producoes_from_cpus(cpus, cat_dir)
        return self._merge_global_producoes(producoes, global_prods)

    def _load_catalogo_from_disk(self, catalogo_id: str) -> dict[str, Any]:
        cat_dir = self.config_root / "catalogos" / catalogo_id
        if not cat_dir.exists():
            raise RuntimeDomainError(f"Catálogo '{catalogo_id}' não encontrado em {cat_dir}")

        # Bundle cache: 648+ individual file reads → 1 read after first load.
        # Saves ~1.5s local, 8-10s on WSL+OneDrive paths.
        # Invalidated automatically when any catalog directory mtime changes.
        bundle_path = cat_dir / ".catalog_bundle.json"
        if self._catalog_bundle_valid(cat_dir, bundle_path):
            try:
                return json.loads(bundle_path.read_text(encoding="utf-8"))
            except Exception:
                pass  # corrupted bundle — fall through to full reload

        catalogo: dict[str, Any] = {
            "cpus": [],
            "insumos": [],
            "templates": {},
            "produtividades": [],
        }

        catalogo["cpus"] = self._load_cpus_from_cpu_dir(cat_dir / "cpus")
        if not catalogo["cpus"]:
            cpus_file = cat_dir / "cpus.json"
            if cpus_file.exists():
                catalogo["cpus"] = self._load_cpus_from_json(cpus_file)

        catalogo["insumos"] = self._load_insumos(cat_dir)

        templates_path = cat_dir / "templates.json"
        if templates_path.exists():
            data = json.loads(templates_path.read_text(encoding="utf-8"))
            catalogo["templates"] = data.get("templates", data) if isinstance(data, dict) else {}

        catalogo["producoes"] = self._load_and_synthesize_producoes(catalogo["cpus"], cat_dir)

        # Persiste bundle para acelerar próximas cargas (best-effort).
        try:
            bundle_path.write_text(json.dumps(catalogo, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        return catalogo

    def _load_producoes_from_cpus(
        self, cpus: list[dict[str, Any]], cat_dir: Path | None = None
    ) -> list[dict[str, Any]]:
        """Deriva e carrega artefatos Producao a partir dos producao_id referenciados pelas CPUs."""
        seen: set[str] = set()
        result: list[dict[str, Any]] = []

        # Locais de busca ordenada: Global (config/producoes) e Catálogo
        search_dirs = [self.config_root / "producoes"]
        if cat_dir:
            search_dirs.append(cat_dir / "producoes")
            search_dirs.append(cat_dir / "produtividades")

        for cpu in cpus:
            prod_id = cpu.get("producao_id_ref") or cpu.get("producao_id")
            if not prod_id or prod_id in seen:
                continue

            for p_dir in search_dirs:
                if not p_dir.exists():
                    continue
                path = p_dir / f"{prod_id}.json"
                if path.exists():
                    try:
                        result.append(json.loads(path.read_text(encoding="utf-8")))
                        seen.add(prod_id)
                        break
                    except Exception:
                        continue
        return result

    def _load_insumos(self, cat_dir: Path) -> list[dict[str, Any]]:
        """Carrega insumos de arquivos individuais ou subpastas por tipo."""
        dir_insumos = cat_dir / "insumos"
        if not dir_insumos.exists() or not dir_insumos.is_dir():
            return []

        insumos: list[dict[str, Any]] = []
        for f in dir_insumos.glob("*.json"):
            try:
                _rt_ingest_insumos(json.loads(f.read_text(encoding="utf-8")), insumos)
            except Exception:
                pass
        for sub in dir_insumos.iterdir():
            if sub.is_dir():
                _rt_load_insumos_subdir(sub, insumos)
        return _rt_dedup_insumos(insumos)

    def load_manifest(self, skill_id: str) -> dict[str, Any] | None:
        key = f"manifest:{skill_id}"
        if key in self._config_cache:
            return self._config_cache[key]
        manifests_dir = Path(__file__).parent.parent / "application" / "skills" / "manifests"
        manifest_path = manifests_dir / skill_id / "skill.toml"
        if not manifest_path.exists():
            self._config_cache[key] = None
            return None
        with manifest_path.open("rb") as f:
            result = tomllib.load(f)
        self._config_cache[key] = result
        return result

    def get_skill_contract(self, skill_id: str) -> SkillExecutionContract:
        if skill_id not in SKILLS:
            raise RuntimeDomainError(f"Skill desconhecida: '{skill_id}'. Disponíveis: {list(SKILLS)}")
        manifest = self.load_manifest(skill_id) or {}
        fn = SKILLS[skill_id]
        signature = list(inspect.signature(fn).parameters.keys())
        inputs_cfg = manifest.get("inputs", {})
        depends_cfg = manifest.get("depends_on", {})
        produces_cfg = manifest.get("produces", {})
        return SkillExecutionContract(
            skill_id=skill_id,
            signature=signature,
            required_inputs=inputs_cfg.get("required", []),
            optional_inputs=inputs_cfg.get("optional", []),
            depends_on_skills=depends_cfg.get("skills", []),
            produces_section=produces_cfg.get("canonical_section"),
            output_schema={"result_type": "SkillResult", "fields": ["canonical", "validacoes", "has_errors"]},
        )

    def check_manifest_deps(self, skill_id: str, project: ProjectStore, version: str) -> list[str]:
        manifest = self.load_manifest(skill_id)
        if manifest is None:
            return []
        dep_skills: list[str] = manifest.get("depends_on", {}).get("skills", [])
        if not dep_skills:
            return []
        log_path = project.version_path(version) / project.INVOCATIONS_LOG
        executed_ok = _rt_parse_executed_skills(log_path)
        return [dep for dep in dep_skills if dep not in executed_ok]

    def create_snapshots(self, project: ProjectStore) -> dict[str, str]:
        snaps = project.snapshots
        contexto = self.load_contexto(project.meta["contexto_id"])
        result: dict[str, str] = {}
        result["jurisdicao"] = snaps.store("jurisdicao", self.load_jurisdicao(contexto.jurisdicao_id))
        result["perfil"] = snaps.store("perfil", self.load_perfil(contexto.perfil_id))
        result["catalogo"] = snaps.store("catalogo", self.load_catalogo(contexto.catalogo_id))
        return result

    def _apply_runtime_defaults(
        self, skill_id: str, project: ProjectStore, contexto: ContextoObra, inputs: dict[str, Any]
    ) -> dict[str, Any]:
        normalized = dict(inputs)
        if skill_id == "01-escopo-e-eap":
            snap_ids = self.create_snapshots(project)
            normalized.setdefault("snapshot_catalogo_id", snap_ids["catalogo"])
            normalized.setdefault("snapshot_perfil_id", snap_ids["perfil"])
            normalized.setdefault("contexto_id", contexto.id)

            # Injeta dados do projeto/escopo se disponíveis (ADR-031 Integration)
            p_meta = project.meta
            normalized.setdefault("nome", p_meta.get("nome"))
            normalized.setdefault("tipo_obra", p_meta.get("tipo_obra", "terraplenagem"))
            normalized.setdefault("localizacao", p_meta.get("localizacao", "Não Definido"))
            normalized.setdefault("data_inicio", p_meta.get("data_inicio"))
            normalized.setdefault("data_termino", p_meta.get("data_termino"))
            normalized.setdefault("data_base_orcamento", p_meta.get("data_base_orcamento"))

            if "coordenadas" not in normalized and "coordenadas" in p_meta:
                normalized["coordenadas"] = p_meta["coordenadas"]
            else:
                normalized.setdefault(
                    "coordenadas",
                    {"lat": p_meta.get("coordenadas_lat", 0.0), "lng": p_meta.get("coordenadas_lng", 0.0)},
                )

            if "regime_trabalho" not in normalized:
                normalized["regime_trabalho"] = {
                    "dias_semana": p_meta.get("dias_semana", 6),
                    "horas_dia": p_meta.get("horas_dia", 8),
                }
        if skill_id == "03-equipes-diretas" and "percentual_encargos" not in normalized:
            jurisd = self.load_jurisdicao(contexto.jurisdicao_id)
            motor = jurisd.get("motor_encargos_sociais", {})
            if motor.get("percentual_total") is not None:
                normalized["percentual_encargos"] = motor["percentual_total"]
            if motor.get("percentual_mensalista") is not None:
                normalized["percentual_encargos_mensalista"] = motor["percentual_mensalista"]
        if skill_id == "09-relatorio-e-artefatos":
            try:
                deliv_cfg = project.read_json("deliverables_config.json", {})
                outputs = deliv_cfg.get("outputs", {}) if isinstance(deliv_cfg, dict) else {}
                normalized.setdefault(
                    "gerar_excel",
                    bool(outputs.get("resultado_xlsx", outputs.get("cronograma_xlsx", True))),
                )
                normalized.setdefault("gerar_modelo_vivo", bool(outputs.get("modelo_vivo_xlsx", False)))
            except Exception:
                pass
        return normalized

    def _build_skill_kwargs(
        self,
        contract: SkillExecutionContract,
        *,
        canonical_in: CanonicalModel | None,
        inputs: dict[str, Any],
        catalogo: dict[str, Any],
        perfil: dict[str, Any],
        contexto: ContextoObra,
        project: ProjectStore,
        version: str,
    ) -> dict[str, Any]:
        providers: dict[str, Any] = {
            "canonical_in": canonical_in,
            "inputs": inputs,
            "catalogo": catalogo,
            "perfil": perfil,
            "contexto": contexto,
            "project": project,
            "version": version,
            "runtime": self,
        }
        kwargs: dict[str, Any] = {}
        for param in contract.signature:
            if param in providers:
                kwargs[param] = providers[param]
        return kwargs

    def _rsk_resolve_missing_deps(
        self,
        contract: Any,
        skill_id: str,
        project: Any,
        v: str,
        _executed_ok: set[str] | None,
    ) -> list[str]:
        if _executed_ok is not None:
            return [d for d in contract.depends_on_skills if d not in _executed_ok]
        return self.check_manifest_deps(skill_id, project, v)

    def _rsk_handle_error(
        self,
        exc: Exception,
        skill_id: str,
        canonical_in: Any,
        project: Any,
        v: str,
        ts_inicio: Any,
        execution_id: str,
        correlation_id: str,
        trace_id: str | None,
    ) -> None:
        error_kind = "DOMINIO" if isinstance(exc, RuntimeDomainError) else "TECNICO"
        project.log_invocation(
            v,
            {
                "ts": ts_inicio.isoformat(),
                "execution_id": execution_id,
                "correlation_id": correlation_id,
                "skill": skill_id,
                "status": "ERRO",
                "error_kind": error_kind,
                "erro": str(exc),
            },
        )
        if skill_id in _GATE_SKILLS and canonical_in is not None:
            blocked = list(set(canonical_in.pipeline_blocked_from) | {skill_id})
            tainted = canonical_in.model_copy(
                update={
                    "pipeline_blocked_from": blocked,
                    "pipeline_integridade": "CORROMPIDO",
                }
            )
            project.save_canonical(tainted, v, trace_id=trace_id, created_by=f"taint:{skill_id}")
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeTechnicalError(f"Falha técnica ao executar skill '{skill_id}': {exc}") from exc

    def _rsk_execution_ids(self, normalized_inputs: dict, project: Any, v: str) -> tuple[str, str]:
        from uuid import uuid4 as _uuid4

        execution_id = normalized_inputs.get("execution_id") or str(_uuid4())
        correlation_id = normalized_inputs.get("correlation_id") or f"{project.meta['id']}:{v}"
        return execution_id, correlation_id

    def _rsk_build_log_entry(
        self,
        contract: Any,
        result: Any,
        ts_inicio: Any,
        ts_fim: Any,
        execution_id: str,
        correlation_id: str,
        skill_id: str,
    ) -> dict:
        return {
            "ts": ts_inicio.isoformat(),
            "execution_id": execution_id,
            "correlation_id": correlation_id,
            "skill": skill_id,
            "contract": {
                "required_inputs": contract.required_inputs,
                "optional_inputs": contract.optional_inputs,
                "depends_on_skills": contract.depends_on_skills,
                "produces_section": contract.produces_section,
            },
            "status": "ERRO" if result.has_errors else "OK",
            "duration_ms": int((ts_fim - ts_inicio).total_seconds() * 1000),
            "error_kind": "DOMINIO" if result.has_errors else None,
            "validacoes": [{"codigo": item.codigo, "status": item.status} for item in result.validacoes],
        }

    def run_skill(
        self,
        skill_id: str,
        project: ProjectStore,
        version: str | None = None,
        inputs: dict[str, Any] | None = None,
        trace_id: str | None = None,
        _executed_ok: set[str] | None = None,
    ) -> SkillResult:
        contract = self.get_skill_contract(skill_id)
        skill_fn = SKILLS[skill_id]

        v = version or project.current_version()
        if v is None:
            raise RuntimeDomainError("Nenhuma versão ativa. Execute 'concilium version new' primeiro.")

        missing_deps = self._rsk_resolve_missing_deps(contract, skill_id, project, v, _executed_ok)
        if missing_deps:
            raise RuntimeDomainError(f"Skill '{skill_id}' requer execução prévia bem-sucedida de: {missing_deps}")

        canonical_in = project.load_canonical(v)
        contexto = self.load_contexto(project.meta["contexto_id"])
        perfil = self.load_perfil(contexto.perfil_id)
        catalogo = self._load_resolved_catalogo(contexto.catalogo_id, contexto.jurisdicao_id, project)

        # ADR-065: injeta TemaVisual no catálogo (backward-compat via chave legada)
        catalogo["identidade_visual"] = self.load_tema(contexto.tema_id).to_catalogo_dict()

        normalized_inputs = self._apply_runtime_defaults(skill_id, project, contexto, inputs or {})

        ts_inicio = datetime.now(UTC)
        execution_id, correlation_id = self._rsk_execution_ids(normalized_inputs, project, v)
        kwargs = self._build_skill_kwargs(
            contract,
            canonical_in=canonical_in,
            inputs=normalized_inputs,
            catalogo=catalogo,
            perfil=perfil,
            contexto=contexto,
            project=project,
            version=v,
        )

        try:
            result = skill_fn(**kwargs)
        except Exception as exc:
            self._rsk_handle_error(
                exc, skill_id, canonical_in, project, v, ts_inicio, execution_id, correlation_id, trace_id
            )

        should_save = not (skill_id == "00-escopo" and result.has_errors)
        result, should_save = self._process_taint(skill_id, result, should_save)
        result, should_save = self._process_decision_variables(normalized_inputs, result, should_save)

        if should_save:
            project.save_canonical(
                result.canonical,
                v,
                trace_id=trace_id,
                created_by=skill_id,
            )

        self._process_side_effects(skill_id, result, project, v)

        ts_fim = datetime.now(UTC)
        project.log_invocation(
            v, self._rsk_build_log_entry(contract, result, ts_inicio, ts_fim, execution_id, correlation_id, skill_id)
        )
        return result

    def run_skill_on_plano(
        self,
        skill_id: str,
        project: ProjectStore,
        plano_store: Any,  # EscopoStore.PlanoStore
        inputs: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> SkillResult:
        """Executa uma skill sobre um Plano específico (ADR-031).

        Resolve o estado (canônico) diretamente do store do plano.
        """
        contract = self.get_skill_contract(skill_id)
        skill_fn = SKILLS[skill_id]

        canonical_in = plano_store.load_canonical()
        # Se não há canônico no plano, mas é a skill 00, iniciamos um novo
        if canonical_in is None and skill_id != "01-escopo-e-eap":
            raise RuntimeDomainError(
                f"Plano '{plano_store.plano_id}' não possui estado inicial. Execute '01-escopo-e-eap' primeiro."
            )

        # Carrega metadados do escopo para o contexto
        escopo_meta = plano_store.escopo_store.meta
        contexto, perfil, catalogo = self._rsop_load_context(escopo_meta, project)

        # Mescla metadados do escopo nos inputs base (ADR-031)
        base_inputs = dict(escopo_meta)
        base_inputs.update(inputs or {})

        normalized_inputs = self._apply_runtime_defaults(skill_id, project, contexto, base_inputs)

        # Injeta IDs de escopo/plano nos inputs se não presentes (ADR-031 tracking)
        normalized_inputs.setdefault("escopo_id", escopo_meta["escopo_id"])
        normalized_inputs.setdefault("plano_id", plano_store.plano_id)

        ts_inicio = datetime.now(UTC)
        execution_id = normalized_inputs.get("execution_id") or str(uuid4())

        kwargs = self._build_skill_kwargs(
            contract,
            canonical_in=canonical_in,
            inputs=normalized_inputs,
            catalogo=catalogo,
            perfil=perfil,
            contexto=contexto,
            project=project,
            version=plano_store.plano_id,
        )

        result = _rsop_execute_skill(skill_fn, kwargs, skill_id, execution_id, ts_inicio, plano_store)

        # Processamento de Taint e Variáveis de Decisão
        should_save = not (skill_id == "00-escopo" and result.has_errors)
        result, should_save = self._process_taint(skill_id, result, should_save)
        result, should_save = self._process_decision_variables(normalized_inputs, result, should_save)

        if should_save:
            plano_store.save_canonical(result.canonical, created_by=skill_id)

        # Side effects (outputs)
        v_label = f"{escopo_meta['escopo_id']}/{plano_store.plano_id}"
        self._process_side_effects(skill_id, result, project, v_label)

        plano_store.log_invocation(
            {
                "ts": ts_inicio.isoformat(),
                "execution_id": execution_id,
                "skill": skill_id,
                "status": "ERRO" if result.has_errors else "OK",
                "duration_ms": int((datetime.now(UTC) - ts_inicio).total_seconds() * 1000),
            }
        )
        return result

    def _rsop_load_context(self, escopo_meta: dict, project: Any) -> tuple:
        """Load contexto, perfil and catalogo for run_skill_on_plano."""
        contexto = self.load_contexto(escopo_meta.get("contexto_id") or project.meta["contexto_id"])
        perfil = self.load_perfil(escopo_meta.get("snapshot_perfil_id") or contexto.perfil_id)
        catalogo_id = escopo_meta.get("snapshot_catalogo_id") or contexto.catalogo_id
        catalogo = self._load_resolved_catalogo(catalogo_id, contexto.jurisdicao_id, project)
        catalogo["identidade_visual"] = self.load_tema(contexto.tema_id).to_catalogo_dict()
        return contexto, perfil, catalogo

    def _process_taint(self, skill_id: str, result: SkillResult, should_save: bool) -> tuple[SkillResult, bool]:
        if result.has_errors and skill_id in _GATE_SKILLS:
            canonical_before = result.canonical
            blocked = list(set(canonical_before.pipeline_blocked_from) | {skill_id})
            result = SkillResult(
                canonical_before.model_copy(
                    update={
                        "pipeline_blocked_from": blocked,
                        "pipeline_integridade": "CORROMPIDO",
                    }
                ),
                result.validacoes,
            )
            return result, True

        elif not result.has_errors and skill_id in _GATE_SKILLS:
            current_blocked = set(result.canonical.pipeline_blocked_from)
            if skill_id in current_blocked:
                new_blocked = sorted(current_blocked - {skill_id})
                new_integridade = "CORROMPIDO" if new_blocked else None
                result = SkillResult(
                    result.canonical.model_copy(
                        update={
                            "pipeline_blocked_from": new_blocked,
                            "pipeline_integridade": new_integridade,
                        }
                    ),
                    result.validacoes,
                )
                return result, True

        return result, should_save

    def _process_decision_variables(
        self, normalized_inputs: dict[str, Any], result: SkillResult, should_save: bool
    ) -> tuple[SkillResult, bool]:
        dv_raw = normalized_inputs.get("decision_variables")
        if dv_raw is not None and not result.has_errors:
            try:
                from concilium.domain.models.decision_variables import DecisionVariables

                dv_obj = DecisionVariables.model_validate(dv_raw) if isinstance(dv_raw, dict) else dv_raw
                if result.canonical.decision_variables != dv_obj:
                    result = SkillResult(
                        result.canonical.model_copy(update={"decision_variables": dv_obj}),
                        result.validacoes,
                        result.artifacts,
                    )
                    return result, True
            except Exception:
                pass
        return result, should_save

    def _process_side_effects(self, skill_id: str, result: SkillResult, project: ProjectStore, v: str) -> None:
        _persist_typed_artifacts(result, project, v)

        if skill_id == "09-relatorio-e-artefatos":
            try:
                _deliv_cfg = project.read_json("deliverables_config.json", {})
                _outputs_cfg: dict = _deliv_cfg.get("outputs", {})
            except Exception:
                _outputs_cfg = {}
            _handle_skill_09_side_effects(result, project, v, _outputs_cfg)

        elif skill_id == "12-registro-decisoes":
            decision_log = getattr(result, "decision_log", None)
            if decision_log:
                payload = json.dumps(decision_log, indent=2, ensure_ascii=False, default=_json_default)
                project.save_intermediate_file(
                    "decision_log.json",
                    payload,
                    v,
                )
                (project.version_path(v) / "decision_log.json").write_text(payload, encoding="utf-8")

        elif skill_id == "04-cronograma":
            _handle_skill_04_side_effects(result, project, v)

    def run_pipeline(
        self,
        store: ProjectStore,
        skill_inputs: dict[str, dict] | None = None,
        invocation_context: dict[str, Any] | None = None,
    ) -> list[dict]:
        """Executa o pipeline completo via SkillExecutor (domain-agnostic).

        O domínio é injetado como três closures:
        - providers_factory: resolve configs e normaliza inputs por skill
        - resolve_state: extrai canônico do resultado + aplica taint e decision variables
        - on_after_skill: persiste estado, processa side effects, grava invocations.log
        """
        skill_inputs = skill_inputs or {}
        invocation_context = invocation_context or {}
        version = store.current_version()
        if version is None:
            raise RuntimeDomainError("Nenhuma versão ativa. Execute 'concilium version new' primeiro.")

        initial_state = store.load_canonical(version)
        skip_bootstrap = initial_state is not None

        # ── Callback 1: providers ────────────────────────────────────────────
        providers_factory = functools.partial(self._rp_providers_factory, store, version)

        # ── Callback 2: state resolution (taint + decision variables) ────────
        def resolve_state(skill_id: str, result: Any, prev_state: Any) -> Any:
            return _rp_resolve_state(skill_id, result, skill_inputs)

        # ── Callback 3: side effects + persistence + log ─────────────────────
        on_before_skill = functools.partial(_rp_print_skill_start)

        def on_after_skill(skill_id: str, result: Any, new_state: Any, record: ExecutionRecord) -> None:
            _rp_on_after_skill(self, store, version, invocation_context, skill_id, result, new_state, record)

        # Skill 01 inicializa o canônico e deve rodar apenas quando não há estado prévio.
        # Em re-run/fork com canônico existente, pulamos a bootstrap para evitar VAL-ESCOPO-01.
        active_skills = (
            SKILLS if not skip_bootstrap else {sid: fn for sid, fn in SKILLS.items() if sid != "01-escopo-e-eap"}
        )
        executor = SkillExecutor(active_skills, MANIFEST_META)  # type: ignore[arg-type]
        _final_state, records = executor.run_pipeline(
            state_in=initial_state,
            providers_factory=providers_factory,
            skill_inputs=skill_inputs,
            resolve_state=resolve_state,
            on_before_skill=on_before_skill,
            on_after_skill=on_after_skill,
        )

        return _rp_format_records(records)

    def _rp_providers_factory(self, store: Any, version: str, skill_id: str, state: Any, extra_inputs: dict) -> dict:
        """Build providers dict for run_pipeline callback."""
        contexto = self.load_contexto(store.meta["contexto_id"])
        perfil = self.load_perfil(contexto.perfil_id)
        catalogo = self._load_resolved_catalogo(contexto.catalogo_id, contexto.jurisdicao_id, store)
        catalogo["identidade_visual"] = self.load_tema(contexto.tema_id).to_catalogo_dict()
        normalized = self._apply_runtime_defaults(skill_id, store, contexto, extra_inputs)
        return {
            "canonical_in": state,
            "inputs": normalized,
            "catalogo": catalogo,
            "perfil": perfil,
            "contexto": contexto,
            "project": store,
            "version": version,
            "runtime": self,
        }

    def _meta_is_gate(self, skill_id: str) -> bool:
        return MANIFEST_META.get(skill_id, {}).get("gate", False)

    def plan_with_decisions(
        self,
        canonical: CanonicalModel,
        decisions: Any,
        catalogo: dict | None = None,
        perfil: dict | None = None,
        extra_inputs: dict | None = None,
    ) -> tuple:
        from concilium.application.optimizer.loop import adjust_schedule

        return adjust_schedule(
            canonical_in=canonical,
            decision_variables=decisions,
            catalogo=catalogo,
            perfil=perfil,
            extra_inputs=extra_inputs,
        )
