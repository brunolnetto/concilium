"""ProjectHandle/ProjectRepository via BlobStoragePort (ADR-047)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from concilium.domain.models.canonical import CanonicalModel
from concilium.domain.repositories.blob_storage_port import BlobStoragePort

from ._bdi_perfil_freeze import (
    bdi_perfil_versao_filename,
    bdi_perfil_versoes_referenciadas,
    extract_bdi_perfil_versao,
)


class StorageProjectHandle:
    """ProjectHandle backed by BlobStoragePort (ADR-047 §D5).

    Não depende de Path local — todas as operações delegam ao storage.
    Pode ser usado com SharePointBlobStorage ou LocalBlobStorage.
    """

    _META_FILE = "meta.json"
    _CANONICAL_FILE = "canonical.json"
    INVOCATIONS_LOG = "invocations.log"
    _PREMISSAS_EFETIVAS_FILE = "premissas_efetivas.json"
    _PREMISSAS_POR_SKILL_FILE = "premissas_por_skill.json"

    def __init__(self, storage: BlobStoragePort, project_id: str) -> None:
        self._storage = storage
        self._project_id = project_id

    def _path(self, relative: str) -> str:
        """Resolve caminho absoluto dentro do projeto no storage."""
        return f"{self._project_id}/{relative.lstrip('/')}"

    @staticmethod
    def _get_output_subdir(filename: str) -> str:
        """Determina o subdiretório baseado na extensão do arquivo.

        returns: "visualizations" para imagens, "reports" para PDFs/XLSXs
        """
        ext = Path(filename).suffix.lower()
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"):
            return "visualizations"
        if ext in (".pdf", ".xlsx", ".xls", ".csv"):
            return "reports"
        return "reports"  # fallback

    @property
    def meta(self) -> dict[str, Any]:
        return self.read_json(self._META_FILE, {})

    @property
    def tipo_projeto(self) -> str:
        return self.meta.get("tipo_projeto", "hot_project")

    @property
    def status_eap(self) -> str:
        # ADR-063 §D3: status_eap tracks EAP composition readiness for "project" type
        return self.meta.get("status_eap", "ATIVO")

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

    def new_version(
        self,
        base: str | None = None,
        *,
        criado_por: str | None = None,
        role_criador: str | None = None,
        procurement_intent: str | None = None,
        forked_from: str | None = None,
        motivo: str | None = None,
    ) -> str:
        existing = self.list_versions()
        next_num = (max((int(v[1:]) for v in existing), default=0)) + 1
        new_name = f"v{next_num}"

        # Write empty invocations log (marks the version as existing)
        self._storage.gravar_blob(self._path(f"{new_name}/{self.INVOCATIONS_LOG}"), b"")

        # Copy-on-write from base
        source = base or self.current_version()
        if source:
            try:
                canon_bytes = self._storage.ler_blob(self._path(f"{source}/{self._CANONICAL_FILE}"))
                self._storage.gravar_blob(self._path(f"{new_name}/{self._CANONICAL_FILE}"), canon_bytes)
            except FileNotFoundError:
                pass

        # ADR-119 D2: grava metadados de autoria por versão
        m = self.meta
        raw_history = m.get("version_history")
        version_history: dict = raw_history if isinstance(raw_history, dict) else {}
        version_history[new_name] = {
            "criado_em": datetime.now(UTC).isoformat(),
            "criado_por": criado_por,
            "role_criador": role_criador,
            "procurement_intent": procurement_intent,
            "forked_from": forked_from or source,
            "motivo": motivo,
        }
        m["version_history"] = version_history
        m["current_version"] = new_name
        self.write_json(self._META_FILE, m)
        return new_name

    def get_version_meta(self, version: str) -> dict[str, Any]:
        """ADR-119 D2: retorna metadados de autoria de uma versão específica."""
        version_history = self.meta.get("version_history")
        if not isinstance(version_history, dict):
            return {}
        return version_history.get(version) or {}

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

    def _is_readonly(self, version: str) -> bool:
        """Equivalente ao chmod 444 do `ProjectStore` local: em BlobStoragePort não há
        bit de permissão a checar de forma agnóstica de backend, então
        `approved_versions` no meta.json (a mesma fonte de verdade que
        `approve()` grava) já basta como sinal de imutabilidade."""
        return version in (self.meta.get("approved_versions") or [])

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
        if self._is_readonly(v):
            raise PermissionError(f"Versão {v} está APROVADA (read-only). Crie nova versão antes de modificar.")
        payload = model.model_dump_json(indent=2)
        self._storage.gravar_blob(self._path(f"{v}/{self._CANONICAL_FILE}"), payload.encode("utf-8"))
        self._write_canonical_meta_sidecar(
            v, payload, trace_id=trace_id, created_by=created_by, parent_refs=parent_refs
        )

    def _write_canonical_meta_sidecar(
        self,
        version: str,
        payload_json: str,
        *,
        trace_id: str | None,
        created_by: str,
        parent_refs: list | None,
    ) -> None:
        """ADR-018 §D2: sidecar de proveniência (paridade com FileProjectHandle/project.py).

        Best-effort — nunca deve falhar o save do canônico por causa disso.
        """
        try:
            from hashlib import sha256

            from concilium.domain.models.artifact import ArtifactKind, ArtifactMeta

            meta = ArtifactMeta(
                kind=ArtifactKind.CANONICAL,
                schema_name="CanonicalModel",
                schema_version="2026-05-03",
                created_by=created_by,
                trace_id=trace_id,
                parent_refs=parent_refs or [],
                content_hash=sha256(payload_json.encode()).hexdigest(),
                version=version,
            )
            self.write_json(f"{version}/canonical.meta.json", meta.model_dump(mode="json"))
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning("Sidecar write falhou (best-effort, canonical preservado): %s", exc)

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

    def write_lines(self, relative_path: str, lines: list[str]) -> None:
        """Reescreve o blob por completo (diferente de append_jsonl) — usado para

        varreduras de anonimização de PII (LGPD Art. 18) sobre um .jsonl append-only."""
        content = ("\n".join(lines) + "\n") if lines else ""
        self._storage.gravar_blob(self._path(relative_path), content.encode("utf-8"))

    def read_bytes(self, relative_path: str) -> bytes | None:
        try:
            return self._storage.ler_blob(self._path(relative_path))
        except FileNotFoundError:
            return None

    def write_bytes(self, relative_path: str, data: bytes) -> None:
        self._storage.gravar_blob(self._path(relative_path), data)

    def exists(self, relative_path: str) -> bool:
        return self._storage.blob_existe(self._path(relative_path))

    def save_intermediate_file(self, filename: str, data: bytes | str, version: str) -> Path:
        """Salva arquivo em {version}/intermediate/{filename}. Aceita bytes ou str.

        O Path retornado é lógico (não um path de filesystem real) — nenhum
        chamador atual usa o valor de retorno, mantido só por conformidade com
        ProjectHandle (equivalente ao retorno real do FileProjectHandle).
        """
        relative = f"{version}/intermediate/{filename}"
        content = data.encode("utf-8") if isinstance(data, str) else data
        self._storage.gravar_blob(self._path(relative), content)
        return Path(self._path(relative))

    def load_intermediate_file(self, filename: str, version: str | None = None) -> bytes | None:
        """Carrega arquivo de {version}/intermediate/{filename}. None se não existir."""
        v = version or self.current_version()
        if v is None:
            return None
        return self.read_bytes(f"{v}/intermediate/{filename}")

    def set_overlay(
        self,
        item_type: str,
        item_id: str,
        overlay_data: dict[str, Any],
        actor: str = "system",
        motivo: str = "",
    ) -> None:
        """ADR-066: persist item overlay (delta) + audit entry."""
        overlay_file = f"overrides/{item_type}s_overlay.json"
        overlay = self.read_json(overlay_file, {})
        if not isinstance(overlay, dict):
            overlay = {}
        overlay[item_id] = overlay_data
        self.write_json(overlay_file, overlay)
        self.append_jsonl(
            "overrides/overlay_audit.jsonl",
            {
                "event": "set_overlay",
                "item_type": item_type,
                "item_id": item_id,
                "actor": actor,
                "motivo": motivo,
                "fields": list(overlay_data.keys()),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    def load_resolved_catalog(self, version: str | None = None) -> dict[str, Any] | None:
        """ADR-066: load the compact resolved catalog persisted for a run."""
        v = version or self.current_version()
        if v is None:
            return None
        return self.read_json(f"{v}/resolved_catalog.json", None)

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
        for blob in blobs:
            try:
                self._storage.deletar_blob(blob)
            except Exception:  # pragma: no cover
                pass

    def list_output_files(self, version: str | None = None) -> list[str]:
        """Nomes de arquivo em {version}/outputs/, sem o subdiretório
        (visualizations/reports) — paridade com `ProjectStore.list_output_files`."""
        v = version or self.current_version()
        if not v:
            return []
        prefix = self._path(f"{v}/outputs")
        blobs = self._storage.listar_blobs(prefix)
        return sorted({b.rsplit("/", 1)[-1] for b in blobs if not b.endswith("/")})

    def load_output_file(self, version: str | None = None, filename: str = "resultado.xlsx") -> bytes | None:
        v = version or self.current_version()
        if not v:
            return None

        subdir = self._get_output_subdir(filename)
        data = self.read_bytes(f"{v}/outputs/{subdir}/{filename}")
        if data is not None:
            return data

        # Fallback: tentar no outro diretório (compatibilidade)
        fallback_subdir = "reports" if subdir == "visualizations" else "visualizations"
        return self.read_bytes(f"{v}/outputs/{fallback_subdir}/{filename}")

    def save_output_file(self, data: bytes, version: str | None = None, filename: str = "resultado.xlsx") -> Path:
        v = version or self.current_version()
        if not v:
            raise RuntimeError("Nenhuma versão ativa.")

        subdir = self._get_output_subdir(filename)
        self._storage.gravar_blob(self._path(f"{v}/outputs/{subdir}/{filename}"), data)
        return Path(self._project_id) / v / "outputs" / subdir / filename

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
        self.append_jsonl(f"{version}/{self.INVOCATIONS_LOG}", entry)

    # ── Premissas efetivas (issue #123 — congelamento no modelo vN flat) ──
    # Espelha PlanoStore.write_premissas_efetivas/read_premissas_por_skill
    # (escopo_store.py, issue #121) e ProjectStore (project.py) — mesma lógica
    # de hash, armazenada por versão via BlobStoragePort em vez de filesystem local.

    def write_premissas_efetivas(
        self, version: str, skill_id: str, normalized_inputs: dict[str, Any], escopo_meta: dict[str, Any]
    ) -> None:
        from hashlib import sha256

        payload = json.dumps(normalized_inputs, sort_keys=True, default=str)
        content_hash = sha256(payload.encode()).hexdigest()
        escopo_hash = sha256(json.dumps(escopo_meta, sort_keys=True, default=str).encode()).hexdigest()
        ts = datetime.now(UTC).isoformat()

        self.write_json(
            f"{version}/{self._PREMISSAS_EFETIVAS_FILE}",
            {"skill_id": skill_id, "hash": content_hash, "ts": ts, "inputs": normalized_inputs},
        )

        por_skill = self.read_premissas_por_skill(version)
        registro: dict[str, Any] = {"hash": content_hash, "escopo_hash": escopo_hash, "ts": ts}
        bdi_perfil_versao = extract_bdi_perfil_versao(normalized_inputs)
        if bdi_perfil_versao is not None:
            registro["bdi_perfil_versao"] = bdi_perfil_versao
        por_skill[skill_id] = registro
        self.write_json(f"{version}/{self._PREMISSAS_POR_SKILL_FILE}", por_skill)

    def read_premissas_por_skill(self, version: str) -> dict[str, dict[str, Any]]:
        result = self.read_json(f"{version}/{self._PREMISSAS_POR_SKILL_FILE}", {})
        return result if isinstance(result, dict) else {}

    def _protect_bdi_perfil_versoes(self, version: str) -> None:
        """Protege (aprovar_versao) os snapshots de perfil BDI usados pelas skills desta versão (issue #123).

        `bdi/perfil_bdi.json` (cabeça) não é protegido — só os snapshots
        `perfil_bdi_v{NNN}.json` efetivamente referenciados.
        """
        versoes = bdi_perfil_versoes_referenciadas(self.read_premissas_por_skill(version))
        for versao in versoes:
            relative = f"bdi/{bdi_perfil_versao_filename(versao)}"
            if self.exists(relative):
                self._storage.aprovar_versao(self._path(relative))

    def approve(self, version: str) -> None:
        self._storage.aprovar_versao(self._path(f"{version}/{self._CANONICAL_FILE}"))
        for fname in (self._PREMISSAS_EFETIVAS_FILE, self._PREMISSAS_POR_SKILL_FILE):
            relative = f"{version}/{fname}"
            if self.exists(relative):
                self._storage.aprovar_versao(self._path(relative))
        self._protect_bdi_perfil_versoes(version)
        self.update_meta(approved_versions=[*(self.meta.get("approved_versions") or []), version])

    @property
    def snapshots(self) -> Any:
        from .storage_escopo_repository import StorageSnapshotStore

        return StorageSnapshotStore(self._storage, self._project_id)

    def list_escopos(self) -> list[str]:
        idx = self.read_json("escopos/_index.json", {"escopo_ids": []})
        escopo_ids = idx.get("escopo_ids", [])
        return sorted(escopo_ids) if isinstance(escopo_ids, list) else []

    def escopo(self, escopo_id: str = "default") -> Any:
        from .storage_escopo_repository import StorageEscopoHandle

        return StorageEscopoHandle(self._storage, self._project_id, escopo_id)

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
        horas_improdutivas_dia: float = 0.5,
        snapshot_catalogo_id: str = "",
        snapshot_perfil_id: str = "",
        bdi_perfil_id: str | None = None,
        logistica_consumiveis: dict[str, dict[str, float]] | None = None,
        roster_mo: list[dict[str, Any]] | None = None,
        roster_eq: list[dict[str, Any]] | None = None,
    ) -> Any:
        """ADR-056 §A3 — cria escopo via BlobStoragePort (ADR-031 via cloud storage).

        Estrutura: {project_id}/escopos/{escopo_id}/meta.json — formato plano
        (não aninhado), espelhando `ProjectStore.create_escopo` (project.py) para
        que `to_escopo()`/`Escopo.model_validate()` funcionem igual em qualquer
        backend (`projeto_id`/`coordenadas_lat`/`coordenadas_lng` são campos
        obrigatórios no topo do modelo `Escopo`, não aninhados).
        """
        from .storage_escopo_repository import StorageEscopoHandle

        if self.exists(f"escopos/{escopo_id}/meta.json"):
            raise FileExistsError(f"Escopo '{escopo_id}' já existe no projeto.")

        pm = self.meta
        escopo_meta = {
            "escopo_id": escopo_id,
            "projeto_id": pm.get("id", self._project_id),
            "nome": nome,
            "tipo_obra": tipo_obra,
            "localizacao": localizacao,
            "coordenadas_lat": coordenadas_lat,
            "coordenadas_lng": coordenadas_lng,
            "dias_semana": dias_semana,
            "horas_dia": horas_dia,
            "horas_improdutivas_dia": horas_improdutivas_dia,
            "data_inicio": data_inicio,
            "data_termino": data_termino,
            "status": "RASCUNHO",
            "snapshot_catalogo_id": snapshot_catalogo_id or pm.get("snapshot_catalogo_id", ""),
            "snapshot_perfil_id": snapshot_perfil_id or pm.get("snapshot_perfil_id", ""),
            "bdi_perfil_id": bdi_perfil_id,
            # ADR-128 F5: sempre um dict (mesmo vazio) — JSON-serializável de forma estável.
            "logistica_consumiveis": logistica_consumiveis or {},
            # ADR-173 D4 / ADR-174 D2: sempre uma lista (mesmo vazia) — mesma
            # convenção de logistica_consumiveis.
            "roster_mo": roster_mo or [],
            "roster_eq": roster_eq or [],
            "revisao": 1,
            "criado_em": datetime.now(UTC).isoformat(),
        }
        self.write_json(f"escopos/{escopo_id}/meta.json", escopo_meta)
        self.write_json(f"escopos/{escopo_id}/planos/_index.json", {"plano_ids": []})

        # Update project-level escopo index
        idx = self.read_json("escopos/_index.json", {"escopo_ids": []})
        if escopo_id not in idx["escopo_ids"]:
            idx["escopo_ids"].append(escopo_id)
        self.write_json("escopos/_index.json", idx)

        return StorageEscopoHandle(self._storage, self._project_id, escopo_id)

    def write_canonical_raw(self, content: dict[str, Any], version: str | None = None) -> None:
        v = version or self.current_version()
        if not v:
            raise RuntimeError("Nenhuma versão ativa.")
        if self._is_readonly(v):
            raise PermissionError(f"Versão {v} é read-only")
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

    def __init__(self, storage: BlobStoragePort, projects_prefix: str = "projetos") -> None:
        self._storage = storage
        self._prefix = projects_prefix.strip("/")

    @property
    def _index_path(self) -> str:
        return f"{self._prefix}/_index.json" if self._prefix else "_index.json"

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

            def deletar_blob(self, path: str) -> None:
                self._inner.deletar_blob(f"{self._prefix}/{path.lstrip('/')}")

            def aprovar_versao(self, path: str) -> None:
                self._inner.aprovar_versao(f"{self._prefix}/{path.lstrip('/')}")

        return _PrefixedStorage(self._storage, projects_prefix)

    def list_projects(self) -> list[StorageProjectHandle]:
        try:
            index = json.loads(self._storage.ler_blob(self._index_path).decode("utf-8"))
        except FileNotFoundError:
            return []
        return [StorageProjectHandle(self._full_storage(pid), pid) for pid in index.get("project_ids", [])]

    def create_project(
        self, nome: str, contexto_id: str, catalogo_base: str | None = None, project_id: str | None = None
    ) -> StorageProjectHandle:
        project_id = project_id or str(uuid.uuid4())
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
            index = json.loads(self._storage.ler_blob(self._index_path).decode("utf-8"))
        except FileNotFoundError:
            index = {"project_ids": []}
        if project_id not in index["project_ids"]:
            index["project_ids"].append(project_id)
        self._storage.gravar_blob(
            self._index_path,
            json.dumps(index, indent=2).encode("utf-8"),
        )
