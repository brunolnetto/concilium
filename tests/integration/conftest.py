"""Fixtures para testes de integração ADR-104."""

import pytest


@pytest.fixture(scope="session")
def agis_benchmark(config_root):
    """Fixture que retorna o canonical model do benchmark AGIS após execução completa.

    Executa o pipeline completo do AGIS via BenchmarkFacade e retorna um wrapper
    com o canonical model com todos os dados processados.
    """
    from concilium.application.benchmarks.execution.facade import BenchmarkFacade

    # Criar facade a partir do config_root
    # BenchmarkFacade descobre benchmarks_root e projects_root automaticamente
    root = config_root.parent
    facade = BenchmarkFacade.from_root(root)

    # Executar benchmark AGIS SEMPRE do zero (reset=True).
    #
    # ADR-104/NEP-043 (issue #125): esta fixture é session-scoped, então dentro de
    # UM MESMO processo pytest o benchmark já só roda uma vez — reset=False não
    # ganhava nada em velocidade aqui, só criava risco.
    #
    # `reset=False` faz `BenchmarkRunner._load_existing_report_if_fresh()`
    # devolver o canonical + relatório já persistidos em
    # `benchmarks/projetos/AGIS/` (diretório real do working tree, gitignored
    # mas NÃO efêmero) sem rodar nenhum código do pipeline atual, sempre que
    # esse diretório já existir — não importa de qual commit ele veio.
    #
    # Isso é uma armadilha clássica de bisect/dev local: se alguém já rodou o
    # benchmark AGIS num commit antigo (ex: investigando #121/#125 com git
    # bisect/checkout), o diretório fica no working tree e os testes voltam a
    # "passar" ou "falhar" refletindo aquele commit antigo, não o HEAD atual.
    # Foi exatamente isso que reproduzimos ao investigar a falha relatada na
    # #125: com reset=True (fresh) os dois testes batem com o baseline atual;
    # só reaparecia divergência ao reaproveitar um cache gerado por um commit
    # anterior. Ver INVESTIGACAO_125.md na raiz do repo para os detalhes.
    facade.run_single("AGIS", reset=True)

    # Carregar canonical model do projeto — project_id é determinístico (= slug do
    # benchmark, "AGIS") via BenchmarkRunner._find_or_create/build_local_project_repository.
    from concilium.infrastructure.storage.store_factory import build_local_project_repository

    repo = build_local_project_repository(facade.projects_root)
    try:
        store = repo.get_project("AGIS")
    except FileNotFoundError:
        raise FileNotFoundError(f"AGIS project not found under {facade.projects_root} after benchmark run") from None
    canonical = store.load_canonical()
    return BenchmarkWrapper(canonical)


class BenchmarkWrapper:
    """Wrapper para acessar dados do benchmark AGIS nos testes."""

    def __init__(self, canonical_model):
        self.canonical = canonical_model
