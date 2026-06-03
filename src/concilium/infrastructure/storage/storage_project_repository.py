"""ProjectHandle/ProjectRepository via BlobStoragePort (ADR-047)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from concilium.domain.models.canonical import CanonicalModel
from concilium.domain.repositories.blob_storage_port import BlobStoragePort


class StorageProjectHandle:
    """ProjectHandle backed by BlobStoragePort (ADR-047 §D5).

    Não depende de Path local — todas as operações delegam ao storage.
    Pode ser usado com SharePointBlobStorage ou LocalBlobStorage.
    """

    _META_FILE = "meta.json"
    _CANONICAL_FILE = "canonical.json"
    _INVOCATIONS_LOG = "invocations.log"

    def __init__(self, storage: BlobStoragePort, project_id: str) -> None:
        self._storage = storage
        self._project_id = project_id

    def _path(self, relative: str) -> str:
        """Resolve caminho absoluto dentro do projeto no storage."""
        return f"{self._project_id}/{relative.lstrip('/')}"

    @property
    def meta(self) -> dict[str, Any]:
        return self.read_json(self._META_FILE, {})

    def update_meta(self, **changes: Any) -> None:
        m = self.meta
        m.update(changes)
        self.write_json(self._META_FILE, m)

    def list_versions(self) -> list[str]:
        blobs = self._storage.listar_blobs(self._project_id)
        versions = set()
        for blob in blobs:
            # "projId/v3/canonical.json" → "v3"
            parts = blob.removeprefix(self._project_id + "/").split("/")
            if parts and parts[0].startswith("v") and parts[0][1:].isdigit():
                versions.add(parts[0])
        return sorted(versions, key=lambda v: int(v[1:]))

    def current_version(self) -> str | None:
        return self.meta.get("current_version")

    def new_version(self, base: str | None = None) -> str:
        existing = self.list_versions()
        next_num = (max((int(v[1:]) for v in existing), default=0)) + 1
        new_name = f"v{next_num}"

        # Write empty invocations log (marks the version as existing)
        self._storage.gravar_blob(self._path(f"{new_name}/{self._INVOCATIONS_LOG}"), b"")

        # Copy-on-write from base
        source = base or self.current_version()
        if source:
            try:
                canon_bytes = self._storage.ler_blob(self._path(f"{source}/{self._CANONICAL_FILE}"))
                self._storage.gravar_blob(self._path(f"{new_name}/{self._CANONICAL_FILE}"), canon_bytes)
            except FileNotFoundError:
                pass

        self.update_meta(current_version=new_name)
        return new_name

    def version_path(self, version: str) -> Path:
        return Path(self._project_id) / version

    def load_canonical(self, version: str | None = None) -> CanonicalModel | None:
        v = version or self.current_version()
        if v is None:
            return None
        try:
            data = self._storage.ler_blob(self._path(f"{v}/{self._CANONICAL_FILE}"))
            return CanonicalModel.model_validate_json(data.decode("utf-8"))
        except (FileNotFoundError, Exception):
            return None

    def save_canonical(
        self,
        model: CanonicalModel,
        version: str | None = None,
        trace_id: str | None = None,
        created_by: str = "runtime",
        parent_refs: list | None = None,
    ) -> None:
        v = version or self.current_version()
        if v is None:
            raise RuntimeError("Nenhuma versão ativa — chame new_version() primeiro.")
        payload = model.model_dump_json(indent=2)
        self._storage.gravar_blob(self._path(f"{v}/{self._CANONICAL_FILE}"), payload.encode("utf-8"))

    def read_json(self, relative_path: str, default: Any) -> Any:
        try:
            data = self._storage.ler_blob(self._path(relative_path))
            return json.loads(data.decode("utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    def write_json(self, relative_path: str, payload: Any) -> None:
        content = json.dumps(payload, indent=2, ensure_ascii=False, default=str).encode("utf-8")
        self._storage.gravar_blob(self._path(relative_path), content)

    def append_jsonl(self, relative_path: str, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=False, default=str) + "\n"
        existing = b""
        try:
            existing = self._storage.ler_blob(self._path(relative_path))
        except FileNotFoundError:
            pass
        self._storage.gravar_blob(self._path(relative_path), existing + line.encode("utf-8"))

    def read_lines(self, relative_path: str) -> list[str]:
        try:
            data = self._storage.ler_blob(self._path(relative_path))
            return data.decode("utf-8").splitlines()
        except FileNotFoundError:
            return []

    def read_bytes(self, relative_path: str) -> bytes | None:
        try:
            return self._storage.ler_blob(self._path(relative_path))
        except FileNotFoundError:
            return None

    def exists(self, relative_path: str) -> bool:
        return self._storage.blob_existe(self._path(relative_path))

    def list_file_names(self, relative_dir: str) -> list[str]:
        prefix = self._path(relative_dir)
        blobs = self._storage.listar_blobs(prefix)
        results = []
        for blob in blobs:
            # Extract just the filename (no subdirs)
            name = blob.removeprefix(prefix + "/").removeprefix(prefix)
            if "/" not in name and name:
                results.append(name)
        return sorted(results)

    def delete_tree(self, relative_path: str) -> None:
        prefix = self._path(relative_path)
        blobs = self._storage.listar_blobs(prefix)
        for _blob in blobs:
            try:
                pass
            except Exception:
                pass

    def list_output_files(self, version: str | None = None) -> list[str]:
        v = version or self.current_version()
        if not v:
            return []
        prefix = self._path(f"{v}/outputs")
        blobs = self._storage.listar_blobs(prefix)
        return [b.removeprefix(prefix + "/") for b in blobs if not b.endswith("/")]

    def load_output_file(self, version: str | None = None, filename: str = "resultado.xlsx") -> bytes | None:
        v = version or self.current_version()
        if not v:
            return None
        return self.read_bytes(f"{v}/outputs/{filename}")

    def save_output_file(self, data: bytes, version: str | None = None, filename: str = "resultado.xlsx") -> Path:
        v = version or self.current_version()
        if not v:
            raise RuntimeError("Nenhuma versão ativa.")
        self._storage.gravar_blob(self._path(f"{v}/outputs/{filename}"), data)
        return Path(self._project_id) / v / "outputs" / filename

    # ── CPU overrides ─────────────────────────────────────────────────────

    def extend_cpu(self, cpu_id: str, cpu_data: dict[str, Any], actor: str = "system", motivo: str = "") -> None:
        overrides = self.read_json("overrides/cpus_override.json", {})
        overrides[cpu_id] = cpu_data
        self.write_json("overrides/cpus_override.json", overrides)
        self.append_jsonl(
            "audit_log.jsonl",
            {
                "event": "extend_cpu",
                "actor": actor,
                "motivo": motivo,
                "cpu_id": cpu_id,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    def resolve_cpu(self, cpu_id: str) -> dict[str, Any] | None:
        overrides = self.read_json("overrides/cpus_override.json", {})
        return overrides.get(cpu_id)

    def log_invocation(self, version: str, entry: dict[str, Any]) -> None:
        self.append_jsonl(f"{version}/{self._INVOCATIONS_LOG}", entry)

    def approve(self, version: str) -> None:
        self._storage.aprovar_versao(self._path(f"{version}/{self._CANONICAL_FILE}"))

    @property
    def snapshots(self) -> Any:
        return None

    def list_escopos(self) -> list[str]:
        return []

    def escopo(self, escopo_id: str = "default") -> Any:
        return None

    def create_escopo(
        self,
        escopo_id: str,
        nome: str,
        tipo_obra: str,
        localizacao: str,
        coordenadas_lat: float,
        coordenadas_lng: float,
        data_inicio: str,
        data_termino: str,
        dias_semana: int = 6,
        horas_dia: int = 8,
        snapshot_catalogo_id: str = "",
        snapshot_perfil_id: str = "",
        bdi_perfil_id: str | None = None,
    ) -> Any:
        """ADR-056 §A3 — cria escopo via BlobStoragePort (ADR-031 via cloud storage).

        Estrutura: {project_id}/escopos/{escopo_id}/meta.json
        """
        escopo_meta = {
            "escopo_id": escopo_id,
            "nome": nome,
            "tipo_obra": tipo_obra,
            "localizacao": localizacao,
            "coordenadas": {"lat": coordenadas_lat, "lng": coordenadas_lng},
            "data_inicio": data_inicio,
            "data_termino": data_termino,
            "regime_trabalho": {"dias_semana": dias_semana, "horas_dia": horas_dia},
            "snapshot_catalogo_id": snapshot_catalogo_id,
            "snapshot_perfil_id": snapshot_perfil_id,
            "bdi_perfil_id": bdi_perfil_id,
            "criado_em": datetime.now(UTC).isoformat(),
        }
        self.write_json(f"escopos/{escopo_id}/meta.json", escopo_meta)
        self.write_json(f"escopos/{escopo_id}/planos/_index.json", {"plano_ids": []})

        # Update project-level escopo index
        idx = self.read_json("escopos/_index.json", {"escopo_ids": []})
        if escopo_id not in idx["escopo_ids"]:
            idx["escopo_ids"].append(escopo_id)
        self.write_json("escopos/_index.json", idx)

        return {"escopo_id": escopo_id, "meta": escopo_meta}

    def write_canonical_raw(self, content: dict[str, Any], version: str | None = None) -> None:
        v = version or self.current_version()
        if not v:
            raise RuntimeError("Nenhuma versão ativa.")
        payload = json.dumps(content, indent=2, ensure_ascii=False, default=str).encode("utf-8")
        self._storage.gravar_blob(self._path(f"{v}/{self._CANONICAL_FILE}"), payload)

    @property
    def root(self) -> Path:
        return Path(self._project_id)


class StorageProjectRepository:
    """ProjectRepository backed by BlobStoragePort (ADR-047 §D5).

    Uso com SharePoint:
        storage = SharePointBlobStorage.from_env()
        repo = StorageProjectRepository(storage)
        project = repo.create_project("Obra Norte", "mendeslobo")
    """

    _PROJECTS_INDEX = "projetos/_index.json"

    def __init__(self, storage: BlobStoragePort, projects_prefix: str = "projetos") -> None:
        self._storage = storage
        self._prefix = projects_prefix.strip("/")

    def _full_storage(self, project_id: str) -> BlobStoragePort:
        """Returns a view of storage prefixed with `projects_prefix` only.

        StorageProjectHandle._path() prepends project_id, so this storage
        must NOT include project_id in its prefix — only the projects root.
        Final path in underlying storage: {prefix}/{project_id}/{relative}.
        """
        projects_prefix = self._prefix

        class _PrefixedStorage(BlobStoragePort):
            def __init__(self, inner: BlobStoragePort, prefix: str) -> None:
                self._inner = inner
                self._prefix = prefix

            def ler_blob(self, path: str) -> bytes:
                return self._inner.ler_blob(f"{self._prefix}/{path.lstrip('/')}")

            def gravar_blob(self, path: str, content: bytes) -> None:
                full = f"{self._prefix}/{path.lstrip('/')}"
                self._inner.gravar_blob(full, content)

            def listar_blobs(self, prefix: str) -> list[str]:
                full_prefix = f"{self._prefix}/{prefix.lstrip('/')}"
                blobs = self._inner.listar_blobs(full_prefix)
                strip = f"{self._prefix}/"
                return [b.removeprefix(strip) for b in blobs]

            def blob_existe(self, path: str) -> bool:
                return self._inner.blob_existe(f"{self._prefix}/{path.lstrip('/')}")

            def aprovar_versao(self, path: str) -> None:
                self._inner.aprovar_versao(f"{self._prefix}/{path.lstrip('/')}")

        return _PrefixedStorage(self._storage, projects_prefix)

    def list_projects(self) -> list[StorageProjectHandle]:
        try:
            index = json.loads(self._storage.ler_blob(self._PROJECTS_INDEX).decode("utf-8"))
        except FileNotFoundError:
            return []
        return [StorageProjectHandle(self._full_storage(pid), pid) for pid in index.get("project_ids", [])]

    def create_project(self, nome: str, contexto_id: str, catalogo_base: str | None = None) -> StorageProjectHandle:
        project_id = str(uuid.uuid4())
        scoped = self._full_storage(project_id)
        handle = StorageProjectHandle(scoped, project_id)

        meta: dict[str, Any] = {
            "id": project_id,
            "nome": nome,
            "contexto_id": contexto_id,
            "criado_em": datetime.now(UTC).isoformat(),
            "current_version": None,
            "catalogo_base": catalogo_base,
        }
        handle.write_json("meta.json", meta)

        for fname in (
            "overrides/insumos_override.json",
            "overrides/cpus_override.json",
            "overrides/bdi_override.json",
            "overrides/mobilizacao_policy_override.json",
        ):
            handle.write_json(fname, {})

        self._update_index(project_id)
        return handle

    def get_project(self, project_id: str) -> StorageProjectHandle:
        scoped = self._full_storage(project_id)
        if not scoped.blob_existe(f"{project_id}/meta.json"):
            raise FileNotFoundError(f"Projeto '{project_id}' não encontrado no storage.")
        return StorageProjectHandle(scoped, project_id)

    def _update_index(self, project_id: str) -> None:
        try:
            index = json.loads(self._storage.ler_blob(self._PROJECTS_INDEX).decode("utf-8"))
        except FileNotFoundError:
            index = {"project_ids": []}
        if project_id not in index["project_ids"]:
            index["project_ids"].append(project_id)
        self._storage.gravar_blob(
            self._PROJECTS_INDEX,
            json.dumps(index, indent=2).encode("utf-8"),
        )
