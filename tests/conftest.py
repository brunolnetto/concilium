"""Fixtures pytest para testes do Concilium.

PERFORMANCE NOTES:
==================
- Session-scoped fixtures (_session_*): executam UMA VEZ por sessão pytest inteira
- Class-scoped fixtures: executam UMA VEZ por classe de teste
- Function-scoped: executam para CADA teste (padrão)

OTIMIZAÇÕES IMPLEMENTADAS:
--------------------------
1. **Fixtures session-scoped** para pipelines pesados (skills 01-09: ~50-80s)
2. **Class-scoped projeto_analitico** economiza ~20-28s (1× ao invés de 7× copytree)
3. **Performance hooks** medem automaticamente fixtures > 0.5s
4. **Ignore patterns** em copytree evitam copiar PDFs, ZIPs, referencias/

PRÓXIMAS OTIMIZAÇÕES (se necessário):
-------------------------------------
- **pytest-xdist**: Paralelizar testes em múltiplos workers
  Uso: `pytest -n auto tests/integration/`
  Ganho esperado: 2-4× mais rápido em máquina com 4+ cores

- **pytest-split**: Dividir testes em grupos balanceados para CI
  Uso: `pytest --splits 4 --group 1`

- **Hardlinks ao invés de copytree**: Para projetos > 100MB
  Requer implementação de helper copy_project_with_hardlinks()
"""

# Ensure the package source dir is on sys.path so tests can import `concilium`
import sys
import time
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


@pytest.hookimpl(tryfirst=True)
def pytest_fixture_setup(fixturedef, request):
    """Hook para monitorar performance de fixtures lentas."""
    # Monitora fixtures session/class-scoped, ou function-scoped que tenham "pipeline" no nome
    if (
        fixturedef.scope in ("session", "class")
        or "pipeline" in fixturedef.argname
        or "analitico" in fixturedef.argname
    ):
        fixturedef._start_time = time.time()


@pytest.hookimpl(trylast=True)
def pytest_fixture_post_finalizer(fixturedef, request):
    """Log de performance para fixtures lentas."""
    if hasattr(fixturedef, "_start_time"):
        elapsed = time.time() - fixturedef._start_time
        if elapsed > 0.5:  # Log se > 0.5s (reduzido de 1s para pegar mais detalhes)
            print(f"\n[PERF] {fixturedef.argname} ({fixturedef.scope}): {elapsed:.2f}s")


project_root = Path(__file__).resolve().parents[1]
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import os
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("CONCILIUM__PDF_RENDERER", "fpdf2")

from concilium.application.runtime import Runtime
from concilium.infrastructure.clients.openmeteo import DadosClimaticosMensais, OpenMeteoClient
from concilium.infrastructure.storage.project import ProjectStore


@pytest.fixture(scope="session")
def config_root() -> Path:
    """Path do diretório de configuração com dados seed."""
    return Path(__file__).parent.parent / "config"


@pytest.fixture
def projetos_root(tmp_path: Path) -> Path:
    """Diretório isolado de projetos para cada teste."""
    p = tmp_path / "projetos"
    p.mkdir()
    return p


@pytest.fixture(scope="session")
def runtime(config_root: Path) -> Runtime:
    return Runtime(config_root)


@pytest.fixture
def projeto_terraplenagem(projetos_root: Path) -> ProjectStore:
    """Projeto novo para o cenário de terraplenagem.

    Usa contexto "test" (estável para CI, não evolui com mudanças em catalogos de produção).
    Testes são isolados de mudanças futuras em dados reais.
    """
    return ProjectStore.init(projetos_root, "terraplenagem-aracoiaba-test", "test")


@pytest.fixture(scope="session")
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


@pytest.fixture(scope="session")
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


