from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from concilium.application.services.project.project_repository import ProjectHandle, ProjectRepository

from .project import ProjectStore


def _rc_try_override(override_path: object, cpu_id: str, json_mod) -> dict | None:
    """Tries loading cpu from project-local override file."""
    from pathlib import Path as _Path

    p = _Path(str(override_path))
    if not p.exists():
        return None
    try:
        override = json_mod.loads(p.read_text(encoding="utf-8"))
        if cpu_id in override:
            return override[cpu_id]
    except Exception:
        pass
    return None


def _rc_try_file(path: object) -> dict | None:
    """Tries loading a single JSON file; returns None on miss or error."""
    from pathlib import Path as _Path

    p = _Path(str(path))
    if not p.exists():
        return None
    try:
        import json as _json

        return _json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _rc_try_aggregate(aggregate: object, cpu_id: str, json_mod) -> dict | None:
    """Searches an aggregated cpus.json file for the given cpu_id."""
    from pathlib import Path as _Path

    p = _Path(str(aggregate))
    if not p.exists():
        return None
    try:
        data = json_mod.loads(p.read_text(encoding="utf-8"))
        cpus = data.get("cpus", data) if isinstance(data, dict) else data
        if isinstance(cpus, list):
            for cpu in cpus:
                if isinstance(cpu, dict) and cpu.get("codigo") == cpu_id:
                    return cpu
    except Exception:
        pass
    return None


def _rc_try_snapshots(snaps_dir: object, cpu_id: str, json_mod) -> dict | None:
    """Searches snapshot catalog files (newest first) for the given cpu_id."""
    from pathlib import Path as _Path

    p = _Path(str(snaps_dir))
    if not p.exists():
        return None
    for snap_file in sorted(p.glob("catalogo-*.json"), reverse=True):
        try:
            snap = json_mod.loads(snap_file.read_text(encoding="utf-8"))
            cpus = snap.get("cpus", [])
            if isinstance(cpus, list):
                for cpu in cpus:
                    if isinstance(cpu, dict) and cpu.get("codigo") == cpu_id:
                        return cpu
        except Exception:  # pragma: no cover
            continue
    return None


