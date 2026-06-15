from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BenchmarkInferenceTraceEntry:
    field: str
    source_path: str
    rule_id: str
    fallback_applied: bool = False


@dataclass
class BenchmarkInferencePack:
    benchmark_mode: bool
    benchmark_inference_policy_version: str = "v2"
    skill_inputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    reference_projection: dict[str, Any] | None = None
    trace: list[BenchmarkInferenceTraceEntry] = field(default_factory=list)


class BenchmarkInferenceService:
    @staticmethod
    def derive(reference: dict[str, Any] | None) -> BenchmarkInferencePack:
        # NEP-030: injeção mínima honesta.
        # benchmark_mode=True injetado APENAS no skill-09 (relatório de comparação).
        # Skill-09: ativa confronto com referência e suprime seções de produção pura.
        # Skill-08 (consolidação financeira): executa em modo de produção normal —
        #   usa bdi_rates.get("indireto") do perfil, como em produção. Injetar
        #   benchmark_mode aqui era circular e causava divergências no consolidado.
        # Skill-06: executa em modo de produção normal — sem fork de comportamento.
        # bdi_indireto_efetivo NÃO é mais injetado (era circular: garantia que o resultado
        # fechasse com a referência independente da qualidade do algoritmo).
        pack = BenchmarkInferencePack(
            benchmark_mode=True,
            skill_inputs={
                "09-relatorio-e-artefatos": {"benchmark_mode": True},
            },
            reference_projection=None,
            trace=[
                BenchmarkInferenceTraceEntry(
                    field="benchmark_mode",
                    source_path="policy.default — NEP-030: skill-09 only",
                    rule_id="INF-BENCH-001",
                )
            ],
        )

        if reference is not None and not isinstance(reference, dict):
            return pack

        # NEP-030 D2: _derive_bdi_indireto_efetivo removida da cadeia de injeção.
        # Era um resíduo circular: (venda_ref - Σ com_bdi) / custo_indir - 1.
        # Skill-08 agora usa bdi_rates.get("indireto") do perfil, como em produção.
        pack.trace.append(
            BenchmarkInferenceTraceEntry(
                field="bdi_indireto_efetivo",
                source_path="NEP-030: removed — skill-08 uses profile rate",
                rule_id="INF-BENCH-030-D2",
            )
        )

        if reference is None:
            return pack

        ref_proj, ref_trace = BenchmarkInferenceService._extract_reference_projection(reference)
        pack.reference_projection = ref_proj
        pack.trace.extend(ref_trace)
        if isinstance(ref_proj, dict):
            # reference_projection: apenas para comparação final em skill-09.
            # Nenhum campo é usado em cálculos de skills 06/08.
            pack.skill_inputs.setdefault("09-relatorio-e-artefatos", {})["benchmark_reference_projection"] = ref_proj

        return pack

    @staticmethod
    def apply_to_skill_inputs(
        skill_inputs: dict[str, dict[str, Any]],
        pack: BenchmarkInferencePack,
    ) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = deepcopy(skill_inputs)
        for skill_id, additions in (pack.skill_inputs or {}).items():
            cur = out.get(skill_id)
            if not isinstance(cur, dict):
                cur = {}
            cur.update(additions)
            out[skill_id] = cur
        return out

    @staticmethod
    def _extract_reference_projection(
        ref: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, list[BenchmarkInferenceTraceEntry]]:
        trace: list[BenchmarkInferenceTraceEntry] = []
        resultado = ref.get("resultado") if isinstance(ref.get("resultado"), dict) else {}

        direto_itemizado = BenchmarkInferenceService._sum_planejamento_subtotal(ref, "sem_bdi")
        if isinstance(direto_itemizado, (int, float)):
            trace.append(
                BenchmarkInferenceTraceEntry(
                    field="reference_projection.custo_direto",
                    source_path="planejamento_detalhado[].subtotal.sem_bdi.total",
                    rule_id="INF-BENCH-101",
                )
            )

        confronto_ref = (
            resultado.get("benchmark_confronto_referencia")
            if isinstance(resultado.get("benchmark_confronto_referencia"), dict)
            else None
        )
        if isinstance(confronto_ref, dict):
            out = {
                "custo_direto": confronto_ref.get("custo_direto"),
                "custo_indireto": confronto_ref.get("custo_indireto"),
                "custo_total": confronto_ref.get("custo_total"),
                "preco_venda": confronto_ref.get("preco_venda"),
            }
            trace.append(
                BenchmarkInferenceTraceEntry(
                    field="reference_projection",
                    source_path="resultado.benchmark_confronto_referencia",
                    rule_id="INF-BENCH-102",
                )
            )
            if isinstance(direto_itemizado, (int, float)):
                out["custo_direto"] = direto_itemizado
                if isinstance(out.get("custo_indireto"), (int, float)):
                    out["custo_total"] = round(float(direto_itemizado) + float(out["custo_indireto"]), 2)
            return out, trace

        canonical = resultado.get("canonical") if isinstance(resultado.get("canonical"), dict) else {}
        if isinstance(canonical, dict) and canonical:
            custo = canonical.get("custo") if isinstance(canonical.get("custo"), dict) else {}
            venda = canonical.get("venda") if isinstance(canonical.get("venda"), dict) else {}
            custo_indireto = BenchmarkInferenceService._sum_indireto(custo)
            out = {
                "custo_direto": custo.get("direto_equipes"),
                "custo_indireto": custo_indireto if custo_indireto != 0 else None,
                "custo_total": custo.get("total"),
                "preco_venda": venda.get("total_com_bdi") or venda.get("total_custo_plus"),
            }
            trace.append(
                BenchmarkInferenceTraceEntry(
                    field="reference_projection",
                    source_path="resultado.canonical",
                    rule_id="INF-BENCH-103",
                    fallback_applied=True,
                )
            )
            if isinstance(direto_itemizado, (int, float)):
                out["custo_direto"] = direto_itemizado
                if isinstance(out.get("custo_indireto"), (int, float)):
                    out["custo_total"] = round(float(direto_itemizado) + float(out["custo_indireto"]), 2)
            return out, trace

        return None, trace

    @staticmethod
    def _derive_bdi_indireto_efetivo(
        ref: dict[str, Any],
    ) -> tuple[float | None, list[BenchmarkInferenceTraceEntry]]:
        trace: list[BenchmarkInferenceTraceEntry] = []
        resultado = ref.get("resultado") if isinstance(ref.get("resultado"), dict) else {}
        confronto = (
            resultado.get("benchmark_confronto_referencia")
            if isinstance(resultado.get("benchmark_confronto_referencia"), dict)
            else {}
        )
        preco_ref = confronto.get("preco_venda") if isinstance(confronto.get("preco_venda"), (int, float)) else None
        if preco_ref is None and isinstance(resultado.get("preco_venda_total"), (int, float)):
            preco_ref = float(resultado.get("preco_venda_total"))

        indireto_ref = (
            confronto.get("custo_indireto") if isinstance(confronto.get("custo_indireto"), (int, float)) else None
        )
        if indireto_ref is None and isinstance(resultado.get("custo_indireto_total"), (int, float)):
            indireto_ref = float(resultado.get("custo_indireto_total"))

        direto_com_bdi = BenchmarkInferenceService._sum_planejamento_subtotal(ref, "com_bdi")

        if not isinstance(preco_ref, (int, float)):
            return None, trace
        if not isinstance(indireto_ref, (int, float)) or float(indireto_ref) <= 0:
            return None, trace
        if not isinstance(direto_com_bdi, (int, float)):
            return None, trace
        if float(preco_ref) <= float(direto_com_bdi):
            return None, trace

        value = round((float(preco_ref) - float(direto_com_bdi)) / float(indireto_ref) - 1.0, 8)
        trace.append(
            BenchmarkInferenceTraceEntry(
                field="skill_inputs.06-resultado-financeiro.bdi_indireto_efetivo",
                source_path="(preco_venda_ref - sum(planejamento.com_bdi))/custo_indireto_ref - 1",
                rule_id="INF-BENCH-201",
            )
        )
        return value, trace

    @staticmethod
    def _sum_planejamento_subtotal(ref: dict[str, Any], mode: str) -> float | None:
        itens = ref.get("planejamento_detalhado") if isinstance(ref.get("planejamento_detalhado"), list) else None
        if not isinstance(itens, list) or not itens:
            planejamento = ref.get("planejamento") if isinstance(ref.get("planejamento"), dict) else {}
            itens = planejamento.get("itens") if isinstance(planejamento.get("itens"), list) else None
        if not isinstance(itens, list) or not itens:
            return None

        total = 0.0
        found_any = False
        for item in itens:
            if not isinstance(item, dict):
                continue
            subtotal = item.get("subtotal")
            if not isinstance(subtotal, dict):
                continue
            branch = subtotal.get(mode)
            if not isinstance(branch, dict):
                continue
            val = branch.get("total")
            if isinstance(val, (int, float)):
                total += float(val)
                found_any = True
        if not found_any:
            return None
        return round(total, 2)

    @staticmethod
    def _sum_indireto(custo: dict[str, Any]) -> float:
        total = 0.0
        for key, value in custo.items():
            if isinstance(value, (int, float)) and str(key).startswith("indireto_"):
                total += float(value)
        return round(total, 2)
