"""Commands: bdi show, bdi update.

Permite ao Engenheiro Sênior visualizar e atualizar o perfil BDI de um projeto
via HiL (Human-in-the-Loop). O perfil é um snapshot imutável versionado;
cada atualização gera um BdiPerfilDiff para rastreabilidade.

"""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import Any

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from concilium.domain.models.financial.bdi import BdiPerfilDiff, PerfilBdiProjeto, PerfilTributarioProjeto
from concilium.presentation.cli.shared import resolve_project

app = typer.Typer(
    name="bdi",
    help="Gestão do perfil BDI do projeto (ADR-023 §D6).",
    no_args_is_help=True,
)


def _perfil_path(project_root: Path) -> Path:
    return project_root / "bdi" / "perfil_bdi.json"


def _bdi_aplic_flags(aplic: dict) -> list:
    def flag(k: str) -> str:
        return "[OK]" if aplic.get(k, {}).get("aplicavel") else "[X]"

    return [flag("iss"), flag("pis"), flag("cofins"), flag("cssl"), flag("ir")]


@app.command("show")
def bdi_show(
    projeto: str = typer.Argument(..., help="Nome ou UUID do projeto."),
) -> None:
    """Exibe o perfil BDI atual do projeto."""
    project = resolve_project(projeto)
    path = _perfil_path(project.root)

    if not path.exists():
        rprint("[yellow]Nenhum perfil BDI encontrado para este projeto.[/yellow]")
        rprint(f"  Use [bold]concilium bdi update {projeto} --from-file perfil.json[/bold] para configurar.")
        raise typer.Exit(0)

    perfil = json.loads(path.read_text(encoding="utf-8"))
    console = Console()

    console.rule(f"[bold cyan]Perfil BDI — {projeto}[/bold cyan]")
    rprint(f"  Versão:          [bold]{perfil.get('versao', '?')}[/bold]")
    rprint(f"  Content hash:    {perfil.get('content_hash', '?')}")
    rprint(f"  Confirmado por:  {perfil.get('confirmado_por', '?')}")
    rprint(f"  Data:            {perfil.get('data_confirmacao', '?')}")
    if perfil.get("motivo_revisao"):
        rprint(f"  Motivo revisão:  {perfil['motivo_revisao']}")

    # Tributário
    trib = perfil.get("tributario", {})
    if trib:
        rprint("\n[bold]Regime Tributário:[/bold]")
        rprint(f"  Regime: {trib.get('regime', '?')}")
        rprint(f"  Município: {trib.get('municipio', '?')}")
        rprint(f"  ISS municipal: {trib.get('iss_aliquota_municipal', 0) * 100:.1f}%")
        # Show per-category applicability
        cats_display = ["mao_obra", "material", "servicos", "indireto", "diesel"]
        t = Table("Categoria", "ISS", "PIS", "COFINS", "CSSL", "IR", show_header=True)
        for cat_key in cats_display:
            aplic = trib.get(cat_key, {})
            t.add_row(cat_key, *_bdi_aplic_flags(aplic))
        console.print(t)

    # Lucro
    lucro = perfil.get("lucro", {})
    if lucro:
        rprint("\n[bold]Metas de Lucro (%):[/bold]")
        for campo, valor in lucro.items():
            rprint(f"  {campo}: {valor:.1f}%")


def _bu_show_bdi_diff(
    console: Console,
    perfil_anterior: PerfilBdiProjeto | None,
    novo_perfil: PerfilBdiProjeto,
    versao: int,
    trib_model: PerfilTributarioProjeto,
) -> None:
    """Displays BDI profile diff or new-profile summary to console."""
    from rich import print as rprint

    if perfil_anterior:
        console.rule("[bold]Diff do Perfil BDI[/bold]")
        try:
            ant_dict = perfil_anterior.model_dump(mode="json")
            nov_dict = novo_perfil.model_dump(mode="json")
            campos: list[str] = []
            for secao in ("tributario", "lucro"):
                for k, v in nov_dict.get(secao, {}).items():
                    if ant_dict.get(secao, {}).get(k) != v:
                        campos.append(f"{secao}.{k}")
            if campos:
                for campo in campos:
                    partes = campo.split(".", 1)
                    val_ant = ant_dict.get(partes[0], {}).get(partes[1], "?")
                    val_nov = nov_dict.get(partes[0], {}).get(partes[1], "?")
                    rprint(f"  [yellow]{campo}[/yellow]: {val_ant} \u2192 [green]{val_nov}[/green]")
            else:
                rprint("  [dim]Nenhuma altera\u00e7\u00e3o detectada.[/dim]")
        except Exception:
            rprint("  [dim]Diff n\u00e3o dispon\u00edvel.[/dim]")
    else:
        rprint(f"\n[bold]Novo perfil BDI \u2014 vers\u00e3o {versao}[/bold]")
        rprint(f"  Regime: {trib_model.regime}")
        rprint(f"  Munic\u00edpio: {trib_model.municipio}")


