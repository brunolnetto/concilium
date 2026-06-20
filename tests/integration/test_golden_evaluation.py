"""ADR-114: Golden Example de Avaliação — invariantes algébricos e regressão.

Dois tipos de verificação:
  1. Invariantes algébricos — sempre verificáveis a partir do referencia.json
     (não dependem de rodar o pipeline)
  2. Invariantes de regressão — verificam que o pipeline produz os valores esperados
     (requerem execução do pipeline; marcados como 'slow' até calibração completa)

Para calibrar os valores de regressão:
  pytest tests/integration/test_golden_evaluation.py::TestGoldenRegression --run-golden
  → roda o pipeline e imprime os valores para atualizar este arquivo
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_GOLDEN_REF = Path(__file__).parents[2] / "benchmarks/data/GOLDEN/referencia.json"
_ABS_TOL = 0.0001  # 0.01% — invariantes algébricos
_REG_TOL = 0.005   # 0.5%  — invariantes de regressão


@pytest.fixture(scope="module")
def golden_ref() -> dict:
    """Carrega o referencia.json do benchmark GOLDEN."""
    return json.loads(_GOLDEN_REF.read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# Tipo 1: Invariantes algébricos (não precisam do pipeline)
# Falha = bug de fórmula ou dados inconsistentes no referencia.json
# ─────────────────────────────────────────────────────────────────────────────

class TestAlgebraicInvariants:
    """Verifica Q×PU=subtotal e consistência do referencia.json sem rodar o pipeline."""

    def test_golden_ref_file_exists(self):
        assert _GOLDEN_REF.exists(), f"Golden reference não encontrada: {_GOLDEN_REF}"

    def test_golden_ref_is_valid_json(self, golden_ref):
        assert isinstance(golden_ref, dict)
        assert "planejamento" in golden_ref
        assert "eap" in golden_ref

    def test_pu_x_q_equals_subtotal_sem_bdi_for_each_item(self, golden_ref):
        """Q × PU.total = subtotal_sem_bdi para cada item (invariante fundamental)."""
        for item in golden_ref.get("planejamento", []):
            item_id = item["item_id"]
            q = float(item["quantitativo"])
            pu_total = float(item["preco_unitario"]["total"])
            subtotal = float(item["subtotal"]["sem_bdi"]["total"])
            expected = round(q * pu_total, 2)
            desvio = abs(expected - subtotal) / max(abs(subtotal), 1.0)
            assert desvio <= _ABS_TOL, (
                f"{item_id}: Q={q} × PU={pu_total} = {expected} ≠ subtotal_sem_bdi={subtotal} "
                f"(desvio={desvio:.4%})"
            )

    def test_pu_components_sum_to_total(self, golden_ref):
        """PU.material + PU.diesel + PU.mao_obra + PU.equipamentos = PU.total."""
        for item in golden_ref.get("planejamento", []):
            item_id = item["item_id"]
            pu = item["preco_unitario"]
            components = pu.get("material", 0) + pu.get("diesel", 0) + pu.get("mao_obra", 0) + pu.get("equipamentos", 0)
            total = float(pu["total"])
            assert abs(components - total) <= _ABS_TOL * max(total, 1), (
                f"{item_id}: Σ componentes PU = {components} ≠ PU.total = {total}"
            )

    def test_eap_and_planejamento_item_ids_match(self, golden_ref):
        """Cada item_id na EAP deve ter entrada correspondente no planejamento."""
        eap_ids = {e["item_id"] for e in golden_ref.get("eap", [])}
        planj_ids = {p["item_id"] for p in golden_ref.get("planejamento", [])}
        missing = eap_ids - planj_ids
        assert not missing, f"Itens da EAP sem planejamento: {missing}"

    def test_quantitativos_consistent_between_eap_and_planejamento(self, golden_ref):
        """Quantitativo da EAP deve ser igual ao do planejamento para cada item."""
        eap_q = {e["item_id"]: e["quantitativo"] for e in golden_ref.get("eap", [])}
        for p in golden_ref.get("planejamento", []):
            assert p["quantitativo"] == eap_q[p["item_id"]], (
                f"{p['item_id']}: Q_eap={eap_q[p['item_id']]} ≠ Q_planej={p['quantitativo']}"
            )

    def test_sum_subtotal_sem_bdi_is_reasonable(self, golden_ref):
        """Soma dos subtotais sem BDI deve ser > 0 e < 10 bilhões."""
        total = sum(float(p["subtotal"]["sem_bdi"]["total"]) for p in golden_ref.get("planejamento", []))
        assert total > 0, "Soma subtotais_sem_bdi deve ser > 0"
        assert total < 10_000_000_000, "Soma subtotais_sem_bdi parece excessiva"


# ─────────────────────────────────────────────────────────────────────────────
# Tipo 2: Invariantes de regressão (requerem execução do pipeline)
# Falha = mudança arquitetural; atualizar golden com commit 'golden(update): razão'
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def golden_benchmark(config_root):
    """Executa o pipeline GOLDEN e retorna o canonical + report.

    Usa reset=True para garantir execução fresca (não usa cache).
    Fixture session-scoped para evitar múltiplas execuções.
    """
    from concilium.application.benchmarks.execution.facade import BenchmarkFacade
    from concilium.application.skills.phase_classifier import PipelineMode

    root = config_root.parent
    facade = BenchmarkFacade.from_root(root)
    facade.run_single("GOLDEN", reset=True, mode=PipelineMode.OLTP)

    from concilium.infrastructure.storage.project import ProjectStore
    agis_store_root = facade.projects_root / "GOLDEN"
    if not agis_store_root.exists():
        pytest.skip("GOLDEN benchmark não foi executado — rodar manualmente com --run-golden")

    store = ProjectStore(root=agis_store_root)
    canonical = store.load_canonical()
    return canonical


class TestGoldenRegression:
    """Verifica que o pipeline GOLDEN produz valores esperados (ADR-114 D3)."""

    @pytest.mark.slow
    def test_golden_pipeline_completes_without_errors(self, golden_benchmark):
        """Pipeline GOLDEN completa sem erros críticos."""
        assert golden_benchmark is not None

    @pytest.mark.slow
    def test_custo_direto_instancial_leq_custo_catalogo(self, golden_benchmark):
        """Invariante ADR-085: custo_instancial ≤ custo_catálogo (Q×PU)."""
        ref = json.loads(_GOLDEN_REF.read_text(encoding="utf-8"))
        custo_catalogo = sum(
            float(p["subtotal"]["sem_bdi"]["total"]) for p in ref.get("planejamento", [])
        )
        custo_instancial = sum(
            eq.custo_total for eq in golden_benchmark.equipes_diretas
        )
        assert custo_instancial <= custo_catalogo * (1 + _ABS_TOL), (
            f"Invariante ADR-085 violada: custo_instancial={custo_instancial:,.2f} > "
            f"custo_catalogo={custo_catalogo:,.2f}"
        )

    @pytest.mark.slow
    def test_margem_pct_above_minimum(self, golden_benchmark):
        """Invariante ADR-060: margem_pct ≥ MARGEM_MINIMA (5%)."""
        from concilium.domain.constants import MARGEM_MINIMA
        resultado = getattr(golden_benchmark, "resultado", None)
        if resultado is None:
            pytest.skip("Canonical sem resultado — pipeline OLAP necessário")
        margem = getattr(resultado, "margem_pct", None) or getattr(resultado, "margem_bruta", None)
        if margem is None:
            pytest.skip("Margem não calculada neste modo de pipeline")
        assert margem >= MARGEM_MINIMA, (
            f"Margem {margem:.2%} abaixo do mínimo {MARGEM_MINIMA:.2%} (ADR-060)"
        )

    @pytest.mark.slow
    def test_all_three_eap_items_scheduled(self, golden_benchmark):
        """Todos os 3 itens da EAP devem ter distribuição semanal."""
        scheduled_ids = {sa.activity_id for sa in (golden_benchmark.cronograma.scheduled_activities or [])}
        expected = {"eap-01", "eap-02", "eap-03"}
        missing = expected - scheduled_ids
        assert not missing, f"Itens sem agendamento: {missing}"

    @pytest.mark.slow
    def test_makespan_in_expected_range(self, golden_benchmark):
        """Makespan deve estar entre 4 e 20 semanas para o GOLDEN."""
        makespan = golden_benchmark.cronograma.makespan_weeks
        assert 4 <= makespan <= 20, (
            f"Makespan {makespan} fora do intervalo esperado [4, 20] semanas. "
            "Verifique as produtividades dos CPUs."
        )

    @pytest.mark.slow
    def test_margem_formula_uses_operational_price(self, golden_benchmark):
        """ADR-114 D2 / ADR-085: margem = (total_custo_plus - custo.total) / total_custo_plus.

        Usa o PREÇO OPERACIONAL (total_custo_plus), NÃO total_com_bdi (catálogo).
        """
        r = getattr(golden_benchmark, "resultado", None)
        if r is None:
            pytest.skip("Canonical sem resultado — pipeline OLAP necessário")
        venda_plus = getattr(r.venda, "total_custo_plus", None)
        custo_total = r.custo.total
        if not venda_plus:
            pytest.skip("total_custo_plus ausente")
        margem_calc = (venda_plus - custo_total) / venda_plus
        assert abs(margem_calc - r.margem_pct) <= _ABS_TOL, (
            f"Fórmula de margem divergente: (venda_plus={venda_plus:,.2f} - custo={custo_total:,.2f})"
            f"/venda_plus = {margem_calc:.4f} ≠ margem_pct={r.margem_pct:.4f}"
        )

    @pytest.mark.slow
    def test_regression_against_calibrated_values(self, golden_benchmark):
        """Regressão: valores do pipeline batem com resultado calibrado no referencia.json (tol 0.5%)."""
        ref = json.loads(_GOLDEN_REF.read_text(encoding="utf-8"))
        expected = ref.get("resultado", {})
        if not expected.get("$calibrado"):
            pytest.skip("GOLDEN ainda não calibrado")
        r = getattr(golden_benchmark, "resultado", None)
        if r is None:
            pytest.skip("Canonical sem resultado — pipeline OLAP necessário")

        checks = [
            ("custo.direto_equipes", r.custo.direto_equipes, expected["custo"]["direto_equipes"]),
            ("custo.total", r.custo.total, expected["custo"]["total"]),
            ("venda.total_com_bdi", r.venda.total_com_bdi, expected["venda"]["total_com_bdi"]),
            ("margem_pct", r.margem_pct, expected["margem_pct"]),
        ]
        for nome, atual, esperado in checks:
            if esperado in (None, 0):
                continue
            desvio = abs(atual - esperado) / abs(esperado)
            assert desvio <= _REG_TOL, (
                f"Regressão em {nome}: atual={atual:,.4f} vs calibrado={esperado:,.4f} "
                f"(desvio={desvio:.2%} > {_REG_TOL:.1%}). Se intencional, recalibrar com "
                f"commit 'golden(update): <razão>'."
            )


# ─────────────────────────────────────────────────────────────────────────────
# Tipo 3: Invariantes matemáticos da saída (pós-pipeline)
# Verificam consistência interna do canonical — não dependem de valores absolutos
# ─────────────────────────────────────────────────────────────────────────────

class TestCanonicalMathInvariants:
    """Verifica invariantes matemáticos internos do canonical GOLDEN."""

    @pytest.mark.slow
    def test_sum_equipes_custo_total_is_positive(self, golden_benchmark):
        """Soma dos custo_total das equipes diretas deve ser > 0."""
        total = sum(eq.custo_total for eq in golden_benchmark.equipes_diretas)
        assert total > 0, "Custo total das equipes deve ser > 0"

    @pytest.mark.slow
    def test_no_negative_costs_in_equipes(self, golden_benchmark):
        """Nenhuma equipe deve ter custo_total negativo."""
        for eq in golden_benchmark.equipes_diretas:
            assert eq.custo_total >= 0, f"{eq.equip_id if hasattr(eq, 'equip_id') else eq}: custo negativo"

    @pytest.mark.slow
    def test_distribuicao_semanal_sums_to_one_per_item(self, golden_benchmark):
        """Distribuição semanal de cada atividade deve somar ~1.0 (100%)."""
        for eq in golden_benchmark.equipes_diretas:
            distrib = getattr(eq, "distribuicao_semanal", None) or {}
            if distrib:
                total = sum(distrib.values())
                assert abs(total - 1.0) <= 0.01, (
                    f"Distribuição semanal de {getattr(eq, 'item_id', '?')} soma {total:.4f} ≠ 1.0"
                )
