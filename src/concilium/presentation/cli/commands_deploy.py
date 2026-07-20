"""CLI para registro de deploy/promoção — ADR-144 D1.

Comandos:
    concilium ops deploy record-promotion --image-tag T --api-revision R --mcp-revision R [--resumo TEXTO]

Pensado para rodar dentro do container recém-promovido (via `az containerapp
exec`), não no runner de CI/local — assim usa as credenciais reais de
storage já configuradas no ambiente (mesmas que o app usa em runtime),
evitando a ambiguidade de qual backend o CI enxergaria (ver ADR-144 D1).

`--resumo` deve receber as mensagens de commit brutas do intervalo promovido,
sem pré-processamento — quem consome esse texto (via `ping()`, ADR-144 D2) é
sempre um agente LLM, que contextualiza sozinho:

    RESUMO=$(git log "${PREV_TAG}..${NEW_TAG}" --format='%s')
    concilium ops deploy record-promotion --image-tag "$NEW_TAG" \\
        --api-revision "$API_REV" --mcp-revision "$MCP_REV" --resumo "$RESUMO"
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import typer
from rich import print as rprint

deploy_app = typer.Typer(
    name="deploy",
    help="Registro de deploy/promoção consultável em runtime (ADR-144).",
    no_args_is_help=True,
)


def _get_deploy_log_store():
    from concilium.infrastructure.deploy.deploy_log_store import DeployLogStore
    from concilium.infrastructure.storage.store_factory import build_system_blob_storage

    return DeployLogStore(build_system_blob_storage())


@deploy_app.command("record-promotion")
def record_promotion(
    image_tag: Annotated[str, typer.Option("--image-tag", help="Tag da imagem promovida no ACR.")],
    api_revision: Annotated[str, typer.Option("--api-revision", help="Nome da revision ACA da API promovida.")],
    mcp_revision: Annotated[str, typer.Option("--mcp-revision", help="Nome da revision ACA do MCP promovida.")],
    resumo: Annotated[
        str,
        typer.Option(
            "--resumo",
            help="Mensagens de commit brutas do intervalo promovido "
            "(ex.: git log <prev>..<novo> --format='%s'), sem pré-processamento.",
        ),
    ] = "",
) -> None:
    """Grava a promoção atual em `deploy/latest.json` — sobrescreve a anterior.

    `ping()` (ADR-144 D2) compara essa entrada contra o cursor de cada
    `client_id` para decidir se há novidade de deploy a reportar.
    """
    from concilium.infrastructure.deploy.deploy_log_store import DeployLogEntry

    entry = DeployLogEntry(
        image_tag=image_tag,
        api_revision=api_revision,
        mcp_revision=mcp_revision,
        promoted_at=datetime.now(UTC).isoformat(),
        resumo=resumo,
    )
    _get_deploy_log_store().save_latest(entry)

    rprint(f"[bold green]✓[/bold green] Deploy registrado: image_tag={image_tag} em {entry.promoted_at}")
