"""ADR-024 — Snapshot auditável de catálogo com cache local e detecção de mudanças.

CatalogSnapshot: registro imutável datado do catálogo (SHA-256 de conteúdo normalizado).
CatalogDiff: diff entre dois snapshots consecutivos.
Integrado ao ArtifactMeta via catalog_snapshot_id.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

# ── Snapshot ──────────────────────────────────────────────────────────────


class CatalogSnapshotMeta(BaseModel):
    """Metadados do snapshot — leve, indexável sem carregar o payload completo."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str = Field(default_factory=lambda: str(uuid4()))
    catalog_name: str  # ex: "mendeslobo"
    version_hash: str  # SHA-256 do conteúdo normalizado
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_url: str | None = None  # URL da planilha Google Sheets ou path local
    source_tab: str | None = None  # aba da planilha (se aplicável)
    created_by: str  # service account, usuário ou "local_loader"
    project_ids: list[str] = Field(default_factory=list)  # append-only


class CatalogSnapshot(BaseModel):
    """Snapshot imutável e datado do catálogo completo (ADR-024 §D2).

    Regra de imutabilidade: snapshots com version_hash já existente não são regravados.
    Apenas project_ids recebe append.
    """

    model_config = ConfigDict(frozen=True)

    meta: CatalogSnapshotMeta
    cpus: list[dict] = Field(default_factory=list)
    insumos: dict[str, list[dict]] = Field(default_factory=dict)  # chave: tipo
    produtividades: list[dict] = Field(default_factory=list)
    funcoes: list[dict] = Field(default_factory=list)  # mapeamento canônico funcao_id -> insumo_id
    tabela_bdi: dict | None = None
    tabela_encargos: dict | None = None

    @classmethod
    def compute_hash(cls, cpus: list, insumos: dict, produtividades: list, funcoes: list | None = None) -> str:
        """SHA-256 de conteúdo normalizado (chaves sorted, floats arredondados a 6 casas)."""
        import json

        def _normalize(obj: Any) -> Any:
            if isinstance(obj, float):
                return round(obj, 6)
            if isinstance(obj, dict):
                return {k: _normalize(v) for k, v in sorted(obj.items())}
            if isinstance(obj, list):
                return [_normalize(i) for i in obj]
            return obj

        payload = _normalize(
            {
                "cpus": cpus,
                "insumos": insumos,
                "produtividades": produtividades,
                "funcoes": funcoes or [],
            }
        )
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def create(
        cls,
        catalog_name: str,
        cpus: list[dict],
        insumos: dict[str, list[dict]],
        produtividades: list[dict],
        created_by: str,
        funcoes: list[dict] | None = None,
        source_url: str | None = None,
        source_tab: str | None = None,
        tabela_bdi: dict | None = None,
        tabela_encargos: dict | None = None,
        project_id: str | None = None,
    ) -> CatalogSnapshot:
        version_hash = cls.compute_hash(cpus, insumos, produtividades, funcoes)
        meta = CatalogSnapshotMeta(
            catalog_name=catalog_name,
            version_hash=version_hash,
            source_url=source_url,
            source_tab=source_tab,
            created_by=created_by,
            project_ids=[project_id] if project_id else [],
        )
        return cls(
            meta=meta,
            cpus=cpus,
            insumos=insumos,
            produtividades=produtividades,
            funcoes=funcoes or [],
            tabela_bdi=tabela_bdi,
            tabela_encargos=tabela_encargos,
        )


# ── Diff ──────────────────────────────────────────────────────────────────


class CatalogDiff(BaseModel):
    """Diff entre dois snapshots de catálogo consecutivos (ADR-024 §D5).

    Gerado como artefato (ArtifactKind.CATALOG_DIFF) em pré-00-escopo quando
    o hash do catálogo muda entre execuções do mesmo projeto.
    """

    model_config = ConfigDict(frozen=True)

    diff_id: str = Field(default_factory=lambda: str(uuid4()))
    previous_snapshot_id: str
    current_snapshot_id: str
    computed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    changed: bool

    cpus_added: list[str] = Field(default_factory=list)
    cpus_removed: list[str] = Field(default_factory=list)
    cpus_modified: list[str] = Field(default_factory=list)

    insumos_added: list[str] = Field(default_factory=list)
    insumos_removed: list[str] = Field(default_factory=list)
    insumos_modified: list[str] = Field(default_factory=list)

    produtividades_added: list[str] = Field(default_factory=list)
    produtividades_removed: list[str] = Field(default_factory=list)
    produtividades_modified: list[str] = Field(default_factory=list)

    summary: str = ""  # ex: "3 CPUs modificadas, 1 insumo adicionado"


