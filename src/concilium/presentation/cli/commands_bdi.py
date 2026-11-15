"""Commands: bdi show, bdi update.

Permite ao Engenheiro Sênior visualizar e atualizar o perfil BDI de um projeto
via HiL (Human-in-the-Loop). O perfil é um snapshot imutável versionado;
cada atualização gera um BdiPerfilDiff para rastreabilidade.

`bdi show` exibe o que o preço exato lê (N9.1, #206): a declaração exata salva
e as camadas efetivas por categoria. O perfil em ponto flutuante só é
identificado como legado; os seus valores não são exibidos nem convertidos.

"""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import Any

import typer
from rich import print as rprint
from rich.console import Console

from concilium.application.scheduling.exact_pricing_declaration import (
    PROJECT_SCHEMA,
    PricingDeclarationError,
    validate_project_declaration,
)
from concilium.application.scheduling.project_bdi_exact_status import (
    ESTADO_TEXTO,
    EXACT,
    exact_project_bdi_status,
    load_project_profile,
)
from concilium.application.scheduling.project_bdi_exact_store import (
    ProjectBdiExactError,
    save_exact_project_bdi,
    version_path,
)
from concilium.domain.models.financial.bdi import BdiPerfilDiff, PerfilBdiProjeto, PerfilTributarioProjeto
from concilium.presentation.cli.shared import resolve_project

app = typer.Typer(
    name="bdi",
    help="Gestão do perfil BDI do projeto (ADR-023 §D6).",
    no_args_is_help=True,
)


def _perfil_path(project_root: Path) -> Path:
    return project_root / "bdi" / "perfil_bdi.json"


def _load_profile(project: Any) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """Perfil da construtora do contexto do projeto: `(perfil_id, perfil, motivo)`."""
    from concilium.application.runtime import Runtime
    from concilium.presentation.cli.shared import _config_root

    return load_project_profile(Runtime(_config_root()), project.meta)


_ORIGEM = {"profile": "perfil", "project": "projeto"}

def _campo(nome: str, campo: dict[str, str]) -> str:
    return f"{nome}={campo['valor']} [{_ORIGEM[campo['origem']]}]"


def bdi_status_lines(projeto: str, status: dict[str, Any]) -> list[str]:
    """Linhas de texto simples de `bdi show` a partir do status exato do projeto."""
    estado = status["estado"]
    lines = [f"Perfil BDI — {projeto}", f"Estado: {estado} — {ESTADO_TEXTO[estado]}"]
    if status["motivo"]:
        lines.append(f"Motivo: {status['motivo']}")
    registro = status["registro"]
    if registro is not None:
        lines += [
            f"  Versão:          {registro['versao']}",
            f"  Confirmado por:  {registro['confirmado_por']}",
            f"  Data:            {registro['confirmado_em']}",
            f"  Content hash:    {registro['content_hash']}",
        ]
        if registro.get("motivo_revisao"):
            lines.append(f"  Motivo revisão:  {registro['motivo_revisao']}")
        lines.append(f"  Fonte:           {status['declaracao']['fonte']}")
        lines.append("Campos declarados pelo projeto (os demais são do perfil da construtora):")
        lines += [f"  {c['linha']}.{c['campo']} = {c['valor']}" for c in status["campos_declarados"]]
    camadas = status["camadas"]
    if camadas is not None:
        lines.append(
            f"Camadas efetivas por categoria (perfil '{status['perfil_id']}' fundido com o projeto; "
            "valores exatos, origem entre colchetes):"
        )
        for categoria, c in camadas["categorias"].items():
            lines.append(
                f"  {categoria} (linha {c['linha']}, {c['natureza']}): markup = {c['markup']} "
                f"(≈ {c['markup_aprox']}, aproximado)"
            )
            lines.append(f"    overhead: {_campo('ac', c['ac'])}  {_campo('rsg', c['rsg'])}  {_campo('df', c['df'])}")
            lines.append(f"    lucro:    {_campo('l', c['l'])}")
            lines.append("    tributos: " + "  ".join(_campo(nome, t) for nome, t in c["tributos"].items()))
    elif status["camadas_motivo"]:
        lines.append(f"Camadas efetivas não exibidas: {status['camadas_motivo']}")
    legado = status["perfil_legado"]
    if legado["existe"]:
        lines.append(
            f"Perfil legado em ponto flutuante: bdi/perfil_bdi.json v{legado.get('versao', '?')} "
            f"(confirmado por {legado.get('confirmado_por', '?')}) — não é usado pelo preço exato e nunca é convertido."
        )
    if estado != EXACT:
        lines.append(
            f"Para declarar em forma exata: concilium bdi update {projeto} --from-file exato.json "
            f"--confirmado-por <nome> (JSON com schema {PROJECT_SCHEMA}, números como strings exatas)."
        )
    return lines


