"""CLI unificada de validação.

Comandos:
  concilium validate project <projeto> [--version vN] [--json]
  concilium validate benchmark <slug> [--json]
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import typer
from rich import print as rprint
from rich.table import Table

from concilium.presentation.cli.shared import _tools_root, parse_project_version, resolve_project

app = typer.Typer(
    name="validate",
    help="Validação unificada para projeto e benchmark.",
    no_args_is_help=True,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _empty_resumo() -> dict[str, int]:
    return {"verde": 0, "amarelo": 0, "vermelho": 0}


def _tally_resumo(validacoes: list, resumo: dict) -> None:
    for v in validacoes:
        st = str(v.get("status") or "").upper()
        if st == "OK":
            resumo["verde"] += 1
        elif st == "AVISO":
            resumo["amarelo"] += 1
        elif st in ("ERRO", "EXCEPTION"):
            resumo["vermelho"] += 1


def _collect_project_validacoes(canonical_dict: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    validacoes: list[dict[str, Any]] = []
    resumo = _empty_resumo()

    raw_list = (canonical_dict.get("resultado") or {}).get("validacoes")
    items_list = raw_list if raw_list else []
    for item in items_list:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").upper()
        codigo = str(item.get("codigo") or "VAL-GENERIC")
        mensagem = str(item.get("mensagem") or "")
        validacoes.append({"codigo": codigo, "status": status, "mensagem": mensagem})

    _tally_resumo(validacoes, resumo)

    return validacoes, resumo


def _val_status_color(status: str) -> str:
    if status == "OK":
        return "green"
    if status == "AVISO":
        return "yellow"
    return "red"


def _render_human(payload: dict[str, Any]) -> None:
    rprint(f"[bold cyan]Validação[/bold cyan] {payload['target_type']} :: {payload['target_id']}")
    rprint(
        f"Fonte: contexto={payload['source'].get('contexto_id')} versão={payload['source'].get('version')} ts={payload['source'].get('timestamp')}"  # noqa: E501
    )

    if payload.get("margem_pct") is not None:
        margem_pct = payload["margem_pct"]
        status_margem = payload.get("status_margem", "")
        color = "green" if str(status_margem).upper() == "APROVADO" else "yellow"
        rprint(f"Margem: [{color}]{margem_pct * 100:.2f}%[/{color}] ({status_margem})")

    resumo = payload.get("resumo_convergencia") or _empty_resumo()
    rprint(
        "Resumo convergência => "
        f"[green]VERDE={resumo.get('verde', 0)}[/green] "
        f"[yellow]AMARELO={resumo.get('amarelo', 0)}[/yellow] "
        f"[red]VERMELHO={resumo.get('vermelho', 0)}[/red]"
    )

    table = Table(title="Validações", show_header=True, header_style="bold")
    table.add_column("Código", style="cyan")
    table.add_column("Status", width=12)
    table.add_column("Mensagem")

    for v in payload.get("validacoes") or []:
        status = str(v.get("status") or "")
        color = _val_status_color(status)
        table.add_row(str(v.get("codigo") or ""), f"[{color}]{status}[/{color}]", str(v.get("mensagem") or ""))

    rprint(table)


@app.command("project")
def validate_project(
    project_ref: str = typer.Argument(..., help="Nome ou UUID do projeto. Aceita formato projeto@vN."),
    version: str = typer.Option("", "--version", help="Versão explícita (vN). Se vazio, usa current_version."),
    as_json: bool = typer.Option(False, "--json", help="Emite payload JSON no contrato unificado."),
) -> None:
    """Valida projeto com contrato comum."""
    nome, ver_inline = parse_project_version(project_ref)
    project = resolve_project(nome)
    resolved_version = version or ver_inline or project.current_version()
    canonical = project.load_canonical(resolved_version)
    if canonical is None:
        rprint("[red]Projeto sem canônico para validar. Execute o pipeline primeiro.[/red]")
        raise typer.Exit(1)

    canonical_dict = canonical.model_dump() if hasattr(canonical, "model_dump") else {}
    validacoes, resumo = _collect_project_validacoes(canonical_dict)

    payload: dict[str, Any] = {
        "target_type": "project",
        "target_id": project.meta.get("id"),
        "source": {
            "contexto_id": project.meta.get("contexto_id"),
            "version": resolved_version,
            "timestamp": _now_iso(),
        },
        "resumo_convergencia": resumo,
        "validacoes": validacoes,
    }
    if canonical.resultado:
        payload["margem_pct"] = canonical.resultado.margem_pct
        payload["status_margem"] = getattr(canonical.resultado, "status_margem", "")

    if as_json:
        rprint(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        _render_human(payload)


@app.command("benchmark")
def validate_benchmark(
    slug: str = typer.Argument(..., help="Slug do benchmark (ex: AGIS)."),
    as_json: bool = typer.Option(False, "--json", help="Emite payload JSON no contrato unificado."),
) -> None:
    """Valida benchmark com contrato comum."""
    from concilium.application.benchmarks.analysis import validate_pipeline_integrity

    result = validate_pipeline_integrity(slug.upper(), root=_tools_root())
    checkpoints = result.get("validacoes_fechamento") or []

    validacoes: list[dict[str, Any]] = []
    resumo = _empty_resumo()
    for idx, cp in enumerate(checkpoints, start=1):
        status_raw = str(cp.get("status") or "").upper()
        if status_raw == "OK":
            resumo["verde"] += 1
            status = "OK"
        else:
            resumo["vermelho"] += 1
            status = "ERRO"
        validacoes.append(
            {
                "codigo": f"VAL-BENCH-CHK-{idx:02d}",
                "status": status,
                "mensagem": f"{cp.get('checkpoint')}: status={status_raw} delta={cp.get('delta', cp.get('delta_indireto_adicionado', 0))}",  # noqa: E501
            }
        )

    payload = {
        "target_type": "benchmark",
        "target_id": slug.upper(),
        "source": {
            "contexto_id": result.get("analise_base_referencia", {}).get("contexto_id", "benchmark"),
            "version": "n/a",
            "timestamp": _now_iso(),
        },
        "resumo_convergencia": resumo,
        "validacoes": validacoes,
    }

    if as_json:
        rprint(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        _render_human(payload)
