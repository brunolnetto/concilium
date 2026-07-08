"""ConciliumService — parte extraída de concilium_service.py (mixin _ArtifactsReferenceMixin)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._host_protocol import ConciliumServiceHost

    _Base = ConciliumServiceHost
else:
    _Base = object


class _ArtifactsReferenceMixin(_Base):
    """Métodos de artifacts_reference de ConciliumService."""

    def list_artifacts(self, project_id: str, version: str | None) -> dict[str, Any]:
        return self._dependencies.project_service.list_artifacts(project_id, version)

    def get_artifact_bytes(self, project_id: str, version: str | None, kind: str, filename: str) -> tuple[bytes, str]:
        return self._dependencies.project_service.get_artifact_bytes(project_id, version, kind, filename)

    def get_benchmark_reference(self, project_id: str) -> dict[str, Any]:
        return self._dependencies.project_service.get_benchmark_reference(project_id)

    def get_diagnostico_pe(self, project_id: str) -> dict:
        """ADR-060/061: Retorna diagnóstico de PE e backtracking do último run."""
        canonical = self._dependencies.project_service.get_last_canonical(project_id)
        if canonical is None:
            return {"diagnostico_pe": None, "backtracking_pe": None}
        diag = getattr(canonical, "diagnostico_pe", None)
        back = getattr(canonical, "backtracking_pe", None)
        return {
            "diagnostico_pe": diag.to_dict() if diag else None,
            "backtracking_pe": back.to_dict() if back else None,
        }

    def get_calendario_operacional(self, project_id: str, version: str | None = None) -> dict[str, Any]:
        canonical, resolved_version = self._load_canonical_for_version(project_id, version)
        if canonical is None:
            return {"version": resolved_version, "semanas": []}

        semanas: list[dict[str, Any]] = []
        calendario = list(getattr(canonical, "calendario_operacional", []) or [])
        clima_por_semana: dict[str, float] = {}
        total_por_semana: dict[str, float] = {}
        cron = getattr(canonical, "cronograma", None)
        if cron:
            for sa in cron.scheduled_activities:
                for semana_iso, dist in sa.distribuicao_semanal.items():
                    clima_por_semana.setdefault(
                        semana_iso,
                        float(getattr(dist, "fator_clima", getattr(dist, "eficiencia", 1.0)) or 1.0),
                    )
                    total_por_semana.setdefault(
                        semana_iso,
                        float(getattr(dist, "fator_total", getattr(dist, "eficiencia", 1.0)) or 1.0),
                    )

        for row in calendario:
            data = row.model_dump() if hasattr(row, "model_dump") else dict(row)
            semana = str(data.get("semana_iso", ""))
            semanas.append(
                {
                    **data,
                    "fator_clima": round(clima_por_semana.get(semana, 1.0), 4),
                    "fator_total": round(total_por_semana.get(semana, clima_por_semana.get(semana, 1.0)), 4),
                }
            )

        return {"version": resolved_version, "semanas": semanas}

    def simulate_calendario_operacional(
        self,
        project_id: str,
        payload: dict[str, Any],
        version: str | None = None,
    ) -> dict[str, Any]:
        base = self.get_calendario_operacional(project_id, version)
        overrides = dict((payload or {}).get("fator_calendario_semanal", {}) or {})
        simulado: list[dict[str, Any]] = []
        for row in base.get("semanas", []):
            semana = str(row.get("semana_iso", ""))
            _fc = row.get("fator_clima")
            fator_clima = float(_fc if _fc is not None else 1.0)
            _fk_raw = overrides.get(semana, row.get("fator_calendario"))
            fator_cal = float(_fk_raw if _fk_raw is not None else 1.0)
            simulado.append(
                {
                    **row,
                    "fator_calendario": round(fator_cal, 4),
                    "fator_total": round(fator_clima * fator_cal, 4),
                }
            )
        return {"version": base.get("version"), "simulado": simulado}

    def _load_canonical_for_version(self, project_id: str, version: str | None = None):
        """Loads canonical for a specific version (or current when omitted)."""
        repository = getattr(self._dependencies, "repository", None)
        if repository is not None and hasattr(repository, "get_project"):
            try:
                project = repository.get_project(project_id)
                return project.load_canonical(version), (version or project.current_version())
            except Exception:
                pass

        # Compatibilidade com stubs/fluxos legados sem ProjectRepository completo.
        if version is None:
            project_service = getattr(self._dependencies, "project_service", None)
            if project_service is not None and hasattr(project_service, "get_last_canonical"):
                try:
                    return project_service.get_last_canonical(project_id), version
                except Exception:
                    pass

        return None, version

