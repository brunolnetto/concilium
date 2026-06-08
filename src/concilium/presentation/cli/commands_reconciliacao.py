"""Comando CLI para reconciliação de planejamento.txt ↔ canonical."""

from pathlib import Path

import typer

from concilium.application.benchmarks.reconciliacao_planejamento import (
    ReconciliadorPlanejamento,
    gerar_relatorio_reconciliacao,
)
from concilium.infrastructure.storage.project import ProjectStore


def reconciliar(
    slug: str = typer.Option("AGIS", help="Slug do benchmark (ex: AGIS, RUMO)"),
    projects_root: str | None = typer.Option(
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

        # Gerar relatório básico
        if analise:
            relatorio = gerar_relatorio_reconciliacao(analise)
            typer.echo(relatorio)

            # Executar análise LLM
            typer.echo("\n🤖 Executando análise com LLM para interpretação de disparidades...\n")

            from concilium.application.benchmarks.analise_llm_reconciliacao import (
                AnalisadorLLMReconciliacao,
                gerar_relatorio_llm,
            )

            try:
                import os

                # Converter dados para dicts simples para envio ao LLM
                dados_plan_simples = {}
                for item_id, custo in analise.planejamento.items():
                    dados_plan_simples[item_id] = {
                        "descricao": custo.descricao,
                        "total_sem_bdi": custo.total_sem_bdi,
                        "total_com_bdi": custo.total_com_bdi,
                    }

                # Análise LLM (com suporte a variável de ambiente)
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    raise ValueError(
                        "ANTHROPIC_API_KEY não configurada. Configure via: export ANTHROPIC_API_KEY=sk-..."
                    )

                analisador = AnalisadorLLMReconciliacao(api_key=api_key)
                analise_llm = analisador.analisar(
                    dados_planejamento=dados_plan_simples,
                    dados_canonical=analise.canonical_direto,
                    disparidades=analise.disparidades,
                )

                relatorio_llm = gerar_relatorio_llm(analise_llm)
                typer.echo(relatorio_llm)

                # Salvar relatórios
                output_dir = (benchmark_dir / "artifacts" / "outputs").resolve()
                output_dir.mkdir(parents=True, exist_ok=True)

                relatorio_path = output_dir / "reconciliacao_planejamento.txt"
                relatorio_path.write_text(relatorio, encoding="utf-8")

                relatorio_llm_path = output_dir / "reconciliacao_analise_llm.txt"
                relatorio_llm_path.write_text(relatorio_llm, encoding="utf-8")

                typer.echo(f"\n✅ Relatórios salvos em:\n   - {relatorio_path}\n   - {relatorio_llm_path}")
            except Exception as e:
                typer.echo(f"\n⚠️  Erro na análise LLM (continuando com relatório básico): {e}", err=True)
                # Continuar mesmo sem análise LLM

        else:
            typer.echo("❌ Análise falhou")
            raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"❌ Erro durante análise: {e}", err=True)
        raise typer.Exit(1)
