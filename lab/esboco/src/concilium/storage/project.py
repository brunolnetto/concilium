"""Filesystem versionado de projetos: copy-on-write, append-only após approve."""

import json
import os
import shutil
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from concilium.models.canonical import CanonicalModel
from concilium.storage.snapshot import SnapshotStore


class ProjectStore:
    """Gerencia diretório de um projeto: versões, current symlink, persistência do canônico.

    Estrutura:
        projetos/{uuid}/
        ├── meta.json
        ├── snapshots/  (compartilhado entre versões)
        ├── v1/
        │   ├── canonical.json
        │   ├── invocations.log
        │   └── outputs/
        ├── v2/
        └── current → vN
    """

    META_FILE = "meta.json"
    CANONICAL_FILE = "canonical.json"
    INVOCATIONS_LOG = "invocations.log"

    def __init__(self, root: Path):
        """root = projetos/{uuid}/"""
        self.root = root

    @classmethod
    def init(cls, projetos_root: Path, nome: str, perfil_id: str, jurisdicao_id: str) -> "ProjectStore":
        """Cria novo projeto. Retorna o ProjectStore configurado."""
        project_id = str(uuid4())
        proj_root = projetos_root / project_id
        proj_root.mkdir(parents=True, exist_ok=False)
        (proj_root / "snapshots").mkdir()

        meta = {
            "id": project_id,
            "nome": nome,
            "perfil_construtora_id": perfil_id,
            "jurisdicao_id": jurisdicao_id,
            "criado_em": datetime.now(UTC).isoformat(),
            "current_version": None,
        }
        (proj_root / cls.META_FILE).write_text(json.dumps(meta, indent=2))
        return cls(proj_root)

    @property
    def meta(self) -> dict[str, Any]:
        return json.loads((self.root / self.META_FILE).read_text())

    def update_meta(self, **changes: Any) -> None:
        m = self.meta
        m.update(changes)
        (self.root / self.META_FILE).write_text(json.dumps(m, indent=2, default=str))

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
        """Cria nova versão (copy-on-write da base ou da current). Retorna o nome (v3, v4...).

        Se base é None e existe current_version, usa-a.
        Se não há nenhuma versão, cria v1 vazia.
        """
        existing = self.list_versions()
        next_num = (max((int(v[1:]) for v in existing), default=0)) + 1
        new_name = f"v{next_num}"
        new_path = self.root / new_name
        new_path.mkdir()
        (new_path / "outputs").mkdir()
        (new_path / self.INVOCATIONS_LOG).touch()

        # Copy-on-write
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
        if not path.exists():
            return None
        return CanonicalModel.model_validate_json(path.read_text())

    def save_canonical(self, model: CanonicalModel, version: str | None = None) -> None:
        """Persiste canônico. Falha se versão é read-only."""
        v = version or self.current_version()
        if v is None:
            raise ValueError("Nenhuma versão ativa para persistir")
        vpath = self.root / v
        if self._is_readonly(vpath):
            raise PermissionError(
                f"Versão {v} está APROVADA (read-only). Crie nova versão antes de modificar."
            )
        path = vpath / self.CANONICAL_FILE
        path.write_text(model.model_dump_json(indent=2))

    def write_canonical_raw(self, content: dict, version: str | None = None) -> None:
        """Escreve canônico cru — usado quando ainda não temos modelo Pydantic completo (init)."""
        v = version or self.current_version()
        if v is None:
            raise ValueError("Nenhuma versão ativa")
        vpath = self.root / v
        if self._is_readonly(vpath):
            raise PermissionError(f"Versão {v} é read-only")
        (vpath / self.CANONICAL_FILE).write_text(json.dumps(content, indent=2, default=str))

    def log_invocation(self, version: str, entry: dict) -> None:
        """Append linha JSONL no log de invocações."""
        log_path = self.root / version / self.INVOCATIONS_LOG
        with log_path.open("a") as f:
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