class FileProjectHandle(ProjectHandle):
    def __init__(self, store: ProjectStore):
        self._store = store

    @property
    def root(self) -> Path:
        return self._store.root

    @property
    def snapshots(self) -> Any:
        return self._store.snapshots

    @property
    def meta(self) -> dict[str, Any]:
        return self._store.meta

    @property
    def tipo_projeto(self) -> str:
        return self._store.meta.get("tipo_projeto", "hot_project")

    @property
    def status_eap(self) -> str:
        # ADR-063 §D3: status_eap tracks EAP composition readiness for "project" type
        return self._store.meta.get("status_eap", "ATIVO")

    def update_meta(self, **changes: Any) -> None:
        self._store.update_meta(**changes)

    def list_versions(self) -> list[str]:
        return self._store.list_versions()

    def current_version(self) -> str | None:
        return self._store.current_version()

    def new_version(self, base: str | None = None, **kwargs: Any) -> str:  # ADR-119 D2
        return self._store.new_version(base=base, **kwargs)

    def get_version_meta(self, version: str) -> dict:  # ADR-119 D2
        return self._store.get_version_meta(version)

    def version_path(self, version: str) -> Path:
        return self._store.version_path(version)

    def load_canonical(self, version: str | None = None) -> Any:
        return self._store.load_canonical(version)

    def save_canonical(
        self,
        model: Any,
        version: str | None = None,
        trace_id: str | None = None,
        created_by: str = "runtime",
        parent_refs: list | None = None,
    ) -> None:
        self._store.save_canonical(
            model,
            version=version,
            trace_id=trace_id,
            created_by=created_by,
            parent_refs=parent_refs,
        )

    def write_canonical_raw(self, content: dict[str, Any], version: str | None = None) -> None:
        self._store.write_canonical_raw(content, version=version)

    def list_output_files(self, version: str | None = None) -> list[str]:
        return self._store.list_output_files(version)

    def save_output_file(self, data: bytes, version: str | None = None, filename: str = "resultado.xlsx") -> Path:
        return self._store.save_output_file(data, version=version, filename=filename)

    def load_output_file(self, version: str | None = None, filename: str = "resultado.xlsx") -> bytes | None:
        return self._store.load_output_file(version, filename)

    def set_overlay(
        self,
        item_type: str,
        item_id: str,
        overlay_data: dict[str, Any],
        actor: str = "system",
        motivo: str = "",
    ) -> None:
        """ADR-066: persist item overlay (delta) + audit entry."""
        from datetime import UTC, datetime

        overlay_file = f"overrides/{item_type}s_overlay.json"
        overlay = self._store.read_json(overlay_file, {})
        if not isinstance(overlay, dict):
            overlay = {}
        overlay[item_id] = overlay_data
        self._store.write_json(overlay_file, overlay)

        audit_path = self._store.root / "overrides" / "overlay_audit.jsonl"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "event": "set_overlay",
            "item_type": item_type,
            "item_id": item_id,
            "actor": actor,
            "motivo": motivo,
            "fields": list(overlay_data.keys()),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        with audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def extend_cpu(self, cpu_id: str, cpu_data: dict[str, Any], actor: str = "system", motivo: str = "") -> None:
        # ADR-066: overlay only
        self.set_overlay("cpu", cpu_id, cpu_data, actor=actor, motivo=motivo)

    def load_resolved_catalog(self, version: str | None = None) -> dict[str, Any] | None:
        """ADR-066: load the compact resolved catalog persisted for a run."""
        v = version or self._store.current_version()
        if not v:
            return None
        path = self._store.root / v / "resolved_catalog.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def set_compensacao_ineficiencias(self, compensacao: dict, actor: str = "system", motivo: str = "") -> None:
        self._store.set_compensacao_ineficiencias(compensacao, actor=actor, motivo=motivo)

    def resolve_cpu(self, cpu_id: str) -> dict[str, Any] | None:
        # 1. Override local do projeto (mais alta prioridade)
        override_path = self._store.root / "overrides" / "cpus_override.json"
        result = _rc_try_override(override_path, cpu_id, json)
        if result is not None:
            return result

        catalogo_base = self.meta.get("catalogo_base")
        concilium_root = self._store.root.parents[1]

        if catalogo_base:
            # 2. Arquivo individual: config/catalogos/{base}/cpus/{cpu_id}.json
            individual = concilium_root / "config" / "catalogos" / catalogo_base / "cpus" / f"{cpu_id}.json"
            result = _rc_try_file(individual)
            if result is not None:
                return result

            # 3. Arquivo agregado: config/catalogos/{base}/cpus.json
            aggregate = concilium_root / "config" / "catalogos" / catalogo_base / "cpus.json"
            result = _rc_try_aggregate(aggregate, cpu_id, json)
            if result is not None:
                return result

        # 4. Snapshot do catálogo do projeto (fallback imutável)
        snaps_dir = self._store.root / "snapshots"
        return _rc_try_snapshots(snaps_dir, cpu_id, json)

    def read_json(self, relative_path: str, default: Any) -> Any:
        path = self._store.root / relative_path
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def write_json(self, relative_path: str, payload: Any) -> None:
        path = self._store.root / relative_path
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    def append_jsonl(self, relative_path: str, payload: dict[str, Any]) -> None:
        path = self._store.root / relative_path
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    def read_lines(self, relative_path: str) -> list[str]:
        path = self._store.root / relative_path
        if not path.exists():
            return []
        return path.read_text(encoding="utf-8").splitlines()

    def read_bytes(self, relative_path: str) -> bytes | None:
        path = self._store.root / relative_path
        if not path.exists():
            return None
        return path.read_bytes()

    def save_intermediate_file(self, filename: str, data: bytes | str, version: str) -> Path:
        return self._store.save_intermediate_file(filename, data, version)

    def load_intermediate_file(self, filename: str, version: str | None = None) -> bytes | None:
        return self._store.load_intermediate_file(filename, version)

    def list_file_names(self, relative_dir: str) -> list[str]:
        path = self._store.root / relative_dir
        if not path.exists():
            return []
        return sorted(child.name for child in path.iterdir() if child.is_file())

    def delete_tree(self, relative_path: str) -> None:
        path = self._store.root / relative_path
        if path.exists() and path.is_dir():
            shutil.rmtree(path)

    def exists(self, relative_path: str) -> bool:
        return (self._store.root / relative_path).exists()

    def log_invocation(self, version: str, entry: dict[str, Any]) -> None:
        self._store.log_invocation(version, entry)

    def approve(self, version: str) -> None:
        self._store.approve(version)

    def list_escopos(self) -> list[str]:
        return self._store.list_escopos()

    def escopo(self, escopo_id: str = "default") -> Any:
        return self._store.escopo(escopo_id)

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
        return self._store.create_escopo(
            escopo_id=escopo_id,
            nome=nome,
            tipo_obra=tipo_obra,
            localizacao=localizacao,
            coordenadas_lat=coordenadas_lat,
            coordenadas_lng=coordenadas_lng,
            data_inicio=data_inicio,
            data_termino=data_termino,
            dias_semana=dias_semana,
            horas_dia=horas_dia,
            snapshot_catalogo_id=snapshot_catalogo_id,
            snapshot_perfil_id=snapshot_perfil_id,
            bdi_perfil_id=bdi_perfil_id,
        )


class FileProjectRepository(ProjectRepository):
    def __init__(self, projects_root: Path):
        self._projects_root = projects_root

    def list_projects(self) -> list[ProjectHandle]:
        items: list[ProjectHandle] = []
        if not self._projects_root.exists():
            return items
        for project_dir in sorted(self._projects_root.iterdir()):
            meta_path = project_dir / ProjectStore.META_FILE
            if not project_dir.is_dir() or not meta_path.exists():
                continue
            items.append(FileProjectHandle(ProjectStore(project_dir)))
        return items

    def create_project(self, nome: str, contexto_id: str, catalogo_base: str | None = None) -> ProjectHandle:
        return FileProjectHandle(ProjectStore.init(self._projects_root, nome, contexto_id, catalogo_base=catalogo_base))

    def get_project(self, project_id: str) -> ProjectHandle:
        project_dir = self._projects_root / project_id
        if not project_dir.exists() or not (project_dir / ProjectStore.META_FILE).exists():
            raise FileNotFoundError(f"Projeto '{project_id}' nao encontrado.")
        return FileProjectHandle(ProjectStore(project_dir))
