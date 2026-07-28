from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class ProjectHandle(Protocol):
    @property
    def root(self) -> Path: ...

    @property
    def meta(self) -> dict[str, Any]: ...

    @property
    def tipo_projeto(self) -> str: ...

    @property
    def status_eap(self) -> str: ...

    def update_meta(self, **changes: Any) -> None: ...

    def list_versions(self) -> list[str]: ...

    def current_version(self) -> str | None: ...

    def new_version(
        self,
        base: str | None = None,
        *,
        criado_por: str | None = None,
        role_criador: str | None = None,
        procurement_intent: str | None = None,
        forked_from: str | None = None,
        motivo: str | None = None,
    ) -> str: ...

    def get_version_meta(self, version: str) -> dict[str, Any]: ...

    def version_path(self, version: str) -> Path: ...

    def load_canonical(self, version: str | None = None) -> Any: ...

    def list_output_files(self, version: str | None = None) -> list[str]: ...

    def load_output_file(self, version: str | None = None, filename: str = "resultado.xlsx") -> bytes | None: ...

    def extend_cpu(self, cpu_id: str, cpu_data: dict[str, Any], actor: str = "system", motivo: str = "") -> None: ...

    def resolve_cpu(self, cpu_id: str) -> dict[str, Any] | None: ...

    def read_json(self, relative_path: str, default: Any) -> Any: ...

    def write_json(self, relative_path: str, payload: Any) -> None: ...

    def append_jsonl(self, relative_path: str, payload: dict[str, Any]) -> None: ...

    def read_lines(self, relative_path: str) -> list[str]: ...

    def write_lines(self, relative_path: str, lines: list[str]) -> None: ...

    def read_bytes(self, relative_path: str) -> bytes | None: ...

    def save_intermediate_file(self, filename: str, data: bytes | str, version: str) -> Path: ...

    def load_intermediate_file(self, filename: str, version: str | None = None) -> bytes | None: ...

    def set_overlay(
        self,
        item_type: str,
        item_id: str,
        overlay_data: dict[str, Any],
        actor: str = "system",
        motivo: str = "",
    ) -> None: ...

    def load_resolved_catalog(self, version: str | None = None) -> dict[str, Any] | None: ...

    def list_file_names(self, relative_dir: str) -> list[str]: ...

    def delete_tree(self, relative_path: str) -> None: ...

    def exists(self, relative_path: str) -> bool: ...

    # ── Contrato de fato usado pelos callers (CLI/runtime/skills) ─────────────
    # Presentes em FileProjectHandle E StorageProjectHandle; declarados aqui para
    # o contrato refletir o uso real (mesma classe de gap do issue #41).

    @property
    def snapshots(self) -> Any: ...

    def save_canonical(
        self,
        model: Any,
        version: str | None = None,
        trace_id: str | None = None,
        created_by: str = "runtime",
        parent_refs: list | None = None,
    ) -> None: ...

    def write_canonical_raw(self, content: dict[str, Any], version: str | None = None) -> None: ...

    def save_output_file(self, data: bytes, version: str | None = None, filename: str = "resultado.xlsx") -> Path: ...

    def log_invocation(self, version: str, entry: dict[str, Any]) -> None: ...

    # ADR-121/#123: congelamento de premissas efetivas no modelo vN flat —
    # espelha PlanoStore.write_premissas_efetivas/read_premissas_por_skill
    # (escopo_store.py), mas escopado por versão em vez de por plano.
    def write_premissas_efetivas(
        self, version: str, skill_id: str, normalized_inputs: dict[str, Any], escopo_meta: dict[str, Any]
    ) -> None: ...

    def read_premissas_por_skill(self, version: str) -> dict[str, dict[str, Any]]: ...

    def approve(self, version: str) -> None: ...

    def list_escopos(self) -> list[str]: ...

    def escopo(self, escopo_id: str = "default") -> Any: ...

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
        logistica_consumiveis: dict[str, dict[str, float]] | None = None,
    ) -> Any: ...


class ProjectRepository(Protocol):
    def list_projects(self) -> list[ProjectHandle]: ...

    def create_project(self, nome: str, contexto_id: str, catalogo_base: str | None = None) -> ProjectHandle: ...

    def get_project(self, project_id: str) -> ProjectHandle: ...
