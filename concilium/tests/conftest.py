"""Fixtures pytest para testes do Concilium."""

# Ensure the package source dir is on sys.path so tests can import `concilium`
import sys
from pathlib import Path

# Garante asyncio_mode=auto mesmo em versões antigas do pytest-asyncio
import pytest


def pytest_configure(config):
    """Registra markers e configura asyncio se o plugin estiver presente."""
    try:
        import pytest_asyncio  # noqa: F401

        # Força o modo auto via API interna se o ini_option não foi lido
        if not config.option.__dict__.get("asyncio_mode"):
            config.option.asyncio_mode = "auto"
    except (ImportError, AttributeError):
        pass


@pytest.fixture(scope="session", autouse=True)
def _preload_all_cli_groups():
    """Garante que todos os grupos CLI estejam registrados para testes com CliRunner.

    CliRunner invoca `app` diretamente sem passar por `main()`, então o dispatch
    lazy nunca roda. Este fixture carrega todos os grupos uma vez por sessão.
    """
    try:
        from concilium.presentation.main import _load_all

        _load_all()
    except Exception:
        pass  # CLI pode não estar disponível em todos os contextos de teste


project_root = Path(__file__).resolve().parents[1]
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from concilium.infrastructure.clients.openmeteo import DadosClimaticosMensais, OpenMeteoClient

try:
    from concilium.application.runtime import Runtime
except ModuleNotFoundError:
    from concilium.application.runtime import Runtime
from concilium.infrastructure.storage.project import ProjectStore


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
    """Projeto novo para o cenário de terraplenagem.

    Usa contexto "test" (estável para CI, não evolui com mudanças em catalogos de produção).
    Testes são isolados de mudanças futuras em dados reais.
    """
    return ProjectStore.init(projetos_root, "terraplenagem-aracoiaba-test", "test")


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
        "04": {"5mm": 9, "10mm": 5, "20mm": 2},
        "05": {"5mm": 5, "10mm": 2, "20mm": 0},
        "06": {"5mm": 2, "10mm": 1, "20mm": 0},
        "07": {"5mm": 1, "10mm": 0, "20mm": 0},
        "08": {"5mm": 1, "10mm": 0, "20mm": 0},
        "09": {"5mm": 2, "10mm": 1, "20mm": 0},
        "10": {"5mm": 4, "10mm": 2, "20mm": 0},
        "11": {"5mm": 7, "10mm": 4, "20mm": 1},
        "12": {"5mm": 10, "10mm": 6, "20mm": 2},
    }
    # Dados semanais sintéticos para ano 2024 — proporcionais ao padrão mensal
    # Cada mês tem ~4-5 semanas; os dias de chuva são distribuídos uniformemente
    # Semanas geradas: W01-W52 do ano 2024
    _semanas_por_mes = {
        "01": ["2024-W01", "2024-W02", "2024-W03", "2024-W04"],
        "02": ["2024-W05", "2024-W06", "2024-W07", "2024-W08"],
        "03": ["2024-W09", "2024-W10", "2024-W11", "2024-W12", "2024-W13"],
        "04": ["2024-W14", "2024-W15", "2024-W16", "2024-W17"],
        "05": ["2024-W18", "2024-W19", "2024-W20", "2024-W21", "2024-W22"],
        "06": ["2024-W23", "2024-W24", "2024-W25", "2024-W26"],
        "07": ["2024-W27", "2024-W28", "2024-W29", "2024-W30"],
        "08": ["2024-W31", "2024-W32", "2024-W33", "2024-W34", "2024-W35"],
        "09": ["2024-W36", "2024-W37", "2024-W38", "2024-W39"],
        "10": ["2024-W40", "2024-W41", "2024-W42", "2024-W43", "2024-W44"],
        "11": ["2024-W45", "2024-W46", "2024-W47", "2024-W48"],
        "12": ["2024-W49", "2024-W50", "2024-W51", "2024-W52"],
    }
    dias_por_semana: dict[str, dict[str, int]] = {}
    for mes_str, semanas in _semanas_por_mes.items():
        mensal = dias_por_mes_e_threshold[mes_str]
        n = len(semanas)
        for i, semana_key in enumerate(semanas):
            dias_por_semana[semana_key] = {
                t: round(total / n) if i < n - 1 else (total - round(total / n) * (n - 1))
                for t, total in mensal.items()
            }

    client = MagicMock(spec=OpenMeteoClient)
    client.fetch_dados_anuais.return_value = DadosClimaticosMensais(
        latitude=-4.3622,
        longitude=-38.7392,
        ano_referencia=2024,
        fonte="open-meteo",
        dias_precipitacao_mensal=dias_por_mes_e_threshold,
        dias_precipitacao_semanal=dias_por_semana,
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
        "eap": [
            {
                "item_id": "eap-01",
                "ordem": 1,
                "cpu_id": "ESCO-CARGA-1CAT-DMT2000",
                "descricao": "Escavação 1ª categoria",
                "unidade": "m3",
                "quantitativo": 80000,
            },
            {
                "item_id": "eap-02",
                "ordem": 2,
                "cpu_id": "COMPACT-ATERRO-100PN",
                "descricao": "Compactação de aterro",
                "unidade": "m3",
                "quantitativo": 75000,
            },
            {
                "item_id": "eap-03",
                "ordem": 3,
                "cpu_id": "REGULARIZACAO-SUBLEITO",
                "descricao": "Regularização de subleito",
                "unidade": "m2",
                "quantitativo": 28000,
            },
        ],
    }


@pytest.fixture
def amostra_terraplenagem_path() -> Path:
    """Resolve a amostra por ordem determinística de fontes conhecidas."""
    sample_name = "01-terraplenagem-feliz.json"
    candidates: list[Path] = []

    samples_env = os.environ.get("CONCILIUM_SAMPLES_DIR")
    if samples_env:
        candidates.append(Path(samples_env) / sample_name)

    # Local canônico dentro do repositório (tests/samples/).
    candidates.append(Path(__file__).resolve().parent / "samples" / sample_name)

    # Compatibilidade com fluxo do Claude Desktop.
    candidates.append(Path("/home/claude/concilium-samples") / sample_name)

    # Fallback legado no repositório.
    for parent in Path(__file__).resolve().parents:
        candidates.append(parent / "data" / "samples" / sample_name)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    attempted = "\n".join(f"- {p}" for p in candidates)
    raise FileNotFoundError(
        "Amostra de terraplenagem não encontrada. Caminhos verificados:\n"
        f"{attempted}\n"
        "Defina CONCILIUM_SAMPLES_DIR para apontar para os samples."
    )
