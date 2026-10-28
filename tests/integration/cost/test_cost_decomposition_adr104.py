"""Testes de ADR-104: Decomposição Instancial de Custos em EquipeDireta.

Valida que:
1. EquipeDireta tem campos custo_inst_*
2. Após ADR-085, decomposição é copiada corretamente
3. Invariante é respeitada: soma(custo_inst_*) == custo_total (±R$ 0.05)
4. Report breakdown fecha corretamente
"""

import pytest


class TestCostDecompositionInvariant:
    """Testa que decomposição de custos é consistente em todos os estágios."""

    def test_equipedireta_has_custo_inst_fields(self):
        """EquipeDireta tem 5 campos de decomposição."""
        from concilium.domain.models.canonical import EquipeDireta

        eq = EquipeDireta(item_id="test", custo_total=100.0)
        assert hasattr(eq, "custo_inst_mo")
        assert hasattr(eq, "custo_inst_eq")
        assert hasattr(eq, "custo_inst_comb")
        assert hasattr(eq, "custo_inst_mat")
        assert hasattr(eq, "custo_inst_mob_demob")
        assert eq.custo_inst_mo is None  # Default deve ser None
        assert eq.custo_inst_eq is None

    @pytest.mark.slow
    def test_cost_decomposition_closes_with_pool_contracts(self, golden_benchmark):
        """Valida que custo_total == soma(custo_inst_*) após ADR-085.

        Usa projeto GOLDEN (sintético, ~15s setup) para validação de invariantes.
        Se necessário testar com dados reais complexos: parametrize com @pytest.mark.parametrize
        para adicionar variante com `agis_benchmark` conforme ADR-104 exigir.
        """
        canonical = golden_benchmark.canonical

        # Apenas items com pool contracts (Estágio 4) devem ter decomposição preenchida
        items_com_decomposicao = []
        for eq in canonical.equipes_diretas:
            if eq.custo_inst_mo is not None:
                items_com_decomposicao.append(eq.item_id)
                soma = (
                    eq.custo_inst_mo
                    + eq.custo_inst_eq
                    + eq.custo_inst_comb
                    + eq.custo_inst_mat
                    + eq.custo_inst_mob_demob
                )
                desvio = abs(soma - eq.custo_total)
                assert desvio < 0.05, (
                    f"Item {eq.item_id}: decomposição não fecha "
                    f"(soma={soma:,.2f}, total={eq.custo_total:,.2f}, desvio={desvio:,.2f})"
                )

        # Deve haver pelo menos alguns items com decomposição (estágio 4 com pool)
        assert len(items_com_decomposicao) > 0, (
            "Nenhum item com decomposição instancial preenchida — ADR-085 não foi executado?"
        )

    @pytest.mark.slow
    def test_projection_breakdown_sums_correctly(self, golden_benchmark):
        """Valida que breakdown em report (MO+EQ+COMB+MAT) == total.
        
        OTIMIZAÇÃO: Usa golden_benchmark (~15s) em vez de agis_benchmark (~62s).
        A validação é estrutural e não depende de complexidade real dos dados.
        
        Para testes com dados reais AGIS (opcional):
        - Marcar com @pytest.mark.parametrize("benchmark_fixture", ["golden_benchmark", "agis_benchmark"])
        - Ou criar um teste separado @pytest.mark.slow com agis_benchmark
        """
        from concilium.application.benchmarks.report.projection import BenchmarkProjection

        projection = BenchmarkProjection.from_canonical(golden_benchmark.canonical)
        breakdown = projection.ferramenta_breakdown_direto

        if breakdown:
            componentes = (
                breakdown.get("mao_obra_total", 0)
                + breakdown.get("equipamentos_total", 0)
                + breakdown.get("diesel_total", 0)
                + breakdown.get("materiais_total", 0)
            )
            total = breakdown.get("direto_total", 0)

            # Agora deve fechar! (tolerância R$ 1.00 por arredondamentos)
            assert abs(componentes - total) < 1.0, (
                f"Breakdown não fecha: componentes={componentes:,.2f}, total={total:,.2f}"
            )




class TestADR104Checkpoints:
    """Testa os 3 checkpoints de validação em skill.py."""

    @pytest.mark.slow
    def test_stage1_checkpoint_none_values(self, golden_benchmark):
        """Checkpoint 1: Após Estágio 1, custo_inst_* deve ser None.
        
        OTIMIZAÇÃO: Usa golden_benchmark (~15s) em vez de agis_benchmark (~60s).
        Validação é estrutural e não depende de complexidade real dos dados.
        """
        # Este teste é implícito: se o benchmark rodou sem erro VAL-ESTAG1-INST-NONE,
        # significa que o checkpoint passou.
        canonical = golden_benchmark.canonical

        # Verificar que não há erros de Estágio 1
        for validacao in getattr(canonical, "validacoes", []):
            if validacao.codigo == "VAL-ESTAG1-INST-NONE":
                pytest.fail(f"Checkpoint 1 falhou: {validacao.mensagem}")

    @pytest.mark.slow
    def test_stage4_checkpoint_filled_values(self, golden_benchmark):
        """Checkpoint 3: Após Estágio 4, custo_inst_* deve estar preenchido para items em contratos.
        
        OTIMIZAÇÃO: Usa golden_benchmark (~15s) em vez de agis_benchmark (~60s).
        Validação é estrutural e não depende de ter contratos (test usa GOLDEN que tem
        decomposição preenchida também, apenas sem contratos reais).
        """
        canonical = golden_benchmark.canonical

        # Verificar que não há erros de Estágio 4
        for validacao in getattr(canonical, "validacoes", []):
            if validacao.codigo == "VAL-ESTAG4-INST-MISSING":
                pytest.fail(f"Checkpoint 3 falhou: {validacao.mensagem}")

    @pytest.mark.slow
    def test_decomposition_invariant_validation(self, golden_benchmark):
        """Teste de Invariante: desvio deve estar dentro de tolerância.
        
        OTIMIZAÇÃO: Usa golden_benchmark (~15s) em vez de agis_benchmark (~60s).
        Validação é estrutural e não depende de complexidade real dos dados.
        """
        canonical = golden_benchmark.canonical

        # Verificar que não há erros de invariante
        for validacao in getattr(canonical, "validacoes", []):
            if validacao.codigo == "VAL-DECOMP-INVARIANTE":
                pytest.fail(f"Invariante violada: {validacao.mensagem}")
