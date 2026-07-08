"""ConciliumService — parte extraída de concilium_service.py (mixin _CuboAnaliticoMixin)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from ._host_protocol import ConciliumServiceHost

    _Base = ConciliumServiceHost
else:
    _Base = object


class _CuboAnaliticoMixin(_Base):
    """Métodos de cubo_analitico de ConciliumService."""

    def get_cubo_analitico(self, project_id: str, version: str | None = None) -> dict[str, Any]:
        """ADR-058/NEP-024: Retorna o cubo analítico e seus agregados derivados."""
        canonical, resolved_version = self._load_canonical_for_version(project_id, version)
        if canonical is None:
            return {"version": resolved_version, "cubo_analitico": None}
        cubo = getattr(canonical, "cubo_analitico", None)
        if cubo is None:
            from concilium.domain.services.analytics.cubo_analitico_builder import CuboAnaliticoBuilder

            cubo = CuboAnaliticoBuilder().build(canonical)
        return {"version": resolved_version, "cubo_analitico": cubo.to_dict() if cubo else None}

    @staticmethod
    def get_cubo_pool_projection_contract() -> dict[str, Any]:
        """ADR-086 D6.1: contrato navegável das faces do cubo de pool."""
        from concilium.application.services.analytics.cubo_pool_projection import (
            cubo_pool_projection_contract,
        )

        return cubo_pool_projection_contract()

    def get_cubo_pool_projection(
        self,
        project_id: str,
        *,
        version: str | None = None,
        face: str = "instancia_ciclo_vida",
        granularidade: str = "mes",
        top_n: int = 300,
        atividade_id: str | None = None,
        instancia_id: str | None = None,
    ) -> dict[str, Any]:
        """ADR-086 D6.1: projeção honesta e descritiva da decomposição de pool de recursos."""
        from concilium.application.services.analytics.cubo_pool_projection import (
            resolve_cubo_pool_projection,
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
                "invariantes_violacoes": [],
            }
        proj = resolve_cubo_pool_projection(
            canonical,
            face=face,
            granularidade=granularidade,
            top_n=top_n,
            atividade_id=atividade_id,
            instancia_id=instancia_id,
        )
        proj["version"] = resolved_version
        return proj

    @staticmethod
    def get_cubo_projection_contract() -> dict[str, Any]:
        faces: dict[str, dict[str, Any]] = {
            "tempo_natureza": {
                "label": "Tempo x natureza",
                "unit_type": "currency_brl",
                "measure_profiles": ["financial_default"],
                "aggregation_modes": ["sum"],
            },
            "tempo_componente": {
                "label": "Tempo x componente BDI",
                "unit_type": "currency_brl",
                "measure_profiles": ["financial_default"],
                "aggregation_modes": ["sum"],
            },
            "categoria_componente": {
                "label": "Categoria x componente BDI",
                "unit_type": "currency_brl",
                "measure_profiles": ["financial_default"],
                "aggregation_modes": ["sum"],
            },
            "atividade_componente": {
                "label": "Atividade x componente BDI",
                "unit_type": "currency_brl",
                "measure_profiles": ["financial_default"],
                "aggregation_modes": ["sum"],
            },
            "diesel_temporal": {
                "label": "Diesel temporal",
                "unit_type": "volume_liter",
                "measure_profiles": ["financial_default"],
                "aggregation_modes": ["sum"],
            },
            "abc_curva": {
                "label": "Curva ABC",
                "unit_type": "currency_brl",
                "measure_profiles": ["abc_custo_direto"],
                "aggregation_modes": ["pareto"],
            },
            "s_curve_custo": {
                "label": "S-curve de custo",
                "unit_type": "currency_brl",
                "measure_profiles": ["financial_default"],
                "aggregation_modes": ["cumulative"],
            },
            "recursos_ativos_tempo": {
                "label": "Recursos ativos no tempo",
                "unit_type": "count",
                "measure_profiles": ["recursos_ativos"],
                "aggregation_modes": ["sum", "count_distinct"],
            },
        }
        return {
            "faces": faces,
            "granularidades": ["semana", "mes", "bimestre", "trimestre", "semestre", "ano"],
            "measure_profiles": ["financial_default", "abc_custo_direto", "recursos_ativos"],
            "aggregation_modes": ["sum", "count_distinct", "cumulative", "pareto"],
            "abc_defaults": {"threshold_a": 0.80, "threshold_b": 0.95},
        }

    @staticmethod
    def _resolve_cubo_projection_rows(
        cubo: Any,
        face: str,
        granularidade: Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"],
        top_n: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
        from ..analytics.cube_projection_views import resolve_cubo_projection_rows

        return resolve_cubo_projection_rows(cubo, face, granularidade, top_n)

    @staticmethod
    def _bucket_from_week_iso(
        week_iso: str,
        granularidade: Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"],
    ) -> str:
        from ..analytics.cube_projection_views import bucket_from_week_iso

        return bucket_from_week_iso(week_iso, granularidade)

    def _resolve_abc_curva_rows(
        self,
        canonical: Any,
        top_n: int,
        threshold_a: float,
        threshold_b: float,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]], str, str, dict[str, Any]]:
        from ..analytics.cube_projection_views import resolve_abc_curva_rows

        return resolve_abc_curva_rows(canonical, top_n, threshold_a, threshold_b)

    def _resolve_s_curve_rows(
        self,
        canonical: Any,
        granularidade: Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"],
        top_n: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]], str, str, dict[str, Any]]:
        from ..analytics.cube_projection_views import resolve_s_curve_rows

        return resolve_s_curve_rows(canonical, granularidade, top_n)

    def _resolve_recursos_ativos_rows(
        self,
        canonical: Any,
        granularidade: Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"],
        top_n: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]], str, str, dict[str, Any]]:
        from ..analytics.cube_projection_views import resolve_recursos_ativos_rows

        return resolve_recursos_ativos_rows(canonical, granularidade, top_n)

    def _validate_cube_projection_params(
        self,
        contract: dict[str, Any],
        face: str,
        granularidade: str,
        categoria: str | None,
        componente_bdi: str | None,
        abc_threshold_a: float,
        abc_threshold_b: float,
    ) -> None:
        """Valida os parâmetros básicos de uma projeção do cubo analítico (levanta ValueError se inválidos)."""
        allowed_faces = {
            "tempo_natureza",
            "tempo_componente",
            "categoria_componente",
            "atividade_componente",
            "diesel_temporal",
            "abc_curva",
            "s_curve_custo",
            "recursos_ativos_tempo",
        }
        allowed_granularidade = set(contract["granularidades"])
        allowed_categoria = {"mao_obra", "equipamento", "diesel", "material"}
        allowed_componentes = {
            "custo_direto",
            "overhead_ac",
            "overhead_df",
            "overhead_r",
            "overhead_cr",
            "margem_l",
            "tributo_cofins",
            "tributo_iss",
            "tributo_pis",
            "tributo_cssl",
            "tributo_ir",
        }
        if face not in allowed_faces:
            raise ValueError(f"Face de projeção não suportada: {face}")
        if granularidade not in allowed_granularidade:
            raise ValueError(f"Granularidade inválida: {granularidade}")
        if categoria is not None and categoria not in allowed_categoria:
            raise ValueError(f"Categoria inválida: {categoria}")
        if componente_bdi is not None and componente_bdi not in allowed_componentes:
            raise ValueError(f"Componente BDI inválido: {componente_bdi}")
        if not (0.0 < abc_threshold_a < abc_threshold_b < 1.0):
            raise ValueError("Thresholds ABC inválidos: use 0 < a < b < 1")

    def _resolve_measure_and_aggregation(
        self,
        contract: dict[str, Any],
        face_specs: dict[str, Any],
        face: str,
        measure_profile: str | None,
        aggregation_mode: str | None,
    ) -> tuple[str, str]:
        """Resolve e valida measure_profile/aggregation_mode contra o contrato global e o da face."""
        allowed_measure_profile = set(contract["measure_profiles"])
        allowed_aggregation_mode = set(contract["aggregation_modes"])
        face_measure_profiles_list = list(face_specs[face]["measure_profiles"])
        face_aggregation_modes_list = list(face_specs[face]["aggregation_modes"])
        face_measure_profiles = set(face_measure_profiles_list)
        face_aggregation_modes = set(face_aggregation_modes_list)
        resolved_measure_profile = measure_profile or face_measure_profiles_list[0]
        resolved_aggregation_mode = aggregation_mode or face_aggregation_modes_list[0]
        if resolved_measure_profile not in allowed_measure_profile:
            raise ValueError(f"Measure profile inválido: {resolved_measure_profile}")
        if resolved_aggregation_mode not in allowed_aggregation_mode:
            raise ValueError(f"Aggregation mode inválido: {resolved_aggregation_mode}")
        if resolved_measure_profile not in face_measure_profiles:
            raise ValueError(f"Measure profile inválido para a face: {resolved_measure_profile} em {face}")
        if resolved_aggregation_mode not in face_aggregation_modes:
            raise ValueError(f"Aggregation mode inválido para a face: {resolved_aggregation_mode} em {face}")
        return resolved_measure_profile, resolved_aggregation_mode

    def _load_canonical_and_cubo(self, project_id: str, version: str | None) -> tuple[Any, str | None, Any]:
        """Carrega o canônico da versão e retorna (canonical, resolved_version, cubo_analitico)."""
        canonical, resolved_version = self._load_canonical_for_version(project_id, version)
        if canonical is None:
            return None, resolved_version, None
        cubo = getattr(canonical, "cubo_analitico", None)
        if cubo is None:
            from concilium.domain.services.analytics.cubo_analitico_builder import CuboAnaliticoBuilder

            cubo = CuboAnaliticoBuilder().build(canonical)
        return canonical, resolved_version, cubo

    def _build_cube_projection_result(
        self,
        canonical: Any,
        cubo: Any,
        face: str,
        granularidade: Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"],
        categoria: str | None,
        componente_bdi: str | None,
        atividade_id: str | None,
        top_n: int,
        abc_threshold_a: float,
        abc_threshold_b: float,
        resolved_version: str | None,
        resolved_measure_profile: str,
        resolved_aggregation_mode: str,
    ) -> dict[str, Any]:
        """Filtra o cubo, monta o payload de projeção e monta o resultado final da API."""
        bounded_top_n = max(1, min(int(top_n), 2000))
        cubo_filtrado = cubo.slice(categoria=categoria, atividade_id=atividade_id, componente_bdi=componente_bdi)

        from ..analytics.cube_projection_views import build_cube_projection_payload

        projection_payload = build_cube_projection_payload(
            canonical=canonical,
            cubo=cubo_filtrado,
            face=face,
            granularidade=granularidade,
            top_n=bounded_top_n,
            abc_threshold_a=abc_threshold_a,
            abc_threshold_b=abc_threshold_b,
        )
        rows = projection_payload["rows"]
        columns = projection_payload["columns"]
        chart_hint = str(projection_payload["chart_hint"])
        unit_type = str(projection_payload["unit_type"])
        operator_meta = projection_payload["operator_meta"]

        return {
            "version": resolved_version,
            "face": face,
            "granularidade": granularidade,
            "measure_profile": resolved_measure_profile,
            "aggregation_mode": resolved_aggregation_mode,
            "unit_type": unit_type,
            "chart_hint": chart_hint,
            "columns": columns,
            "operator_meta": operator_meta,
            "filtros_aplicados": {
                "categoria": categoria,
                "componente_bdi": componente_bdi,
                "atividade_id": atividade_id,
                "top_n": bounded_top_n,
            },
            "totais": {
                "total_preco_venda": float(cubo_filtrado.total_preco_venda),
                "total_custo_direto": float(cubo_filtrado.total_custo_direto),
                "total_overhead": float(cubo_filtrado.total_overhead),
                "total_margem": float(cubo_filtrado.total_margem),
                "total_tributos": float(cubo_filtrado.total_tributos),
                "total_consumo_diesel_L": float(cubo_filtrado.total_consumo_diesel_L),
            },
            "rows": rows,
        }

    def get_cubo_analitico_projection(
        self,
        project_id: str,
        *,
        version: str | None = None,
        face: str = "tempo_natureza",
        granularidade: Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"] = "mes",
        categoria: str | None = None,
        componente_bdi: str | None = None,
        atividade_id: str | None = None,
        top_n: int = 300,
        measure_profile: str | None = None,
        aggregation_mode: str | None = None,
        abc_threshold_a: float = 0.80,
        abc_threshold_b: float = 0.95,
    ) -> dict[str, Any]:
        """ADR-069: Projeções navegáveis do cubo para UX iterativa de filtros."""
        # Validate parameters early — before loading canonical, so callers get
        # immediate errors on invalid face/granularidade regardless of project state.
        contract = self.get_cubo_projection_contract()
        face_specs = contract["faces"]
        self._validate_cube_projection_params(
            contract, face, granularidade, categoria, componente_bdi, abc_threshold_a, abc_threshold_b
        )
        resolved_measure_profile, resolved_aggregation_mode = self._resolve_measure_and_aggregation(
            contract, face_specs, face, measure_profile, aggregation_mode
        )

        canonical, resolved_version, cubo = self._load_canonical_and_cubo(project_id, version)
        if canonical is None:
            return {
                "version": resolved_version,
                "face": face,
                "granularidade": granularidade,
                "rows": [],
                "filtros_aplicados": {},
            }

        return self._build_cube_projection_result(
            canonical,
            cubo,
            face,
            granularidade,
            categoria,
            componente_bdi,
            atividade_id,
            top_n,
            abc_threshold_a,
            abc_threshold_b,
            resolved_version,
            resolved_measure_profile,
            resolved_aggregation_mode,
        )

