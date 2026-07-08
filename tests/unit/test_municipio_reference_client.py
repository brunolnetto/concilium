"""Testes para MunicipioReferenceClient (ADR-129 D1/D2/D4).

Cobre: leitura do dataset de referência, cache em memória, resolução do
município mais próximo dentro de um raio, e desempate por população quando
municípios estão a distância comparável.
"""

from __future__ import annotations

import json
import re

import pytest

from concilium.infrastructure.clients.municipios import (
    MunicipioReferenceClient,
    MunicipioReferencia,
    haversine_km,
)


@pytest.fixture
def dataset_path(tmp_path):
    """Dataset sintético e determinístico para os testes (não usa o bundle real)."""
    data = {
        "municipios": [
            {
                "codigo_ibge": "2304400",
                "nome": "Fortaleza",
                "uf": "CE",
                "latitude": -3.7172,
                "longitude": -38.5433,
                "populacao": 2686612,
            },
            {
                "codigo_ibge": "2303709",
                "nome": "Eusebio",
                "uf": "CE",
                "latitude": -3.8907,
                "longitude": -38.4509,
                "populacao": 55000,
            },
            {
                "codigo_ibge": "3550308",
                "nome": "Sao Paulo",
                "uf": "SP",
                "latitude": -23.5505,
                "longitude": -46.6333,
                "populacao": 12300000,
            },
        ]
    }
    path = tmp_path / "municipios_referencia.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestHaversine:
    def test_distancia_zero_para_mesmo_ponto(self):
        assert haversine_km(-3.7172, -38.5433, -3.7172, -38.5433) == pytest.approx(0.0, abs=1e-6)

    def test_distancia_conhecida_fortaleza_sao_paulo(self):
        # Distância real Fortaleza-São Paulo é ~2380km (linha reta / grande círculo)
        d = haversine_km(-3.7172, -38.5433, -23.5505, -46.6333)
        assert 2200 < d < 2500


class TestMunicipioReferenceClient:
    def test_listar_por_uf_retorna_apenas_municipios_da_uf(self, dataset_path):
        client = MunicipioReferenceClient(dataset_path=dataset_path)
        municipios = client.listar_por_uf("CE")
        assert {m.nome for m in municipios} == {"Fortaleza", "Eusebio"}

    def test_listar_por_uf_normaliza_case(self, dataset_path):
        client = MunicipioReferenceClient(dataset_path=dataset_path)
        assert len(client.listar_por_uf("ce")) == 2

    def test_listar_por_uf_desconhecida_retorna_lista_vazia(self, dataset_path):
        client = MunicipioReferenceClient(dataset_path=dataset_path)
        assert client.listar_por_uf("XX") == []

    def test_cache_evita_releitura_do_arquivo(self, dataset_path, monkeypatch):
        client = MunicipioReferenceClient(dataset_path=dataset_path)
        client.listar_por_uf("CE")

        chamadas = {"count": 0}
        original_read_text = type(dataset_path).read_text

        def _read_text_espiao(self, *args, **kwargs):
            chamadas["count"] += 1
            return original_read_text(self, *args, **kwargs)

        monkeypatch.setattr(type(dataset_path), "read_text", _read_text_espiao)
        client.listar_por_uf("SP")  # segunda chamada — não deve reler o arquivo
        assert chamadas["count"] == 0

    def test_municipio_mais_proximo_retorna_o_mais_perto(self, dataset_path):
        client = MunicipioReferenceClient(dataset_path=dataset_path)
        # Ponto bem perto de Eusebio
        resultado = client.municipio_mais_proximo(-3.89, -38.45, raio_km=100)
        assert resultado is not None
        assert resultado.nome == "Eusebio"

    def test_municipio_mais_proximo_fora_do_raio_retorna_none(self, dataset_path):
        client = MunicipioReferenceClient(dataset_path=dataset_path)
        # Ponto no Ceará, mas raio muito curto para alcançar qualquer município do dataset
        resultado = client.municipio_mais_proximo(-3.9, -38.6, raio_km=1)
        assert resultado is None

    def test_municipio_mais_proximo_sem_raio_ignora_limite(self, dataset_path):
        client = MunicipioReferenceClient(dataset_path=dataset_path)
        resultado = client.municipio_mais_proximo(-3.9, -38.6, raio_km=None)
        assert resultado is not None
        assert resultado.nome == "Eusebio"

    def test_desempate_por_populacao_quando_equidistante(self, tmp_path):
        """ADR-129 D4: dois municípios à mesma distância — vence o mais populoso."""
        data = {
            "municipios": [
                {
                    "codigo_ibge": "1",
                    "nome": "Vila Pequena",
                    "uf": "CE",
                    "latitude": 0.0,
                    "longitude": 1.0,
                    "populacao": 1000,
                },
                {
                    "codigo_ibge": "2",
                    "nome": "Cidade Grande",
                    "uf": "CE",
                    "latitude": 0.0,
                    "longitude": -1.0,
                    "populacao": 500000,
                },
            ]
        }
        path = tmp_path / "empate.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        client = MunicipioReferenceClient(dataset_path=path)

        # Ponto de referência exatamente entre os dois — mesma distância haversine
        resultado = client.municipio_mais_proximo(0.0, 0.0, raio_km=1000)
        assert resultado is not None
        assert resultado.nome == "Cidade Grande"

    def test_bundled_dataset_carrega_sem_erro(self):
        """O dataset padrão embutido no pacote deve existir e ser válido."""
        client = MunicipioReferenceClient()
        todos = client.listar_por_uf("CE")
        assert len(todos) >= 1

    def test_municipio_referencia_e_imutavel(self):
        from dataclasses import FrozenInstanceError

        m = MunicipioReferencia(
            codigo_ibge="1", nome="X", uf="CE", latitude=0.0, longitude=0.0, populacao=1
        )
        with pytest.raises(FrozenInstanceError):
            m.nome = "Y"  # type: ignore[misc]

    def test_dataset_ausente_levanta_erro_contextualizado(self, tmp_path):
        """Copilot (PR #69): erro deve indicar qual path do dataset falhou."""
        missing = tmp_path / "nao_existe.json"
        client = MunicipioReferenceClient(dataset_path=missing)
        with pytest.raises(FileNotFoundError, match=re.escape(str(missing))):
            client.listar_por_uf("CE")

    def test_dataset_corrompido_levanta_erro_contextualizado(self, tmp_path):
        """Copilot (PR #69): JSON inválido deve indicar qual path do dataset falhou."""
        bad = tmp_path / "corrompido.json"
        bad.write_text("{ isso nao e json valido", encoding="utf-8")
        client = MunicipioReferenceClient(dataset_path=bad)
        with pytest.raises(ValueError, match=re.escape(str(bad))):
            client.listar_por_uf("CE")
