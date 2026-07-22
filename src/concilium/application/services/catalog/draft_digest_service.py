"""Digest periódico de rascunhos de catálogo pendentes de aprovação (ADR-141).

Aplica o critério do ADR-140 D1 (condição e): o role catalog-manager acumula
naturalmente várias instâncias do mesmo tipo de evento (rascunho aberto por
um engineer via `criar_rascunho_catalogo`, ADR-120) — por isso o digest, não
o envio atômico por rascunho.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from concilium.application.orchestrators.catalog_draft_lifecycle import (
    ESTADO_RASCUNHO,
    ESTADO_REVISADO,
    estado_rascunho,
)
from concilium.application.services.catalog.contexto_version_service import ContextoVersionService
from concilium.application.services.notifications import notify_catalog_drafts_pending
from concilium.infrastructure.auth.auth_store import get_auth_store


def rascunhos_pendentes(config_root: Path) -> dict[str, list[dict[str, Any]]]:
    """Retorna {contexto_id: [versão, ...]} para toda versão de rascunho ainda não decidida.

    Pendente (ADR-141 D1) = `_rascunho` True, estado RASCUNHO/REVISADO (não
    rejeitado nem aprovado — ver `catalog_draft_lifecycle.estado_rascunho`,
    ADR-120 D5), e ainda não promovida (version != current_version do contexto).
    """
    svc = ContextoVersionService(config_root)
    pendentes: dict[str, list[dict[str, Any]]] = {}
    for contexto in svc.list_contexts():
        current = contexto.get("current_version")
        for versao in contexto.get("versions", []):
            if (
                versao.get("_rascunho")
                and estado_rascunho(versao) in (ESTADO_RASCUNHO, ESTADO_REVISADO)
                and versao.get("version") != current
            ):
                pendentes.setdefault(str(contexto["id"]), []).append(versao)
    return pendentes


def enviar_digest_rascunhos_pendentes(config_root: Path | None = None) -> int:
    """Envia um email consolidado para cada catalog-manager ativo com email cadastrado.

    Retorna quantos emails foram efetivamente enviados. Se não há nenhum
    rascunho pendente, não consulta destinatários nem envia nada (ADR-141 D4
    — silêncio é o comportamento correto, sem "0 pendências" recorrente).
    """
    root = config_root
    if root is None:
        from concilium.infrastructure.settings import get_storage

        root = get_storage().config_root

    pendentes = rascunhos_pendentes(root)
    if not pendentes:
        return 0

    destinatarios = [
        c for c in get_auth_store().list_clients() if c.active and "catalog-manager" in c.roles and c.email
    ]
    return sum(1 for c in destinatarios if notify_catalog_drafts_pending(c.email, pendentes))
