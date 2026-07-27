"""Digest periódico de rascunhos de catálogo pendentes de aprovação (ADR-141, ADR-150).

Aplica o critério do ADR-140 D1 (condição e): o role catalog-manager acumula
naturalmente várias instâncias do mesmo tipo de evento (rascunho aberto por
um engineer via `criar_rascunho_catalogo`, ADR-120) — por isso o digest, não
o envio atômico por rascunho. ADR-150 D5 estende o mesmo digest para incluir
rascunhos de override de projeto, endereçados também ao dono do projeto.
"""

from __future__ import annotations

import json
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

PROJETO_KEY_PREFIX = "projeto:"


def _contar_overrides(proj_dir: Path, filename: str) -> int:
    """Conta entradas pendentes num arquivo de override de projeto (0 se ausente/inválido)."""
    overrides_file = proj_dir / "overrides" / filename
    if not overrides_file.exists():
        return 0
    try:
        overrides = json.loads(overrides_file.read_text(encoding="utf-8"))
        return len(overrides) if isinstance(overrides, dict) else 0
    except Exception:
        return 0


def _estado_rascunho_pendente(proj_dir: Path) -> dict[str, Any] | None:
    """Lê o estado do rascunho de projeto; None se ausente, JSON inválido ou estado terminal."""
    estado_file = proj_dir / "overrides" / "_rascunho_estado.json"
    if not estado_file.exists():
        return None
    try:
        estado_data = json.loads(estado_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    if estado_rascunho(estado_data) not in (ESTADO_RASCUNHO, ESTADO_REVISADO):
        return None
    return estado_data


def _owner_id_do_projeto(proj_dir: Path) -> str | None:
    """Lê o owner_id do meta.json do projeto (None se ausente/JSON inválido)."""
    meta_file = proj_dir / "meta.json"
    if not meta_file.exists():
        return None
    try:
        return json.loads(meta_file.read_text(encoding="utf-8")).get("owner_id")
    except Exception:
        return None


def _motivo_overrides(n_insumo: int, n_cpu: int) -> str:
    motivos = []
    if n_insumo:
        motivos.append(f"{n_insumo} override(s) de insumo")
    if n_cpu:
        motivos.append(f"{n_cpu} override(s) de CPU")
    return " e ".join(motivos) + " pendente(s) de promoção"


def _rascunhos_projeto_pendentes(projects_root: Path) -> dict[str, list[dict[str, Any]]]:
    """Overrides de projeto pendentes de promoção (ADR-150 D1/D5).

    Pendente = arquivo de estado (`_rascunho_estado.json`) em RASCUNHO/REVISADO
    (não terminal) E ao menos um override (insumo e/ou CPU) ainda não
    promovido/arquivado — mesmos dois tipos cobertos por
    `promover_override_projeto` (ADR-150, extensão CPU). `bdi_override.json`
    não entra aqui: não tem caminho de promoção (ver ADR-150, seção Achados).
    Projetos sem edição alguma (sem arquivo de estado) não aparecem — nada a decidir.
    """
    pendentes: dict[str, list[dict[str, Any]]] = {}
    for proj_dir in sorted(p for p in projects_root.iterdir() if p.is_dir()):
        estado_data = _estado_rascunho_pendente(proj_dir)
        if estado_data is None:
            continue

        n_insumo = _contar_overrides(proj_dir, "insumos_override.json")
        n_cpu = _contar_overrides(proj_dir, "cpus_override.json")
        if not n_insumo and not n_cpu:
            continue

        projeto_id = proj_dir.name
        pendentes[f"{PROJETO_KEY_PREFIX}{projeto_id}"] = [
            {
                "version": f"{PROJETO_KEY_PREFIX}{projeto_id}",
                "motivo": _motivo_overrides(n_insumo, n_cpu),
                "created_by": estado_data.get("created_by"),
                "projeto_id": projeto_id,
                "owner_id": _owner_id_do_projeto(proj_dir),
            }
        ]
    return pendentes


def rascunhos_pendentes(config_root: Path, projects_root: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Retorna {contexto_id: [versão, ...]} para toda versão de rascunho ainda não decidida.

    Pendente (ADR-141 D1) = `_rascunho` True, estado RASCUNHO/REVISADO (não
    rejeitado nem aprovado — ver `catalog_draft_lifecycle.estado_rascunho`,
    ADR-120 D5), e ainda não promovida (version != current_version do contexto).

    Quando `projects_root` é informado (ADR-150 D5), o dict retornado também
    inclui entradas `"projeto:{id}"` para overrides de projeto pendentes de
    promoção — mesma forma de item (`version`/`motivo`/`created_by`), com
    `projeto_id`/`owner_id` extra para roteamento do destinatário.
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

    if isinstance(projects_root, Path) and projects_root.exists():
        pendentes.update(_rascunhos_projeto_pendentes(projects_root))
    return pendentes


def _resolver_raizes(config_root: Path | None, projects_root: Path | None) -> tuple[Path, Path | None]:
    """Resolve config_root/projects_root a partir do storage global quando config_root é omitido."""
    if config_root is not None:
        return config_root, projects_root

    from concilium.infrastructure.settings import get_storage

    storage = get_storage()
    root = storage.config_root
    if projects_root is None:
        projects_root = storage.projects_root
    return root, projects_root


def _emails_catalog_managers(clients: list[Any]) -> set[str]:
    return {c.email for c in clients if c.active and "catalog-manager" in c.roles and c.email}


def _owner_ids_pendentes(pendentes: dict[str, list[dict[str, Any]]]) -> set[str]:
    return {
        versao.get("owner_id")
        for key, versoes in pendentes.items()
        if key.startswith(PROJETO_KEY_PREFIX)
        for versao in versoes
        if versao.get("owner_id")
    }


def _emails_donos_projeto(clients: list[Any], owner_ids: set[str]) -> set[str]:
    return {c.email for c in clients if c.active and c.client_id in owner_ids and c.email}


def enviar_digest_rascunhos_pendentes(config_root: Path | None = None, projects_root: Path | None = None) -> int:
    """Envia um email consolidado para cada catalog-manager ativo com email cadastrado,
    e para cada dono de projeto com override de projeto pendente (ADR-150 D5).

    Retorna quantos emails foram efetivamente enviados. Se não há nenhum
    rascunho pendente, não consulta destinatários nem envia nada (ADR-141 D4
    — silêncio é o comportamento correto, sem "0 pendências" recorrente).
    """
    root, projects_root = _resolver_raizes(config_root, projects_root)

    pendentes = rascunhos_pendentes(root, projects_root)
    if not pendentes:
        return 0

    clients = get_auth_store().list_clients()
    destinatarios = _emails_catalog_managers(clients)

    owner_ids = _owner_ids_pendentes(pendentes)
    if owner_ids:
        destinatarios |= _emails_donos_projeto(clients, owner_ids)

    return sum(1 for email in destinatarios if notify_catalog_drafts_pending(email, pendentes))
