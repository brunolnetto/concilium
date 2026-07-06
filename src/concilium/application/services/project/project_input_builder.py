from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from concilium.application.benchmarks.execution.batch import find_benchmark_reference
from concilium.application.benchmarks.spec.spec_loader import BenchmarkSpecLoader


@dataclass(frozen=True)
class PreparedProjectInputs:
    inputs_escopo: dict[str, Any]
    skill_inputs: dict[str, dict[str, Any]]
    benchmark_slug: str | None
    benchmark_reference: dict[str, Any] | None
    contexto_version: str | None = None  # ADR-062: context version at project creation time
    perfil_id: str | None = None  # ADR-062: resolved profile id
    perfil_version: str | None = None  # ADR-062: profile version at project creation time


class ProjectInputBuilder:
    def __init__(self, config_root: Path, benchmarks_root: Path):
        self._config_root = config_root
        self._benchmarks_root = benchmarks_root

    def prepare(self, req: Any) -> PreparedProjectInputs:
        if req.benchmark_slug or req.referencia_path:
            ref_path: Path | None = None
            slug = req.benchmark_slug.upper() if req.benchmark_slug else None
            if req.referencia_path:
                ref_path = Path(req.referencia_path).resolve()
            else:
                # req.referencia_path é falsy aqui, logo req.benchmark_slug (e portanto
                # slug) é sempre truthy pelo guard `if req.benchmark_slug or req.referencia_path`.
                assert slug is not None
                ref_path = find_benchmark_reference(self._benchmarks_root, slug)
            if ref_path is None or not ref_path.exists():
                raise FileNotFoundError("Referencia de benchmark nao encontrada.")

            benchmark_reference = json.loads(ref_path.read_text(encoding="utf-8"))
            loader = BenchmarkSpecLoader(self._config_root)
            spec = loader.load(ref_path)
            req.contexto_id = spec.contexto_id

            # ADR-062: spec already carries resolved context_version and perfil_version
            return PreparedProjectInputs(
                inputs_escopo=spec.inputs_escopo,
                skill_inputs=self._build_skill_inputs_from_spec(spec),
                benchmark_slug=spec.slug,
                benchmark_reference=benchmark_reference,
                contexto_version=spec.contexto_version,
                perfil_id=spec.perfil_id,
                perfil_version=spec.perfil_version,
            )

        inputs_escopo = {
            "nome": req.nome or "Projeto Prototype",
            "tipo_obra": req.tipo_obra,
            "localizacao": req.localizacao,
            "coordenadas": {"lat": req.coordenadas_lat, "lng": req.coordenadas_lng},
            "regime_trabalho": {"dias_semana": req.dias_semana, "horas_dia": req.horas_dia},
            "data_inicio": req.data_inicio,
            "data_termino": req.data_termino,
            "eap": [item.model_dump() for item in req.eap],
        }
        return PreparedProjectInputs(
            inputs_escopo=inputs_escopo,
            skill_inputs={"01-escopo-e-eap": inputs_escopo},
            benchmark_slug=None,
            benchmark_reference=None,
        )

    @staticmethod
    def _build_skill_inputs_from_spec(spec: Any) -> dict[str, dict[str, Any]]:
        skill_inputs: dict[str, dict[str, Any]] = {}
        if spec.inputs_escopo:
            if "contexto_id" not in spec.inputs_escopo:
                spec.inputs_escopo["contexto_id"] = spec.contexto_id
            skill_inputs["01-escopo-e-eap"] = spec.inputs_escopo
        if spec.inputs_01A:
            skill_inputs["03-catalogo-de-recursos"] = spec.inputs_01A
        if spec.inputs_cronograma:
            skill_inputs["04-cronograma"] = spec.inputs_cronograma
        skill_inputs.update(spec.extra_inputs)
        # NEP-041 F4: mesclar na chave unificada (extra_inputs pode trazer consolidacao_inputs)
        if spec.inputs_indiretos:
            skill_inputs.setdefault("06-resultado-financeiro", {}).update(spec.inputs_indiretos)
        return skill_inputs
