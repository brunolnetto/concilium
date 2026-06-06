"""Helper functions for commands_manage (A)."""

# ruff: noqa: F401
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from concilium.presentation.cli.shared import resolve_project


def _load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else default
    except Exception:
        return default


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _cq_validate_cpus(cpus: list, validador: object) -> tuple[list, list, list]:
    erros: list = []
    avisos: list = []
    cpus_bloqueadas: list = []
    for cpu in cpus:
        for r in validador.validar_cpu_completa(cpu):  # type: ignore[union-attr]
            if r.status == "ERRO":
                erros.append((cpu["codigo"], r))
                if r.codigo in ["VAL-CPU-STR-02", "VAL-CPU-STR-03"]:
                    cpus_bloqueadas.append(cpu["codigo"])
            elif r.status == "AVISO":
                avisos.append((cpu["codigo"], r))
    return erros, avisos, cpus_bloqueadas


def _cq_validate_insumos(insumos: list, validador: object) -> tuple[list, list]:
    avisos: list = []
    insumos_obsoletos: list = []
    for insumo in insumos:
        res_v = validador.validar_vigencia(insumo)  # type: ignore[union-attr]
        if res_v.status == "AVISO":
            insumos_obsoletos.append(insumo["codigo"])
            avisos.append((insumo["codigo"], res_v))
        res_e = validador.validar_encoding(insumo)  # type: ignore[union-attr]
        if res_e.status == "AVISO":
            avisos.append((insumo["codigo"], res_e))
    return avisos, insumos_obsoletos


def _cq_print_blocked_cpus(cpus_bloqueadas: list, erros: list, console: object) -> None:
    if not cpus_bloqueadas:
        return
    table_err = Table(title="CPUs com Risco de Inviabilidade (Cronograma)", header_style="bold red")
    table_err.add_column("Código CPU", style="cyan")
    table_err.add_column("Causa do Bloqueio")
    for codigo, err in erros:
        if codigo in cpus_bloqueadas:
            table_err.add_row(codigo, err.mensagem)
    console.print(table_err)  # type: ignore[union-attr]


def _cq_print_encoding_alerts(avisos: list, console: object) -> None:
    alertas_encoding = [a for a in avisos if a[1].codigo == "VAL-CAT-ENC-01"]
    if not alertas_encoding:
        return
    table_enc = Table(title="Alertas de Corrupção de Texto (Mojibake)", header_style="bold yellow")
    table_enc.add_column("Item", style="cyan")
    table_enc.add_column("Evidência")
    for item, alert in alertas_encoding[:10]:
        table_enc.add_row(item, alert.mensagem)
    if len(alertas_encoding) > 10:
        table_enc.add_row("...", f"Mais {len(alertas_encoding) - 10} alertas omitidos")
    console.print(table_enc)  # type: ignore[union-attr]


def _cq_fmt_pct(part_len: int, total_len: int) -> str:
    p = (part_len / total_len) * 100 if total_len else 0
    color = "green" if p >= 95 else "yellow" if p >= 70 else "red"
    return f"[{color}]{p:.1f}%[/{color}]"


