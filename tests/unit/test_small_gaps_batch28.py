"""Coverage batch 28 — mobilizacao_simulator, jobs/repository, producao,
week_mapper, permission_guard, completeness, executive_summary."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

# ---------------------------------------------------------------------------
# mobilizacao_simulator.py line 228:
# taxa_desmobilizacao=0 with semanas_plateau set → return n_maximo (line 228)
# (line 206 is unreachable because MobilizacaoPolicy.taxa_mobilizacao has gt=0)
# ---------------------------------------------------------------------------


class TestMobilizacaoSimulatorDesmobZero:
    def _make_policy(self, **kwargs):
        from concilium.domain.models.planning.mobilizacao import MobilizacaoPolicy

        return MobilizacaoPolicy(**kwargs)

    def test_taxa_desmobilizacao_zero_returns_n_maximo_after_plateau(self):
        """Line 228: taxa_desmobilizacao=0, semanas_plateau set, t past plateau → n_maximo."""
        from concilium.domain.services.planning.mobilizacao_simulator import (
            WorkforcePolicySimulator,
        )

        # taxa_mobilizacao=2 (gt=0 ✓), semanas_plateau=5, taxa_desmobilizacao=0 (default)
        policy = self._make_policy(
            n_inicial=1,
            n_maximo=3,
            taxa_mobilizacao=2.0,
            semanas_plateau=5,
            taxa_desmobilizacao=0.0,
        )
        sim = WorkforcePolicySimulator()
        # t=20 > t_plateau_end=(ceil((3-1)/2)=1)+5=6 → demob phase; taxa_desmob=0 → line 228
        result = sim._compute_n(policy, t=20)
        assert result == 3  # n_maximo returned


# ---------------------------------------------------------------------------
# jobs/repository.py line 156:
# _build_repository() with backend != "inmemory" → raises ValueError
# ---------------------------------------------------------------------------


class TestJobsRepositoryUnsupportedBackend:
    def test_unsupported_backend_raises_value_error(self):
        """Line 156: backend='redis' → ValueError."""
        from concilium.application.jobs.repository import _build_repository

        with patch.dict("os.environ", {"CONCILIUM__JOBS_REPOSITORY": "redis"}):
            try:
                _build_repository()
                raise AssertionError("Expected ValueError")
            except ValueError as exc:
                assert "redis" in str(exc)

    def test_inner_double_check_skips_reinit_on_race(self):
        """Line 169->172: deterministically exercises the inner
        `if _repository is None:` False branch by simulating another thread
        having already initialized `_repository` while this one waited to
        acquire `_repository_lock`."""
        import concilium.application.jobs.repository as jobs_repo_mod

        jobs_repo_mod.reset_repository()
        sentinel = object()

        class _FakeLock:
            def __enter__(self):
                jobs_repo_mod._repository = sentinel
                return self

            def __exit__(self, *exc):
                return False

        with patch.object(jobs_repo_mod, "_repository_lock", _FakeLock()):
            result = jobs_repo_mod.get_job_repository()
        assert result is sentinel
        jobs_repo_mod.reset_repository()


# ---------------------------------------------------------------------------
# producao.py line 33:
# obter_ou_erro("NONEXISTENT") → raises FileNotFoundError
# ---------------------------------------------------------------------------


class TestRepositorioProducaoObterOuErro:
    def test_obter_ou_erro_raises_when_not_found(self, tmp_path):
        """Line 33: producao not found → obter returns None → raises FileNotFoundError."""
        from concilium.infrastructure.repositories.producao import RepositorioProducao

        repo = RepositorioProducao(producoes_dir=tmp_path)
        try:
            repo.obter_ou_erro("NONEXISTENT-ID")
            raise AssertionError("Expected FileNotFoundError")
        except FileNotFoundError as exc:
            assert "NONEXISTENT-ID" in str(exc)


# ---------------------------------------------------------------------------
# week_mapper.py line 109:
# num_to_iso empty (numeric keys but no data_inicio) → return ref
# ---------------------------------------------------------------------------


class TestNormalizeReferenciaWeeksEmptyMap:
    def test_numeric_scheme_but_no_data_inicio_returns_ref_unchanged(self):
        """Line 109: build_numeric_to_iso_map returns {} → not num_to_iso → return ref."""
        from concilium.application.benchmarks.input_derivation.week_mapper import (
            normalize_referencia_weeks,
        )

        ref = {
            "cronograma": {
                "semanas": {"1": {}, "2": {}},  # numeric keys, but no data_inicio
                "atividades": [],
            }
        }
        result = normalize_referencia_weeks(ref)
        # Returned unchanged (same object)
        assert result is ref


# ---------------------------------------------------------------------------
# permission_guard.py lines 350-351: validate_tool_coverage with no _tool_manager
# permission_guard.py lines 371-372: build_tool_permission_map with no _tool_manager
# permission_guard.py lines 391-393: patch_mcp_auth_permissions with no _tool_manager
# permission_guard.py line 400: tool without fn → continue
# ---------------------------------------------------------------------------


class TestPermissionGuardAttributeErrorPaths:
    def _server_no_tool_manager(self):
        """Server object that raises AttributeError on ._tool_manager._tools."""
        return SimpleNamespace()  # no _tool_manager attribute at all

    def test_validate_tool_coverage_no_tool_manager_returns_empty(self):
        """Lines 350-351: AttributeError → return []."""
        from concilium.infrastructure.auth.permission_guard import validate_tool_coverage

        result = validate_tool_coverage(self._server_no_tool_manager())
        assert result == []

    def test_build_tool_permission_map_no_tool_manager_returns_empty(self):
        """Lines 371-372: AttributeError → return {}."""
        from concilium.infrastructure.auth.permission_guard import build_tool_permission_map

        result = build_tool_permission_map(self._server_no_tool_manager())
        assert result == {}

    def test_patch_mcp_auth_permissions_no_tool_manager_returns_early(self):
        """Lines 391-393: AttributeError → log warning → return."""
        from concilium.infrastructure.auth.permission_guard import patch_mcp_auth_permissions

        # Should not raise
        patch_mcp_auth_permissions(self._server_no_tool_manager())

    def test_patch_mcp_auth_permissions_tool_without_fn_is_skipped(self):
        """Line 400: tool has no 'fn' attribute → continue."""
        from concilium.infrastructure.auth.permission_guard import patch_mcp_auth_permissions

        tool_no_fn = SimpleNamespace()  # no fn
        server = SimpleNamespace()
        server._tool_manager = SimpleNamespace()
        server._tool_manager._tools = {"tool_a": tool_no_fn}

        # Should not raise; tool_no_fn is skipped via continue
        patch_mcp_auth_permissions(server)


# ---------------------------------------------------------------------------
# completeness.py line 46:
# producao with confianca_pct < 60 → prods_baixa += 1
# completeness.py line 118:
# _find_cpu_by_description: cpu descricao is substring of input → return cpu
# ---------------------------------------------------------------------------


class TestCompletenessAnalyzeProducoes:
    def test_low_confianca_increments_prods_baixa(self):
        """Line 46: producao with confianca_pct=50 < 60 → prods_baixa=1."""
        from concilium.infrastructure.catalog.completeness import _analyze_producoes_quality

        producoes = [
            {"origem": {"tipo": "calibrado_contra_obra_real"}, "qualidade": {"confianca_pct": 50}},
        ]
        prods_reais, prods_tabela, prods_baixa, confianca_media = _analyze_producoes_quality(producoes)
        assert prods_reais == 1
        assert prods_baixa == 1
        assert confianca_media == 50.0

    def test_high_confianca_does_not_increment_prods_baixa(self):
        """Validate that confianca_pct >= 60 is not counted as baixa."""
        from concilium.infrastructure.catalog.completeness import _analyze_producoes_quality

        producoes = [
            {"origem": {}, "qualidade": {"confianca_pct": 80}},
        ]
        _, _, prods_baixa, _ = _analyze_producoes_quality(producoes)
        assert prods_baixa == 0


class TestCompletenessFinCpuByDescription:
    def test_cpu_descricao_substring_of_input_returns_cpu(self):
        """Line 118: cpu.descricao.lower() in descricao_lower → return cpu."""
        from concilium.infrastructure.catalog.completeness import CatalogGapDetector

        detector = CatalogGapDetector()
        cpu_a = {"descricao": "escavação hidráulica"}
        # input is a longer string that contains cpu_a's descricao as substring
        result = detector._find_cpu_by_description("escavação hidráulica de rocha", [cpu_a])
        assert result is cpu_a

    def test_no_match_returns_none(self):
        """Return None when no CPU description matches."""
        from concilium.infrastructure.catalog.completeness import CatalogGapDetector

        detector = CatalogGapDetector()
        cpu_a = {"descricao": "compactação de aterro"}
        result = detector._find_cpu_by_description("escavação hidráulica", [cpu_a])
        assert result is None


# ---------------------------------------------------------------------------
# executive_summary.py line 20:
# _get(dict, key) → isinstance(obj, dict) True → return obj.get(key, default)
# ---------------------------------------------------------------------------


class TestExecutiveSummaryGetDict:
    def test_get_with_dict_returns_value(self):
        """Line 20: obj is dict → return obj.get(key, default)."""
        from concilium.application.runtime.deliverables.reports.executive_summary import _get

        result = _get({"foo": "bar"}, "foo", "default")
        assert result == "bar"

    def test_get_with_dict_missing_key_returns_default(self):
        """Line 20: obj is dict, key missing → return default."""
        from concilium.application.runtime.deliverables.reports.executive_summary import _get

        result = _get({"other": 1}, "foo", "fallback")
        assert result == "fallback"


# ---------------------------------------------------------------------------
# completeness.py lines 30-38: _as_health_status full branch coverage
# ---------------------------------------------------------------------------


class TestCompletenessAsHealthStatus:
    def test_adequado(self):
        from concilium.infrastructure.catalog.completeness import _as_health_status

        assert _as_health_status("ADEQUADO") == "ADEQUADO"

    def test_parcial(self):
        from concilium.infrastructure.catalog.completeness import _as_health_status

        assert _as_health_status("PARCIAL") == "PARCIAL"

    def test_insuficiente(self):
        from concilium.infrastructure.catalog.completeness import _as_health_status

        assert _as_health_status("INSUFICIENTE") == "INSUFICIENTE"

    def test_unexpected_value_raises_value_error(self):
        import pytest

        from concilium.infrastructure.catalog.completeness import _as_health_status

        with pytest.raises(ValueError, match="Status de saúde do catálogo inesperado"):
            _as_health_status("BOGUS")
