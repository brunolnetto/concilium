#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evals — Layer 1: Base Data Management

Valida:
- Tabelas obrigatórias definidas no skill
- Verificação de colunas críticas
- Sincronização de nomes exatos (MÃO DE OBRA, EQUIPAMENTOS)
- Relatório de saúde dos dados
"""

import pandas as pd
import pytest

from conftest import MOCK_MAO_DE_OBRA, MOCK_EQUIPAMENTOS, MOCK_BDI


# ---------------------------------------------------------------------------
# Casos de avaliação sem dependência de LLM
# ---------------------------------------------------------------------------

class TestTableDefinitions:
    """Verifica que o skill conhece todas as tabelas obrigatórias."""

    REQUIRED_TABLES = [
        "DADOS", "PRODUÇÕES", "PRATICABILIDADE",
        "MÃO DE OBRA", "EQUIPAMENTOS", "BDI",
    ]

    def test_all_required_tables_defined(self, base_skill):
        """Layer 1 deve ter definições para todas as tabelas base."""
        defined = set(base_skill.TABLE_DEFINITIONS.keys())
        for table in self.REQUIRED_TABLES:
            assert table in defined, (
                f"Tabela obrigatória '{table}' ausente em TABLE_DEFINITIONS"
            )

    def test_mao_de_obra_requires_exact_match(self, base_skill):
        """MÃO DE OBRA exige correspondência exata de nomes (sem aproximação)."""
        defn = base_skill.TABLE_DEFINITIONS.get("MÃO DE OBRA", {})
        assert defn.get("exact_match_required") is True, (
            "MÃO DE OBRA deve ter exact_match_required=True para evitar "
            "vínculos errados ao calcular custos de equipe"
        )

    def test_equipamentos_requires_exact_match(self, base_skill):
        """EQUIPAMENTOS também deve exigir correspondência exata."""
        defn = base_skill.TABLE_DEFINITIONS.get("EQUIPAMENTOS", {})
        assert defn.get("exact_match_required") is True


class TestDataValidation:
    """Valida a qualidade dos dados em tabelas mock."""

    def test_mao_de_obra_has_salario_column(self):
        """Tabela MÃO DE OBRA deve conter coluna 'Salário'."""
        assert "Salário" in MOCK_MAO_DE_OBRA.columns

    def test_mao_de_obra_no_null_salaries(self):
        """Todos os salários de MÃO DE OBRA devem ser > 0."""
        assert (MOCK_MAO_DE_OBRA["Salário"] > 0).all(), (
            "Existem funcionários com salário inválido (zero ou nulo)"
        )

    def test_equipamentos_no_null_values(self):
        """Todos os equipamentos devem ter custo mensal definido."""
        assert (MOCK_EQUIPAMENTOS["Valor Mensal"] > 0).all()

    def test_bdi_percentages_within_range(self):
        """BDI deve estar entre 0% e 100%."""
        assert (MOCK_BDI["% BDI"] > 0).all()
        assert (MOCK_BDI["% BDI"] < 100).all()

    def test_praticabilidade_between_zero_and_one(self, base_skill):
        """Fator de produtividade deve estar entre 0 e 1."""
        df = base_skill._cache["PRATICABILIDADE"]
        assert (df["% Produtivo"] >= 0).all()
        assert (df["% Produtivo"] <= 1).all()

    def test_praticabilidade_covers_all_months(self, base_skill):
        """Deve haver fator de produtividade para os 12 meses."""
        df = base_skill._cache["PRATICABILIDADE"]
        assert len(df) == 12, f"Esperado 12 meses, encontrado {len(df)}"


class TestEncargosTable:
    """Valida que a tabela ENCARGOS totaliza 66% (critério crítico)."""

    def test_encargos_total_equals_66_percent(self, base_skill):
        """Soma de encargos: 31% + 30% + 5% = 66%."""
        df = base_skill._cache["ENCARGOS"]
        total = df["% Encargo"].sum()
        assert abs(total - 66.0) < 0.01, (
            f"Total de encargos esperado: 66%, encontrado: {total}%"
        )

    def test_encargos_multiplier_is_1_66(self, base_skill):
        """Multiplicador aplicado ao salário base deve ser 1.66."""
        df = base_skill._cache["ENCARGOS"]
        rate = df["% Encargo"].sum() / 100
        multiplier = 1 + rate
        assert abs(multiplier - 1.66) < 0.01, (
            f"Multiplicador ENCARGOS esperado 1.66, calculado {multiplier:.4f}"
        )


class TestCPUReference:
    """CPU deve existir e ter preços positivos."""

    def test_cpu_has_custo_unitario(self, base_skill):
        """CPU precisa da coluna de custo unitário sem BDI."""
        df = base_skill._cache["CPU"]
        assert "Custo Unit. s/ BDI" in df.columns

    def test_cpu_costs_positive(self, base_skill):
        """Todos os preços unitários da CPU devem ser positivos."""
        df = base_skill._cache["CPU"]
        assert (df["Custo Unit. s/ BDI"] > 0).all()


class TestSyncReferences:
    """Nomes em EQUIPE devem bater exatamente com MÃO DE OBRA e EQUIPAMENTOS."""

    def test_operator_name_exact_match(self, base_skill):
        """Nome 'Operador de Escavadeira' deve estar na tabela MÃO DE OBRA."""
        mao_de_obra = base_skill._cache["MÃO DE OBRA"]
        funcoes = mao_de_obra["Função"].tolist()
        assert "Operador de Escavadeira" in funcoes, (
            "Nome 'Operador de Escavadeira' não encontrado em MÃO DE OBRA. "
            "Verificar sincronização de nomes."
        )

    def test_equipment_name_exact_match(self, base_skill):
        """Nome 'Escavadeira Hidráulica' deve estar em EQUIPAMENTOS."""
        equipamentos = base_skill._cache["EQUIPAMENTOS"]
        nomes = equipamentos["Equipamento"].tolist()
        assert "Escavadeira Hidráulica" in nomes
