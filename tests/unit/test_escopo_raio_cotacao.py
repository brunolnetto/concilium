"""Testes para Escopo.raio_cotacao_km (ADR-129 D5).

Campo opcional que ativa a camada de resolução de preço por proximidade
geográfica (ADR-129 D2) quando preenchido. Ausente (`None`) preserva o
comportamento por UF (default do sistema).
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from concilium.domain.models.project.escopo import Escopo


def _escopo_kwargs(**overrides) -> dict:
    base = dict(
        escopo_id="lote-a",
        projeto_id="proj-1",
        nome="Lote A",
        tipo_obra="terraplenagem",
        localizacao="Fortaleza-CE",
        coordenadas_lat=-3.7172,
        coordenadas_lng=-38.5433,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
    )
    base.update(overrides)
    return base


class TestRaioCotacaoKm:
    def test_default_e_none(self):
        escopo = Escopo(**_escopo_kwargs())
        assert escopo.raio_cotacao_km is None

    def test_aceita_override_por_projeto(self):
        escopo = Escopo(**_escopo_kwargs(raio_cotacao_km=50.0))
        assert escopo.raio_cotacao_km == 50.0

    def test_rejeita_raio_negativo(self):
        with pytest.raises(ValidationError):
            Escopo(**_escopo_kwargs(raio_cotacao_km=-10.0))

    def test_aceita_raio_grande_para_obra_remota(self):
        escopo = Escopo(**_escopo_kwargs(raio_cotacao_km=500.0))
        assert escopo.raio_cotacao_km == 500.0
