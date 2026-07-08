"""ADR-128 D4 — `tanque_sugerido` (UI) lê `DisponibilidadeConsumivel` com fallback heurístico.

Escrito antes da implementação (red phase).
"""

from __future__ import annotations

from concilium.domain.models.catalog.disponibilidade_consumivel import DisponibilidadeConsumivel
from concilium.presentation.ui.organisms.layout._cube_analytics import calcular_tanque_sugerido


class TestCalcularTanqueSugerido:
    def test_fallback_heuristic_when_no_disponibilidade(self):
        """Sem DisponibilidadeConsumivel, mantém a heurística atual: pico × 1.5 × 2."""
        assert calcular_tanque_sugerido(pico_l=100.0, disponibilidade=None) == 300.0

    def test_fallback_heuristic_when_capacidade_not_set(self):
        disp = DisponibilidadeConsumivel(estoque_inicial=10.0)
        assert calcular_tanque_sugerido(pico_l=100.0, disponibilidade=disp) == 300.0

    def test_uses_capacidade_armazenamento_when_present(self):
        disp = DisponibilidadeConsumivel(capacidade_armazenamento=5000.0, estoque_inicial=1000.0)
        assert calcular_tanque_sugerido(pico_l=100.0, disponibilidade=disp) == 5000.0
