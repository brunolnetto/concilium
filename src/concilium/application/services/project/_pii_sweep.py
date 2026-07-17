"""Direito de ser esquecido (LGPD Art. 18), Fase 3 — varredura de client_id em

audit trails de projeto e catálogo, chamada por `forget-user`/`remove-user --forget`
(`presentation/cli/commands_auth.py`).

Diferente de `AuthStore.forget_client()` (que apaga a PII do próprio ClientRecord),
aqui `client_id` NÃO é apagado — é substituído por um alias opaco e estável
(gerado uma vez por operação de esquecimento) em todo lugar onde aparece como
autor/dono/aprovador. O alias preserva a correlação "essas entradas são da mesma
pessoa esquecida" sem preservar QUEM ela era — é isso que distingue anonimização
(mantém o registro, remove o vínculo pessoal) de deleção (LGPD Art. 12 §2: dado
anonimizado deixa de ser dado pessoal).

Escopo coberto (decisão explícita, não é uma varredura de "tudo que pode conter
client_id"):
  - audit_log.jsonl de cada projeto (actor, version_action.actor_id,
    ownership_action.{actor_id,owner_anterior,owner_proposto_ou_novo})
  - meta.json de cada projeto: owner_id, version_history[*].criado_por,
    ownership_transfer_pending.{owner_atual,owner_proposto}
  - arquivos de versão de catálogo (config_root/**/versions/v*.json — contextos,
    perfis, temas, jurisdições e rascunhos usam o mesmo ConfigVersionService e
    o mesmo padrão de path, ver contexto_version_service.py)

Fora do escopo (limitação conhecida, não perseguida por falta de writer
confirmado ou por ser código morto — ver levantamento que motivou esta feature):
  CatalogSnapshotMeta.created_by, InsumoOverride/CPUOverride/BDIOverride.aprovado_por.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .project_files import DEFAULT_PROJECT_FILES
from .project_repository import ProjectHandle, ProjectRepository


def _replace_value(obj: Any, old: str, new: str) -> tuple[Any, int]:
    """Substitui recursivamente toda string == `old` por `new` em dicts/lists.

    Genérico de propósito (não hardcoda nomes de campo como "actor"/"criado_por"):
    audit trails têm formatos heterogêneos (ver módulo) e um novo campo de autoria
    adicionado no futuro é coberto automaticamente, sem precisar atualizar esta
    varredura. Retorna (objeto_transformado, quantidade_de_substituições).
    """
    if isinstance(obj, dict):
        count = 0
        result = {}
        for k, v in obj.items():
            new_v, c = _replace_value(v, old, new)
            result[k] = new_v
            count += c
        return result, count
    if isinstance(obj, list):
        count = 0
        result = []
        for item in obj:
            new_item, c = _replace_value(item, old, new)
            result.append(new_item)
            count += c
        return result, count
    if obj == old:
        return new, 1
    return obj, 0


def _sweep_audit_log(project: ProjectHandle, client_id: str, alias: str) -> int:
    lines = project.read_lines(DEFAULT_PROJECT_FILES.audit_log)
    if not lines:
        return 0
    affected = 0
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError:
            out.append(line)  # linha ilegível preservada como está (best-effort)
            continue
        new_record, n = _replace_value(record, client_id, alias)
        if n:
            affected += 1
        out.append(json.dumps(new_record, ensure_ascii=False, default=str))
    if affected:
        project.write_lines(DEFAULT_PROJECT_FILES.audit_log, out)
    return affected


def _sweep_meta(project: ProjectHandle, client_id: str, alias: str) -> int:
    """Só os campos de autoria/ownership do meta.json — não varre o resto (config

    operacional do projeto, sem relação com autoria de usuário)."""
    meta = project.meta
    updates: dict[str, Any] = {}
    affected = 0

    if meta.get("owner_id") == client_id:
        updates["owner_id"] = alias
        affected += 1

    version_history = meta.get("version_history")
    if isinstance(version_history, dict):
        new_vh, n = _replace_value(version_history, client_id, alias)
        if n:
            updates["version_history"] = new_vh
            affected += n

    pending = meta.get("ownership_transfer_pending")
    if isinstance(pending, dict):
        new_pending, n = _replace_value(pending, client_id, alias)
        if n:
            updates["ownership_transfer_pending"] = new_pending
            affected += n

    if updates:
        project.update_meta(**updates)
    return affected


def sweep_project(project: ProjectHandle, client_id: str, alias: str) -> dict[str, int]:
    """Varre um único projeto. Retorna contagem por categoria (para relato ao admin)."""
    return {
        "audit_log_entries": _sweep_audit_log(project, client_id, alias),
        "meta_fields": _sweep_meta(project, client_id, alias),
    }


def sweep_all_projects(repository: ProjectRepository, client_id: str, alias: str) -> dict[str, int]:
    """Varre todos os projetos do repositório. Best-effort por projeto: uma falha

    (ex.: projeto corrompido) não deve abortar a varredura dos demais."""
    totals = {"projects_scanned": 0, "projects_affected": 0, "audit_log_entries": 0, "meta_fields": 0}
    for project in repository.list_projects():
        totals["projects_scanned"] += 1
        try:
            stats = sweep_project(project, client_id, alias)
        except Exception:
            continue
        if stats["audit_log_entries"] or stats["meta_fields"]:
            totals["projects_affected"] += 1
        totals["audit_log_entries"] += stats["audit_log_entries"]
        totals["meta_fields"] += stats["meta_fields"]
    return totals


def sweep_catalog_version_files(config_root: Path, client_id: str, alias: str) -> int:
    """Varre config_root/**/versions/v*.json — contextos, perfis, temas, jurisdições

    e rascunhos de catálogo (ADR-120) usam todos o mesmo ConfigVersionService e o
    mesmo padrão de path (`config/<subdir>/<entity_id>/versions/vN.json`), então uma
    única varredura recursiva cobre todos sem precisar enumerar subdir por subdir.
    Retorna a quantidade de arquivos afetados. Sempre filesystem local (config_root
    não passa por BlobStoragePort — ver ConfigVersionService).
    """
    affected = 0
    for vfile in Path(config_root).glob("**/versions/v*.json"):
        try:
            data = json.loads(vfile.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        new_data, n = _replace_value(data, client_id, alias)
        if n:
            vfile.write_text(json.dumps(new_data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            affected += 1
    return affected