@pytest.fixture(scope="session")
def _session_pipeline_sk03(tmp_path_factory, runtime, inputs_escopo_terraplenagem, mock_openmeteo_aracoiaba):
    """Executa skills 01→03 UMA VEZ por sessão de teste. Retorna proj.root.

    Base compartilhada por _session_pipeline_sk09 e _session_edge_case_sk09;
    evita duplicar as 3 skills iniciais (idênticas entre os dois pipelines
    de contexto 'test').

    PERFORMANCE: Skills 01-03 (especialmente 03-catalogo) são as mais lentas (~70s).
    Compartilhar este base é crítico para performance de toda a suite.
    """
    projetos_root = tmp_path_factory.mktemp("session_sk03")
    proj = ProjectStore.init(projetos_root, "session-sk03-test", "test")
    proj.new_version()

    # Desabilitar PDF em testes: render_markdown_pdf é o maior gargalo de skill-09 (~20-25s)
    # Testes que validam conteúdo de Excel/Markdown ainda funcionam normalmente.

    _deliverables = {
        "outputs": {
            "relatorio_md": True,
            "relatorio_pdf": False,  # PDF lento — não testado aqui
            "memorial_bdi_md": True,
            "memorial_bdi_pdf": False,  # PDF lento — não testado aqui
            "resultado_xlsx": True,
            "graficos_png": False,  # analytic cube PNGs: ~60s — não testados aqui
        }
    }
    proj.write_json("deliverables_config.json", _deliverables)

    runtime.run_skill("01-escopo-e-eap", proj, inputs=inputs_escopo_terraplenagem)
    with patch(
        "concilium.infrastructure.clients.openmeteo.OpenMeteoClient",
        return_value=mock_openmeteo_aracoiaba,
    ):
        runtime.run_skill("02-produtividade-climatica", proj, inputs={"ano_referencia": 2024})

    # Skill 03 é o maior gargalo (~50-60s) - carrega catálogo completo
    runtime.run_skill("03-catalogo-de-recursos", proj, inputs={})
    return proj.root


@pytest.fixture(scope="session")
def _session_pipeline_sk09(tmp_path_factory, runtime, _session_pipeline_sk03):
    """Executa pipeline 04→09 UMA VEZ por sessão, copiando do base pós-03.

    Compartilhada entre test_samples_end_to_end.py e test_pipeline.py para
    eliminar a segunda execução redundante do pipeline completo.
    Todos os consumidores são read-only; testes que modificam o projeto
    recebem uma cópia isolada via shutil.copytree.

    PERFORMANCE: ~10-15s para skills 04-09. Base sk03 já tem catálogo carregado.
    """
    _start = time.time()
    dest = tmp_path_factory.mktemp("session_sk09") / "projeto"
    shutil.copytree(_session_pipeline_sk03, dest)
    proj = ProjectStore(dest)

    cron_inputs = {
        "num_equipes_por_item": {
            "eap-01": {f"2026-W{w:02d}": 1 for w in range(23, 31)},
            "eap-02": {f"2026-W{w:02d}": 1 for w in range(27, 37)},
            "eap-03": {f"2026-W{w:02d}": 1 for w in range(35, 41)},
        }
    }
    _t = time.time()
    runtime.run_skill("04-cronograma", proj, inputs=cron_inputs)
    print(f"\n[PERF] sk09/04-cronograma: {time.time() - _t:.2f}s")
    _t = time.time()
    runtime.run_skill("05-equipes-e-alocacao", proj, inputs={})
    print(f"[PERF] sk09/05-equipes: {time.time() - _t:.2f}s")
    _t = time.time()
    runtime.run_skill("06-resultado-financeiro", proj, inputs={})  # NEP-041 F4: unifica 06+07+08
    print(f"[PERF] sk09/06-resultado-financeiro: {time.time() - _t:.2f}s")
    _t = time.time()
    r = runtime.run_skill("09-relatorio-e-artefatos", proj, inputs={})
    print(f"[PERF] sk09/09-relatorio: {time.time() - _t:.2f}s")
    print(f"[PERF] Pipeline sk09 completo: {time.time() - _start:.2f}s")
    return proj, r


@pytest.fixture(scope="session")
def _session_edge_case_sk09(tmp_path_factory, runtime, _session_pipeline_sk03):
    """Executa pipeline edge case (04→09, cron mínimo) UMA VEZ por sessão, copiando do base pós-03.

    Utilizada por TestExcelEdgeCases para validar geração de Excel com dados incompletos.
    O cronograma mínimo (apenas eap-01 por uma semana) propositalmente diverge do
    pipeline principal (_session_pipeline_sk09) para cobrir o cenário de stress.
    Reutiliza _session_pipeline_sk03 para evitar duplicar skills 01→03.

    PERFORMANCE: ~5-8s (edge case é mais rápido por ter menos dados).
    """
    _start = time.time()
    dest = tmp_path_factory.mktemp("session_edge_sk09") / "projeto"
    shutil.copytree(_session_pipeline_sk03, dest)
    proj = ProjectStore(dest)

    cron_inputs = {"num_equipes_por_item": {"eap-01": {"2026-W31": 1}}}  # cronograma mínimo
    runtime.run_skill("04-cronograma", proj, inputs=cron_inputs)
    runtime.run_skill("05-equipes-e-alocacao", proj, inputs={})
    runtime.run_skill("06-resultado-financeiro", proj, inputs={})  # NEP-041 F4: unifica 06+07+08
    runtime.run_skill("09-relatorio-e-artefatos", proj, inputs={})
    print(f"\n[PERF] Pipeline edge case sk09: {time.time() - _start:.2f}s")
    return proj


