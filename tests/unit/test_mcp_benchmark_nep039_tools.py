"""Tests for MCP tools registered in benchmark_nep039.py (NEP-039).

Strategy: call `register(server, store)` with a MagicMock store and a mock
FastMCP instance whose `.tool` side-effect captures decorated callables.
Each inner function is then invoked directly so no MCP transport is needed.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from concilium.application.benchmarks.diff_service import BenchmarkDiffResult
from concilium.domain.benchmark.models import BenchmarkExecution, BenchmarkMetadata
from concilium.presentation.mcp.tools.benchmark_nep039 import register

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_server_and_tools(store):
    """Build a mock FastMCP server and return a dict of captured tool functions."""
    tools: dict = {}
    server = MagicMock()

    # server.tool(description=...) must return a decorator that receives the fn
    def _tool_decorator(description=None, **_kw):
        def _capture(fn):
            tools[fn.__name__] = fn
            return fn

        return _capture

    server.tool.side_effect = _tool_decorator
    register(server, store)
    return server, tools


def _make_meta(
    benchmark_id: str = "BENCH_001",
    nome: str = "Benchmark Teste",
    origem: str = "Real",
    tags: list | None = None,
    versao: int = 1,
    imutavel: bool = False,
) -> BenchmarkMetadata:
    return BenchmarkMetadata(
        benchmark_id=benchmark_id,
        nome=nome,
        origem=origem,
        tags=tags or ["civil"],
        criado_em=datetime(2025, 1, 15, 8, 0, 0),
        versao=versao,
        imutavel=imutavel,
    )


def _make_execution(
    execution_id: str,
    benchmark_id: str = "BENCH_001",
    projeto_id: str = "proj-abc",
    status: str = "SUCESSO",
    versao: int = 1,
    discrepancia_sumario: dict | None = None,
) -> BenchmarkExecution:
    return BenchmarkExecution(
        execution_id=execution_id,
        benchmark_id=benchmark_id,
        versao=versao,
        projeto_id=projeto_id,
        status=status,
        executado_em=datetime(2025, 3, 1, 10, 0, 0),
        discrepancia_sumario=discrepancia_sumario,
    )


@pytest.fixture
def store():
    return MagicMock()


@pytest.fixture
def tools(store):
    _, t = _make_server_and_tools(store)
    return t


# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------


class TestRegister:
    def test_all_tools_registered(self, store):
        """register() must register exactly the six expected tool names."""
        _, tools = _make_server_and_tools(store)
        expected = {
            "consultar_benchmark",
            "listar_benchmarks_nep039",
            "executar_benchmark_nep039",
            "editar_benchmark",
            "marcar_benchmark_imutavel",
            "comparar_execucoes_benchmark",
        }
        assert set(tools.keys()) == expected

    def test_server_tool_called_six_times(self, store):
        server, _ = _make_server_and_tools(store)
        assert server.tool.call_count == 6


# ---------------------------------------------------------------------------
# consultar_benchmark
# ---------------------------------------------------------------------------


class TestConsultarBenchmark:
    def test_not_found_returns_erro(self, store, tools):
        store.get_metadata.return_value = None
        result = tools["consultar_benchmark"](benchmark_id="GHOST")
        assert "erro" in result
        assert result["status"] == "NAO_ENCONTRADO"
        assert "GHOST" in result["erro"]

    def test_found_returns_all_keys(self, store, tools):
        meta = _make_meta()
        exec_ok = _make_execution("e1", status="SUCESSO", projeto_id="proj-1")
        exec_fail = _make_execution("e2", status="FALHA", projeto_id="proj-2")
        store.get_metadata.return_value = meta
        store.get_execution_history.return_value = [exec_ok, exec_fail]

        result = tools["consultar_benchmark"](benchmark_id="BENCH_001")

        expected_keys = {
            "benchmark_id",
            "nome",
            "origem",
            "tags",
            "versao",
            "imutavel",
            "criado_em",
            "execucoes_historico",
            "total_projetos_derivados",
        }
        assert expected_keys.issubset(result.keys())
        assert result["benchmark_id"] == "BENCH_001"
        assert result["versao"] == 1
        assert result["imutavel"] is False

    def test_total_projetos_derivados_counts_only_sucesso(self, store, tools):
        """Only SUCESSO executions contribute to total_projetos_derivados."""
        meta = _make_meta()
        executions = [
            _make_execution("e1", status="SUCESSO", projeto_id="proj-1"),
            _make_execution("e2", status="SUCESSO", projeto_id="proj-2"),
            _make_execution("e3", status="FALHA", projeto_id="proj-3"),
            _make_execution("e4", status="PENDENTE", projeto_id="proj-4"),
        ]
        store.get_metadata.return_value = meta
        store.get_execution_history.return_value = executions

        result = tools["consultar_benchmark"](benchmark_id="BENCH_001")

        assert result["total_projetos_derivados"] == 2

    def test_total_projetos_derivados_deduplicates_project_ids(self, store, tools):
        """The same project_id twice counts as one unique project."""
        meta = _make_meta()
        executions = [
            _make_execution("e1", status="SUCESSO", projeto_id="proj-SHARED"),
            _make_execution("e2", status="SUCESSO", projeto_id="proj-SHARED"),
            _make_execution("e3", status="SUCESSO", projeto_id="proj-OTHER"),
        ]
        store.get_metadata.return_value = meta
        store.get_execution_history.return_value = executions

        result = tools["consultar_benchmark"](benchmark_id="BENCH_001")

        assert result["total_projetos_derivados"] == 2

    def test_execucoes_historico_format(self, store, tools):
        """Each history entry must have the required sub-keys."""
        meta = _make_meta()
        exec1 = _make_execution("e1")
        store.get_metadata.return_value = meta
        store.get_execution_history.return_value = [exec1]

        result = tools["consultar_benchmark"](benchmark_id="BENCH_001")

        entry = result["execucoes_historico"][0]
        assert entry["execution_id"] == "e1"
        assert entry["projeto_id"] == "proj-abc"
        assert entry["status"] == "SUCESSO"
        assert "executado_em" in entry
        assert "discrepancia_sumario" in entry

    def test_empty_history(self, store, tools):
        meta = _make_meta()
        store.get_metadata.return_value = meta
        store.get_execution_history.return_value = []

        result = tools["consultar_benchmark"](benchmark_id="BENCH_001")

        assert result["execucoes_historico"] == []
        assert result["total_projetos_derivados"] == 0

    def test_criado_em_is_isoformat_string(self, store, tools):
        meta = _make_meta()
        store.get_metadata.return_value = meta
        store.get_execution_history.return_value = []

        result = tools["consultar_benchmark"](benchmark_id="BENCH_001")

        # Must be parseable as ISO datetime
        dt = datetime.fromisoformat(result["criado_em"])
        assert dt.year == 2025


# ---------------------------------------------------------------------------
# listar_benchmarks_nep039
# ---------------------------------------------------------------------------


class TestListarBenchmarks:
    def test_empty_store_returns_zero(self, store, tools):
        store.list_all.return_value = []
        result = tools["listar_benchmarks_nep039"]()
        assert result["total"] == 0
        assert result["benchmarks"] == []

    def test_two_benchmarks_returns_total_two(self, store, tools):
        meta1 = _make_meta("B1", nome="Bench 1")
        meta2 = _make_meta("B2", nome="Bench 2", versao=3)
        store.list_all.return_value = [meta1, meta2]

        result = tools["listar_benchmarks_nep039"]()

        assert result["total"] == 2
        assert len(result["benchmarks"]) == 2

    def test_each_entry_has_expected_keys(self, store, tools):
        meta = _make_meta()
        store.list_all.return_value = [meta]

        result = tools["listar_benchmarks_nep039"]()

        entry = result["benchmarks"][0]
        expected_keys = {"benchmark_id", "nome", "origem", "tags", "versao", "imutavel", "criado_em"}
        assert expected_keys.issubset(entry.keys())

    def test_entry_values_match_metadata(self, store, tools):
        meta = _make_meta("AGIS_Q1", nome="AGIS Q1", versao=5, imutavel=True)
        store.list_all.return_value = [meta]

        result = tools["listar_benchmarks_nep039"]()

        entry = result["benchmarks"][0]
        assert entry["benchmark_id"] == "AGIS_Q1"
        assert entry["nome"] == "AGIS Q1"
        assert entry["versao"] == 5
        assert entry["imutavel"] is True

    def test_criado_em_is_isoformat(self, store, tools):
        meta = _make_meta()
        store.list_all.return_value = [meta]

        result = tools["listar_benchmarks_nep039"]()

        entry = result["benchmarks"][0]
        dt = datetime.fromisoformat(entry["criado_em"])
        assert dt.year == 2025


# ---------------------------------------------------------------------------
# executar_benchmark_nep039
# ---------------------------------------------------------------------------


class TestExecutarBenchmark:
    def test_not_found_returns_erro(self, store, tools):
        store.get_metadata.return_value = None
        result = tools["executar_benchmark_nep039"](benchmark_id="GHOST")
        assert "erro" in result

    def test_found_returns_required_keys(self, store, tools):
        meta = _make_meta(versao=2)
        store.get_metadata.return_value = meta

        result = tools["executar_benchmark_nep039"](benchmark_id="BENCH_001")

        assert result["status"] == "PENDENTE"
        assert "project_id" in result
        assert "execution_id" in result
        assert result["benchmark_versao"] == 2

    def test_log_execution_called_once(self, store, tools):
        meta = _make_meta()
        store.get_metadata.return_value = meta

        tools["executar_benchmark_nep039"](benchmark_id="BENCH_001")

        store.log_execution.assert_called_once()

    def test_explicit_project_id_used(self, store, tools):
        meta = _make_meta()
        store.get_metadata.return_value = meta

        result = tools["executar_benchmark_nep039"](
            benchmark_id="BENCH_001",
            criar_novo_projeto=False,
            project_id="proj-explicit-123",
        )

        assert result["project_id"] == "proj-explicit-123"

    def test_auto_project_id_generated_when_none(self, store, tools):
        meta = _make_meta()
        store.get_metadata.return_value = meta

        result = tools["executar_benchmark_nep039"](benchmark_id="BENCH_001")

        # Should be a generated string, not None
        assert result["project_id"] is not None
        assert isinstance(result["project_id"], str)

    def test_execution_id_in_log_matches_response(self, store, tools):
        meta = _make_meta()
        store.get_metadata.return_value = meta

        result = tools["executar_benchmark_nep039"](benchmark_id="BENCH_001")

        logged_exec = store.log_execution.call_args[0][0]
        assert logged_exec.execution_id == result["execution_id"]

    def test_execution_has_pendente_status(self, store, tools):
        meta = _make_meta()
        store.get_metadata.return_value = meta

        tools["executar_benchmark_nep039"](benchmark_id="BENCH_001")

        logged_exec = store.log_execution.call_args[0][0]
        assert logged_exec.status == "PENDENTE"

    def test_benchmark_versao_in_response(self, store, tools):
        meta = _make_meta(versao=7)
        store.get_metadata.return_value = meta

        result = tools["executar_benchmark_nep039"](benchmark_id="BENCH_001")

        assert result["benchmark_versao"] == 7


# ---------------------------------------------------------------------------
# editar_benchmark
# ---------------------------------------------------------------------------


class TestEditarBenchmark:
    def test_not_found_returns_erro(self, store, tools):
        store.get_metadata.return_value = None
        result = tools["editar_benchmark"](benchmark_id="GHOST", patch={"nome": "X"})
        assert "erro" in result

    def test_imutavel_creates_new_version(self, store, tools):
        meta = _make_meta(imutavel=True, versao=1)
        new_meta = _make_meta(imutavel=False, versao=2)
        store.get_metadata.return_value = meta
        store.create_new_version.return_value = new_meta

        result = tools["editar_benchmark"](benchmark_id="BENCH_001", patch={"nome": "Updated"})

        store.create_new_version.assert_called_once()
        assert result["versao_anterior"] == 1
        assert result["versao_nova"] == 2

    def test_imutavel_response_has_required_keys(self, store, tools):
        meta = _make_meta(imutavel=True, versao=1)
        new_meta = _make_meta(imutavel=False, versao=2)
        store.get_metadata.return_value = meta
        store.create_new_version.return_value = new_meta

        result = tools["editar_benchmark"](benchmark_id="BENCH_001", patch={})

        expected = {"benchmark_id", "versao_anterior", "versao_nova", "nome", "tags", "imutavel", "mensagem"}
        assert expected.issubset(result.keys())

    def test_mutavel_updates_inplace(self, store, tools):
        meta = _make_meta(imutavel=False, versao=1)
        updated_meta = _make_meta(imutavel=False, versao=1, nome="Updated Nome")
        store.get_metadata.side_effect = [meta, updated_meta]

        result = tools["editar_benchmark"](benchmark_id="BENCH_001", patch={"nome": "Updated Nome"})

        store.update_metadata.assert_called_once()
        assert "in-place" in result["mensagem"]

    def test_mutavel_calls_get_metadata_twice(self, store, tools):
        """Second get_metadata call fetches the updated state."""
        meta = _make_meta(imutavel=False)
        updated_meta = _make_meta(imutavel=False, nome="V2")
        store.get_metadata.side_effect = [meta, updated_meta]

        tools["editar_benchmark"](benchmark_id="BENCH_001", patch={"nome": "V2"})

        assert store.get_metadata.call_count == 2

    def test_mutavel_response_has_versao_key(self, store, tools):
        meta = _make_meta(imutavel=False, versao=1)
        updated_meta = _make_meta(imutavel=False, versao=1)
        store.get_metadata.side_effect = [meta, updated_meta]

        result = tools["editar_benchmark"](benchmark_id="BENCH_001", patch={})

        assert "versao" in result
        assert "mensagem" in result

    def test_imutavel_does_not_call_update_metadata(self, store, tools):
        meta = _make_meta(imutavel=True)
        new_meta = _make_meta(versao=2)
        store.get_metadata.return_value = meta
        store.create_new_version.return_value = new_meta

        tools["editar_benchmark"](benchmark_id="BENCH_001", patch={})

        store.update_metadata.assert_not_called()


# ---------------------------------------------------------------------------
# marcar_benchmark_imutavel
# ---------------------------------------------------------------------------


class TestMarcarBenchmarkImutavel:
    def test_not_found_returns_erro(self, store, tools):
        store.get_metadata.return_value = None
        result = tools["marcar_benchmark_imutavel"](benchmark_id="GHOST")
        assert "erro" in result

    def test_found_marks_immutable(self, store, tools):
        meta = _make_meta(imutavel=False)
        store.get_metadata.return_value = meta

        result = tools["marcar_benchmark_imutavel"](benchmark_id="BENCH_001")

        assert result["imutavel"] is True

    def test_mark_immutable_called_on_meta(self, store, tools):
        meta = MagicMock(spec=BenchmarkMetadata)
        meta.benchmark_id = "BENCH_001"
        meta.versao = 1
        store.get_metadata.return_value = meta

        tools["marcar_benchmark_imutavel"](benchmark_id="BENCH_001")

        meta.mark_immutable.assert_called_once()

    def test_save_metadata_called(self, store, tools):
        meta = _make_meta()
        store.get_metadata.return_value = meta

        tools["marcar_benchmark_imutavel"](benchmark_id="BENCH_001")

        store.save_metadata.assert_called_once_with(meta)

    def test_response_keys(self, store, tools):
        meta = _make_meta()
        store.get_metadata.return_value = meta

        result = tools["marcar_benchmark_imutavel"](benchmark_id="BENCH_001")

        assert {"benchmark_id", "versao", "imutavel", "mensagem"}.issubset(result.keys())

    def test_benchmark_id_in_response_matches_input(self, store, tools):
        meta = _make_meta(benchmark_id="AGIS_2025")
        store.get_metadata.return_value = meta

        result = tools["marcar_benchmark_imutavel"](benchmark_id="AGIS_2025")

        assert result["benchmark_id"] == "AGIS_2025"


# ---------------------------------------------------------------------------
# comparar_execucoes_benchmark
# ---------------------------------------------------------------------------


class TestCompararExecucoes:
    def _setup_history(self, store, executions):
        """Prepare store.list_all and store.get_execution_history for comparar tool."""
        # list_all returns mocks with .benchmark_id attributes
        bid_mocks = []
        for e in executions:
            m = MagicMock()
            m.benchmark_id = e.benchmark_id
            bid_mocks.append(m)
        store.list_all.return_value = bid_mocks

        # get_execution_history(bid) returns executions for that bid
        from collections import defaultdict

        by_bid = defaultdict(list)
        for e in executions:
            by_bid[e.benchmark_id].append(e)
        store.get_execution_history.side_effect = lambda bid: by_bid.get(bid, [])

    def test_exec1_not_found(self, store, tools):
        self._setup_history(store, [])
        result = tools["comparar_execucoes_benchmark"](execution_1_id="MISSING-1", execution_2_id="MISSING-2")
        assert "erro" in result
        assert "MISSING-1" in result["erro"]

    def test_exec2_not_found(self, store, tools):
        exec1 = _make_execution("e1", benchmark_id="B1")
        self._setup_history(store, [exec1])

        result = tools["comparar_execucoes_benchmark"](execution_1_id="e1", execution_2_id="MISSING-2")
        assert "erro" in result
        assert "MISSING-2" in result["erro"]

    def test_both_found_returns_diff_dict(self, store, tools):
        exec1 = _make_execution("e1", benchmark_id="B1", versao=1)
        exec2 = _make_execution("e2", benchmark_id="B1", versao=2)
        self._setup_history(store, [exec1, exec2])

        diff_result = BenchmarkDiffResult(
            execution_1_id="e1",
            execution_2_id="e2",
            benchmark_id="B1",
            versao_1=1,
            versao_2=2,
            delta_custo_direto_percentual=2.5,
            delta_cronograma_semanas=1,
            delta_margem_lucro_percentual=-0.3,
            itens_impactados=4,
            interpretacao="Regressao: custo 2.5% maior",
            comparado_em=datetime(2025, 4, 1),
        )

        with patch("concilium.presentation.mcp.tools.benchmark_nep039.BenchmarkDiffService") as MockDiffService:
            MockDiffService.return_value.compare.return_value = diff_result
            result = tools["comparar_execucoes_benchmark"](execution_1_id="e1", execution_2_id="e2")

        assert result == diff_result.to_dict()
        assert result["execution_1_id"] == "e1"
        assert result["execution_2_id"] == "e2"

    def test_value_error_from_diff_service_returns_erro(self, store, tools):
        exec1 = _make_execution("e1", benchmark_id="B1")
        exec2 = _make_execution("e2", benchmark_id="B2")  # different benchmark
        self._setup_history(store, [exec1, exec2])

        with patch("concilium.presentation.mcp.tools.benchmark_nep039.BenchmarkDiffService") as MockDiffService:
            MockDiffService.return_value.compare.side_effect = ValueError("different benchmarks")
            result = tools["comparar_execucoes_benchmark"](execution_1_id="e1", execution_2_id="e2")

        assert "erro" in result
        assert "different benchmarks" in result["erro"]

    def test_diff_result_keys_present(self, store, tools):
        exec1 = _make_execution("e1", benchmark_id="B1", versao=1)
        exec2 = _make_execution("e2", benchmark_id="B1", versao=2)
        self._setup_history(store, [exec1, exec2])

        diff_result = BenchmarkDiffResult(
            execution_1_id="e1",
            execution_2_id="e2",
            benchmark_id="B1",
            versao_1=1,
            versao_2=2,
            delta_custo_direto_percentual=0.0,
            delta_cronograma_semanas=0,
            delta_margem_lucro_percentual=0.0,
        )

        with patch("concilium.presentation.mcp.tools.benchmark_nep039.BenchmarkDiffService") as MockDiffService:
            MockDiffService.return_value.compare.return_value = diff_result
            result = tools["comparar_execucoes_benchmark"](execution_1_id="e1", execution_2_id="e2")

        expected_keys = {
            "execution_1_id",
            "execution_2_id",
            "benchmark_id",
            "versao_1",
            "versao_2",
            "delta_custo_direto_percentual",
            "delta_cronograma_semanas",
            "delta_margem_lucro_percentual",
            "itens_impactados",
            "interpretacao",
        }
        assert expected_keys.issubset(result.keys())

    def test_multiple_benchmarks_in_history(self, store, tools):
        """When store has multiple benchmarks, both executions are still found."""
        exec1 = _make_execution("e1", benchmark_id="B1")
        exec2 = _make_execution("e2", benchmark_id="B1")
        exec_other = _make_execution("e-other", benchmark_id="B2")
        self._setup_history(store, [exec1, exec2, exec_other])

        diff_result = BenchmarkDiffResult(
            execution_1_id="e1",
            execution_2_id="e2",
            benchmark_id="B1",
            versao_1=1,
            versao_2=1,
            delta_custo_direto_percentual=0.0,
            delta_cronograma_semanas=0,
            delta_margem_lucro_percentual=0.0,
        )

        with patch("concilium.presentation.mcp.tools.benchmark_nep039.BenchmarkDiffService") as MockDiffService:
            MockDiffService.return_value.compare.return_value = diff_result
            result = tools["comparar_execucoes_benchmark"](execution_1_id="e1", execution_2_id="e2")

        assert "erro" not in result
