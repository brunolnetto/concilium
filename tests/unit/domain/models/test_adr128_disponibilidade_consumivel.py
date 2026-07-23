"""ADR-128 — Disponibilidade de Recursos Consumíveis: TDD test suite (Fase 1 e 3).

Cobre:
  - `DisponibilidadeConsumivel` (D1): validação de estoque/capacidade.
  - `parse_prazo_entrega` (F3): normalização de texto livre → dias numéricos,
    pré-requisito explícito da ADR para reaproveitar `AtributosInsumo.prazo_entrega`.

Escrito antes da implementação (red phase).
"""

from __future__ import annotations

import pytest

from concilium.domain.models.catalog.disponibilidade_consumivel import (
    DisponibilidadeConsumivel,
    parse_prazo_entrega,
)

# ── DisponibilidadeConsumivel ────────────────────────────────────────────────


class TestDisponibilidadeConsumivelDefaults:
    def test_all_fields_optional_default_is_unrestricted(self):
        """Sem nenhum campo preenchido, o dado representa disponibilidade irrestrita (D1)."""
        disp = DisponibilidadeConsumivel()
        assert disp.capacidade_armazenamento is None
        assert disp.estoque_inicial == 0.0
        assert disp.taxa_reabastecimento_max is None
        assert disp.lead_time_reabastecimento_dias is None

    def test_accepts_fully_populated_values(self):
        disp = DisponibilidadeConsumivel(
            capacidade_armazenamento=1000.0,
            estoque_inicial=500.0,
            taxa_reabastecimento_max=200.0,
            lead_time_reabastecimento_dias=3.0,
        )
        assert disp.capacidade_armazenamento == 1000.0
        assert disp.estoque_inicial == 500.0
        assert disp.taxa_reabastecimento_max == 200.0
        assert disp.lead_time_reabastecimento_dias == 3.0


class TestDisponibilidadeConsumivelValidation:
    def test_negative_capacidade_armazenamento_raises(self):
        with pytest.raises(ValueError, match="capacidade_armazenamento"):
            DisponibilidadeConsumivel(capacidade_armazenamento=-1.0)

    def test_negative_estoque_inicial_raises(self):
        with pytest.raises(ValueError, match="estoque_inicial"):
            DisponibilidadeConsumivel(estoque_inicial=-10.0)

    def test_negative_taxa_reabastecimento_max_raises(self):
        with pytest.raises(ValueError, match="taxa_reabastecimento_max"):
            DisponibilidadeConsumivel(taxa_reabastecimento_max=-5.0)

    def test_negative_lead_time_raises(self):
        with pytest.raises(ValueError, match="lead_time_reabastecimento_dias"):
            DisponibilidadeConsumivel(lead_time_reabastecimento_dias=-1.0)

    def test_estoque_inicial_above_capacidade_raises(self):
        with pytest.raises(ValueError, match="estoque_inicial"):
            DisponibilidadeConsumivel(capacidade_armazenamento=100.0, estoque_inicial=200.0)

    def test_estoque_inicial_equal_capacidade_is_valid(self):
        disp = DisponibilidadeConsumivel(capacidade_armazenamento=100.0, estoque_inicial=100.0)
        assert disp.estoque_inicial == 100.0


# ── parse_prazo_entrega (F3) ──────────────────────────────────────────────────


class TestParsePrazoEntrega:
    def test_none_returns_none(self):
        assert parse_prazo_entrega(None) is None

    def test_empty_string_returns_none(self):
        assert parse_prazo_entrega("") is None
        assert parse_prazo_entrega("   ") is None

    def test_imediato_returns_zero(self):
        assert parse_prazo_entrega("Imediato") == 0.0
        assert parse_prazo_entrega("imediato") == 0.0
        assert parse_prazo_entrega("  Imediato  ") == 0.0

    def test_n_dias_returns_numeric_days(self):
        assert parse_prazo_entrega("15 dias") == 15.0
        assert parse_prazo_entrega("1 dia") == 1.0
        assert parse_prazo_entrega("7dias") == 7.0

    def test_decimal_dias_with_comma(self):
        assert parse_prazo_entrega("2,5 dias") == 2.5

    def test_unrecognized_text_returns_none(self):
        assert parse_prazo_entrega("sob consulta") is None
        assert parse_prazo_entrega("N/A") is None


# ── DisponibilidadeConsumivel.from_prazo_entrega (F3: reaproveitamento sem campo duplicado) ──


class TestDisponibilidadeConsumivelFromPrazoEntrega:
    def test_builds_lead_time_from_prazo_entrega_text(self):
        """`prazo_entrega` (AtributosInsumo, texto livre) alimenta lead_time_reabastecimento_dias
        sem introduzir um campo numérico duplicado no catálogo (ADR-128 §D1)."""
        disp = DisponibilidadeConsumivel.from_prazo_entrega("15 dias")
        assert disp.lead_time_reabastecimento_dias == 15.0

    def test_builds_with_zero_lead_time_for_imediato(self):
        disp = DisponibilidadeConsumivel.from_prazo_entrega("Imediato")
        assert disp.lead_time_reabastecimento_dias == 0.0

    def test_unrecognized_text_yields_none_lead_time(self):
        disp = DisponibilidadeConsumivel.from_prazo_entrega("sob consulta")
        assert disp.lead_time_reabastecimento_dias is None

    def test_forwards_other_fields(self):
        disp = DisponibilidadeConsumivel.from_prazo_entrega(
            "7 dias", capacidade_armazenamento=100.0, estoque_inicial=20.0, taxa_reabastecimento_max=5.0
        )
        assert disp.capacidade_armazenamento == 100.0
        assert disp.estoque_inicial == 20.0
        assert disp.taxa_reabastecimento_max == 5.0
        assert disp.lead_time_reabastecimento_dias == 7.0