@app.command("show")
def bdi_show(
    projeto: str = typer.Argument(..., help="Nome ou UUID do projeto."),
) -> None:
    """Exibe a declaração exata de BDI do projeto e as camadas efetivas por categoria (N9.1)."""
    project = resolve_project(projeto)
    perfil_id, perfil, motivo = _load_profile(project)
    status = exact_project_bdi_status(project, perfil, perfil_id=perfil_id, perfil_motivo=motivo)
    console = Console()
    for line in bdi_status_lines(projeto, status):
        console.print(line, markup=False, highlight=False, soft_wrap=True)


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


def _bu_update_exato(
    projeto: str, declaracao: dict[str, Any], confirmado_por: str, motivo: str | None, yes: bool
) -> None:
    """Valida e salva a declaração exata do projeto (N9.1) em `bdi/perfil_bdi_exato*.json`."""
    try:
        validate_project_declaration(declaracao)
    except PricingDeclarationError as e:
        rprint(f"[red]Declaração exata inválida: {e}[/red]")
        raise typer.Exit(1) from None

    project = resolve_project(projeto)
    rprint(f"\n[bold]Declaração exata de BDI do projeto[/bold] — fonte: {declaracao['fonte']}")
    for linha, campos in declaracao["linhas"].items():
        if "l" in campos:
            rprint(f"  {linha}.l = {campos['l']}")
        for tributo, entrada in campos.get("tributos", {}).items():
            valor = entrada["aliquota"] if entrada["aplicavel"] else "não aplicável"
            rprint(f"  {linha}.{tributo} = {valor}")
    if not yes and not typer.confirm(f"\nConfirmar declaração exata de BDI para '{projeto}'?", default=False):
        rprint("[yellow]Operação cancelada.[/yellow]")
        raise typer.Exit(0)
    try:
        salvo = save_exact_project_bdi(
            project,
            str(project.meta["id"]),
            declaracao,
            confirmado_por=confirmado_por,
            motivo_revisao=motivo,
        )
    except ProjectBdiExactError as e:
        rprint(f"[red]Declaração exata não salva: {e}[/red]")
        raise typer.Exit(1) from None
    rprint(f"\n[green][OK][/green] Declaração exata de BDI v{salvo['versao']} salva.")
    rprint(f"  Hash: {salvo['content_hash']}")
    rprint(f"  Path: {version_path(salvo['versao'])}")
    for campo in (salvo.get("diff") or {}).get("campos_alterados", []):
        rprint(f"  [yellow]alterado[/yellow]: {campo}")


@app.command("update")
def bdi_update(
    projeto: str = typer.Argument(..., help="Nome ou UUID do projeto."),
    from_file: Path = typer.Option(
        ...,
        "--from-file",
        "-f",
        help="JSON com o perfil BDI: declaração exata (schema concilium.projeto.bdi-exato.v1) ou tributario + lucro.",
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

    # N9.1: um arquivo com o schema da declaração exata segue o caminho exato —
    # é o único que o preço exato lê; o perfil em ponto flutuante nunca é convertido.
    if isinstance(novo_raw, dict) and novo_raw.get("schema") == PROJECT_SCHEMA:
        _bu_update_exato(projeto, novo_raw, confirmado_por, motivo, yes)
        return

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
