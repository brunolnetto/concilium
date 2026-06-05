"""CLI health check — nível 1 (ambiente) + nível 2 (conteúdo), sem criar projetos."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

console = Console()


def _hc_check_catalogo_health(rt: object, ctx_id: str) -> tuple:
    """Returns (name, ok, detail) for a single catalogue health check."""
    from concilium.application.orchestrators.catalog_governance import (
        collect_catalog_critical_errors,
    )

    try:
        ctx = rt.load_contexto(ctx_id)
        catalogo = rt.load_catalogo(ctx.catalogo_id)
        erros = collect_catalog_critical_errors(catalogo)
        n_cpus = len(catalogo.get("cpus", []))
        ok = len(erros) == 0
        detail = f"{n_cpus} CPUs"
        if erros:
            detail += f", {len(erros)} erro(s) cr\u00edtico(s)"
        return (f"Cat\u00e1logo [{ctx_id}]", ok, detail)
    except Exception as exc:
        return (f"Cat\u00e1logo [{ctx_id}]", False, str(exc))


def _hc_check_catalogs(rows: list, contexto_ids: list, config_dir: object) -> None:
    """Appends catalogue health rows; no-op if no contexts or config dir missing."""
    if not contexto_ids or not config_dir.exists():
        return
    from concilium.application.runtime import Runtime

    try:
        rt = Runtime(config_dir)
        for ctx_id in contexto_ids:
            rows.append(_hc_check_catalogo_health(rt, ctx_id))
    except Exception as exc:
        rows.append(("Runtime", False, str(exc)))


def _hc_check_sharepoint(rows: list) -> None:
    """Appends SharePoint connectivity row if CONCILIUM__SP_DRIVE_ID is set."""
    import os

    sp_drive = os.environ.get("CONCILIUM__SP_DRIVE_ID", "")
    if not sp_drive:
        return
    try:
        from concilium.infrastructure.adapters.sharepoint_blob_storage import (
            SharePointBlobStorage,
        )

        storage = SharePointBlobStorage.from_env()
        result = storage.health_check()
        ok = result.get("status") == "ok"
        detail = result.get("drive_name", "") or result.get("message", "")
        rows.append(("SharePoint conectividade", ok, detail or "ok"))
    except ImportError:
        rows.append(
            (
                "SharePoint conectividade",
                False,
                "msal/httpx n\u00e3o instalados \u2014 execute: pip install 'concilium[sharepoint]'",
            )
        )
    except Exception as exc:
        rows.append(("SharePoint conectividade", False, str(exc)[:80]))


def health() -> None:
    """Pré-voo: verifica configuração, catálogo e skill registry.

    Nível 1 — Ambiente: variáveis de ambiente, diretórios obrigatórios.
    Nível 2 — Conteúdo: SkillRegistry, contextos, saúde de cada catálogo.

    Retorna exit code 0 se tudo OK, 1 se qualquer item falhar.
    Seguro para CI: não cria nem altera dados.
    """
    from concilium.presentation.cli.shared import _config_root, _projetos_root

    rows: list[tuple[str, bool, str]] = []

    config_dir = _config_root()
    proj_dir = _projetos_root()

    # ── Nível 1: Ambiente ──────────────────────────────────────────────────

    rows.append(("Config root existe", config_dir.exists(), str(config_dir)))
    rows.append(("Projects root configurado", True, str(proj_dir)))

    contextos_dir = config_dir / "contextos"
    rows.append(("Dir contextos existe", contextos_dir.exists(), str(contextos_dir)))

    catalogos_dir = config_dir / "catalogos"
    rows.append(("Dir catálogos existe", catalogos_dir.exists(), str(catalogos_dir)))

    # ── Nível 2: Conteúdo ──────────────────────────────────────────────────

    # Skill Registry
    try:
        from concilium.application.skills.registry import SkillRegistry

        registry = SkillRegistry()
        n_skills = len(registry.get_all_skills())
        rows.append(("SkillRegistry", True, f"{n_skills} skills registradas"))
    except Exception as exc:
        rows.append(("SkillRegistry", False, str(exc)))

    # Contextos disponíveis
    contexto_ids: list[str] = []
    if contextos_dir.exists():
        contexto_ids = [p.stem for p in sorted(contextos_dir.glob("*.json"))]
    rows.append(
        (
            "Contextos disponíveis",
            len(contexto_ids) > 0,
            f"{len(contexto_ids)} encontrado(s): {', '.join(contexto_ids) or '—'}",
        )
    )

    # Saúde por catálogo
    _hc_check_catalogs(rows, contexto_ids, config_dir)

    # ── Nível 3: SharePoint (ADR-047 §D7) — só se variáveis presentes ────────
    _hc_check_sharepoint(rows)

    # ── Render ─────────────────────────────────────────────────────────────

    table = Table(
        title="Concilium — Health Check",
        show_header=True,
        header_style="bold cyan",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("Componente", style="dim", min_width=36)
    table.add_column("", justify="center", width=4)
    table.add_column("Detalhe", min_width=50)

    all_ok = True
    for name, ok, detail in rows:
        icon = "✅" if ok else "❌"
        detail_markup = f"[red]{detail}[/red]" if not ok else detail
        if not ok:
            all_ok = False
        table.add_row(name, icon, detail_markup)

    console.print()
    console.print(table)
    console.print()

    if all_ok:
        console.print("[green bold]✓ Sistema saudável — pronto para operar.[/green bold]")
    else:
        console.print("[red bold]⚠  Sistema degradado — corrija os itens acima antes de operar.[/red bold]")
        raise typer.Exit(1)
