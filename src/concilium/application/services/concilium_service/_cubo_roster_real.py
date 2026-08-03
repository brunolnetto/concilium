"""ConciliumService — parte extraída (mixin _CuboRosterRealMixin, ADR-174)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._host_protocol import ConciliumServiceHost

    _Base = ConciliumServiceHost
else:
    _Base = object


class _CuboRosterRealMixin(_Base):
    """Métodos de cubo de roster real de ConciliumService (ADR-174).

    Desvio deliberado frente aos outros mixins de cubo (`_CuboAnaliticoMixin`,
    `_CuboEstoqueConsumivelMixin`): aqueles só precisam do canonical, porque seu
    dado de entrada já foi "baked-in" por uma skill. Roster (`Escopo.roster_mo`/
    `roster_eq`, ADR-173/174) nunca é baked-in no canonical por design (ADR-160
    D1) — este mixin busca o `Escopo` à parte, via `repository.get_project`.
    """

    @staticmethod
    def get_cubo_roster_real_projection_contract() -> dict[str, Any]:
        """ADR-174: contrato navegável das faces do cubo de roster real."""
        from concilium.application.services.analytics.cubo_roster_real_projection import (
            cubo_roster_real_projection_contract,
        )

        return cubo_roster_real_projection_contract()

    def get_cubo_roster_real_projection(
        self,
        project_id: str,
        *,
        version: str | None = None,
        escopo_id: str = "default",
        face: str = "resumo_por_instancia",
        granularidade: str = "mes",
        top_n: int = 300,
        categoria: str | None = None,
        grupo_id: str | None = None,
        instancia_id: str | None = None,
    ) -> dict[str, Any]:
        """ADR-174: projeção do custo por instância real de roster (MO+EQ)."""
        from concilium.application.services.analytics.cubo_roster_real_projection import (
            resolve_cubo_roster_real_projection,
        )

        canonical, resolved_version = self._load_canonical_for_version(project_id, version)
        if canonical is None:
            return {
                "version": resolved_version,
                "face": face,
                "rows": [],
                "narrativa": [],
                "filtros_aplicados": {},
                "invariantes_ok": True,
            }

        roster_mo, roster_eq = self._load_roster_real(project_id, escopo_id)
        catalogo = self._load_catalogo_best_effort(project_id)

        proj = resolve_cubo_roster_real_projection(
            canonical,
            roster_mo,
            roster_eq,
            catalogo,
            face=face,
            granularidade=granularidade,
            top_n=top_n,
            categoria=categoria,
            grupo_id=grupo_id,
            instancia_id=instancia_id,
        )
        proj["version"] = resolved_version
        return proj

    def _load_roster_real(self, project_id: str, escopo_id: str) -> tuple[list[Any], list[Any]]:
        """Roster nunca é baked-in no canonical — busca à parte no Escopo (ADR-174 D6)."""
        repository = getattr(self._dependencies, "repository", None)
        if repository is None:
            return [], []
        try:
            project = repository.get_project(project_id)
            escopo = project.escopo(escopo_id).to_escopo()
        except Exception:
            return [], []
        if escopo is None:
            return [], []
        return list(escopo.roster_mo), list(escopo.roster_eq)

    def _load_catalogo_best_effort(self, project_id: str) -> dict[str, Any] | None:
        """Sem catálogo, custo_indireto de MO degrada para 0.0 (mesmo padrão de
        toda a cadeia ADR-165/166/173) — nunca lança erro."""
        from concilium.application.runtime import Runtime

        repository = getattr(self._dependencies, "repository", None)
        if repository is None:
            return None
        try:
            project = repository.get_project(project_id)
        except Exception:
            return None
        candidate_ids = self._candidate_catalog_ids(project)
        rt = Runtime(self.config_root)
        for catalog_id in candidate_ids:
            try:
                return rt.load_catalogo(catalog_id)
            except Exception:
                continue
        return None
