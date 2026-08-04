from __future__ import annotations

from typing import Any

from concilium.application.runtime import Runtime
from concilium.application.services.project.project_repository import ProjectHandle
from concilium.application.skills.base import SkillResult
from concilium.infrastructure.services.catalog_audit import load_and_audit_catalog


class LifecycleCoordinator:
    """Orquestrador de Lifecycle e Governança de Dados (ADR-035).

    Esta camada 'abraça' a execução do runtime, garantindo que o avanço do planejamento
    respeite os Quality Gates de dados e as regras de transição de estado.
    """

    def __init__(self, runtime: Runtime):
        self.runtime = runtime

    def avancar_plano(
        self,
        skill_id: str,
        project: ProjectHandle,
        plano_store: Any,
        inputs: dict[str, Any] | None = None,
        force_data_gate: bool = True,
    ) -> SkillResult:
        """Executa um passo de avanço no planejamento com auditoria de governança."""

        # 1. Data Management Gate (Governança de Dados)
        if force_data_gate:
            self._audit_data_governance(project, plano_store)

        normalized_inputs = self._inject_project_catalog_layers(project, inputs)

        # 2. Execution (Planning Advancement)
        result = self.runtime.run_skill_on_plano(skill_id, project, plano_store, inputs=normalized_inputs)
        return result

    def _inject_project_catalog_layers(
        self,
        project: ProjectHandle,
        inputs: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Injeta camadas de catálogo do projeto para resolução em cascata (ADR-040/041)."""
        enriched = dict(inputs or {})

        if "insumos_override" not in enriched:
            try:
                loaded = project.read_json("overrides/insumos_override.json", None)
                if isinstance(loaded, dict):
                    enriched["insumos_override"] = loaded
            except Exception:
                # Best-effort: a execução não deve falhar por parse de override.
                pass

        if "jurisdicao_id" not in enriched:
            contexto_id = enriched.get("contexto_id") or project.meta.get("contexto_id")
            if contexto_id:
                try:
                    contexto = self.runtime.load_contexto(str(contexto_id))
                    enriched["jurisdicao_id"] = contexto.jurisdicao_id
                except Exception:
                    pass

        return enriched

    def _audit_data_governance(self, project: ProjectHandle, plano_store: Any):
        """Executa Quality Gates sobre os dados de gestão que alimentam o plano."""
        escopo_meta = plano_store.escopo_store.meta
        snapshot_catalogo_id = escopo_meta.get("snapshot_catalogo_id")
        if snapshot_catalogo_id:
            self.runtime.load_catalogo(snapshot_catalogo_id)
            load_and_audit_catalog(self.runtime, snapshot_catalogo_id)
            return

        contexto_id = escopo_meta.get("contexto_id") or project.meta.get("contexto_id")
        if not contexto_id:
            return  # Sem catálogo/contexto vinculado ainda

        load_and_audit_catalog(self.runtime, contexto_id)
