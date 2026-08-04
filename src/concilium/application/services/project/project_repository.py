from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from concilium.domain.models.canonical import CanonicalModel
    from concilium.domain.models.project.escopo import Escopo

INVOCATIONS_LOG_FILENAME = "invocations.log"


class PlanoHandle(Protocol):
    """Contrato de um Plano de Trabalho dentro de um Escopo (ADR-031 §D3).

    Implementações: `PlanoStore` (filesystem, via `EscopoStore`) e
    `StoragePlanoHandle` (BlobStoragePort — sharepoint/s3/azure/gdrive/local).
    """

    # Referência ao Escopo pai — usado por `run_skill_on_plano` para acessar
    # `escopo_meta` (contexto_id/snapshot_catalogo_id/snapshot_perfil_id) e por
    # `new_iteration()` para manter o índice de planos consistente.
    escopo_store: EscopoHandle | None

    @property
    def plano_id(self) -> str: ...

    @property
    def meta(self) -> dict[str, Any]: ...

    @property
    def status(self) -> str: ...

    def load_canonical(self) -> CanonicalModel | None: ...

    def save_canonical(
        self,
        model: CanonicalModel,
        trace_id: str | None = None,
        created_by: str = "runtime",
        parent_refs: list | None = None,
    ) -> None: ...

    def write_canonical_raw(self, content: dict) -> None: ...

    def log_invocation(self, entry: dict) -> None: ...

    def read_invocations(self) -> list[dict]: ...

    def write_premissas_efetivas(
        self, skill_id: str, normalized_inputs: dict[str, Any], escopo_meta: dict[str, Any]
    ) -> None: ...

    def read_premissas_por_skill(self) -> dict[str, dict[str, Any]]: ...

    def save_output_file(self, data: bytes, filename: str = "resultado.xlsx") -> Path: ...

    def load_output_file(self, filename: str = "resultado.xlsx") -> bytes | None: ...

    def list_output_files(self) -> list[str]: ...

    def save_intermediate_file(self, filename: str, data: bytes | str) -> Path: ...

    def load_intermediate_file(self, filename: str) -> bytes | None: ...

    def write_json(self, relative_path: str, payload: Any) -> None: ...

    def read_json(self, relative_path: str, default: Any) -> Any: ...

    def approve(self) -> None: ...

    def archive(self) -> None: ...

    def set_em_analise(self) -> None: ...

    def new_iteration(self, base_plano: PlanoHandle | None = None) -> PlanoHandle: ...


class EscopoHandle(Protocol):
    """Contrato de um Escopo dentro de um projeto (ADR-031 §D3).

    Implementações: `EscopoStore` (filesystem) e `StorageEscopoHandle`
    (BlobStoragePort — sharepoint/s3/azure/gdrive/local).
    """

    @property
    def escopo_id(self) -> str: ...

    @property
    def meta(self) -> dict[str, Any]: ...

    def update_meta(self, **changes: Any) -> None: ...

    def to_escopo(self) -> Escopo | None: ...

    def upsert_roster_mo_membro(self, membro: dict[str, Any]) -> None: ...

    def upsert_roster_eq_ativo(self, ativo: dict[str, Any]) -> None: ...

    def list_plans(self) -> list[str]: ...

    def plan(self, plano_id: str) -> PlanoHandle: ...

    def create_plan(
        self, nome: str, hipotese: str | None = None, plano_id: str | None = None
    ) -> PlanoHandle: ...

    def approved_plan(self) -> PlanoHandle | None: ...

    def active_plan(self) -> PlanoHandle | None: ...

    def approve_plan(self, plano_id: str) -> list[str]: ...


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

    def write_bytes(self, relative_path: str, data: bytes) -> None: ...

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

    # Nome do arquivo de log de invocações dentro de version_path(version) —
    # NÃO usar `version_path(version) / INVOCATIONS_LOG` como Path real: para
    # backends não-filesystem esse Path é lógico (não-backed). Usar sempre
    # `log_invocation`/`read_lines(f"{version}/{INVOCATIONS_LOG}")`.
    INVOCATIONS_LOG: str

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

    def escopo(self, escopo_id: str = "default") -> EscopoHandle: ...

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
    ) -> EscopoHandle: ...


class ProjectRepository(Protocol):
    def list_projects(self) -> Sequence[ProjectHandle]: ...

    def create_project(
        self, nome: str, contexto_id: str, catalogo_base: str | None = None, project_id: str | None = None
    ) -> ProjectHandle: ...

    def get_project(self, project_id: str) -> ProjectHandle: ...
