"""Testes para Escopo.logistica_consumiveis (ADR-128 F5).

Campo opcional que dá ao motor de estoque de consumíveis (ADR-128/139) uma fonte
real de capacidade logística de projeto/escopo — ausente (`None`) preserva o
comportamento anterior (nenhum ReplenishableResource construído a partir de dado
de projeto).
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from concilium.domain.models.project.escopo import Escopo, LogisticaConsumivelConfig


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


class TestLogisticaConsumiveis:
    def test_default_e_none(self):
        escopo = Escopo(**_escopo_kwargs())
        assert escopo.logistica_consumiveis is None

    def test_aceita_override_por_insumo(self):
        escopo = Escopo(
            **_escopo_kwargs(
                logistica_consumiveis={
                    "MA-DIESEL-S10": LogisticaConsumivelConfig(
                        capacidade_armazenamento=15000.0,
                        estoque_inicial=5000.0,
                        taxa_reabastecimento_max=3000.0,
                    )
                }
            )
        )
        assert escopo.logistica_consumiveis["MA-DIESEL-S10"].capacidade_armazenamento == 15000.0
        assert escopo.logistica_consumiveis["MA-DIESEL-S10"].estoque_inicial == 5000.0

    def test_aceita_dict_cru_via_model_validate(self):
        """MCP/persistência entregam dict cru (JSON), não LogisticaConsumivelConfig
        já instanciado — Escopo deve validar/converter automaticamente."""
        escopo = Escopo.model_validate(
            {
                **_escopo_kwargs(),
                "logistica_consumiveis": {"MA-DIESEL-S10": {"estoque_inicial": 100.0}},
            }
        )
        assert isinstance(escopo.logistica_consumiveis["MA-DIESEL-S10"], LogisticaConsumivelConfig)
        assert escopo.logistica_consumiveis["MA-DIESEL-S10"].estoque_inicial == 100.0

    def test_aceita_multiplos_insumos(self):
        escopo = Escopo(
            **_escopo_kwargs(
                logistica_consumiveis={
                    "MA-DIESEL-S10": LogisticaConsumivelConfig(estoque_inicial=100.0),
                    "MA-BRITA-19": LogisticaConsumivelConfig(estoque_inicial=200.0),
                }
            )
        )
        assert set(escopo.logistica_consumiveis) == {"MA-DIESEL-S10", "MA-BRITA-19"}

    def test_rejeita_estoque_inicial_negativo(self):
        with pytest.raises(ValidationError):
            LogisticaConsumivelConfig(estoque_inicial=-1.0)

    def test_rejeita_capacidade_armazenamento_negativa(self):
        with pytest.raises(ValidationError):
            LogisticaConsumivelConfig(capacidade_armazenamento=-1.0)

    def test_campos_desconhecidos_sao_ignorados(self):
        """model_config extra='ignore' — tolera campos extras de payloads futuros."""
        cfg = LogisticaConsumivelConfig.model_validate({"estoque_inicial": 10.0, "campo_futuro": "x"})
        assert cfg.estoque_inicial == 10.0
