"""Filesystem versionado de projetos: copy-on-write, append-only após approve."""

import json
import os
import shutil
import stat
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from concilium.domain.models.canonical import CanonicalModel

from .escopo_store import EscopoStore
from .snapshot import SnapshotStore


class ProjectStore:
    def extend_cpu(self, cpu_id: str, cpu_data: dict, actor: str = "system", motivo: str = "") -> None:
        """Adiciona ou sobrescreve uma CPU no override local do projeto e registra auditoria."""
        override = self.read_json("overrides/cpus_override.json", {})
        override[cpu_id] = cpu_data
        self.write_json("overrides/cpus_override.json", override)
        audit_path = self.root / "audit_log.jsonl"
        event = {
            "event": "extend_cpu",
            "actor": actor,
            "motivo": motivo,
            "cpu_id": cpu_id,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        with audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def set_compensacao_ineficiencias(self, compensacao: dict, actor: str = "system", motivo: str = "") -> None:
        """Salva/atualiza bloco de compensação de ineficiências estruturais (ADR-39) no projeto e registra auditoria."""
        self.write_json(
            "compensacao_ineficiencias.json",
            {
                "compensacao": compensacao,
                "actor": actor,
                "motivo": motivo,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        audit_path = self.root / "audit_log.jsonl"
        event = {
            "event": "set_compensacao_ineficiencias",
            "actor": actor,
            "motivo": motivo,
            "compensacao": compensacao,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        with audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    META_FILE = "meta.json"
    CANONICAL_FILE = "canonical.json"
    INVOCATIONS_LOG = "invocations.log"

    def __init__(self, root: Path):
        """root = projetos/{uuid}/"""
        self.root = root

    def read_json(self, relative_path: str, default: Any) -> Any:
        path = self.root / relative_path
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def write_json(self, relative_path: str, payload: Any) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    @classmethod
    def init(
        cls,
        projetos_root: Path,
        nome: str,
        contexto_id: str,
        catalogo_base: str | None = None,
        derivado_de_benchmark: str | None = None,
        benchmark_versao: int | None = None,
        benchmark_execution_id: str | None = None,
    ) -> "ProjectStore":
        """Cria novo projeto. Retorna o ProjectStore configurado."""
        # Use benchmark slug as project_id if available, otherwise generate UUID
        # This makes directory structure cleaner and more readable for benchmarks
        project_id = derivado_de_benchmark if derivado_de_benchmark else str(uuid4())
        proj_root = projetos_root / project_id
        # exist_ok=True: suporta reset que preserva overrides/ (o dir pode já existir só com overrides)
        proj_root.mkdir(parents=True, exist_ok=True)
        (proj_root / "snapshots").mkdir(exist_ok=True)

        overrides_dir = proj_root / "overrides"
        overrides_dir.mkdir(exist_ok=True)
        for fname in ("cpus_overlay.json", "insumos_overlay.json"):
            f = overrides_dir / fname
            if not f.exists():
                f.write_text("{}", encoding="utf-8")

        meta = {
            "id": project_id,
            "nome": nome,
            "contexto_id": contexto_id,
            "criado_em": datetime.now(UTC).isoformat(),
            "current_version": None,
            "catalogo_base": catalogo_base,
            "derivado_de_benchmark": derivado_de_benchmark,
            "benchmark_versao": benchmark_versao,
            "benchmark_execution_id": benchmark_execution_id,
        }
        (proj_root / cls.META_FILE).write_text(json.dumps(meta, indent=2))
        return cls(proj_root)

    @property
    def meta(self) -> dict[str, Any]:
        return json.loads((self.root / self.META_FILE).read_text(encoding="utf-8"))

    def update_meta(self, **changes: Any) -> None:
        m = self.meta
        m.update(changes)
        (self.root / self.META_FILE).write_text(json.dumps(m, indent=2, default=str), encoding="utf-8")

    @property
    def snapshots(self) -> SnapshotStore:
        return SnapshotStore(self.root / "snapshots")

    def list_versions(self) -> list[str]:
        """Lista versões existentes em ordem (v1, v2, v3, ...)."""
        return sorted(
            (p.name for p in self.root.iterdir() if p.is_dir() and p.name.startswith("v") and p.name[1:].isdigit()),
            key=lambda v: int(v[1:]),
        )

    def current_version(self) -> str | None:
        return self.meta.get("current_version")

    def version_path(self, version: str) -> Path:
        return self.root / version

    def _is_readonly(self, path: Path) -> bool:
        """Versão APROVADA tem canonical.json com chmod 444."""
        cf = path / self.CANONICAL_FILE
        if not cf.exists():
            return False
        return not bool(cf.stat().st_mode & stat.S_IWUSR)

    def new_version(self, base: str | None = None) -> str:
        """Cria nova versão (copy-on-write). Retorna o nome (v3, v4...) — v1 se não há versões."""
        existing = self.list_versions()
        next_num = (max((int(v[1:]) for v in existing), default=0)) + 1
        new_name = f"v{next_num}"
        new_path = self.root / new_name
        new_path.mkdir()
        (new_path / "outputs").mkdir()
        (new_path / self.INVOCATIONS_LOG).touch()

        source = base or self.current_version()
        if source and (self.root / source / self.CANONICAL_FILE).exists():
            shutil.copy(
                self.root / source / self.CANONICAL_FILE,
                new_path / self.CANONICAL_FILE,
            )

        self.update_meta(current_version=new_name)
        return new_name

    def load_canonical(self, version: str | None = None) -> CanonicalModel | None:
        """Carrega canônico da versão especificada (ou current)."""
        v = version or self.current_version()
        if v is None:
            return None
        path = self.root / v / self.CANONICAL_FILE
        for attempt in range(3):
            if not path.exists():
                if attempt == 2:
                    return None
                time.sleep(0.1)
                continue

            try:
                return CanonicalModel.model_validate_json(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                if attempt == 2:
                    return None
                time.sleep(0.1)

        return None

    def save_canonical(
        self,
        model: CanonicalModel,
        version: str | None = None,
        trace_id: str | None = None,
        created_by: str = "runtime",
        parent_refs: list | None = None,
    ) -> None:
        """Persiste canônico + sidecar canonical.meta.json (ADR-018 §D2). Falha se read-only."""
        v = version or self.current_version()
        if v is None:
            raise ValueError("Nenhuma versão ativa para persistir")
        vpath = self.root / v
        if self._is_readonly(vpath):
            raise PermissionError(f"Versão {v} está APROVADA (read-only). Crie nova versão antes de modificar.")
        path = vpath / self.CANONICAL_FILE
        payload_json = model.model_dump_json(indent=2)
        path.write_text(payload_json, encoding="utf-8")

        try:
            from hashlib import sha256

            from concilium.domain.models.artifact import ArtifactKind, ArtifactMeta

            from .artifact_store import FileSystemArtifactStore

            content_hash = sha256(payload_json.encode()).hexdigest()
            meta = ArtifactMeta(
                kind=ArtifactKind.CANONICAL,
                schema_name="CanonicalModel",
                schema_version="2026-05-03",
                created_by=created_by,
                trace_id=trace_id,
                parent_refs=parent_refs or [],
                content_hash=content_hash,
                version=v,
            )
            store = FileSystemArtifactStore(vpath)
            store.save_meta_sidecar(path, meta)
        except Exception as _sidecar_exc:
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "Sidecar write falhou (best-effort, canonical preservado): %s", _sidecar_exc
            )

    def write_canonical_raw(self, content: dict, version: str | None = None) -> None:
        """Escreve canônico cru — usado quando ainda não temos modelo Pydantic completo (init)."""
        v = version or self.current_version()
        if v is None:
            raise ValueError("Nenhuma versão ativa")
        vpath = self.root / v
        if self._is_readonly(vpath):
            raise PermissionError(f"Versão {v} é read-only")
        (vpath / self.CANONICAL_FILE).write_text(json.dumps(content, indent=2, default=str), encoding="utf-8")

    def log_invocation(self, version: str, entry: dict) -> None:
        """Append linha JSONL no log de invocações."""
        log_path = self.root / version / self.INVOCATIONS_LOG
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def approve(self, version: str) -> None:
        """Marca versão como APROVADA: chmod 444 no canonical.json + invocations.log."""
        vpath = self.root / version
        if not vpath.exists():
            raise FileNotFoundError(f"Versão {version} não existe")
        for fname in (self.CANONICAL_FILE, self.INVOCATIONS_LOG):
            f = vpath / fname
            if f.exists():
                os.chmod(f, 0o444)
        self.update_meta(approved_versions=[*self.meta.get("approved_versions", []), version])

    def save_intermediate_file(self, filename: str, data: bytes | str, version: str) -> Path:
        """Salva arquivo em {version}/intermediate/{filename}. Aceita bytes ou str."""
        intermediate_dir = self.root / version / "intermediate"
        intermediate_dir.mkdir(parents=True, exist_ok=True)
        output_path = intermediate_dir / filename
        if isinstance(data, str):
            output_path.write_text(data, encoding="utf-8")
        else:
            output_path.write_bytes(data)
        return output_path

    def load_intermediate_file(self, filename: str, version: str | None = None) -> bytes | None:
        """Carrega arquivo de {version}/intermediate/{filename}. Retorna None se não existir."""
        v = version or self.current_version()
        if v is None:
            return None
        path = self.root / v / "intermediate" / filename
        return path.read_bytes() if path.exists() else None

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

    def save_output_file(self, data: bytes, version: str | None = None, filename: str = "resultado.xlsx") -> Path:
        """Salva arquivo binário em {version}/outputs/{subdir}/{filename}.

        Imagens (PNG, JPG, etc) → outputs/visualizations/
        PDFs e planilhas → outputs/reports/
        """
        v = version or self.current_version()
        if v is None:
            raise ValueError("Nenhuma versão ativa para persistir")

        subdir = self._get_output_subdir(filename)
        outputs_dir = self.root / v / "outputs" / subdir
        outputs_dir.mkdir(parents=True, exist_ok=True)
        output_path = outputs_dir / filename
        output_path.write_bytes(data)
        return output_path

    def load_output_file(self, version: str | None = None, filename: str = "resultado.xlsx") -> bytes | None:
        """Carrega arquivo binário de {version}/outputs/{subdir}/{filename}.

        Procura em outputs/visualizations ou outputs/reports conforme extensão.
        Retorna None se inexistente.
        """
        v = version or self.current_version()
        if v is None:
            return None

        subdir = self._get_output_subdir(filename)
        output_path = self.root / v / "outputs" / subdir / filename
        if output_path.exists():
            return output_path.read_bytes()

        # Fallback: tentar no outro diretório (para compatibilidade)
        fallback_subdir = "reports" if subdir == "visualizations" else "visualizations"
        fallback_path = self.root / v / "outputs" / fallback_subdir / filename
        if fallback_path.exists():
            return fallback_path.read_bytes()

        return None

    def list_output_files(self, version: str | None = None) -> list[str]:
        """Lista nomes de arquivos em {version}/outputs/, recursivamente em subdiretórios."""
        v = version or self.current_version()
        if v is None:
            return []
        outputs_dir = self.root / v / "outputs"
        if not outputs_dir.exists():
            return []

        files = []
        for subdir_path in outputs_dir.iterdir():
            if subdir_path.is_dir():
                for f in subdir_path.iterdir():
                    if f.is_file():
                        files.append(f.name)
        return sorted(files)

    def resolve_cpu(self, cpu_id: str) -> dict | None:
        """Resolve CPU pelo id: override → catálogo base (individual + agregado) → snapshot."""
        # 1. Override local do projeto — via read_json para consistência com o store
        override = self.read_json("overrides/cpus_override.json", {})
        if cpu_id in override:
            return override[cpu_id]

        catalogo_base = self.meta.get("catalogo_base")
        # concilium_root: project.py está em src/concilium/infrastructure/storage/

        concilium_root = Path(__file__).parents[4]

        if catalogo_base:
            individual = concilium_root / "config" / "catalogos" / catalogo_base / "cpus" / f"{cpu_id}.json"
            if individual.exists():
                try:
                    return json.loads(individual.read_text(encoding="utf-8"))
                except Exception:
                    pass

            aggregate = concilium_root / "config" / "catalogos" / catalogo_base / "cpus.json"
            if aggregate.exists():
                try:
                    data = json.loads(aggregate.read_text(encoding="utf-8"))
                    cpus = data.get("cpus", data) if isinstance(data, dict) else data
                    for cpu in cpus if isinstance(cpus, list) else []:
                        if isinstance(cpu, dict) and cpu.get("codigo") == cpu_id:
                            return cpu
                except Exception:
                    pass

        snaps_dir = self.root / "snapshots"
        if snaps_dir.exists():
            for snap_file in sorted(snaps_dir.glob("catalogo-*.json"), reverse=True):
                try:
                    snap = json.loads(snap_file.read_text(encoding="utf-8"))
                    for cpu in snap.get("cpus", []) if isinstance(snap, dict) else []:
                        if isinstance(cpu, dict) and cpu.get("codigo") == cpu_id:
                            return cpu
                except Exception:
                    continue
        return None

    def list_escopos(self) -> list[str]:
        """Lista IDs de escopos existentes."""
        d = self.root / "escopos"
        if not d.exists():
            return []
        return sorted(p.name for p in d.iterdir() if p.is_dir())

    def escopo(self, escopo_id: str = "default") -> EscopoStore:
        """Retorna EscopoStore para o escopo solicitado."""
        return EscopoStore(self.root / "escopos" / escopo_id)

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
    ) -> EscopoStore:
        """Cria novo escopo no projeto. Falha se escopo_id já existir."""
        escopo_dir = self.root / "escopos" / escopo_id
        if escopo_dir.exists():
            raise FileExistsError(f"Escopo '{escopo_id}' já existe no projeto.")
        (escopo_dir / "planos").mkdir(parents=True, exist_ok=True)

        pm = self.meta
        meta = {
            "escopo_id": escopo_id,
            "projeto_id": pm.get("id", str(self.root.name)),
            "nome": nome,
            "tipo_obra": tipo_obra,
            "localizacao": localizacao,
            "coordenadas_lat": coordenadas_lat,
            "coordenadas_lng": coordenadas_lng,
            "dias_semana": dias_semana,
            "horas_dia": horas_dia,
            "data_inicio": data_inicio,
            "data_termino": data_termino,
            "status": "RASCUNHO",
            "snapshot_catalogo_id": snapshot_catalogo_id or pm.get("snapshot_catalogo_id", ""),
            "snapshot_perfil_id": snapshot_perfil_id or pm.get("snapshot_perfil_id", ""),
            "bdi_perfil_id": bdi_perfil_id,
            "revisao": 1,
            "criado_em": datetime.now(UTC).isoformat(),
        }
        (escopo_dir / EscopoStore.ESCOPO_FILE).write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
        return EscopoStore(escopo_dir)
