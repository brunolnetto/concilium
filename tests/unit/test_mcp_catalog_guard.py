"""Tests for CatalogMutationGuard and CatalogMutationConflict.

Covers:
  - CatalogMutationConflict.__init__: attributes, defaults, __str__ format
  - CatalogMutationGuard.check_can_mutate:
      Rule 1 — CORROMPIDO raises conflict with correct attrs
      Rule 2 — pipeline_blocked_from non-empty raises conflict
      Rule 3 — EM_EXECUCAO within TTL raises conflict; boundary/elapsed passes
  - Happy paths: no conflict when conditions are clear
  - CatalogMutationGuard.assert_safe_to_mutate: always returns None
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from concilium.presentation.mcp.guards.catalog_guard import (
    TTL_LOCK_SECONDS,
    CatalogMutationConflict,
    CatalogMutationGuard,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_canonical(
    pipeline_integridade: str | None = None,
    pipeline_blocked_from: list[str] | None = None,
    status_projeto: str = "RASCUNHO",
) -> MagicMock:
    """Build a minimal CanonicalModel mock."""
    canonical = MagicMock()
    canonical.pipeline_integridade = pipeline_integridade
    canonical.pipeline_blocked_from = pipeline_blocked_from or []
    projeto = MagicMock()
    projeto.status = status_projeto
    canonical.projeto = projeto
    return canonical


# ── CatalogMutationConflict ───────────────────────────────────────────────────


class TestCatalogMutationConflict:
    def test_basic_attributes(self):
        exc = CatalogMutationConflict(
            project_id="proj-123",
            reason="pipeline corrompido",
            pipeline_integridade="CORROMPIDO",
            blocked_skills=["skill-A", "skill-B"],
        )
        assert exc.project_id == "proj-123"
        assert exc.reason == "pipeline corrompido"
        assert exc.pipeline_integridade == "CORROMPIDO"
        assert exc.blocked_skills == ["skill-A", "skill-B"]

    def test_blocked_skills_defaults_to_empty_list_when_none(self):
        exc = CatalogMutationConflict(project_id="p", reason="r")
        assert exc.blocked_skills == []

    def test_blocked_skills_defaults_to_empty_list_when_omitted(self):
        exc = CatalogMutationConflict(project_id="p", reason="r", blocked_skills=None)
        assert exc.blocked_skills == []

    def test_pipeline_integridade_defaults_to_none(self):
        exc = CatalogMutationConflict(project_id="p", reason="r")
        assert exc.pipeline_integridade is None

    def test_str_contains_project_id_and_reason(self):
        exc = CatalogMutationConflict(project_id="proj-42", reason="motivo X")
        msg = str(exc)
        assert "proj-42" in msg
        assert "motivo X" in msg

    def test_str_format_prefix(self):
        exc = CatalogMutationConflict(project_id="proj-42", reason="motivo X")
        assert str(exc).startswith("[CatalogMutationConflict]")

    def test_is_exception(self):
        exc = CatalogMutationConflict(project_id="p", reason="r")
        assert isinstance(exc, Exception)


# ── CatalogMutationGuard — Rule 1: CORROMPIDO ─────────────────────────────────


class TestRule1Corrompido:
    def setup_method(self):
        self.guard = CatalogMutationGuard()

    def test_raises_when_corrompido(self):
        canonical = _make_canonical(pipeline_integridade="CORROMPIDO")
        with pytest.raises(CatalogMutationConflict):
            self.guard.check_can_mutate(project_id="proj-1", canonical=canonical)

    def test_conflict_has_correct_project_id(self):
        canonical = _make_canonical(pipeline_integridade="CORROMPIDO")
        with pytest.raises(CatalogMutationConflict) as exc_info:
            self.guard.check_can_mutate(project_id="proj-1", canonical=canonical)
        assert exc_info.value.project_id == "proj-1"

    def test_conflict_pipeline_integridade_is_corrompido(self):
        canonical = _make_canonical(pipeline_integridade="CORROMPIDO")
        with pytest.raises(CatalogMutationConflict) as exc_info:
            self.guard.check_can_mutate(project_id="proj-1", canonical=canonical)
        assert exc_info.value.pipeline_integridade == "CORROMPIDO"

    def test_conflict_blocked_skills_populated(self):
        canonical = _make_canonical(
            pipeline_integridade="CORROMPIDO",
            pipeline_blocked_from=["skill-gate-1", "skill-gate-2"],
        )
        with pytest.raises(CatalogMutationConflict) as exc_info:
            self.guard.check_can_mutate(project_id="proj-1", canonical=canonical)
        assert exc_info.value.blocked_skills == ["skill-gate-1", "skill-gate-2"]

    def test_conflict_blocked_skills_empty_when_none_blocked(self):
        canonical = _make_canonical(pipeline_integridade="CORROMPIDO", pipeline_blocked_from=[])
        with pytest.raises(CatalogMutationConflict) as exc_info:
            self.guard.check_can_mutate(project_id="proj-1", canonical=canonical)
        assert exc_info.value.blocked_skills == []

    def test_conflict_reason_mentions_corrompido(self):
        canonical = _make_canonical(pipeline_integridade="CORROMPIDO")
        with pytest.raises(CatalogMutationConflict) as exc_info:
            self.guard.check_can_mutate(project_id="proj-1", canonical=canonical)
        assert "CORROMPIDO" in exc_info.value.reason

    def test_corrompido_blocks_even_when_status_ok(self):
        """CORROMPIDO should block unconditionally regardless of project status."""
        canonical = _make_canonical(
            pipeline_integridade="CORROMPIDO",
            status_projeto="RASCUNHO",
        )
        with pytest.raises(CatalogMutationConflict):
            self.guard.check_can_mutate(project_id="proj-1", canonical=canonical)


# ── CatalogMutationGuard — Rule 2: blocked_from non-empty ────────────────────


class TestRule2BlockedFrom:
    def setup_method(self):
        self.guard = CatalogMutationGuard()

    def test_raises_when_pipeline_blocked_from_nonempty(self):
        canonical = _make_canonical(
            pipeline_integridade="OK",
            pipeline_blocked_from=["skill-gate-3"],
        )
        with pytest.raises(CatalogMutationConflict):
            self.guard.check_can_mutate(project_id="proj-2", canonical=canonical)

    def test_conflict_blocked_skills_match(self):
        canonical = _make_canonical(
            pipeline_integridade="OK",
            pipeline_blocked_from=["skill-A", "skill-B"],
        )
        with pytest.raises(CatalogMutationConflict) as exc_info:
            self.guard.check_can_mutate(project_id="proj-2", canonical=canonical)
        assert exc_info.value.blocked_skills == ["skill-A", "skill-B"]

    def test_conflict_project_id_correct(self):
        canonical = _make_canonical(
            pipeline_blocked_from=["skill-X"],
        )
        with pytest.raises(CatalogMutationConflict) as exc_info:
            self.guard.check_can_mutate(project_id="meu-projeto", canonical=canonical)
        assert exc_info.value.project_id == "meu-projeto"

    def test_conflict_pipeline_integridade_forwarded(self):
        canonical = _make_canonical(
            pipeline_integridade="PARCIAL",
            pipeline_blocked_from=["skill-X"],
        )
        with pytest.raises(CatalogMutationConflict) as exc_info:
            self.guard.check_can_mutate(project_id="proj-2", canonical=canonical)
        assert exc_info.value.pipeline_integridade == "PARCIAL"

    def test_conflict_reason_mentions_skills(self):
        canonical = _make_canonical(
            pipeline_blocked_from=["gate-skill-99"],
        )
        with pytest.raises(CatalogMutationConflict) as exc_info:
            self.guard.check_can_mutate(project_id="proj-2", canonical=canonical)
        assert "gate-skill-99" in exc_info.value.reason

    def test_multiple_blocked_skills_all_in_reason(self):
        canonical = _make_canonical(
            pipeline_blocked_from=["skill-A", "skill-B", "skill-C"],
        )
        with pytest.raises(CatalogMutationConflict) as exc_info:
            self.guard.check_can_mutate(project_id="proj-2", canonical=canonical)
        reason = exc_info.value.reason
        assert "skill-A" in reason
        assert "skill-B" in reason
        assert "skill-C" in reason


# ── CatalogMutationGuard — Rule 3: EM_EXECUCAO + TTL ─────────────────────────


class TestRule3EmExecucaoTTL:
    def setup_method(self):
        self.guard = CatalogMutationGuard()

    def test_raises_when_within_ttl(self):
        canonical = _make_canonical(status_projeto="EM_EXECUCAO")
        run_started_at = datetime.now(UTC) - timedelta(seconds=60)  # 1 min ago
        with pytest.raises(CatalogMutationConflict):
            self.guard.check_can_mutate(
                project_id="proj-3",
                canonical=canonical,
                run_started_at=run_started_at,
            )

    def test_remaining_minutes_in_reason(self):
        canonical = _make_canonical(status_projeto="EM_EXECUCAO")
        fixed_now = datetime(2025, 6, 1, 10, 0, 0, tzinfo=UTC)
        # started 60 seconds before fixed_now → (TTL - 60) seconds remain
        run_started_at = fixed_now - timedelta(seconds=60)
        with patch(
            "concilium.presentation.mcp.guards.catalog_guard.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = fixed_now
            with pytest.raises(CatalogMutationConflict) as exc_info:
                self.guard.check_can_mutate(
                    project_id="proj-3",
                    canonical=canonical,
                    run_started_at=run_started_at,
                )
        reason = exc_info.value.reason
        expected_minutes = int((TTL_LOCK_SECONDS - 60) / 60)
        assert str(expected_minutes) in reason

    def test_conflict_project_id_correct(self):
        canonical = _make_canonical(status_projeto="EM_EXECUCAO")
        run_started_at = datetime.now(UTC)
        with pytest.raises(CatalogMutationConflict) as exc_info:
            self.guard.check_can_mutate(
                project_id="meu-projeto-exec",
                canonical=canonical,
                run_started_at=run_started_at,
            )
        assert exc_info.value.project_id == "meu-projeto-exec"

    def test_passes_when_ttl_elapsed(self):
        """When run started more than TTL ago, no conflict should be raised."""
        canonical = _make_canonical(status_projeto="EM_EXECUCAO")
        run_started_at = datetime.now(UTC) - timedelta(seconds=TTL_LOCK_SECONDS + 10)
        # Should not raise
        result = self.guard.check_can_mutate(
            project_id="proj-3",
            canonical=canonical,
            run_started_at=run_started_at,
        )
        assert result is None

    def test_passes_when_run_started_at_is_none(self):
        """No run_started_at → Rule 3 cannot apply."""
        canonical = _make_canonical(status_projeto="EM_EXECUCAO")
        result = self.guard.check_can_mutate(
            project_id="proj-3",
            canonical=canonical,
            run_started_at=None,
        )
        assert result is None

    def test_passes_when_status_is_not_em_execucao(self):
        """Different status → Rule 3 does not apply even with recent run."""
        canonical = _make_canonical(status_projeto="CONCLUIDO")
        run_started_at = datetime.now(UTC)
        result = self.guard.check_can_mutate(
            project_id="proj-3",
            canonical=canonical,
            run_started_at=run_started_at,
        )
        assert result is None

    def test_boundary_exactly_at_lock_until_passes(self):
        """now == lock_until exactly → condition is now < lock_until, so should pass."""
        canonical = _make_canonical(status_projeto="EM_EXECUCAO")
        fixed_now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        run_started_at = fixed_now - timedelta(seconds=TTL_LOCK_SECONDS)
        # At boundary: now == lock_until, condition is strictly <, so no raise
        with patch(
            "concilium.presentation.mcp.guards.catalog_guard.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = fixed_now
            result = self.guard.check_can_mutate(
                project_id="proj-3",
                canonical=canonical,
                run_started_at=run_started_at,
            )
        assert result is None

    def test_one_second_before_lock_until_raises(self):
        """now == lock_until - 1s → still within TTL → raises."""
        canonical = _make_canonical(status_projeto="EM_EXECUCAO")
        fixed_now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        run_started_at = fixed_now - timedelta(seconds=TTL_LOCK_SECONDS - 1)
        with patch(
            "concilium.presentation.mcp.guards.catalog_guard.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = fixed_now
            with pytest.raises(CatalogMutationConflict):
                self.guard.check_can_mutate(
                    project_id="proj-3",
                    canonical=canonical,
                    run_started_at=run_started_at,
                )


# ── Happy paths ───────────────────────────────────────────────────────────────


class TestHappyPath:
    def setup_method(self):
        self.guard = CatalogMutationGuard()

    def test_returns_none_when_all_clear(self):
        canonical = _make_canonical(
            pipeline_integridade="OK",
            pipeline_blocked_from=[],
            status_projeto="RASCUNHO",
        )
        result = self.guard.check_can_mutate(project_id="proj-ok", canonical=canonical)
        assert result is None

    def test_returns_none_with_none_integridade(self):
        canonical = _make_canonical(
            pipeline_integridade=None,
            pipeline_blocked_from=[],
            status_projeto="RASCUNHO",
        )
        result = self.guard.check_can_mutate(project_id="proj-ok", canonical=canonical)
        assert result is None

    def test_returns_none_with_projeto_none(self):
        """canonical.projeto is None → status defaults to RASCUNHO, should pass."""
        canonical = MagicMock()
        canonical.pipeline_integridade = "OK"
        canonical.pipeline_blocked_from = []
        canonical.projeto = None
        result = self.guard.check_can_mutate(project_id="proj-ok", canonical=canonical)
        assert result is None

    def test_em_execucao_without_run_started_at_passes(self):
        canonical = _make_canonical(
            pipeline_integridade="OK",
            pipeline_blocked_from=[],
            status_projeto="EM_EXECUCAO",
        )
        result = self.guard.check_can_mutate(
            project_id="proj-ok",
            canonical=canonical,
            run_started_at=None,
        )
        assert result is None

    def test_concluido_with_recent_run_passes(self):
        canonical = _make_canonical(
            pipeline_integridade="OK",
            pipeline_blocked_from=[],
            status_projeto="CONCLUIDO",
        )
        run_started_at = datetime.now(UTC)
        result = self.guard.check_can_mutate(
            project_id="proj-ok",
            canonical=canonical,
            run_started_at=run_started_at,
        )
        assert result is None


# ── assert_safe_to_mutate ─────────────────────────────────────────────────────


class TestAssertSafeToMutate:
    def setup_method(self):
        self.guard = CatalogMutationGuard()

    def test_returns_none_no_args(self):
        result = self.guard.assert_safe_to_mutate(project_id="proj-x")
        assert result is None

    def test_returns_none_with_catalog_name(self):
        result = self.guard.assert_safe_to_mutate(
            project_id="proj-x", catalog_name="mendeslobo"
        )
        assert result is None

    def test_returns_none_empty_catalog_name(self):
        result = self.guard.assert_safe_to_mutate(
            project_id="proj-x", catalog_name=""
        )
        assert result is None

    def test_does_not_raise(self):
        """assert_safe_to_mutate must never raise (no canonical available)."""
        try:
            self.guard.assert_safe_to_mutate(project_id="any-proj")
        except Exception as exc:
            pytest.fail(f"assert_safe_to_mutate raised unexpectedly: {exc}")
