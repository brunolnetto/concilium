"""FlatVersionStore — adaptador que expõe a interface PlanoStore para versões flat (vN).

Permite que run_skill_on_plano seja o único caminho de execução, eliminando run_skill
como implementação duplicada. O modelo flat (usado por benchmarks e cenários) é
acessado via este wrapper sem necessidade de migração do filesystem existente.

Convenção: escopo_id = '__flat__', plano_id = versão flat (ex: "v1").
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from concilium.domain.models.canonical import CanonicalModel

if TYPE_CHECKING:
    from concilium.application.services.project.project_repository import ProjectHandle


class _EscopoStoreProxy:
    """Proxy mínimo de EscopoStore para contexto flat."""

    def __init__(self, project_meta: dict) -> None:
        self._meta = project_meta

    @property
    def meta(self) -> dict:
        m: dict = {
            "escopo_id": "__flat__",
            "contexto_id": self._meta.get("contexto_id", ""),
        }
        if self._meta.get("snapshot_catalogo_id"):
            m["snapshot_catalogo_id"] = self._meta["snapshot_catalogo_id"]
        if self._meta.get("snapshot_perfil_id"):
            m["snapshot_perfil_id"] = self._meta["snapshot_perfil_id"]
        return m


class FlatVersionStore:
    """Wrapper PlanoStore-compatível para versões flat (vN/).

    Implementa a mesma interface de PlanoStore sem alterar o filesystem existente,
    permitindo que run_skill_on_plano sirva como único ponto de execução de skills.
    """

    CANONICAL_FILE = "canonical.json"
    INVOCATIONS_LOG = "invocations.log"

    def __init__(self, project: ProjectHandle, version: str) -> None:
        self._project = project
        self._version = version
        self.root = project.version_path(version)
        self.escopo_store = _EscopoStoreProxy(project.meta)

    @property
    def plano_id(self) -> str:
        return self._version

    @property
    def meta(self) -> dict:
        return {"plano_id": self._version, "status": "RASCUNHO"}

    def load_canonical(self) -> CanonicalModel | None:
        return self._project.load_canonical(self._version)

    def save_canonical(
        self,
        model: CanonicalModel,
        trace_id: str | None = None,
        created_by: str = "runtime",
        parent_refs: list | None = None,
    ) -> None:
        self._project.save_canonical(model, self._version, trace_id=trace_id, created_by=created_by)

    def log_invocation(self, entry: dict) -> None:
        log = self.root / self.INVOCATIONS_LOG
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def read_invocations(self) -> list[dict]:
        log = self.root / self.INVOCATIONS_LOG
        if not log.exists():
            return []
        out: list[dict] = []
        for line in log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
        return out

    # ── Premissas efetivas (issue #123) ─────────────────────────────────
    # Delega para o ProjectHandle/ProjectStore subjacente, que armazena por
    # versão (vN/) em vez de por plano. Isso faz com que run_skill_on_plano
    # (execution.py) congele premissas e detecte staleness também para o
    # modelo vN flat, sem precisar de nenhuma mudança em execution.py — o
    # hasattr() defensivo lá já cobre este wrapper automaticamente.

    def write_premissas_efetivas(
        self, skill_id: str, normalized_inputs: dict[str, Any], escopo_meta: dict[str, Any]
    ) -> None:
        writer = getattr(self._project, "write_premissas_efetivas", None)
        if writer is not None:
            writer(self._version, skill_id, normalized_inputs, escopo_meta)

    def read_premissas_por_skill(self) -> dict[str, dict[str, Any]]:
        reader = getattr(self._project, "read_premissas_por_skill", None)
        if reader is not None:
            return reader(self._version)
        return {}
