"""Scenario Engine runner: gera variações de cenário, executa via Runtime, coleta resultados e métricas.

Conceitos:
    ScenarioResult   — resultado canônico + métricas resumidas
    ScenarioRunner   — orquestra execução sequencial de N cenários via Runtime

Uso programático:
    runner = ScenarioRunner(runtime, project)
    results = runner.run_variations(base_inputs, n=5)
    matrix = runner.compare(results)

CLI:
    concilium scenario run --project p --variations 5
    concilium scenario compare --project p
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from concilium.application.runtime import Runtime
from concilium.domain.models.canonical import CanonicalModel
from concilium.domain.models.decision_variables import DecisionVariables
from concilium.infrastructure.storage.project import ProjectStore

from .config import ScenarioConfig
from .runner_dv import generate_dv_variations, run_dv_scenario
from .runner_utils import apply_custo_delta, apply_duracao_delta, apply_equipe_delta, extract_metricas

PIPELINE_SKILLS = [
    "01-escopo-e-eap",
    "02-produtividade-climatica",
    "03-catalogo-de-recursos",
    "04-cronograma",
    "05-equipes-e-alocacao",
    "06-resultado-financeiro",  # NEP-041 F4: unifica 06+07+08
]

# Pipeline de análise executado após consolidação — opcional, não varia cenários
# NEP-041 F3: 11-avaliacao-intervencoes congelada (dormante) — fora do pipeline automático
ANALYSIS_SKILLS = [
    "09-relatorio-e-artefatos",
    "10-diagnostico-criticidade",
]


@dataclass
class ScenarioResult:
    config: ScenarioConfig
    canonical: CanonicalModel | None
    versao: str
    status: str  # "OK" | "ERRO"
    erro: str | None = None
    metricas: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        """Linha da matriz de comparação."""
        return {
            "cenario_id": self.config.id,
            "nome": self.config.nome,
            "custo_delta": f"{(self.config.custo_delta - 1) * 100:+.0f}%",
            "duracao_delta": f"{(self.config.duracao_delta - 1) * 100:+.0f}%",
            "equipe_delta": f"{(self.config.equipe_delta - 1) * 100:+.0f}%",
            "status": self.status,
            **self.metricas,
        }


def _filter_ok_results(results: list) -> list:
    ok = []
    for r in results:
        if r.status == "OK" and r.metricas:
            ok.append(r)
    return ok


def _count_results_by_status(results: list) -> tuple:
    total_ok = 0
    total_err = 0
    for r in results:
        if r.status == "OK":
            total_ok += 1
        elif r.status == "ERRO":
            total_err += 1
    return total_ok, total_err


def _enrich_ok_summary(summary: dict, ok_results: list) -> None:
    custos = [r.metricas["custo_total"] for r in ok_results if "custo_total" in r.metricas]
    margens = [r.metricas["margem_pct"] for r in ok_results if "margem_pct" in r.metricas]
    if custos:
        summary["custo_min"] = min(custos)
        summary["custo_max"] = max(custos)
        summary["custo_spread_pct"] = round((max(custos) - min(custos)) / min(custos) * 100, 1)
    if margens:
        summary["margem_min"] = min(margens)
        summary["margem_max"] = max(margens)
        best = max(ok_results, key=lambda r: r.metricas.get("margem_pct", -999))
        summary["melhor_cenario"] = best.config.nome
        summary["melhor_cenario_descricao"] = best.config.descricao


def _build_compare_summary(results: list, ok_results: list) -> dict:
    total_ok, total_err = _count_results_by_status(results)
    summary = {
        "total_cenarios": len(results),
        "ok": total_ok,
        "com_erro": total_err,
        "gerado_em": datetime.now(UTC).isoformat(),
    }
    if ok_results:
        _enrich_ok_summary(summary, ok_results)
    return summary


class ScenarioRunner:
    """Executa múltiplos cenários de variação e coleta métricas."""

    def __init__(self, runtime: Runtime, project: ProjectStore) -> None:
        self.runtime = runtime
        self.project = project

    def generate_variations(
        self,
        n: int,
        custo_range: tuple[float, float] = (-0.10, 0.10),
        duracao_range: tuple[float, float] = (-0.05, 0.05),
        equipe_range: tuple[float, float] = (-0.20, 0.20),
    ) -> list[ScenarioConfig]:
        """Gera N cenários interpolando linearmente nos 3 eixos."""
        if n < 1:
            raise ValueError("n deve ser >= 1")
        if n == 1:
            return [ScenarioConfig(nome="base", descricao="Cenário base sem variação")]

        configs: list[ScenarioConfig] = []

        configs.append(
            ScenarioConfig(
                nome="base",
                custo_delta=1.0,
                duracao_delta=1.0,
                equipe_delta=1.0,
                descricao="Cenário base sem variação",
            )
        )

        steps = n - 1
        for i in range(1, steps + 1):
            t = i / steps
            c_min, c_max = 1.0 + custo_range[0], 1.0 + custo_range[1]
            d_min, d_max = 1.0 + duracao_range[0], 1.0 + duracao_range[1]
            _e_min, e_max = 1.0 + equipe_range[0], 1.0 + equipe_range[1]

            if i % 2 == 1:
                c = c_min + t * (1.0 - c_min)
                d = d_min + t * (1.0 - d_min)
                e = 1.0
                prefixo = "otimista"
            else:
                c = 1.0 + t * (c_max - 1.0)
                d = 1.0 + t * (d_max - 1.0)
                e = 1.0 + t * (e_max - 1.0)
                prefixo = "pessimista"

            configs.append(
                ScenarioConfig(
                    nome=f"{prefixo}_{i}",
                    custo_delta=round(c, 3),
                    duracao_delta=round(d, 3),
                    equipe_delta=round(e, 3),
                    descricao=(
                        f"Custo {(c - 1) * 100:+.0f}%, Duração {(d - 1) * 100:+.0f}%, Equipe {(e - 1) * 100:+.0f}%"
                    ),
                )
            )

        return configs[:n]

    def run_scenario(
        self,
        config: ScenarioConfig,
        base_inputs: dict[str, dict[str, Any]],
        skills: list[str] | None = None,
    ) -> ScenarioResult:
        """Executa um único cenário: cria versão, roda pipeline, extrai métricas."""
        pipeline = skills or PIPELINE_SKILLS

        try:
            versao = self.project.new_version()
            for skill_id in pipeline:
                raw_inputs = copy.deepcopy(base_inputs.get(skill_id, {}))

                if config.custo_delta != 1.0:
                    raw_inputs = apply_custo_delta(raw_inputs, config.custo_delta)
                if config.duracao_delta != 1.0:
                    raw_inputs = apply_duracao_delta(raw_inputs, config.duracao_delta)
                if config.equipe_delta != 1.0:
                    raw_inputs = apply_equipe_delta(raw_inputs, config.equipe_delta)

                raw_inputs.update(config.inputs_override.get(skill_id, {}))

                result = self.runtime.run_skill(skill_id, self.project, version=versao, inputs=raw_inputs)
                if result.has_errors:
                    canonical = self.project.load_canonical(versao)
                    return ScenarioResult(
                        config=config,
                        canonical=canonical,
                        versao=versao,
                        status="ERRO",
                        erro=f"Skill {skill_id} falhou: {[v.mensagem for v in result.validacoes if v.status == 'ERRO']}",  # noqa: E501
                        metricas=extract_metricas(canonical),
                    )

            canonical = self.project.load_canonical(versao)
            return ScenarioResult(
                config=config,
                canonical=canonical,
                versao=versao,
                status="OK",
                metricas=extract_metricas(canonical),
            )

        except Exception as e:
            return ScenarioResult(
                config=config,
                canonical=None,
                versao="",
                status="ERRO",
                erro=str(e),
            )

    def run_variations(
        self,
        base_inputs: dict[str, dict[str, Any]],
        n: int = 5,
        skills: list[str] | None = None,
        custo_range: tuple[float, float] = (-0.10, 0.10),
        duracao_range: tuple[float, float] = (-0.05, 0.05),
        equipe_range: tuple[float, float] = (-0.20, 0.20),
    ) -> list[ScenarioResult]:
        """Gera e executa N cenários de variação."""
        configs = self.generate_variations(n, custo_range, duracao_range, equipe_range)
        results: list[ScenarioResult] = []
        for config in configs:
            result = self.run_scenario(config, base_inputs, skills)
            results.append(result)
        return results

    def run_dv_variations(
        self,
        canonical_in: CanonicalModel,
        base_decisions: DecisionVariables | None = None,
        dv2_options: list[dict[str, dict[str, int]]] | None = None,
        dv4_options: list[str] | None = None,
        catalogo: dict[str, Any] | None = None,
        perfil: dict[str, Any] | None = None,
    ) -> list[ScenarioResult]:
        """Gera e executa cenários restritos ao espaço DV1-DV4 (DEC-29)."""
        configs = self.generate_dv_variations(base_decisions, dv2_options, dv4_options)
        return [
            ScenarioResult(
                config=cfg,
                canonical=r.canonical,
                versao="",
                status=r.status,
                erro=r.erro,
                metricas=extract_metricas(r.canonical),
            )
            for cfg in configs
            for r in [run_dv_scenario(cfg, canonical_in, catalogo, perfil)]
        ]

    def generate_dv_variations(
        self,
        base_decisions: DecisionVariables | None = None,
        dv2_options: list[dict[str, dict[str, int]]] | None = None,
        dv4_options: list[str] | None = None,
    ) -> list[ScenarioConfig]:
        """Wrapper para generate_dv_variations from runner_dv module."""
        return generate_dv_variations(base_decisions, dv2_options, dv4_options)

    def run_dv_scenario(
        self,
        config: ScenarioConfig,
        canonical_in: CanonicalModel,
        catalogo: dict[str, Any] | None = None,
        perfil: dict[str, Any] | None = None,
        extra_inputs: dict[str, Any] | None = None,
    ) -> ScenarioResult:
        """Wrapper para run_dv_scenario from runner_dv module."""
        r = run_dv_scenario(config, canonical_in, catalogo, perfil, extra_inputs)
        return ScenarioResult(
            config=r.config,
            canonical=r.canonical,
            versao="",
            status=r.status,
            erro=r.erro,
            metricas=extract_metricas(r.canonical),
        )

    def compare(self, results: list[ScenarioResult]) -> dict[str, Any]:
        """Gera matriz de comparação como dict serializável."""
        rows = [r.to_row() for r in results]
        ok_results = _filter_ok_results(results)
        summary = _build_compare_summary(results, ok_results)
        return {"resumo": summary, "cenarios": rows}

    def save_comparison(self, results: list[ScenarioResult], path: Path) -> Path:
        """Persiste matriz de comparação em JSON."""
        matrix = self.compare(results)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(matrix, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
