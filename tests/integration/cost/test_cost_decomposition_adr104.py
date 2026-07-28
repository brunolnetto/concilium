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

    def test_cost_decomposition_closes_with_pool_contracts(self, agis_benchmark):
        """Valida que custo_total == soma(custo_inst_*) após ADR-085."""
        canonical = agis_benchmark.canonical

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

    def test_projection_breakdown_sums_correctly(self, agis_benchmark):
        """Valida que breakdown em report (MO+EQ+COMB+MAT) == total."""
        from concilium.application.benchmarks.report.projection import BenchmarkProjection

        projection = BenchmarkProjection.from_canonical(agis_benchmark.canonical)
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

    def test_agis_custo_direto_matches_reference(self, agis_benchmark):
        """AGIS: custo_direto instancial (pós TD-1/TD-3 + NEP-043 Bug 2 + ADR-162 D4) deve bater com baseline.

        Histórico de baseline:
          pré-TD-1/TD-3:     R$ 44,259,799.68  — encargos duplos + pool sem n_frentes
          pós-TD-1/TD-3:     R$ 35,255,483.25  — TD-1/TD-3 corrigidos, ainda com encargos duplos
          pós-NEP-043 Bug 2: R$ 16,529,359.75  — encargos CLT não reaplicados sobre taxa all-in
          pós-ADR-162 D4:    R$ 17,611,540.46  — permanência/custo de 1 frente corrigidos p/ rampa

        NEP-043 Bug 2 (2026-06-12): insumos AGIS têm nota_encargos="taxa horária já inclui
        encargos". O engine não deve multiplicar por (1 + enc_horista) uma taxa que já embute
        esses encargos. Correto: custo_fixo_mensal usa preco_unitario × horas_mes diretamente,
        sem replicação do fator CLT. Isso reduz custo_total em ~53% vs o baseline anterior.

        ADR-162 D4 (2026-07-28): `_resolve_permanencia_e_custo_total_ajustados` dividia o
        agregado multi-frente (`team_weeks`/`custo_total`) por um único `num_equipes_paralelas`
        constante — exato só quando o número de frentes é constante em todas as semanas ativas.
        Com rampa (ex: eap-1_6 no AGIS: team_weeks=72, ativos=25, max_n=4 → 72/4=18 semanas
        estimadas vs. 25 semanas reais, ~28% de subestimação), a divisão por um único N
        subestima a permanência/custo de referência. Corrigido via soma semana a semana
        (`_sum_1frente_cost`, robusta a qualquer forma de rampa) — aumenta o agregado em ~6,55%
        (o ajuste antigo só podia subestimar, nunca sobrestimar: `team_weeks/max_n <= ativos`
        sempre, pela definição de `max_n`).

        sum(eq.custo_total) aqui é a soma dos custos de 1-frente por atividade.
        custo.direto_equipes = Σ(custo_total × n_frentes) é o custo real completo (~43.8M).
        """
        canonical = agis_benchmark.canonical

        custo_direto_agregado = sum(eq.custo_total for eq in canonical.equipes_diretas)

        # Baseline instancial pós-TD-1/TD-3 + NEP-043 Bug 2 + ADR-162 D4 (encargos all-in, 1-frente)
        expected = 17_611_540.46
        desvio_pct = abs(custo_direto_agregado - expected) / expected * 100

        assert desvio_pct < 0.5, (
            f"AGIS custo_direto={custo_direto_agregado:,.2f}, esperado={expected:,.2f}, desvio={desvio_pct:.2f}%"
        )

    def test_enrich_copies_decomposition_from_particao(self, agis_benchmark):
        """Items em contratos têm decomposição copiada de particao_por_item."""
        canonical = agis_benchmark.canonical

        # Coletar todos os items que deveriam ter decomposição
        items_esperados = set()
        for contrato in canonical.contratos_recurso:
            for part in contrato.particao_por_item:
                items_esperados.add(part.item_id)

        # Verificar que cada item em contratos tem decomposição
        items_encontrados = set()
        for eq in canonical.equipes_diretas:
            if eq.item_id in items_esperados:
                assert eq.custo_inst_mo is not None, f"Item {eq.item_id}: custo_inst_mo é None, esperava decomposição"
                assert eq.custo_inst_eq is not None, f"Item {eq.item_id}: custo_inst_eq é None"
                items_encontrados.add(eq.item_id)

        # Todos os items esperados devem ter sido encontrados
        assert items_encontrados == items_esperados, (
            f"Items faltando decomposição: {items_esperados - items_encontrados}"
        )


class TestADR104Checkpoints:
    """Testa os 3 checkpoints de validação em skill.py."""

    def test_stage1_checkpoint_none_values(self, agis_benchmark):
        """Checkpoint 1: Após Estágio 1, custo_inst_* deve ser None."""
        # Este teste é implícito: se o benchmark rodou sem erro VAL-ESTAG1-INST-NONE,
        # significa que o checkpoint passou.
        canonical = agis_benchmark.canonical

        # Verificar que não há erros de Estágio 1
        for validacao in getattr(canonical, "validacoes", []):
            if validacao.codigo == "VAL-ESTAG1-INST-NONE":
                pytest.fail(f"Checkpoint 1 falhou: {validacao.mensagem}")

    def test_stage4_checkpoint_filled_values(self, agis_benchmark):
        """Checkpoint 3: Após Estágio 4, custo_inst_* deve estar preenchido para items em contratos."""
        canonical = agis_benchmark.canonical

        # Verificar que não há erros de Estágio 4
        for validacao in getattr(canonical, "validacoes", []):
            if validacao.codigo == "VAL-ESTAG4-INST-MISSING":
                pytest.fail(f"Checkpoint 3 falhou: {validacao.mensagem}")

    def test_decomposition_invariant_validation(self, agis_benchmark):
        """Teste de Invariante: desvio deve estar dentro de tolerância."""
        canonical = agis_benchmark.canonical

        # Verificar que não há erros de invariante
        for validacao in getattr(canonical, "validacoes", []):
            if validacao.codigo == "VAL-DECOMP-INVARIANTE":
                pytest.fail(f"Invariante violada: {validacao.mensagem}")
