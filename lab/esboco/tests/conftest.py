"""Fixtures pytest para testes do Concilium."""

import json
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from concilium.clients.openmeteo import DadosClimaticosMensais, OpenMeteoClient
from concilium.runtime import Runtime
from concilium.storage.project import ProjectStore


@pytest.fixture
def config_root() -> Path:
    """Path do diretório de configuração com dados seed."""
    return Path(__file__).parent.parent / "config"


@pytest.fixture
def projetos_root(tmp_path: Path) -> Path:
    """Diretório isolado de projetos para cada teste."""
    p = tmp_path / "projetos"
    p.mkdir()
    return p


@pytest.fixture
def runtime(config_root: Path) -> Runtime:
    return Runtime(config_root)


@pytest.fixture
def projeto_terraplenagem(projetos_root: Path) -> ProjectStore:
    """Projeto novo para o cenário de terraplenagem."""
    return ProjectStore.init(
        projetos_root, "terraplenagem-aracoiaba-test", "agis", "BR"
    )


@pytest.fixture
def mock_openmeteo_aracoiaba() -> OpenMeteoClient:
    """Cliente Open-Meteo mockado retornando padrão climático realista do Nordeste.

    Reproduz a estrutura de DadosClimaticosMensais.dias_precipitacao_mensal
    com valores plausíveis para Aracoiaba/CE (semiárido com chuvas concentradas
    em jan-abr).
    """
    # Dias de chuva por mês × threshold (mm)
    # Padrão: muita chuva jan-abr, seca jul-out, chuvas leves nov-dez
    dias_por_mes_e_threshold = {
        "01": {"5mm": 12, "10mm": 8, "20mm": 3},
        "02": {"5mm": 14, "10mm": 10, "20mm": 4},
        "03": {"5mm": 13, "10mm": 9, "20mm": 3},
        "04": {"5mm": 9,  "10mm": 5, "20mm": 2},
        "05": {"5mm": 5,  "10mm": 2, "20mm": 0},
        "06": {"5mm": 2,  "10mm": 1, "20mm": 0},
        "07": {"5mm": 1,  "10mm": 0, "20mm": 0},
        "08": {"5mm": 1,  "10mm": 0, "20mm": 0},
        "09": {"5mm": 2,  "10mm": 1, "20mm": 0},
        "10": {"5mm": 4,  "10mm": 2, "20mm": 0},
        "11": {"5mm": 7,  "10mm": 4, "20mm": 1},
        "12": {"5mm": 10, "10mm": 6, "20mm": 2},
    }

    client = MagicMock(spec=OpenMeteoClient)
    client.fetch_dados_anuais.return_value = DadosClimaticosMensais(
        latitude=-4.3622,
        longitude=-38.7392,
        ano_referencia=2024,
        fonte="open-meteo",
        dias_precipitacao_mensal=dias_por_mes_e_threshold,
    )
    return client


@pytest.fixture
def inputs_escopo_terraplenagem() -> dict[str, Any]:
    """Inputs para skill 00 com 3 itens da EAP de terraplenagem."""
    return {
        "nome": "Terraplenagem Aracoiaba — teste",
        "tipo_obra": "terraplenagem",
        "localizacao": "Aracoiaba, CE",
        "coordenadas": {"lat": -4.3622, "lng": -38.7392},
        "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
        "data_inicio": "2026-06-01",
        "data_termino": "2026-12-31",
        "versao_referencia_id": "SICRO_2024_CE",
        "eap": [
            {
                "item_id": "eap-01",
                "ordem": 1,
                "cpu_id": "ESCO-CARGA-1CAT-DMT2000",
                "descricao": "Escavação 1ª categoria",
                "unidade": "m3",
                "quantitativo": 80000,
                "origem_template": True,
            },
            {
                "item_id": "eap-02",
                "ordem": 2,
                "cpu_id": "COMPACT-ATERRO",
                "descricao": "Compactação de aterro",
                "unidade": "m3",
                "quantitativo": 75000,
                "origem_template": True,
            },
            {
                "item_id": "eap-03",
                "ordem": 3,
                "cpu_id": "REGULARIZACAO-SUBLEITO",
                "descricao": "Regularização de subleito",
                "unidade": "m2",
                "quantitativo": 28000,
                "origem_template": False,
            },
        ],
    }


@pytest.fixture
def amostra_terraplenagem_path() -> Path:
    """Path da amostra de terraplenagem produzida na sessão anterior."""
    p = Path("/home/claude/concilium-samples/01-terraplenagem-feliz.json")
    return p
