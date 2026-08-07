"""Helper functions for commands_manage (C)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from concilium.presentation.cli.shared import resolve_project

# ═══════════════════════════════════════════════════════════════════════════════
# catalog compare / catalog merge (issue #134) — agnósticos de fonte: cada origem
# pode ser um catálogo (catalogo_id) ou uma planilha PLANILHA PADRÃO RFI (.xlsm/.xlsx).
# Motor de comparação/merge + resolução de fonte compartilhados com o MCP tool
# equivalente (_catalogo_tools_helpers_b.py) via
# concilium.application.services.catalog.catalog_compare — aqui só a apresentação
# (Console/Table/typer.Exit) é específica da CLI.
# ═══════════════════════════════════════════════════════════════════════════════


def _resolver_tipos(tipo: str) -> list[str]:
    from concilium.application.services.catalog.catalog_compare import resolver_tipos

    try:
        return resolver_tipos(tipo)
    except ValueError as exc:
        rprint(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None


def _resolver_fonte_entidades(origem: str) -> dict[str, list[dict]]:
    from concilium.application.services.catalog.catalog_compare import resolver_fonte_entidades
    from concilium.presentation.mcp._context import _runtime

    rt = _runtime()
    try:
        return resolver_fonte_entidades(origem, rt, rt.config_root.parent)
    except RuntimeError as exc:
        rprint(f"[red]{exc}[/red]")
        raise typer.Exit(2) from None


def _eh_planilha(origem: str) -> bool:
    from concilium.application.services.catalog.catalog_compare import eh_planilha

    return eh_planilha(origem)


def _cc_add_table_row(table: Table, label: str, rep: Any) -> None:
    n_delta = sum(1 for i in rep.inner_high if i["delta"])
    table.add_row(
        label,
        str(len(rep.inner_high)),
        str(n_delta),
        str(len(rep.inner_low)),
        str(len(rep.right_only)),
        str(len(rep.left_only)),
    )


def _gerar_relatorios(
    base: dict[str, list[dict]], origem: dict[str, list[dict]], tipos: list[str]
) -> dict[str, Any]:
    from concilium.application.services.catalog.catalog_compare import gerar_relatorios

    return gerar_relatorios(base, origem, tipos)


def _icm_validar_e_resolver_tipos(destino: str, origem: str, tipo: str, console: Console) -> list[str] | None:
    """Valida destino e resolve tipos para merge. Retorna tipos válidos ou None se falha."""
    if _eh_planilha(destino):
        rprint("[red]Destino do merge precisa ser um catálogo — não é possível escrever em uma planilha.[/red]")
        return None

    tipos = _resolver_tipos(tipo)
    if "cpus" in tipos and _eh_planilha(origem):
        console.print("[yellow]cpus: pulado — planilha RFI não modela esse tipo de entidade.[/yellow]")
        tipos = [t for t in tipos if t != "cpus"]
    if not tipos:
        rprint("[red]Nenhum tipo válido para mesclar.[/red]")
        return None
    return tipos


def _icm_apply_merge(
    destino: str,
    tipos: list[str],
    fonte_destino: dict,
    fonte_origem: dict,
    relatorios: dict,
    apply: bool,
    incluir_novos: bool,
    verify_pu: bool,
    console: Console,
) -> None:
    """Aplica o merge no bundle do destino quando apply=True."""
    from concilium.application.services.catalog.catalog_compare import (
        ID_KEYS,
        aplicar_merge,
        resolver_catalogo_id,
    )
    from concilium.presentation.mcp._context import _runtime

    if not apply:
        return

    rt = _runtime()
    catalogo_id = resolver_catalogo_id(rt, destino)
    bundle = rt.load_catalogo(catalogo_id)
    bundle_path = rt.config_root / "catalogos" / catalogo_id / ".catalog_bundle.json"

    console.print("\n[bold]Aplicando merge...[/bold]")
    for t in tipos:
        merged = aplicar_merge(
            fonte_destino.get(t, []),
            fonte_origem.get(t, []),
            relatorios[t],
            id_key=ID_KEYS[t],
            incluir_novos=incluir_novos,
        )
        if t == "producoes" and "producoes" not in bundle:
            bundle["produtividades"] = merged
        else:
            bundle[t] = merged
        console.print(f"  {t}: {len(merged)} (era {len(fonte_destino.get(t, []))})")

    bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"\n[green]Bundle atualizado:[/green] {bundle_path}")
    if verify_pu:
        _cm_verify_pu(bundle, console)


def _cc_print_summary_table(relatorios: dict[str, Any], console: Console, titulo: str) -> None:
    table = Table(title=titulo, show_header=True, header_style="bold cyan")
    table.add_column("Entidade")
    table.add_column("INNER_HIGH", justify="right")
    table.add_column("INNER_HIGH Delta", justify="right")
    table.add_column("INNER_LOW", justify="right")
    table.add_column("RIGHT_ONLY", justify="right")
    table.add_column("LEFT_ONLY", justify="right")
    for t, rep in relatorios.items():
        _cc_add_table_row(table, t.upper(), rep)
    console.print(table)


def _cc_print_inner_low(relatorios: dict[str, Any], console: Console) -> None:
    all_low = [(item, t.upper()) for t, rep in relatorios.items() for item in rep.inner_low]
    if not all_low:
        return
    console.print(f"\n[yellow]INNER_LOW — {len(all_low)} colisões (importados como RFI-* se aplicado):[/yellow]")
    for item, etype in all_low[:15]:
        base_e = item["catalog"]
        origem_e = item["rfi"]
        base_cod = base_e.get("codigo") or base_e.get("id", "")
        origem_cod = origem_e.get("codigo") or origem_e.get("id", "")
        console.print(
            f"  [{item['score']:.2f}] {etype} "
            f'base={base_cod[:20]} "{base_e.get("descricao", "")[:25]}" '
            f'| origem={origem_cod[:20]} "{origem_e.get("descricao", "")[:25]}"'
        )
    if len(all_low) > 15:
        console.print(f"  ... e mais {len(all_low) - 15}")


def _cc_write_report(
    report_json: str,
    relatorios: dict[str, Any],
    mode: str,
    origem_a: str,
    origem_b: str,
    console: Console,
) -> None:
    from concilium.application.services.catalog.catalog_compare import ID_KEYS

    report_data: dict[str, Any] = {"mode": mode, "origem_a": origem_a, "origem_b": origem_b}
    for t, rep in relatorios.items():
        id_key = ID_KEYS[t]
        report_data[t] = {
            "inner_high": len(rep.inner_high),
            "inner_high_com_delta": sum(1 for i in rep.inner_high if i["delta"]),
            "inner_low": len(rep.inner_low),
            "right_only": len(rep.right_only),
            "left_only": len(rep.left_only),
            "deltas": [{"id": i["catalog"].get(id_key), "delta": i["delta"]} for i in rep.inner_high if i["delta"]][
                :50
            ],
            "colisoes": [
                {"base": i["catalog"].get(id_key), "origem": i["rfi"].get(id_key), "score": i["score"]}
                for i in rep.inner_low
            ],
            "novos": [
                {"id": i["rfi"].get(id_key), "descricao": i["rfi"].get("descricao")} for i in rep.right_only
            ],
        }
    Path(report_json).write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"\n[dim]Relatório JSON salvo em: {report_json}[/dim]")


def _cm_verify_pu(bundle: dict, console: Console) -> None:
    from concilium.application.catalog.pu_calculator import ParametrosCalculo, calcular_catalogo

    insumos = bundle.get("insumos", [])
    producoes = bundle.get("producoes") or bundle.get("produtividades") or []
    resultado = calcular_catalogo(producoes, insumos, ParametrosCalculo())
    faltantes = resultado["referencias_faltantes"]
    if faltantes:
        console.print(f"\n[red]Referências faltantes após merge:[/red] {len(faltantes)}")
        for r in faltantes[:10]:
            console.print(f"  {r['producao_id']}: {r['faltantes']}")
    else:
        console.print(
            f"\n[green]Integridade referencial OK[/green] — {resultado['com_composicao']} produções verificadas"
        )


def _impl_catalog_compare(
    origem_a: str = typer.Argument(..., help="Catálogo (catalogo_id) ou planilha .xlsm/.xlsx"),
    origem_b: str = typer.Argument(..., help="Catálogo (catalogo_id) ou planilha .xlsm/.xlsx"),
    tipo: str = typer.Option("todos", "--tipo", "-t", help="insumos | producoes | cpus | todos"),
) -> None:
    """Compara duas fontes de entidades de catálogo — sempre dry-run (só relatório).

    Cada origem pode ser um catálogo (catalogo_id, ex.: mendeslobo) ou uma planilha
    no formato PLANILHA PADRÃO RFI (.xlsm/.xlsx).

    Operações (como JOIN):
      LEFT_ONLY  : só em origem_a                  -> nenhuma ação
      INNER_HIGH : match confiante (>=0.85)          -> divergências reportadas
      INNER_LOW  : match incerto (0.50-0.85)         -> revisão manual
      RIGHT_ONLY : só em origem_b                  -> candidato a inclusão
    """
    console = Console()
    tipos = _resolver_tipos(tipo)
    if "cpus" in tipos and (_eh_planilha(origem_a) or _eh_planilha(origem_b)):
        console.print("[yellow]cpus: pulado — planilha RFI não modela esse tipo de entidade.[/yellow]")
        tipos = [t for t in tipos if t != "cpus"]
    if not tipos:
        rprint("[red]Nenhum tipo válido para comparar.[/red]")
        raise typer.Exit(1)

    fonte_a = _resolver_fonte_entidades(origem_a)
    fonte_b = _resolver_fonte_entidades(origem_b)

    console.print(f"\n[bold]Comparação de catálogo[/bold] — {origem_a}  x  {origem_b}")
    relatorios = _gerar_relatorios(fonte_a, fonte_b, tipos)
    _cc_print_summary_table(relatorios, console, "Comparação")
    _cc_print_inner_low(relatorios, console)


def _impl_catalog_merge(
    destino: str = typer.Argument(..., help="Catálogo de destino (catalogo_id) — não pode ser planilha."),
    origem: str = typer.Argument(..., help="Catálogo (catalogo_id) ou planilha .xlsm/.xlsx de origem."),
    apply: bool = typer.Option(False, "--apply", help="Aplica as mudanças no bundle (default: dry-run)."),
    incluir_novos: bool = typer.Option(
        True, "--incluir-novos/--no-incluir-novos", help="Inclui RIGHT_ONLY (só na origem) no destino."
    ),
    tipo: str = typer.Option("todos", "--tipo", "-t", help="insumos | producoes | cpus | todos"),
    verify_pu: bool = typer.Option(False, "--verify-pu", help="Verifica integridade referencial após o merge."),
    report_json: str = typer.Option(None, "--report-json", help="Salva relatório detalhado em JSON."),
) -> None:
    """Mescla uma fonte de origem (catálogo ou planilha RFI) no catálogo de destino.

    Sem --apply: dry-run — mesmo relatório que `catalog compare destino origem` mostraria.
    Com --apply: escreve direto no `.catalog_bundle.json` do destino (mesma mecânica do
    antigo merge-rfi — issue #134 não resolve a governança de escrita direta em catálogo).

    Operações (como JOIN):
      LEFT_ONLY  : só no destino                     -> mantém
      INNER_HIGH : match confiante (>=0.85)          -> atualiza dados no destino
      INNER_LOW  : match incerto (0.50-0.85)         -> importa como RFI-* (sem sobrescrever)
      RIGHT_ONLY : só na origem                       -> adiciona ao destino
    """
    console = Console()

    tipos = _icm_validar_e_resolver_tipos(destino, origem, tipo, console)
    if tipos is None:
        raise typer.Exit(2)

    fonte_destino = _resolver_fonte_entidades(destino)
    fonte_origem = _resolver_fonte_entidades(origem)

    mode = "APPLY" if apply else "DRY-RUN"
    console.print(f"\n[bold]Merge de catálogo [{mode}][/bold] — destino: {destino}  <-  origem: {origem}")

    relatorios = _gerar_relatorios(fonte_destino, fonte_origem, tipos)
    _cc_print_summary_table(relatorios, console, "Merge Report")
    _cc_print_inner_low(relatorios, console)

    _icm_apply_merge(destino, tipos, fonte_destino, fonte_origem, relatorios, apply, incluir_novos, verify_pu, console)

    if report_json:
        _cc_write_report(report_json, relatorios, mode, destino, origem, console)
    if not apply:
        console.print("\n[dim]Dry-run — use --apply para aplicar o merge[/dim]")


def _ccp_print_fixed(fixed: list, apply: bool, console) -> None:
    console.print("\n[green]Correções:[/green]")
    for msg in fixed[:30]:
        prefix = "✓" if apply else "→"
        console.print(f"  {prefix} {msg}")
    if len(fixed) > 30:
        console.print(f"  ... e mais {len(fixed) - 30}")


def _impl_catalog_cure_plausibility(
    contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto"),
    apply: bool = typer.Option(False, "--apply", help="Aplica correções (padrão: dry-run)"),
):
    """Curação cirúrgica de anomalias de plausibilidade do catálogo.

    Detecta e corrige (quando possível automaticamente):
      - Encargos armazenados como alpha em vez de alpha-1
      - Preço abaixo do salário mínimo com referência RFI disponível
      - Duplicatas — match exato OU similaridade determinística (ADR-179),
        restrita a faixas de preço validadas; adiciona codigo_referencia_externa,
        remove o código duplicado, mantém o canônico
      - Datas desatualizadas após merge RFI
      - Equipamento sem valor_locacao_mensal (deriva automaticamente)
      - templates.json/estruturas_indiretas (funcao_id de duplicatas fundidas)

    Itens não-automatizáveis são reportados para revisão manual.

    Delega inteiramente para cure_plausibility._run_cure_steps/_persistir_e_validar
    — não duplica a orquestração aqui. Antes duplicava (bundle-only write, sem
    templates.json), o que divergiu e quebrou ao motor de similaridade mudar de
    assinatura; nunca escrever em dois lugares a mesma lógica de novo.
    """
    from concilium.application.catalog.cure_plausibility import ROOT as CURE_ROOT
    from concilium.application.catalog.cure_plausibility import (
        CureReport,
        _persistir_e_validar,
        _run_cure_steps,
    )

    console = Console()

    catalog_root = CURE_ROOT / f"config/catalogos/{contexto_id}"
    bundle_path = catalog_root / ".catalog_bundle.json"
    if not bundle_path.exists():
        rprint(f"[red]Bundle não encontrado: {bundle_path}[/red]")
        raise typer.Exit(1)

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    # deepcopy: protege o snapshot "original" usado no diff de persistência
    # contra cure_* que mutem atributos_especificos por referência (ver
    # cure_plausibility.main() para o achado real que motivou isso).
    insumos_originais = copy.deepcopy(bundle.get("insumos", []))
    producoes_originais = copy.deepcopy(bundle.get("producoes", []) or bundle.get("produtividades", []))

    mode = "APPLY" if apply else "DRY-RUN"
    console.print(f"\n[bold]Curação de Plausibilidade [{mode}][/bold] — contexto: {contexto_id}")

    report = CureReport()
    insumos, producoes = _run_cure_steps(catalog_root, insumos_originais, producoes_originais, report, apply)

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Categoria")
    table.add_column("Quantidade", justify="right")
    table.add_row("Correções automáticas", str(len(report.fixed)))
    table.add_row("Intervenção manual", str(len(report.manual)))
    console.print(table)

    if report.fixed:
        _ccp_print_fixed(report.fixed, apply, console)

    if report.manual:
        console.print("\n[yellow]Requer revisão manual:[/yellow]")
        for msg in report.manual:
            console.print(f"  ⚠ {msg}")

    if apply:
        _persistir_e_validar(catalog_root, insumos_originais, insumos, producoes_originais, producoes)
        console.print(f"\n[green]Arquivos individuais persistidos em:[/green] {catalog_root}")
    else:
        console.print("\n[dim]Dry-run — use --apply para aplicar[/dim]")


def _impl_structure_list(projeto: str):
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


def _impl_plan_init(
    projeto: str,
    nome: str = typer.Option("Plano Principal", "--nome", "-n"),
    escopo: str = typer.Option("default", "--escopo", "-e"),
):
    """Cria novo plano de trabalho (shortcut)."""
    project = resolve_project(projeto)
    es = project.escopo(escopo)
    ps = es.create_plan(nome=nome)
    rprint(f"[green][OK][/green] Plano [bold]{ps.plano_id}[/bold] criado no escopo [bold]{escopo}[/bold].")
