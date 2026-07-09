"""ADR-129 — integração de _resolve_preco_diesel_catalogo à skill de precificação real.

Cobre a lacuna que deixava o ADR "Parcialmente Implementado": os componentes de
D1-D5 existiam e eram testados isoladamente, mas nenhum fluxo real de
orçamentação chamava `geo_diesel_resolver`. Este teste garante que:

  - Sem `raio_cotacao_km` em inputs, o comportamento é idêntico ao anterior à
    ADR-129 (regressão zero — nenhuma chamada de rede automática).
  - `inputs["preco_diesel"]` explícito sempre vence, com ou sem raio_cotacao_km.
  - Com `raio_cotacao_km` presente (opt-in), a resolução regional (proximidade
    -> UF -> FuelPriceClient) é usada.
  - Override de catálogo (MA-DIESEL-S10/DIESEL-S10) continua vencendo por último,
    como já acontecia antes desta integração.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from concilium.domain.constants import PRECO_DIESEL_REFERENCIA


def _load_skill_module():
    """Carrega o skill.py de _precificacao via o loader de produção (dashes no
    caminho exigem contexto de pacote para os imports relativos resolverem)."""
    from concilium.application.skills import load_skill_stage

    load_skill_stage("06-resultado-financeiro", "_precificacao", "run_precificacao_unitaria")
    return sys.modules["_concilium_stagepkg_06_resultado_financeiro_precificacao.skill"]


class TestResolvePrecoDieselRegressaoZero:
    def test_sem_raio_cotacao_km_usa_constante(self):
        mod = _load_skill_module()
        assert mod._resolve_preco_diesel_catalogo({}, {}) == PRECO_DIESEL_REFERENCIA

    def test_preco_diesel_explicito_vence_mesmo_sem_raio(self):
        mod = _load_skill_module()
        assert mod._resolve_preco_diesel_catalogo({"preco_diesel": 8.0}, {}) == 8.0

    def test_preco_diesel_explicito_vence_mesmo_com_raio(self):
        """Override explícito sempre vence — ativar raio_cotacao_km não deve
        sobrepor um preco_diesel informado deliberadamente pelo chamador."""
        mod = _load_skill_module()
        with patch("concilium.infrastructure.clients.fuel.FuelPriceClient") as mock_fuel:
            preco = mod._resolve_preco_diesel_catalogo(
                {"preco_diesel": 8.0, "raio_cotacao_km": 100.0}, {}
            )
        assert preco == 8.0
        mock_fuel.assert_not_called()

    def test_catalogo_vence_sobre_regional(self):
        mod = _load_skill_module()
        catalogo = {"insumos": [{"codigo": "MA-DIESEL-S10", "preco_unitario": 5.55}]}
        assert mod._resolve_preco_diesel_catalogo({}, catalogo) == 5.55


class TestResolvePrecoDieselRegionalOptIn:
    def test_raio_cotacao_km_ativa_resolucao_regional(self):
        mod = _load_skill_module()
        fake_municipio_client = MagicMock()
        fake_fuel_client = MagicMock()

        with (
            patch(
                "concilium.infrastructure.clients.municipios.MunicipioReferenceClient",
                return_value=fake_municipio_client,
            ),
            patch(
                "concilium.infrastructure.clients.fuel.FuelPriceClient",
                return_value=fake_fuel_client,
            ),
            patch(
                "concilium.application.services.catalog.geo_diesel_resolver.resolver_preco_diesel",
                return_value=(7.10, "fuel_api"),
            ) as mock_resolver,
        ):
            preco = mod._resolve_preco_diesel_catalogo(
                {
                    "raio_cotacao_km": 50.0,
                    "coordenadas_lat": -3.7172,
                    "coordenadas_lng": -38.5433,
                    "jurisdicao_id": "BR-CE",
                },
                {},
            )

        assert preco == 7.10
        mock_resolver.assert_called_once()
        _, kwargs = mock_resolver.call_args
        assert kwargs["raio_cotacao_km"] == 50.0
        assert kwargs["jurisdicao_id"] == "BR-CE"

    def test_falha_na_resolucao_regional_nao_propaga_e_cai_para_uf_resolver_real(self):
        """Sem mockar resolver_preco_diesel: usa o resolver real, que por sua vez
        cai para PRECO_DIESEL_REFERENCIA se o FuelPriceClient real falhar (rede
        indisponível em CI) — nunca deve lançar exceção para o pipeline."""
        mod = _load_skill_module()
        preco = mod._resolve_preco_diesel_catalogo(
            {"raio_cotacao_km": 50.0, "coordenadas_lat": 0.0, "coordenadas_lng": 0.0},
            {},
        )
        # coordenadas (0,0) é o placeholder — geo_diesel_resolver trata como "sem
        # localização real" e cai para jurisdicao_id (ausente aqui) -> constante.
        assert preco == PRECO_DIESEL_REFERENCIA
