"""Testes do mecanismo de arbitragem temporal do Repositório de Insumos."""

from datetime import date

import pytest

from concilium.infrastructure.repositories.insumo import RepositorioInsumo


@pytest.fixture
def catalogo_misto():
    """Catálogo contendo insumos versionados e insumos legados (flat)."""
    return {
        "insumos": [
            {
                "codigo": "CIMENTO-CP-II",
                "tipo": "MATERIAL",
                "descricao": "Cimento CP-II (Flat Legado)",
                "unidade": "kg",
                "preco_unitario": 0.85,  # Preço flat fallback
            },
            {
                "id": "DIESEL-S10",
                "codigo": "DIESEL-S10",  # ID legado
                "tipo": "MATERIAL",
                "descricao": "Diesel S10 (Versionado)",
                "unidade": "litro",
                "versoes": [
                    {
                        "versao": "2026-03",
                        "validade": {"inicio": "2026-03-01", "fim": "2026-04-01"},
                        "preco_unitario": 5.90,
                        "fonte_preco": "tabela_referencia",
                        "auditado_por": "sistema",
                        "auditado_em": "2026-03-01T00:00:00Z",
                    },
                    {
                        "versao": "2026-04",
                        "validade": {"inicio": "2026-04-01", "fim": None},
                        "preco_unitario": 6.20,
                        "fonte_preco": "cotacao_mercado",
                        "auditado_por": "sistema",
                        "auditado_em": "2026-04-01T00:00:00Z",
                    },
                ],
            },
        ]
    }


class TestArbitragemTemporalRepositorioInsumo:
    def test_obtem_preco_versionado_na_data_correta(self, catalogo_misto):
        repo = RepositorioInsumo(catalogo_misto)

        # Preço em Março
        preco_mar = repo.preco_na_data("DIESEL-S10", date(2026, 3, 15))
        assert preco_mar == 5.90

        # Preço em Abril
        preco_abr = repo.preco_na_data("DIESEL-S10", date(2026, 4, 15))
        assert preco_abr == 6.20

    def test_fallback_para_preco_flat_se_nao_versionado(self, catalogo_misto):
        repo = RepositorioInsumo(catalogo_misto)

        # Mesmo passando data, ele devolve o preco_unitario base
        preco_flat = repo.preco_na_data("CIMENTO-CP-II", date(2026, 3, 15))
        assert preco_flat == 0.85

    def test_retorna_none_se_fora_da_vigencia(self, catalogo_misto):
        repo = RepositorioInsumo(catalogo_misto)

        # Antes da primeira versão (Mar/2026)
        preco_antigo = repo.preco_na_data("DIESEL-S10", date(2025, 1, 1))
        assert preco_antigo is None

    def test_retorna_none_se_insumo_nao_existe(self, catalogo_misto):
        repo = RepositorioInsumo(catalogo_misto)
        assert repo.preco_na_data("NAO-EXISTE", date.today()) is None