def _bu_persist_bdi_diff(
    perfil_dir: Path,
    perfil_anterior: PerfilBdiProjeto | None,
    novo_perfil: PerfilBdiProjeto,
    versao: int,
    motivo: str | None,
) -> None:
    """Persists BdiPerfilDiff artifact (optional; never raises)."""
    if perfil_anterior is None:
        return
    try:
        import json

        ant_dict2 = perfil_anterior.model_dump(mode="json")
        nov_dict2 = novo_perfil.model_dump(mode="json")
        campos2: list[str] = []
        for secao in ("tributario", "lucro"):
            for k, v in nov_dict2.get(secao, {}).items():
                if ant_dict2.get(secao, {}).get(k) != v:
                    campos2.append(f"{secao}.{k}")
        diff_obj = BdiPerfilDiff(
            projeto_id=novo_perfil.projeto_id,
            versao_anterior=perfil_anterior.versao,
            versao_nova=versao,
            perfil_anterior_id=perfil_anterior.perfil_id,
            perfil_novo_id=novo_perfil.perfil_id,
            motivo=motivo or "",
            campos_alterados=campos2,
            resumo=f"v{perfil_anterior.versao} \u2192 v{versao}: {len(campos2)} campo(s) alterado(s)",
        )
        diff_path = perfil_dir / f"perfil_bdi_diff_v{versao:03d}.json"
        diff_path.write_text(
            json.dumps(diff_obj.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass  # Diff opcional; n\u00e3o interrompe o fluxo principal


@app.command("update")
def bdi_update(
    projeto: str = typer.Argument(..., help="Nome ou UUID do projeto."),
    from_file: Path = typer.Option(
        ...,
        "--from-file",
        "-f",
        help="Caminho para JSON com novo perfil BDI (tributario + lucro).",
        exists=True,
        readable=True,
    ),
    confirmado_por: str = typer.Option(
        ...,
        "--confirmado-por",
        "-u",
        help="Nome do Engenheiro Sênior responsável.",
    ),
    motivo: str | None = typer.Option(
        None,
        "--motivo",
        "-m",
        help="Motivo da revisão (obrigatório se já existe um perfil).",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirma sem prompt interativo."),
) -> None:
    """Atualiza o perfil BDI do projeto (snapshot imutável, ADR-023 §D6).

    Lê 'tributario' e 'lucro' do arquivo JSON, exibe o diff em relação ao
    perfil atual e aguarda confirmação do Engenheiro Sênior antes de persistir.
    """
    import hashlib
    from datetime import datetime

    from concilium.domain.models.financial.bdi import (
        PerfilBdiProjeto,
        PerfilLucroProjeto,
        PerfilTributarioProjeto,
    )

    # Lê novo perfil do arquivo
    try:
        novo_raw: dict[str, Any] = json.loads(from_file.read_text(encoding="utf-8"))
    except Exception as e:
        rprint(f"[red]Falha ao ler arquivo: {e}[/red]")
        raise typer.Exit(1) from None

    try:
        trib_model = PerfilTributarioProjeto.model_validate(novo_raw.get("tributario", {}))
        lucro_model = PerfilLucroProjeto.model_validate(novo_raw.get("lucro", {}))
    except Exception as e:
        rprint(f"[red]Dados inválidos no arquivo: {e}[/red]")
        raise typer.Exit(1) from None

    project = resolve_project(projeto)
    console = Console()
    perfil_dir = project.root / "bdi"
    perfil_path = _perfil_path(project.root)

    versao = 1
    perfil_anterior: PerfilBdiProjeto | None = None

    if perfil_path.exists():
        try:
            anterior_raw = json.loads(perfil_path.read_text(encoding="utf-8"))
            perfil_anterior = PerfilBdiProjeto.model_validate(anterior_raw)
            versao = (anterior_raw.get("versao") or 1) + 1
        except Exception:
            rprint("[yellow]? Perfil anterior corrompido — criando versão 1.[/yellow]")
            versao = 1

    if versao > 1 and not motivo:
        rprint("[red]--motivo é obrigatório ao atualizar um perfil BDI existente.[/red]")
        raise typer.Exit(1)

    agora = datetime.now(UTC)

    # Computa hash antes de criar o modelo (content_hash is required)
    hash_payload = {
        "tributario": trib_model.model_dump(mode="json"),
        "lucro": lucro_model.model_dump(mode="json"),
        "projeto_id": project.meta["id"],
        "versao": versao,
    }
    content_hash = hashlib.sha256(json.dumps(hash_payload, sort_keys=True).encode()).hexdigest()[:16]

    novo_perfil = PerfilBdiProjeto(
        projeto_id=project.meta["id"],
        versao=versao,
        content_hash=content_hash,
        confirmado_em=agora,
        confirmado_por=confirmado_por,
        tributario=trib_model,
        lucro=lucro_model,
    )

    # Mostra diff se houver perfil anterior
    _bu_show_bdi_diff(console, perfil_anterior, novo_perfil, versao, trib_model)

    # Confirmação HiL
    if not yes:
        confirmar = typer.confirm(
            f"\nConfirmar perfil BDI v{versao} para '{projeto}'?",
            default=False,
        )
        if not confirmar:
            rprint("[yellow]Operação cancelada.[/yellow]")
            raise typer.Exit(0)

    # Persiste snapshot imutável
    perfil_dir.mkdir(parents=True, exist_ok=True)
    payload = novo_perfil.model_dump(mode="json")
    payload["motivo_revisao"] = motivo

    versao_path = perfil_dir / f"perfil_bdi_v{versao:03d}.json"
    versao_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    perfil_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # Persiste BdiPerfilDiff como artefato separado
    _bu_persist_bdi_diff(perfil_dir, perfil_anterior, novo_perfil, versao, motivo)

    rprint(f"\n[green][OK][/green] Perfil BDI v{versao} salvo.")
    rprint(f"  Hash: {content_hash}")
    rprint(f"  Path: {versao_path}")
