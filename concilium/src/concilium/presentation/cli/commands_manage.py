"""Commands: catalog, bdi, structure (Escopo/Plano)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from concilium.presentation.cli.shared import resolve_project

app_catalog = typer.Typer(name="catalog", help="Gestão de Catálogos Corporativos.", no_args_is_help=True)
app_bdi = typer.Typer(name="bdi", help="Gestão do perfil BDI do projeto.", no_args_is_help=True)
app_structure = typer.Typer(name="structure", help="Gestão de Escopos e Planos (ADR-031).", no_args_is_help=True)


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


# ── Catalog ───────────────────────────────────────────────────────────


def _fmt_pct_quality(part_count: int, total_count: int) -> str:
    p = (part_count / total_count) * 100 if total_count else 0
    color = "green" if p >= 95 else "yellow" if p >= 70 else "red"
    return f"[{color}]{p:.1f}%[/{color}]"


def _audit_cpus_quality(cpus: list, validador: object) -> tuple[list, list, list]:
    erros: list = []
    avisos: list = []
    cpus_bloqueadas: list = []
    for cpu in cpus:
        res = validador.validar_cpu_completa(cpu)  # type: ignore[union-attr]
        for r in res:
            if r.status == "ERRO":
                erros.append((cpu["codigo"], r))
                if r.codigo in ["VAL-CPU-STR-02", "VAL-CPU-STR-03"]:
                    cpus_bloqueadas.append(cpu["codigo"])
            elif r.status == "AVISO":
                avisos.append((cpu["codigo"], r))
    return erros, avisos, cpus_bloqueadas


def _audit_insumos_quality(insumos: list, validador: object) -> tuple[list, list]:
    insumos_obsoletos: list = []
    avisos: list = []
    for insumo in insumos:
        res_v = validador.validar_vigencia(insumo)  # type: ignore[union-attr]
        if res_v.status == "AVISO":
            insumos_obsoletos.append(insumo["codigo"])
            avisos.append((insumo["codigo"], res_v))
        res_e = validador.validar_encoding(insumo)  # type: ignore[union-attr]
        if res_e.status == "AVISO":
            avisos.append((insumo["codigo"], res_e))
    return insumos_obsoletos, avisos


def _print_merge_report_table(console: object, report_ins: object, report_prod: object) -> None:
    from rich.table import Table

    table = Table(title="Merge Report", show_header=True, header_style="bold cyan")
    table.add_column("Entidade")
    table.add_column("INNER_HIGH", justify="right")
    table.add_column("INNER_HIGH Δ", justify="right")
    table.add_column("INNER_LOW", justify="right")
    table.add_column("RIGHT_ONLY", justify="right")
    table.add_column("LEFT_ONLY", justify="right")
    for label, rep in [("INSUMOS", report_ins), ("PRODUCOES", report_prod)]:
        table.add_row(
            label,
            str(len(rep.inner_high)),
            str(sum(1 for i in rep.inner_high if i["delta"])),
            str(len(rep.inner_low)),
            str(len(rep.right_only)),
            str(len(rep.left_only)),
        )
    console.print(table)  # type: ignore[union-attr]


def _print_inner_low_collisions(console: object, all_low: list) -> None:
    if not all_low:
        return
    console.print(f"\n[yellow]INNER_LOW — {len(all_low)} colisões (importados como RFI-*):[/yellow]")  # type: ignore[union-attr]
    for item, etype in all_low[:15]:
        cat_e = item["catalog"]
        rfi_e = item["rfi"]
        console.print(  # type: ignore[union-attr]
            f"  [{item['score']:.2f}] {etype} "
            f'cat={cat_e.get("codigo", "")[:20]} "{cat_e.get("descricao", "")[:25]}" '
            f'| rfi={rfi_e.get("codigo", "")[:20]} "{rfi_e.get("descricao", "")[:25]}"'
        )
    if len(all_low) > 15:
        console.print(f"  ... e mais {len(all_low) - 15}")  # type: ignore[union-attr]


def _apply_merge_operation(
    console: object,
    bundle: dict,
    bundle_path: object,
    mod: object,
    cat_insumos: list,
    rfi_insumos: list,
    cat_producoes: list,
    rfi_producoes: list,
    report_ins: object,
    report_prod: object,
    verify_pu: bool,
) -> None:
    import json

    new_ins = mod._apply_merge(cat_insumos, rfi_insumos, report_ins)  # type: ignore[union-attr]
    new_prod = mod._apply_merge(cat_producoes, rfi_producoes, report_prod, id_key="id")  # type: ignore[union-attr]
    if "producoes" in bundle:
        bundle["producoes"] = new_prod
    else:
        bundle["produtividades"] = new_prod
    bundle["insumos"] = new_ins
    bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")  # type: ignore[union-attr]
    console.print(f"\n[green]Bundle atualizado:[/green] {bundle_path}")  # type: ignore[union-attr]
    console.print(f"  Insumos:   {len(new_ins)} (era {len(cat_insumos)})")  # type: ignore[union-attr]
    console.print(f"  Producoes: {len(new_prod)} (era {len(cat_producoes)})")  # type: ignore[union-attr]
    if verify_pu:
        from concilium.application.catalog.pu_calculator import ParametrosCalculo, calcular_catalogo

        resultado = calcular_catalogo(new_prod, new_ins, ParametrosCalculo())
        faltantes = resultado["referencias_faltantes"]
        if faltantes:
            console.print(f"\n[red]Referências faltantes após merge:[/red] {len(faltantes)}")  # type: ignore[union-attr]
            for r in faltantes[:10]:
                console.print(f"  {r['producao_id']}: {r['faltantes']}")  # type: ignore[union-attr]
        else:
            console.print(  # type: ignore[union-attr]
                f"\n[green]Integridade referencial OK[/green] — {resultado['com_composicao']} produções verificadas"
            )


def _build_and_save_report_json(
    report_json: str,
    mode: str,
    contexto_id: str,
    report_ins: object,
    report_prod: object,
) -> None:
    import json
    from pathlib import Path

    if not report_json:
        return
    report_data = {
        "mode": mode,
        "contexto_id": contexto_id,
        "insumos": {
            "inner_high": len(report_ins.inner_high),  # type: ignore[union-attr]
            "inner_high_com_delta": sum(1 for i in report_ins.inner_high if i["delta"]),  # type: ignore[union-attr]
            "inner_low": len(report_ins.inner_low),  # type: ignore[union-attr]
            "right_only": len(report_ins.right_only),  # type: ignore[union-attr]
            "left_only": len(report_ins.left_only),  # type: ignore[union-attr]
            "deltas": [
                {"codigo": i["catalog"].get("codigo"), "delta": i["delta"]}
                for i in report_ins.inner_high  # type: ignore[union-attr]
                if i["delta"]
            ][:50],
            "colisoes": [
                {"cat": i["catalog"].get("codigo"), "rfi": i["rfi"].get("codigo"), "score": i["score"]}
                for i in report_ins.inner_low  # type: ignore[union-attr]
            ],
            "novos": [
                {"codigo": i["rfi"].get("codigo"), "descricao": i["rfi"].get("descricao")}
                for i in report_ins.right_only  # type: ignore[union-attr]
            ],
        },
        "producoes": {
            "inner_high": len(report_prod.inner_high),  # type: ignore[union-attr]
            "inner_low": len(report_prod.inner_low),  # type: ignore[union-attr]
            "right_only": len(report_prod.right_only),  # type: ignore[union-attr]
            "left_only": len(report_prod.left_only),  # type: ignore[union-attr]
            "colisoes": [
                {"cat": i["catalog"].get("id"), "rfi": i["rfi"].get("id"), "score": i["score"]}
                for i in report_prod.inner_low  # type: ignore[union-attr]
            ],
            "novos": [
                {"id": i["rfi"].get("id"), "descricao": i["rfi"].get("descricao")}
                for i in report_prod.right_only  # type: ignore[union-attr]
            ],
        },
    }
    Path(report_json).write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[dim]Relatório JSON salvo em: {report_json}[/dim]")


@app_catalog.command("quality")
def catalog_quality(contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto")):
    """Verifica a integridade de composição, ciclos e produtividade do catálogo."""
    from rich.table import Table

    from concilium.domain.validations.circular_deps import verificar_ciclos_cpu
    from concilium.domain.validations.cpu_insumo import ValidadorCPUInsumo
    from concilium.infrastructure.repositories.insumo import RepositorioInsumo
    from concilium.presentation.mcp_server._context import _runtime

    rt = _runtime()
    ctx = rt.load_contexto(contexto_id)
    catalogo = rt.load_catalogo(ctx.catalogo_id)
    validador = ValidadorCPUInsumo(RepositorioInsumo(catalogo))
    console = Console()

    cpus = catalogo.get("cpus", [])
    insumos = catalogo.get("insumos", [])

    erros, avisos_cpu, cpus_bloqueadas = _audit_cpus_quality(cpus, validador)
    insumos_obsoletos, avisos_insumos = _audit_insumos_quality(insumos, validador)
    avisos = avisos_cpu + avisos_insumos
    ciclos = verificar_ciclos_cpu(catalogo)

    insumos_com_preco = [i for i in insumos if i.get("preco_unitario") or i.get("versoes")]

    console.print(f"\n[bold cyan]DIAGNÓSTICO DE SAÚDE DO CATÁLOGO: {ctx.catalogo_id}[/bold cyan]\n")

    table = Table(title="Resumo de Cobertura", show_header=True, header_style="bold magenta")
    table.add_column("Métrica")
    table.add_column("Total", justify="right")
    table.add_column("Cobertura", justify="right")
    table.add_row("Insumos Cadastrados", str(len(insumos)), "100%")
    table.add_row(
        "Insumos com Preço", str(len(insumos_com_preco)), _fmt_pct_quality(len(insumos_com_preco), len(insumos))
    )
    table.add_row(
        "Insumos com Vigência 2025",
        str(len(insumos) - len(insumos_obsoletos)),
        _fmt_pct_quality(len(insumos) - len(insumos_obsoletos), len(insumos)),
    )
    table.add_row("CPUs Cadastradas", str(len(cpus)), "100%")
    table.add_row(
        "CPUs Calculáveis (Portão 02)",
        str(len(cpus) - len(cpus_bloqueadas)),
        _fmt_pct_quality(len(cpus) - len(cpus_bloqueadas), len(cpus)),
    )
    console.print(table)

    if cpus_bloqueadas:
        table_err = Table(title="CPUs com Risco de Inviabilidade (Cronograma)", header_style="bold red")
        table_err.add_column("Código CPU", style="cyan")
        table_err.add_column("Causa do Bloqueio")
        for codigo, err in erros:
            if codigo in cpus_bloqueadas:
                table_err.add_row(codigo, err.mensagem)
        console.print(table_err)

    alertas_encoding = [a for a in avisos if a[1].codigo == "VAL-CAT-ENC-01"]
    if alertas_encoding:
        table_enc = Table(title="Alertas de Corrupção de Texto (Mojibake)", header_style="bold yellow")
        table_enc.add_column("Item", style="cyan")
        table_enc.add_column("Evidência")
        for item, alert in alertas_encoding[:10]:
            table_enc.add_row(item, alert.mensagem)
        if len(alertas_encoding) > 10:
            table_enc.add_row("...", f"Mais {len(alertas_encoding) - 10} alertas omitidos")
        console.print(table_enc)

    if erros or ciclos:
        console.print(f"\n[bold red]STATUS FINAL: REPROVADO PARA PRODUÇÃO ({len(erros)} Erros Críticos)[/bold red]")
    elif avisos:
        console.print(
            f"\n[bold yellow]STATUS FINAL: APROVADO COM RESSALVAS ({len(avisos)} Avisos de Qualidade)[/bold yellow]"
        )
    else:
        console.print("\n[bold green]STATUS FINAL: 100% ÍNTEGRO E CALIBRADO[/bold green]")


@app_catalog.command("simulate")
def catalog_simulate(
    cpu_id: str = typer.Argument(..., help="Código da CPU"),
    contexto_id: str = typer.Option("mendeslobo", "--contexto", "-c", help="ID do contexto"),
    dias: int = typer.Option(30, "--dias", "-d", help="Período em dias corridos"),
    regime: str = typer.Option("6x1", "--regime", "-r", help="Regime (6x1, 5x2, 7x0)"),
    horas_dia: float = typer.Option(8.0, "--horas-dia", "-h", help="Carga horária diária"),
):
    """Simula produção e compara regimes CLT (1.77) vs PJ (1.06) lado a lado."""
    from concilium.domain.services.simulation import SimuladorEngenharia
    from concilium.presentation.mcp_server._context import _runtime

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


@app_catalog.command("export")
def catalog_export(
    contexto_id: str = typer.Option("mendeslobo", "--contexto", "-c", help="ID do contexto"),
    output: str = typer.Option(None, "--output", "-o", help="Caminho do arquivo de saída (.xlsx)"),
):
    """Exporta o catálogo completo para Excel (Auder-Ready)."""
    from concilium.infrastructure.exporters.catalog_excel import CatalogExporterExcel
    from concilium.presentation.mcp_server._context import _runtime

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


@app_catalog.command("survey")
def catalog_survey(
    contexto_id: str = typer.Option("mendeslobo", "--contexto", "-c", help="ID do contexto"),
    jurisdicao_id: str = typer.Option(None, "--jurisdicao", "-j", help="ID da jurisdição para benchmark regional"),
    survey_type: str = typer.Option("price", "--type", "-t", help="Tipo de pesquisa: 'price' ou 'productivity'"),
    output: str = typer.Option(
        None, "--output", "-o", help="Caminho do arquivo de saída (.xlsx) ou camada project/master"
    ),
    target: str = typer.Option(None, "--target", help="Camada de persistência: project|master (ADR-040)."),
    projeto: str = typer.Option(None, "--project", "-p", help="Projeto alvo quando target=project."),
    confirm_master: bool = typer.Option(
        False, "--confirm-master", help="Confirma gravação explícita na camada master."
    ),
    actor: str = typer.Option("cli", "--actor", help="Ator para trilha de auditoria quando target=project."),
):
    """Gera planilha de pesquisa (Mapa de Cotação ou Aferição de Produtividade)."""
    from concilium.infrastructure.exporters.price_survey import PriceSurveyExporter
    from concilium.infrastructure.exporters.productivity_survey import ProductivitySurveyExporter
    from concilium.presentation.mcp_server._context import _config_root, _runtime

    rt = _runtime()
    ctx = rt.load_contexto(contexto_id)
    catalogo = rt.load_catalogo(ctx.catalogo_id)
    # ADR-065: TemaVisual substitui identidade_visual em ContextoObra
    catalogo["identidade_visual"] = rt.load_tema(ctx.tema_id).to_catalogo_dict()
    console = Console()

    layer = (target or "").strip().lower() or None
    if layer is None and output and output.strip().lower() in {"project", "master"}:
        layer = output.strip().lower()
        output = None  # type: ignore[assignment]
    if layer is None:
        layer = "project"
    if layer not in {"project", "master"}:
        rprint("[red]Valor inválido para camada. Use --target project|master.[/red]")
        raise typer.Exit(1)

    if layer == "project" and not projeto:
        rprint(
            "[red]ADR-040: survey agora salva em projeto por padrão.[/red] "
            "Informe --project <id|nome> ou use --target master --confirm-master."
        )
        raise typer.Exit(1)
    if layer == "master" and not confirm_master:
        rprint("[red]Escrita em master requer confirmação explícita.[/red] Use --confirm-master para prosseguir.")
        raise typer.Exit(1)

    if output and output.strip().lower() not in {"project", "master"}:
        path = Path(output)
    else:
        filename = f"pesquisa_{survey_type}_{contexto_id}.xlsx"
        if layer == "project":
            project_store = resolve_project(projeto)
            path = project_store.root / "overrides" / "surveys" / filename
        else:
            path = _config_root() / "catalogos" / ctx.catalogo_id / "surveys" / filename
    path.parent.mkdir(parents=True, exist_ok=True)

    # Resolve jurisdição efetiva para o benchmark
    jur_id = jurisdicao_id or ctx.jurisdicao_id

    with console.status(f"[bold yellow]Gerando mapa de cotação ({jur_id}) em {path.name}..."):
        try:
            if survey_type == "price":
                exporter = PriceSurveyExporter(catalogo, jurisdicao_id=jur_id)
            else:
                exporter = ProductivitySurveyExporter(catalogo, jurisdicao_id=jur_id)  # type: ignore[assignment]
            exporter.export(path)
            console.print(
                f"\n[bold yellow][OK] Mapa de Cotação gerado ({layer}):[/bold yellow] [cyan]{path.absolute()}[/cyan]"
            )
            console.print("Dica: Os campos em destaque Amarelo são para preenchimento do fornecedor.")
            if layer == "project":
                project_store = resolve_project(projeto)
                _append_jsonl(
                    project_store.root / "audit_log.jsonl",
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "actor": actor,
                        "action": "catalog_survey_export",
                        "payload": {
                            "contexto_id": contexto_id,
                            "survey_type": survey_type,
                            "jurisdicao_id": jur_id,
                            "target": layer,
                            "path": str(path),
                        },
                        "result": {"status": "OK"},
                        "status": "OK",
                        "error": None,
                    },
                )
        except Exception as e:
            console.print(f"[bold red]Erro ao gerar pesquisa:[/bold red] {e}")
            raise typer.Exit(1) from None


def _cp_load_override_preco(overrides: dict, insumo_id: str) -> tuple:
    """Validates and extracts (override_item, preco_float) from overrides dict. Raises typer.Exit on error."""
    import typer
    from rich import print as rprint

    if insumo_id not in overrides:
        rprint(f"[red]Insumo {insumo_id} n\u00e3o encontrado em overrides do projeto.[/red]")
        raise typer.Exit(1)
    override_item = overrides.get(insumo_id, {})
    if not isinstance(override_item, dict):
        rprint(f"[red]Override inv\u00e1lido para {insumo_id}. Esperado objeto JSON.[/red]")
        raise typer.Exit(1)
    novo_preco = (
        override_item.get("preco_calibrado") or override_item.get("preco_unitario") or override_item.get("preco")
    )
    if novo_preco is None:
        rprint(f"[red]Override de {insumo_id} n\u00e3o possui pre\u00e7o calibrado para promo\u00e7\u00e3o.[/red]")
        raise typer.Exit(1)
    return override_item, float(novo_preco)


def _cp_get_or_reset_historico(insumo_master: dict) -> list:
    """Returns the historico_precos list, resetting it if it is not a list."""
    historico = insumo_master.setdefault("historico_precos", [])
    if not isinstance(historico, list):
        historico = []
        insumo_master["historico_precos"] = historico
    return historico


def _cp_update_historico(
    historico: list, preco_float: float, dt_iso: str, projeto_origem: str, justificativa: str
) -> None:
    """Updates historico list in-place: closes current open entry and appends new one if price changed."""
    open_entry = None
    for registro in reversed(historico):
        if isinstance(registro, dict) and registro.get("data_fim_vigencia") is None:
            open_entry = registro
            break
    if not (isinstance(open_entry, dict) and float(open_entry.get("preco_unitario", -1)) == preco_float):
        for registro in historico:
            if not isinstance(registro, dict):
                continue
            if registro.get("data_fim_vigencia") is None:
                registro["data_fim_vigencia"] = dt_iso
        historico.append(
            {
                "preco_unitario": preco_float,
                "data_inicio_vigencia": dt_iso,
                "data_fim_vigencia": None,
                "fonte": "PROMOTED_FROM_PROJECT_OVERRIDE",
                "projeto_origem": projeto_origem,
                "justificativa": justificativa,
            }
        )


@app_catalog.command("promote")
def catalog_promote(
    projeto: str = typer.Option(..., "--project", "-p", help="Projeto de origem do override."),
    insumo_id: str = typer.Option(..., "--insumo", "-i", help="Código do insumo a promover."),
    justificativa: str = typer.Option(..., "--justificativa", "-j", help="Justificativa da promoção para master."),
    contexto_id: str = typer.Option(None, "--contexto", "-c", help="Override do contexto (opcional)."),
    data_vigencia: str = typer.Option(None, "--data-vigencia", help="Data efetiva da promoção (YYYY-MM-DD)."),
    actor: str = typer.Option("cli", "--actor", help="Ator para trilha de auditoria."),
    force: bool = typer.Option(False, "--force", help="Confirma ação de promoção para camada master."),
) -> None:
    """Promove override de insumo do projeto para o catálogo master (ADR-040 + ADR-041)."""
    from concilium.application.orchestrators.catalog_governance import (
        CatalogGovernanceError,
        validate_and_resolve_insumo_file,
    )
    from concilium.presentation.mcp_server._context import _config_root, _runtime

    if not force:
        rprint(
            "[red]Promoção para master requer confirmação explícita.[/red] "
            "Reexecute com --force quando a curadoria estiver aprovada."
        )
        raise typer.Exit(1)

    project_store = resolve_project(projeto)
    override_file = project_store.root / "overrides" / "insumos_override.json"
    overrides = _load_json(override_file, {})
    override_item, novo_preco = _cp_load_override_preco(overrides, insumo_id)

    try:
        dt_vigencia = date.fromisoformat(data_vigencia) if data_vigencia else date.today()
    except ValueError:
        rprint("[red]--data-vigencia inválida. Use formato YYYY-MM-DD.[/red]")
        raise typer.Exit(1) from None

    contexto_efetivo = contexto_id or project_store.meta.get("contexto_id")
    if not contexto_efetivo:
        rprint("[red]Não foi possível determinar contexto do projeto para promoção.[/red]")
        raise typer.Exit(1)

    rt = _runtime()
    ctx = rt.load_contexto(contexto_efetivo)
    catalog_root = _config_root() / "catalogos" / ctx.catalogo_id
    try:
        insumo_file = validate_and_resolve_insumo_file(catalog_root, insumo_id, float(novo_preco))
    except CatalogGovernanceError as exc:
        rprint(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None

    insumo_master = _load_json(insumo_file, {})
    historico = _cp_get_or_reset_historico(insumo_master)

    preco_float = float(novo_preco)
    dt_iso = dt_vigencia.isoformat()
    projeto_origem = str(project_store.meta.get("id", project_store.root.name))
    _cp_update_historico(historico, preco_float, dt_iso, projeto_origem, justificativa)

    insumo_master["preco_unitario"] = preco_float
    _write_json(insumo_file, insumo_master)

    promotion_event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "contexto_id": contexto_efetivo,
        "catalogo_id": ctx.catalogo_id,
        "insumo_id": insumo_id,
        "novo_preco": preco_float,
        "data_vigencia": dt_iso,
        "justificativa": justificativa,
        "actor": actor,
        "source_override": override_item,
    }
    _append_jsonl(project_store.root / "overrides" / "historico" / "promotions.jsonl", promotion_event)

    overrides.pop(insumo_id, None)
    _write_json(override_file, overrides)

    _append_jsonl(
        project_store.root / "audit_log.jsonl",
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": actor,
            "action": "catalog_promote_insumo",
            "payload": {
                "insumo_id": insumo_id,
                "novo_preco": preco_float,
                "data_vigencia": dt_iso,
                "justificativa": justificativa,
                "contexto_id": contexto_efetivo,
            },
            "result": {"status": "OK", "catalogo_id": ctx.catalogo_id},
            "status": "OK",
            "error": None,
        },
    )

    rprint(f"[green]Promoção concluída.[/green] {insumo_id} -> master ({ctx.catalogo_id}) com vigência {dt_iso}.")


@app_catalog.command("search")
def catalog_search(
    contexto_id: str = typer.Option(..., "--contexto", "-c"), query: str = typer.Argument(..., help="Termo de busca")
):
    """Busca CPUs por termo no código ou descrição."""
    from concilium.presentation.mcp_server._context import _runtime

    rt = _runtime()
    ctx = rt.load_contexto(contexto_id)
    catalogo = rt.load_catalogo(ctx.catalogo_id)

    console = Console()
    table = Table(title=f"Busca: '{query}' em {contexto_id}")
    table.add_column("Código", style="cyan")
    table.add_column("Descrição")

    q = query.lower()
    for cpu in catalogo.get("cpus", []):
        if q in str(cpu.get("codigo")).lower() or q in str(cpu.get("descricao")).lower():
            table.add_row(cpu.get("codigo"), cpu.get("descricao"))

    console.print(table)


def _build_schema_validators(schema_root: Path) -> tuple:
    """Loads JSON schemas and builds Draft 2020-12 validators. Raises typer.Exit(2) on missing files."""
    from jsonschema import Draft202012Validator, RefResolver

    cpu_schema_path = schema_root / "cpu.schema.json"
    prod_schema_path = schema_root / "producao.schema.json"
    insumo_schema_path = schema_root / "insumo.schema.json"
    for p in [cpu_schema_path, prod_schema_path, insumo_schema_path]:
        if not p.exists():
            rprint(f"[red]Schema não encontrado:[/red] {p}")
            raise typer.Exit(2)
    cpu_schema = json.loads(cpu_schema_path.read_text(encoding="utf-8"))
    prod_schema = json.loads(prod_schema_path.read_text(encoding="utf-8"))
    insumo_schema = json.loads(insumo_schema_path.read_text(encoding="utf-8"))
    common_path = schema_root / "common.schema.json"
    extra = [json.loads(common_path.read_text(encoding="utf-8"))] if common_path.exists() else []
    base_uri = schema_root.resolve().as_uri() + "/"
    schema_store = {s["$id"]: s for s in [cpu_schema, prod_schema, insumo_schema, *extra] if "$id" in s}
    cpu_v = Draft202012Validator(
        cpu_schema, resolver=RefResolver(base_uri=base_uri, referrer=cpu_schema, store=schema_store)
    )
    prod_v = Draft202012Validator(
        prod_schema, resolver=RefResolver(base_uri=base_uri, referrer=prod_schema, store=schema_store)
    )
    ins_v = Draft202012Validator(
        insumo_schema, resolver=RefResolver(base_uri=base_uri, referrer=insumo_schema, store=schema_store)
    )
    return cpu_v, prod_v, ins_v


def _run_schema_validation(validator: object, items: list, entity_prefix: str, id_field: str, erros: list) -> None:
    for item in items:
        item_id = item.get(id_field, f"<sem-{id_field}>")
        for err in validator.iter_errors(item):
            path = ".".join([str(x) for x in err.absolute_path])
            erros.append(f"{entity_prefix} {item_id}: {path or '<root>'} -> {err.message}")


def _check_catalog_semantics(cpus: list, prods: list, erros: list, avisos: list) -> None:
    prod_ids = {p.get("id") for p in prods if p.get("id")}
    for cpu in cpus:
        ref = cpu.get("producao_id_ref")
        if ref and ref not in prod_ids:
            erros.append(f"CPU {cpu.get('codigo')}: producao_id_ref inexistente ({ref})")
    legacy_keys = ["producao_horaria", "producao_id", "equipe"]
    for cpu in cpus:
        presentes = [k for k in legacy_keys if k in cpu]
        if presentes:
            avisos.append(f"CPU {cpu.get('codigo')}: campos legados presentes {presentes}")


def _print_messages_section(console: Console, messages: list, title_markup: str, tail_text: str, limit: int) -> None:
    if not messages:
        return
    console.print(f"\n{title_markup}")
    for msg in messages[:limit]:
        console.print(f" - {msg}")
    if len(messages) > limit:
        console.print(f" ... mais {len(messages) - limit} {tail_text}")


def _print_catalog_validation_results(
    console: Console, cpus: list, prods: list, insumos: list, erros: list, avisos: list, catalogo_id: str
) -> None:
    table = Table(title=f"Validação Schema - {catalogo_id}", show_header=True, header_style="bold cyan")
    table.add_column("Entidade")
    table.add_column("Total")
    table.add_column("Erros")
    table.add_column("Avisos")
    table.add_row(
        "CPU",
        str(len(cpus)),
        str(sum(1 for e in erros if e.startswith("CPU "))),
        str(sum(1 for w in avisos if w.startswith("CPU "))),
    )
    table.add_row("PRODUCAO", str(len(prods)), str(sum(1 for e in erros if e.startswith("PRODUCAO "))), "0")
    table.add_row("INSUMO", str(len(insumos)), str(sum(1 for e in erros if e.startswith("INSUMO "))), "0")
    console.print(table)
    _print_messages_section(console, erros, "[bold red]Erros de schema/semântica:[/bold red]", "erros", 30)
    _print_messages_section(console, avisos, "[bold yellow]Avisos:[/bold yellow]", "avisos", 20)


@app_catalog.command("validate-schema")
def catalog_validate_schema(
    contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto"),
    fail_on_warning: bool = typer.Option(False, "--strict", help="Falha também em avisos semânticos"),
):
    """Valida catálogo contra JSON Schemas (Draft 2020-12) e regras semânticas básicas."""
    from concilium.presentation.mcp_server._context import _runtime

    try:
        cpu_v, prod_v, ins_v = _build_schema_validators(Path("config") / "schemas" / "catalog")
    except ImportError:
        rprint("[red]Dependência 'jsonschema' não encontrada.[/red] Instale com: uv add jsonschema")
        raise typer.Exit(2) from None

    rt = _runtime()
    ctx = rt.load_contexto(contexto_id)
    catalogo = rt.load_catalogo(ctx.catalogo_id)
    console = Console()

    cpus = catalogo.get("cpus", [])
    insumos = catalogo.get("insumos", [])
    prods = catalogo.get("produtividades") or catalogo.get("producoes") or []

    erros: list[str] = []
    avisos: list[str] = []
    _run_schema_validation(cpu_v, cpus, "CPU", "codigo", erros)
    _run_schema_validation(prod_v, prods, "PRODUCAO", "id", erros)
    _run_schema_validation(ins_v, insumos, "INSUMO", "codigo", erros)
    _check_catalog_semantics(cpus, prods, erros, avisos)
    _print_catalog_validation_results(console, cpus, prods, insumos, erros, avisos, ctx.catalogo_id)

    if erros or (fail_on_warning and avisos):
        raise typer.Exit(1)

    console.print("\n[bold green]Schema validation OK[/bold green]")


@app_catalog.command("tendencia")
def catalog_tendencia(
    contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto"),
    jurisdicao_id: str = typer.Option(None, "--jurisdicao", "-j", help="UF (ex: BR-CE) — usa preços SICRO regionais"),
    output: str = typer.Option("", "--output", "-o", help="Salva relatório JSON"),
):
    """Índice de Tendência de Preços (ADR-041 §D5 — Skill 20).

    Calcula variação de preço por categoria usando historico_precos (SCD Type 2)
    e preços SICRO regionais. Identifica categorias com inflação acima da média.
    """
    import json
    from pathlib import Path

    from concilium.application.catalog.price_trend import calcular_tendencia
    from concilium.presentation.mcp_server._context import _config_root

    console = Console()
    bundle_path = _config_root() / "catalogos" / contexto_id / ".catalog_bundle.json"
    if not bundle_path.exists():
        rprint(f"[red]Bundle não encontrado: {bundle_path}[/red]")
        raise typer.Exit(1)

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    insumos = bundle.get("insumos", [])

    relatorio = calcular_tendencia(insumos, jurisdicao_id=jurisdicao_id, contexto_id=contexto_id)

    table = Table(
        title=f"Índice de Tendência de Preços — {contexto_id}" + (f" ({jurisdicao_id})" if jurisdicao_id else ""),
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Categoria")
    table.add_column("Total", justify="right")
    table.add_column("Com Histórico", justify="right")
    table.add_column("Var. Média %", justify="right")
    table.add_column("Var. Mediana %", justify="right")
    table.add_column("Var. Máx %", justify="right")

    for idx in relatorio.indices_por_categoria:

        def _fmt(v):
            return f"{v:+.1f}%" if v is not None else "—"

        color = "green"
        if idx.variacao_media_pct and idx.variacao_media_pct > 15:
            color = "yellow"
        if idx.variacao_media_pct and idx.variacao_media_pct > 30:
            color = "red"
        table.add_row(
            idx.tipo,
            str(idx.n_insumos_total),
            str(idx.n_insumos_com_historico),
            f"[{color}]{_fmt(idx.variacao_media_pct)}[/{color}]",
            _fmt(idx.variacao_mediana_pct),
            _fmt(idx.variacao_max_pct),
        )
    console.print(table)
    console.print(f"\n  Insumos analisados: {relatorio.resumo['total_insumos']}")
    console.print(f"  Com histórico SCD-2: {relatorio.resumo['total_com_historico']}")
    if jurisdicao_id:
        console.print(f"  Com preço SICRO {jurisdicao_id}: {relatorio.resumo['total_com_sicro_regional']}")

    if output:
        import dataclasses

        def _ser(obj):
            if dataclasses.is_dataclass(obj):
                return dataclasses.asdict(obj)
            raise TypeError(f"{type(obj)}")

        Path(output).write_text(
            json.dumps(dataclasses.asdict(relatorio), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        console.print(f"\n[dim]Relatório salvo: {output}[/dim]")


@app_catalog.command("merge-rfi")
def catalog_merge_rfi(
    contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto"),
    apply: bool = typer.Option(False, "--apply", help="Aplica merge (padrão: dry-run)"),
    report_json: str = typer.Option("", "--report-json", help="Salva relatório estruturado em JSON"),
    verify_pu: bool = typer.Option(False, "--verify-pu", help="Verifica integridade de PU após merge"),
):
    """Compara e merge catálogo com PLANILHA PADRÃO RFI."""
    import importlib.util
    import json
    from pathlib import Path

    console = Console()
    tools_dir = Path(__file__).resolve().parents[4].parent / "tools"
    merge_script = tools_dir / "merge_rfi.py"

    if not merge_script.exists():
        rprint(f"[red]Script não encontrado: {merge_script}[/red]")
        raise typer.Exit(2)

    spec = importlib.util.spec_from_file_location("merge_rfi", merge_script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    try:
        import openpyxl
    except ImportError:
        rprint("[red]openpyxl não encontrado.[/red] Execute: uv add openpyxl")
        raise typer.Exit(2) from None

    xlsm = mod.XLSM
    if not xlsm.exists():
        rprint(f"[red]Planilha RFI não encontrada:[/red] {xlsm}")
        raise typer.Exit(2)

    bundle_path = mod.ROOT / f"config/catalogos/{contexto_id}/.catalog_bundle.json"
    if not bundle_path.exists():
        rprint(f"[red]Bundle não encontrado:[/red] {bundle_path}")
        raise typer.Exit(1)

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    cat_insumos = bundle.get("insumos", [])
    cat_producoes = bundle.get("producoes", []) or bundle.get("produtividades", [])

    mode = "APPLY" if apply else "DRY-RUN"
    console.print(f"\n[bold]Merge Catálogo <-> RFI [{mode}][/bold] — contexto: {contexto_id}")
    console.print(f"  Catálogo: {len(cat_insumos)} insumos, {len(cat_producoes)} producoes")

    wb = openpyxl.load_workbook(xlsm, data_only=True, keep_vba=False)
    rfi = mod.extract_rfi(wb)
    wb.close()
    rfi_insumos = rfi["insumos"]
    rfi_producoes = rfi["producoes"]
    console.print(f"  Planilha: {len(rfi_insumos)} insumos, {len(rfi_producoes)} producoes")

    report_ins, _ = mod._merge_entities(cat_insumos, rfi_insumos)
    report_prod, _ = mod._merge_entities(cat_producoes, rfi_producoes, id_key="id")

    _print_merge_report_table(console, report_ins, report_prod)

    all_low = [(i, "INSUMO") for i in report_ins.inner_low] + [(i, "PROD") for i in report_prod.inner_low]
    _print_inner_low_collisions(console, all_low)

    if apply:
        _apply_merge_operation(
            console,
            bundle,
            bundle_path,
            mod,
            cat_insumos,
            rfi_insumos,
            cat_producoes,
            rfi_producoes,
            report_ins,
            report_prod,
            verify_pu,
        )

    _build_and_save_report_json(report_json, mode, contexto_id, report_ins, report_prod)

    if not apply:
        console.print("\n[dim]Dry-run — use --apply para aplicar o merge[/dim]")


@app_catalog.command("cure-plausibility")
def catalog_cure_plausibility(
    contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto"),
    apply: bool = typer.Option(False, "--apply", help="Aplica correções (padrão: dry-run)"),
):
    """Curação cirúrgica de anomalias de plausibilidade do catálogo.

    Detecta e corrige (quando possível automaticamente):
      - Encargos armazenados como alpha em vez de alpha-1
      - Preço abaixo do salário mínimo com referência RFI disponível
      - Duplicatas P#### vs MO-NOME (remove duplicata, mantém código canônico)
      - Datas desatualizadas após merge RFI
      - Equipamento sem valor_locacao_mensal (deriva automaticamente)

    Itens não-automatizáveis são reportados para revisão manual.
    """
    import importlib.util
    from pathlib import Path

    console = Console()
    tools_dir = Path(__file__).resolve().parents[4].parent / "tools"
    script = tools_dir / "cure_plausibility.py"

    if not script.exists():
        rprint(f"[red]Script não encontrado: {script}[/red]")
        raise typer.Exit(2)

    spec = importlib.util.spec_from_file_location("cure_plausibility", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    import json

    bundle_path = mod.ROOT / f"config/catalogos/{contexto_id}/.catalog_bundle.json"
    if not bundle_path.exists():
        rprint(f"[red]Bundle não encontrado: {bundle_path}[/red]")
        raise typer.Exit(1)

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    insumos = bundle.get("insumos", [])
    producoes = bundle.get("producoes", []) or bundle.get("produtividades", [])

    mode = "APPLY" if apply else "DRY-RUN"
    console.print(f"\n[bold]Curação de Plausibilidade [{mode}][/bold] — contexto: {contexto_id}")

    report = mod.CureReport()
    insumos = mod.cure_erros_fisicos(insumos, report, apply)
    insumos, producoes = mod.cure_duplicatas(insumos, producoes, report, apply)
    insumos = mod.cure_stale_rfi(insumos, report, apply)
    insumos = mod.cure_locacao_mensal(insumos, report, apply)
    mod.report_manual(insumos, producoes, report)

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Categoria")
    table.add_column("Quantidade", justify="right")
    table.add_row("Correções automáticas", str(len(report.fixed)))
    table.add_row("Intervenção manual", str(len(report.manual)))
    console.print(table)

    if report.fixed:
        console.print("\n[green]Correções:[/green]")
        for msg in report.fixed[:30]:
            prefix = "✓" if apply else "→"
            console.print(f"  {prefix} {msg}")
        if len(report.fixed) > 30:
            console.print(f"  ... e mais {len(report.fixed) - 30}")

    if report.manual:
        console.print("\n[yellow]Requer revisão manual:[/yellow]")
        for msg in report.manual:
            console.print(f"  ⚠ {msg}")

    if apply:
        if "producoes" in bundle:
            bundle["producoes"] = producoes
        else:
            bundle["produtividades"] = producoes
        bundle["insumos"] = insumos
        bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
        console.print(f"\n[green]Bundle atualizado:[/green] {len(insumos)} insumos, {len(producoes)} producoes")

        from concilium.application.catalog.plausibility_checker import verificar_plausibilidade

        pos = verificar_plausibilidade(insumos, producoes)
        r = pos["resumo"]
        status = "[green]OK[/green]" if r["erros"] == 0 else "[yellow]ATENÇÃO[/yellow]"
        console.print(f"  Pós-curação: {status} — {r['erros']} erros | {r['avisos']} avisos | {r['infos']} infos")
    else:
        console.print("\n[dim]Dry-run — use --apply para aplicar[/dim]")


# ── Structure ────────────────────────────────────────────────────────


@app_structure.command("list")
def structure_list(projeto: str):
    """Lista a árvore de escopos e planos do projeto."""
    project = resolve_project(projeto)
    console = Console()

    table = Table(title=f"Estrutura: {projeto}")
    table.add_column("Escopo", style="cyan")
    table.add_column("Planos (Status)", style="yellow")

    for eid in project.list_escopos():
        es = project.escopo(eid)
        plans_str = "\n".join([f"- {p} ({es.plan(p).status})" for p in es.list_plans()])
        table.add_row(eid, plans_str)

    console.print(table)


@app_structure.command("plan-init")
def plan_init(
    projeto: str,
    nome: str = typer.Option("Plano Principal", "--nome", "-n"),
    escopo: str = typer.Option("default", "--escopo", "-e"),
):
    """Cria novo plano de trabalho (shortcut)."""
    project = resolve_project(projeto)
    es = project.escopo(escopo)
    ps = es.create_plan(nome=nome)
    rprint(f"[green][OK][/green] Plano [bold]{ps.plano_id}[/bold] criado no escopo [bold]{escopo}[/bold].")


# ── BDI ─────────────────────────────────────────────────────────────
# Aqui poderíamos importar os comandos de commands_bdi
