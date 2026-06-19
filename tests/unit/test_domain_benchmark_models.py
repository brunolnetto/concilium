"""Tests for domain/benchmark/models.py."""

from __future__ import annotations

from datetime import UTC, datetime


def _make_meta(**kwargs):
    from concilium.domain.benchmark.models import BenchmarkMetadata

    defaults = dict(
        benchmark_id="bench-1",
        nome="Test Bench",
        origem="manual",
        tags=["tag1"],
        criado_em=datetime.now(UTC),
        versao=1,
        imutavel=False,
    )
    defaults.update(kwargs)
    return BenchmarkMetadata(**defaults)


def _make_exec(**kwargs):
    from concilium.domain.benchmark.models import BenchmarkExecution

    defaults = dict(
        execution_id="exec-1",
        benchmark_id="bench-1",
        versao=1,
        projeto_id="proj-1",
        status="SUCESSO",
        executado_em=datetime.now(UTC),
    )
    defaults.update(kwargs)
    return BenchmarkExecution(**defaults)


class TestBenchmarkState:
    def test_values(self):
        from concilium.domain.benchmark.models import BenchmarkState

        assert BenchmarkState.PENDENTE == "PENDENTE"
        assert BenchmarkState.EM_PROGRESSO == "EM_PROGRESSO"
        assert BenchmarkState.SUCESSO == "SUCESSO"
        assert BenchmarkState.FALHA == "FALHA"


class TestBenchmarkMetadata:
    def test_create(self):
        m = _make_meta()
        assert m.benchmark_id == "bench-1"
        assert m.versao == 1
        assert not m.imutavel

    def test_mark_immutable(self):
        m = _make_meta()
        assert not m.imutavel
        m.mark_immutable()
        assert m.imutavel

    def test_tags_list(self):
        m = _make_meta(tags=["a", "b"])
        assert "a" in m.tags


class TestBenchmarkExecution:
    def test_create_minimal(self):
        e = _make_exec()
        assert e.execution_id == "exec-1"
        assert e.discrepancia_sumario is None

    def test_create_with_discrepancia(self):
        e = _make_exec(discrepancia_sumario={"n_gates": 3, "decision": "REPROVADO"})
        assert e.discrepancia_sumario["n_gates"] == 3

    def test_status_field(self):
        from concilium.domain.benchmark.models import BenchmarkState

        e = _make_exec(status=BenchmarkState.FALHA)
        assert e.status == "FALHA"
