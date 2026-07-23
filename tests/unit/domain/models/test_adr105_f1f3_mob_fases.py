"""ADR-105 F1-F3 — Estrutura de fases mob/operação/demob em EquipeDireta.

TDD: testes escritos antes da implementação dos campos de fase no modelo.

Invariantes:
  - EquipeDireta tem custo_mobilizacao_mensal, custo_operacao_mensal, custo_desmobilizacao_mensal
  - Todos default = 0.0 (retrocompatibilidade total)
  - Quando preenchidos: custo_mobilizacao_mensal + custo_desmobilizacao_mensal ≈ custo_mob_desmob
  - custo_operacao_mensal captura custos recorrentes de canteiro (independente de mob/demob)
  - Campos são opcionais: custo_mob_desmob permanece como campo consolidado (não removido)
"""

from __future__ import annotations

import pytest


class TestEquipeDiretaMobFasesCampos:
    """Novos campos de fase existem com defaults corretos."""

    def test_campos_existem_em_equipe_direta(self):
        from concilium.domain.models.canonical import EquipeDireta

        eq = EquipeDireta(item_id="test", custo_total=0.0)
        assert hasattr(eq, "custo_mobilizacao_mensal")
        assert hasattr(eq, "custo_operacao_mensal")
        assert hasattr(eq, "custo_desmobilizacao_mensal")

    def test_defaults_sao_zero(self):
        from concilium.domain.models.canonical import EquipeDireta

        eq = EquipeDireta(item_id="test", custo_total=0.0)
        assert eq.custo_mobilizacao_mensal == pytest.approx(0.0)
        assert eq.custo_operacao_mensal == pytest.approx(0.0)
        assert eq.custo_desmobilizacao_mensal == pytest.approx(0.0)

    def test_custo_mob_desmob_original_preservado(self):
        from concilium.domain.models.canonical import EquipeDireta

        eq = EquipeDireta(item_id="test", custo_total=50_000.0, custo_mob_desmob=5_000.0)
        assert eq.custo_mob_desmob == pytest.approx(5_000.0)

    def test_campos_aceitam_valores_positivos(self):
        from concilium.domain.models.canonical import EquipeDireta

        eq = EquipeDireta(
            item_id="test",
            custo_total=100_000.0,
            custo_mob_desmob=8_000.0,
            custo_mobilizacao_mensal=3_000.0,
            custo_operacao_mensal=50_000.0,
            custo_desmobilizacao_mensal=5_000.0,
        )
        assert eq.custo_mobilizacao_mensal == pytest.approx(3_000.0)
        assert eq.custo_operacao_mensal == pytest.approx(50_000.0)
        assert eq.custo_desmobilizacao_mensal == pytest.approx(5_000.0)


class TestInvarianteFases:
    """Quando preenchidos, mob + demob ≈ custo_mob_desmob (operação é separado)."""

    def test_mob_mais_demob_aproxima_custo_mob_desmob(self):
        from concilium.domain.models.canonical import EquipeDireta

        mob = 3_000.0
        demob = 5_000.0
        eq = EquipeDireta(
            item_id="i1",
            custo_total=100_000.0,
            custo_mob_desmob=mob + demob,
            custo_mobilizacao_mensal=mob,
            custo_desmobilizacao_mensal=demob,
        )
        soma = eq.custo_mobilizacao_mensal + eq.custo_desmobilizacao_mensal
        assert abs(soma - eq.custo_mob_desmob) < 0.01

    def test_operacao_independente_do_mob_desmob(self):
        from concilium.domain.models.canonical import EquipeDireta

        eq = EquipeDireta(
            item_id="i1",
            custo_total=200_000.0,
            custo_mob_desmob=8_000.0,
            custo_mobilizacao_mensal=3_000.0,
            custo_operacao_mensal=180_000.0,
            custo_desmobilizacao_mensal=5_000.0,
        )
        # operacao NÃO integra custo_mob_desmob — é custo recorrente de canteiro
        assert eq.custo_operacao_mensal == pytest.approx(180_000.0)
        assert abs(eq.custo_mobilizacao_mensal + eq.custo_desmobilizacao_mensal - eq.custo_mob_desmob) < 0.01


class TestRetrocompatibilidade:
    """Código existente que não usa os novos campos não é afetado."""

    def test_modelo_existente_sem_campos_novos_funciona(self):
        from concilium.domain.models.canonical import EquipeDireta

        eq = EquipeDireta(
            item_id="i1",
            custo_total=50_000.0,
            custo_mao_obra_mensal=20_000.0,
            custo_equipamentos_mensal=15_000.0,
            custo_mob_desmob=5_000.0,
        )
        # Campos novos ficam em zero — sem erro, sem regressão
        assert eq.custo_mobilizacao_mensal == pytest.approx(0.0)
        assert eq.custo_desmobilizacao_mensal == pytest.approx(0.0)
        assert eq.custo_operacao_mensal == pytest.approx(0.0)
        # Campo original preservado
        assert eq.custo_mob_desmob == pytest.approx(5_000.0)

    def test_serialization_roundtrip(self):
        from concilium.domain.models.canonical import EquipeDireta

        eq = EquipeDireta(
            item_id="i1",
            custo_total=100_000.0,
            custo_mob_desmob=8_000.0,
            custo_mobilizacao_mensal=3_000.0,
            custo_operacao_mensal=75_000.0,
            custo_desmobilizacao_mensal=5_000.0,
        )
        data = eq.model_dump()
        eq2 = EquipeDireta.model_validate(data)
        assert eq2.custo_mobilizacao_mensal == pytest.approx(eq.custo_mobilizacao_mensal)
        assert eq2.custo_operacao_mensal == pytest.approx(eq.custo_operacao_mensal)
        assert eq2.custo_desmobilizacao_mensal == pytest.approx(eq.custo_desmobilizacao_mensal)
