"""ADR-018 — ArtifactStore: interface e implementação filesystem.

Hoje: sidecar .meta.json ao lado do payload.
Futuro: interface preservada para migração a DB sem mudança nos callers.

Layout:
  projetos/{uuid}/v3/canonical.json         ← payload (CanonicalModel)
  projetos/{uuid}/v3/canonical.meta.json    ← ArtifactMeta (sidecar)

  config/catalogos/<id>/produtividades/ESCO-CARGA-1CAT-PROD-001.json       ← payload (Producao)
  config/catalogos/<id>/produtividades/ESCO-CARGA-1CAT-PROD-001.meta.json  ← ArtifactMeta (sidecar)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from concilium.domain.models.artifact import ArtifactEnvelope, ArtifactKind, ArtifactMeta, ArtifactRef


class ArtifactStore:
    """Interface de storage de artefatos (ADR-018 §Artifact Store Interface)."""

    def save(self, artifact: ArtifactEnvelope[Any]) -> None:
        raise NotImplementedError

    def get(self, ref: ArtifactRef) -> ArtifactEnvelope[Any]:
        raise NotImplementedError

    def list_by_trace(self, trace_id: str) -> list[ArtifactRef]:
        """Todos os artefatos produzidos em uma sessão Claude (mesmo trace_id)."""
        raise NotImplementedError

    def list_by_kind(self, kind: ArtifactKind) -> list[ArtifactRef]:
        raise NotImplementedError


class FileSystemArtifactStore(ArtifactStore):
    """Implementação filesystem: sidecar .meta.json ao lado do payload.

    Recebe um diretório raiz e escreve metadados lá, mantendo
    um índice por trace_id em .artifact_index.jsonl.
    """

    INDEX_FILE = ".artifact_index.jsonl"

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_meta_sidecar(self, payload_path: Path, meta: ArtifactMeta) -> None:
        """Escreve sidecar .meta.json ao lado do payload existente.

        Não escreve o payload — apenas os metadados. Caller é responsável
        por já ter persistido o payload.
        """
        sidecar = payload_path.with_suffix("").with_name(payload_path.stem + ".meta.json")
        sidecar.write_text(meta.model_dump_json(indent=2), encoding="utf-8")
        self._append_index(meta, sidecar)

    def save(self, artifact: ArtifactEnvelope[Any]) -> None:
        """Persiste payload + sidecar no diretório root."""
        payload_path = self.root / f"{artifact.meta.artifact_id}.json"
        payload = artifact.payload
        if hasattr(payload, "model_dump_json"):
            payload_json = payload.model_dump_json(indent=2)
        else:
            payload_json = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
        payload_path.write_text(payload_json, encoding="utf-8")
        self.save_meta_sidecar(payload_path, artifact.meta)

    def get(self, ref: ArtifactRef) -> ArtifactEnvelope[Any]:
        sidecar_path = self.root / f"{ref.artifact_id}.meta.json"
        if not sidecar_path.exists():
            raise FileNotFoundError(f"Artefato '{ref.artifact_id}' não encontrado em {self.root}")
        meta = ArtifactMeta.model_validate_json(sidecar_path.read_text(encoding="utf-8"))
        from concilium.domain.models.artifact import ConciliumArtifactRegistry

        payload_path = sidecar_path.with_name(f"{ref.artifact_id}.json")
        payload_data = json.loads(payload_path.read_text(encoding="utf-8"))
        payload = ConciliumArtifactRegistry.validate(ref.schema_name, payload_data)
        return ArtifactEnvelope(meta=meta, payload=payload)

    def list_by_trace(self, trace_id: str) -> list[ArtifactRef]:
        index_path = self.root / self.INDEX_FILE
        if not index_path.exists():
            return []
        refs: list[ArtifactRef] = []
        for line in index_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("trace_id") == trace_id:
                    refs.append(ArtifactRef.model_validate(entry["ref"]))
            except Exception:
                continue
        return refs

    def list_by_kind(self, kind: ArtifactKind) -> list[ArtifactRef]:
        index_path = self.root / self.INDEX_FILE
        if not index_path.exists():
            return []
        refs: list[ArtifactRef] = []
        for line in index_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("kind") == kind.value:
                    refs.append(ArtifactRef.model_validate(entry["ref"]))
            except Exception:
                continue
        return refs

    def _append_index(self, meta: ArtifactMeta, sidecar_path: Path) -> None:
        index_path = self.root / self.INDEX_FILE
        entry = {
            "artifact_id": meta.artifact_id,
            "kind": meta.kind.value,
            "trace_id": meta.trace_id,
            "schema_name": meta.schema_name,
            "created_at": meta.created_at.isoformat(),
            "sidecar": str(sidecar_path),
            "ref": {
                "artifact_id": meta.artifact_id,
                "version": meta.version,
                "kind": meta.kind.value,
                "schema_name": meta.schema_name,
                "schema_version": meta.schema_version,
                "content_hash": meta.content_hash,
            },
        }
        with index_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
