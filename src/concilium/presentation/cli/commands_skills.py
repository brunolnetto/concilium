"""CLI commands para o grupo 'skills': export de diagrama de dependências."""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(
    name="skills",
    help="Gerenciamento e exportação dos manifests de skills.",
    no_args_is_help=True,
)


@app.command("export")
def skills_export(
    group_by_phase: bool = typer.Option(False, "--group-by-phase", help="Agrupa skills por fase (subgraphs)."),
    show_validations: bool = typer.Option(False, "--show-validations", help="Inclui códigos VAL-* nos nós."),
    output: str | None = typer.Option(None, "--output", "-o", help="Arquivo de saída (.md, .json, .dot)."),
    format: str = typer.Option("mermaid", "--format", "-f", help="mermaid (padrão) | json | dot"),
) -> None:
    """Exporta o grafo de dependências de skills em Mermaid, JSON ou DOT.

    O grafo é derivado dos arquivos skill.toml de cada manifest — reflete as
    dependências reais declaradas, não uma cadeia linear arbitrária.
    """
    from concilium.application.skills.graph_exporter import SkillGraphExporter

    exporter = SkillGraphExporter()

    match format.lower():
        case "json":
            import json

            content = json.dumps(exporter.to_json(), indent=2, ensure_ascii=False)
        case "dot":
            content = exporter.to_dot()
        case _:  # mermaid (default)
            content = exporter.to_mermaid(
                group_by_phase=group_by_phase,
                show_validations=show_validations,
            )

    if output:
        Path(output).write_text(content, encoding="utf-8")
        typer.echo(f"Exportado para: {output}")
    else:
        typer.echo(content)