def _impl_catalog_quality(contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto")):
    """Verifica a integridade de composição, ciclos e produtividade do catálogo."""
    from concilium.domain.validations.circular_deps import verificar_ciclos_cpu
    from concilium.domain.validations.cpu_insumo import ValidadorCPUInsumo
    from concilium.infrastructure.repositories.insumo import RepositorioInsumo
    from concilium.presentation.mcp._context import _runtime

    rt = _runtime()
    ctx = rt.load_contexto(contexto_id)
    catalogo = rt.load_catalogo(ctx.catalogo_id)
    validador = ValidadorCPUInsumo(RepositorioInsumo(catalogo))
    console = Console()

    cpus = catalogo.get("cpus", [])
    insumos = catalogo.get("insumos", [])

    erros, avisos_cpu, cpus_bloqueadas = _cq_validate_cpus(cpus, validador)
    avisos_ins, insumos_obsoletos = _cq_validate_insumos(insumos, validador)
    ciclos = verificar_ciclos_cpu(catalogo)
    avisos = avisos_cpu + avisos_ins

    insumos_com_preco = [i for i in insumos if i.get("preco_unitario") or i.get("versoes")]

    console.print(f"\n[bold cyan]DIAGNÓSTICO DE SAÚDE DO CATÁLOGO: {ctx.catalogo_id}[/bold cyan]\n")
    table = Table(title="Resumo de Cobertura", show_header=True, header_style="bold magenta")
    table.add_column("Métrica")
    table.add_column("Total", justify="right")
    table.add_column("Cobertura", justify="right")
    table.add_row("Insumos Cadastrados", str(len(insumos)), "100%")
    table.add_row("Insumos com Preço", str(len(insumos_com_preco)), _cq_fmt_pct(len(insumos_com_preco), len(insumos)))
    table.add_row(
        "Insumos com Vigência 2025",
        str(len(insumos) - len(insumos_obsoletos)),
        _cq_fmt_pct(len(insumos) - len(insumos_obsoletos), len(insumos)),
    )
    table.add_row("CPUs Cadastradas", str(len(cpus)), "100%")
    table.add_row(
        "CPUs Calculáveis (Portão 02)",
        str(len(cpus) - len(cpus_bloqueadas)),
        _cq_fmt_pct(len(cpus) - len(cpus_bloqueadas), len(cpus)),
    )
    console.print(table)

    _cq_print_blocked_cpus(cpus_bloqueadas, erros, console)
    _cq_print_encoding_alerts(avisos, console)

    if erros or ciclos:
        console.print(f"\n[bold red]STATUS FINAL: REPROVADO PARA PRODUÇÃO ({len(erros)} Erros Críticos)[/bold red]")
    elif avisos:
        console.print(
            f"\n[bold yellow]STATUS FINAL: APROVADO COM RESSALVAS ({len(avisos)} Avisos de Qualidade)[/bold yellow]"
        )
    else:
        console.print("\n[bold green]STATUS FINAL: 100% ÍNTEGRO E CALIBRADO[/bold green]")


def _impl_catalog_simulate(
    cpu_id: str = typer.Argument(..., help="Código da CPU"),
    contexto_id: str = typer.Option("mendeslobo", "--contexto", "-c", help="ID do contexto"),
    dias: int = typer.Option(30, "--dias", "-d", help="Período em dias corridos"),
    regime: str = typer.Option("6x1", "--regime", "-r", help="Regime (6x1, 5x2, 7x0)"),
    horas_dia: float = typer.Option(8.0, "--horas-dia", "-h", help="Carga horária diária"),
):
    """Simula produção e compara regimes CLT (1.77) vs PJ (1.06) lado a lado."""
    from concilium.domain.services.simulation import SimuladorEngenharia
    from concilium.presentation.mcp._context import _runtime

    rt = _runtime()
    ctx = rt.load_contexto(contexto_id)
    catalogo = rt.load_catalogo(ctx.catalogo_id)
    simulador = SimuladorEngenharia(catalogo)
    console = Console()

    try:
        # Roda ambas as simulações
        res_clt = simulador.simular_cpu(cpu_id, dias, regime, horas_dia, "clt")
        res_pj = simulador.simular_cpu(cpu_id, dias, regime, horas_dia, "pj")

        console.print(f"\n[bold cyan]CIÊNCIA DE CUSTOS COMPARATIVA: {cpu_id}[/bold cyan]")
        console.print(f"Cenário: {dias} dias | Regime {regime} | {horas_dia}h/dia\n")

        # Tabela 1: Produção (Comum a ambos)
        table_prod = Table(show_header=True, header_style="bold magenta")
        table_prod.add_column("Desempenho Operacional", style="dim")
        table_prod.add_column("Valor", justify="right")
        table_prod.add_row("Dias Trabalhados", f"{res_clt.dias_trabalhados} dias")
        table_prod.add_row("Produção Total", f"{res_clt.producao_total:,.2f} {res_clt.unidade}")
        console.print(table_prod)

        # Tabela 2: Comparativo de Regimes
        table_comp = Table(
            title="DNA de Custos Diretos: CLT (1.77) vs PJ (1.06)", show_header=True, header_style="bold green"
        )
        table_comp.add_column("Componente de Custo", style="cyan")
        table_comp.add_column("Cenário CLT (1.77)", justify="right")
        table_comp.add_column("Cenário PJ (1.06)", justify="right")

        def fmt_c(v):
            return f"R$ {v:,.2f}"

        # 1. Materiais
        table_comp.add_row("Materiais (Insumos)", fmt_c(res_clt.custo_material), fmt_c(res_pj.custo_material))

        # 2. Mão de Obra
        table_comp.add_row(
            "Mão de Obra (Salário Base)", fmt_c(res_clt.custo_mao_obra_base), fmt_c(res_pj.custo_mao_obra_base)
        )
        table_comp.add_row(
            "Mão de Obra (Encargos)",
            f"[yellow]{fmt_c(res_clt.custo_mao_obra_encargos)}[/yellow]",
            f"[dim]{fmt_c(res_pj.custo_mao_obra_encargos)}[/dim]",
        )

        # 3. Equipamentos e Diesel
        table_comp.add_row(
            "Equipamentos (Capital/Aluguel)",
            fmt_c(res_clt.custo_equipamento_capital),
            fmt_c(res_pj.custo_equipamento_capital),
        )
        table_comp.add_row(
            "Equipamentos (Manutenção)",
            fmt_c(res_clt.custo_equipamento_manutencao),
            fmt_c(res_pj.custo_equipamento_manutencao),
        )
        table_comp.add_row(
            "Diesel (Combustível)",
            f"[blue]{fmt_c(res_clt.custo_diesel_total)}[/blue]",
            f"[blue]{fmt_c(res_pj.custo_diesel_total)}[/blue]",
        )

        table_comp.add_section()
        diff = res_clt.total_direto - res_pj.total_direto
        table_comp.add_row(
            "[bold]TOTAL DIRETO[/bold]",
            f"[bold green]{fmt_c(res_clt.total_direto)}[/bold green]",
            f"[bold white]{fmt_c(res_pj.total_direto)}[/bold white]",
        )

        console.print(table_comp)

        console.print(
            f"\n[bold yellow]Delta de Contratação: {fmt_c(diff)} ({(diff / res_pj.total_direto) * 100:.1f}% de acréscimo no modo CLT)[/bold yellow]"  # noqa: E501
        )

    except Exception as e:
        console.print(f"[bold red]Erro na simulação:[/bold red] {e}")
        # console.print(traceback.format_exc())
        raise typer.Exit(1) from None


def _impl_catalog_export(
    contexto_id: str = typer.Option("mendeslobo", "--contexto", "-c", help="ID do contexto"),
    output: str = typer.Option(None, "--output", "-o", help="Caminho do arquivo de saída (.xlsx)"),
):
    """Exporta o catálogo completo para Excel (Auder-Ready)."""
    from concilium.infrastructure.exporters.catalog_excel import CatalogExporterExcel
    from concilium.presentation.mcp._context import _runtime

    rt = _runtime()
    ctx = rt.load_contexto(contexto_id)
    catalogo = rt.load_catalogo(ctx.catalogo_id)
    # ADR-065: TemaVisual substitui identidade_visual em ContextoObra
    catalogo["identidade_visual"] = rt.load_tema(ctx.tema_id).to_catalogo_dict()
    console = Console()

    if not output:
        output = f"catalogo_{contexto_id}_audit.xlsx"

    path = Path(output)

    with console.status(f"[bold green]Exportando catálogo para {path.name}..."):
        try:
            exporter = CatalogExporterExcel(catalogo)
            exporter.export(path)
            console.print(
                f"\n[bold green][OK] Sucesso![/bold green] Catálogo exportado para: [cyan]{path.absolute()}[/cyan]"
            )
        except Exception as e:
            console.print(f"[bold red]Erro na exportação:[/bold red] {e}")
            raise typer.Exit(1) from None