def _cs_index(items: list, *keys: str) -> dict:
    """Returns first non-empty index dict keyed by any of the given field names."""
    for key in keys:
        idx = {str(item[key]): item for item in items if key in item}
        if idx:
            return idx
    return {}


def _cs_index_insumos(snapshot: object) -> dict:
    """Returns flat index of all insumos across categories, keyed by codigo/id."""
    return {item.get("codigo", item.get("id", "")): item for lst in snapshot.insumos.values() for item in lst}


def _cs_diff_section(prev_idx: dict, curr_idx: dict) -> tuple:
    """Returns (added, removed, modified) sorted lists for a catalog section."""
    added = sorted(set(curr_idx) - set(prev_idx))
    removed = sorted(set(prev_idx) - set(curr_idx))
    modified = sorted(k for k in set(prev_idx) & set(curr_idx) if prev_idx[k] != curr_idx[k])
    return added, removed, modified


def _cs_append_batch_summary(parts: list, added: list, removed: list, modified: list, label: str) -> None:
    """Appends a combined +/-/mod summary line to parts if any list is non-empty."""
    if added or removed or modified:
        parts.append(f"{len(added)} {label} +, {len(removed)} -, {len(modified)} mod.")


def _cs_build_summary(
    added_cpus: list,
    removed_cpus: list,
    modified_cpus: list,
    added_insumos: list,
    removed_insumos: list,
    modified_insumos: list,
    added_prod: list,
    removed_prod: list,
    modified_prod: list,
) -> str:
    """Builds human-readable summary of catalog diff."""
    parts: list[str] = []
    if added_cpus:
        parts.append(f"{len(added_cpus)} CPU(s) adicionada(s)")
    if removed_cpus:
        parts.append(f"{len(removed_cpus)} CPU(s) removida(s)")
    if modified_cpus:
        parts.append(f"{len(modified_cpus)} CPU(s) modificada(s)")
    _cs_append_batch_summary(parts, added_insumos, removed_insumos, modified_insumos, "insumo(s)")
    _cs_append_batch_summary(parts, added_prod, removed_prod, modified_prod, "produt.")
    return "; ".join(parts) if parts else "Sem mudanças"


def compute_catalog_diff(prev: CatalogSnapshot, curr: CatalogSnapshot) -> CatalogDiff:
    """Computa diff entre dois snapshots por código/id dos itens."""

    prev_cpus = _cs_index(prev.cpus, "codigo", "id")
    curr_cpus = _cs_index(curr.cpus, "codigo", "id")
    added_cpus, removed_cpus, modified_cpus = _cs_diff_section(prev_cpus, curr_cpus)

    prev_ins = _cs_index_insumos(prev)
    curr_ins = _cs_index_insumos(curr)
    added_insumos, removed_insumos, modified_insumos = _cs_diff_section(prev_ins, curr_ins)

    prev_prod = _cs_index(prev.produtividades, "id", "codigo")
    curr_prod = _cs_index(curr.produtividades, "id", "codigo")
    added_prod, removed_prod, modified_prod = _cs_diff_section(prev_prod, curr_prod)

    changed = any(
        [
            added_cpus,
            removed_cpus,
            modified_cpus,
            added_insumos,
            removed_insumos,
            modified_insumos,
            added_prod,
            removed_prod,
            modified_prod,
        ]
    )
    summary = _cs_build_summary(
        added_cpus,
        removed_cpus,
        modified_cpus,
        added_insumos,
        removed_insumos,
        modified_insumos,
        added_prod,
        removed_prod,
        modified_prod,
    )

    return CatalogDiff(
        previous_snapshot_id=prev.meta.snapshot_id,
        current_snapshot_id=curr.meta.snapshot_id,
        changed=changed,
        cpus_added=added_cpus,
        cpus_removed=removed_cpus,
        cpus_modified=modified_cpus,
        insumos_added=added_insumos,
        insumos_removed=removed_insumos,
        insumos_modified=modified_insumos,
        produtividades_added=added_prod,
        produtividades_removed=removed_prod,
        produtividades_modified=modified_prod,
        summary=summary,
    )