@pytest.fixture(scope="session")
def _session_pipeline_mendeslobo_sk09(tmp_path_factory, runtime, inputs_escopo_terraplenagem, mock_openmeteo_aracoiaba):
    """Executa pipeline 01→09 com contexto mendeslobo UMA VEZ por sessão.

    Promovida de module-scoped para session-scoped; garante que mesmo que o
    módulo seja dividido no futuro, o pipeline não será executado mais de uma vez.

    PERFORMANCE: ~70-80s total (skill 03 sozinha leva ~50-60s por catálogo mendeslobo maior).
    OTIMIZAÇÃO FUTURA: Compartilhar base sk03 entre contextos diferentes seria complexo
    devido a diferenças nos catálogos por perfil.
    """
    _start = time.time()
    inputs_agis = inputs_escopo_terraplenagem.copy()
    inputs_agis["contexto_id"] = "mendeslobo"

    projetos_root = tmp_path_factory.mktemp("session_mendeslobo_sk09")
    proj = ProjectStore.init(projetos_root, "session-mendeslobo-sk09-test", "test")
    proj.new_version()

    proj.write_json(
        "deliverables_config.json",
        {
            "outputs": {
                "relatorio_md": True,
                "relatorio_pdf": False,
                "memorial_bdi_md": True,
                "memorial_bdi_pdf": False,
                "resultado_xlsx": True,
                "graficos_png": False,
            }
        },
    )

    _t0 = time.time()
    runtime.run_skill("01-escopo-e-eap", proj, inputs=inputs_agis)
    print(f"\n[PERF] Skill 01: {time.time() - _t0:.2f}s")

    _t0 = time.time()
    with patch(
        "concilium.infrastructure.clients.openmeteo.OpenMeteoClient",
        return_value=mock_openmeteo_aracoiaba,
    ):
        runtime.run_skill("02-produtividade-climatica", proj, inputs={"ano_referencia": 2024})
    print(f"[PERF] Skill 02: {time.time() - _t0:.2f}s")

    _t0 = time.time()
    runtime.run_skill("03-catalogo-de-recursos", proj, inputs={})
    print(f"[PERF] Skill 03 (GARGALO catálogo mendeslobo): {time.time() - _t0:.2f}s")

    cron_inputs = {
        "num_equipes_por_item": {
            "eap-01": {f"2026-W{w:02d}": 1 for w in range(23, 31)},
            "eap-02": {f"2026-W{w:02d}": 1 for w in range(27, 37)},
            "eap-03": {f"2026-W{w:02d}": 1 for w in range(35, 41)},
        }
    }
    runtime.run_skill("04-cronograma", proj, inputs=cron_inputs)
    runtime.run_skill("05-equipes-e-alocacao", proj, inputs={})
    runtime.run_skill("06-resultado-financeiro", proj, inputs={})  # NEP-041 F4: unifica 06+07+08
    runtime.run_skill("09-relatorio-e-artefatos", proj, inputs={})
    print(f"[PERF] Pipeline mendeslobo completo: {time.time() - _start:.2f}s")
    return proj


@pytest.fixture(scope="session")
def _wb_sk09(_session_pipeline_sk09):
    """Pre-carrega o Workbook do pipeline session-scoped UMA VEZ.

    Evita N invocações independentes de load_workbook (cada uma ~12–23 s)
    sobre os mesmos bytes. Todos os consumidores são read-only (sheetnames,
    iter_rows) — sem risco de estado compartilhado entre testes.
    """
    from io import BytesIO

    from openpyxl import load_workbook

    _, r = _session_pipeline_sk09
    return load_workbook(BytesIO(r.excel_bytes))


@pytest.fixture
def amostra_terraplenagem_path() -> Path:
    """Resolve a amostra por ordem determinística de fontes conhecidas."""
    sample_name = "01-terraplenagem-feliz.json"
    candidates: list[Path] = []

    samples_env = os.environ.get("CONCILIUM__SAMPLES_DIR")
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
        "Defina CONCILIUM__SAMPLES_DIR para apontar para os samples."
    )
