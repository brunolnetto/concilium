"""Comando CLI para reconciliação de planejamento.txt ↔ canonical."""

from pathlib import Path
from typing import Optional

import typer

from concilium.application.benchmarks.reconciliacao_planejamento import (
    ReconciliadorPlanejamento,
    gerar_relatorio_reconciliacao,
)
from concilium.infrastructure.storage.project import ProjectStore


def reconciliar(
    slug: str = typer.Option("AGIS", help="Slug do benchmark (ex: AGIS, RUMO)"),
    projects_root: Optional[str] = typer.Option(
        None,
        help="Raiz de diretórios de projetos (padrão: benchmarks/projetos/)",
    ),
) -> None:
    """Reconcilia planejamento.txt com canonical model.

    Compara dados de planejamento original (curado em .txt) com dados
    processados pelo pipeline (canonical), identificando disparidades e
    rastreando custos diretos/indiretos com/sem BDI.

    Exemplo:
        concilium benchmark reconciliar --slug AGIS
    """
    slug_upper = slug.upper()

    if projects_root is None:
        # Descobrir automaticamente a partir do CWD
        root = Path.cwd()
        if (root / "benchmarks" / "projetos").exists():
            projects_root = str(root / "benchmarks" / "projetos")
        else:
            typer.echo("❌ Erro: benchmarks/projetos/ não encontrado", err=True)
            raise typer.Exit(1)

    projects_root = Path(projects_root)

    # Descobrir UUID do projeto a partir de meta.json
    import json

    project_store_root = None
    for candidate in projects_root.glob("*/meta.json"):
        try:
            meta = json.loads(candidate.read_text())
            if meta.get("derivado_de_benchmark") == slug_upper:
                project_store_root = candidate.parent
                break
        except Exception:
            continue

    if not project_store_root:
        typer.echo(f"❌ Erro: Projeto {slug_upper} não encontrado em {projects_root}", err=True)
        raise typer.Exit(1)

    # Carregar canonical
    try:
        store = ProjectStore(root=project_store_root)
        canonical = store.load_canonical()
    except Exception as e:
        typer.echo(f"❌ Erro ao carregar canonical: {e}", err=True)
        raise typer.Exit(1)

    # Descobrir planejamento.txt
    benchmarks_root = projects_root.parent / "data"
    benchmark_dir = benchmarks_root / slug_upper
    planejamento_path = benchmark_dir / "artifacts" / "raw" / "planejamento.txt"

    if not planejamento_path.exists():
        typer.echo(f"⚠️  Aviso: planejamento.txt não encontrado em {planejamento_path}", err=True)
        typer.echo("    Análise parcial (canonical apenas)")
        planejamento_path = None

    # Executar análise
    try:
        if planejamento_path:
            reconciliador = ReconciliadorPlanejamento(canonical, planejamento_path)
            analise = reconciliador.analisar()
        else:
            analise = None

        # Gerar relatório
        if analise:
            relatorio = gerar_relatorio_reconciliacao(analise)
            typer.echo(relatorio)

            # Salvar relatório
            output_dir = (benchmark_dir / "artifacts" / "outputs").resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            relatorio_path = output_dir / "reconciliacao_planejamento.txt"
            relatorio_path.write_text(relatorio, encoding="utf-8")
            typer.echo(f"\n✅ Relatório salvo em: {relatorio_path}")
        else:
            typer.echo("❌ Análise falhou")
            raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"❌ Erro durante análise: {e}", err=True)
        raise typer.Exit(1)
