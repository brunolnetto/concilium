"""Coverage batch 10 — concilium_service delegation methods and validation errors."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from concilium.application.services.concilium_service import ConciliumService


def _make_svc():
    deps = MagicMock()
    deps.input_builder._config_root = Path("/nonexistent_fake_root_abc123")
    return ConciliumService(dependencies=deps)


# Lines 742-744: _resolve_cubo_projection_rows delegates to imported fn
# Lines 751-753: _bucket_from_week_iso delegates
# Lines 762-764: _resolve_abc_curva_rows delegates
# Lines 772-774: _resolve_s_curve_rows delegates
# Lines 782-784: _resolve_recursos_ativos_rows delegates
# ---------------------------------------------------------------------------


class TestConciliumServiceStaticDelegates:
    def test_resolve_cubo_projection_rows(self):
        """Lines 742-744: calls resolve_cubo_projection_rows and returns result."""
        mock_result = ([], [], "face_label")
        with patch(
            "concilium.application.services.analytics.cube_projection_views.resolve_cubo_projection_rows",
            return_value=mock_result,
        ) as mock_fn:
            result = ConciliumService._resolve_cubo_projection_rows(MagicMock(), "tempo_natureza", "mes", 50)
        assert result == mock_result
        mock_fn.assert_called_once()

    def test_bucket_from_week_iso(self):
        """Lines 751-753: calls bucket_from_week_iso and returns result."""
        with patch(
            "concilium.application.services.analytics.cube_projection_views.bucket_from_week_iso",
            return_value="2024-01",
        ) as mock_fn:
            result = ConciliumService._bucket_from_week_iso("2024-W01", "mes")
        assert result == "2024-01"
        mock_fn.assert_called_once()

    def test_resolve_abc_curva_rows(self):
        """Lines 762-764: calls resolve_abc_curva_rows and returns result."""
        svc = _make_svc()
        mock_result = ([], [], "abc_label", "abc_type", {})
        with patch(
            "concilium.application.services.analytics.cube_projection_views.resolve_abc_curva_rows",
            return_value=mock_result,
        ) as mock_fn:
            result = svc._resolve_abc_curva_rows(MagicMock(), 10, 0.8, 0.95)
        assert result == mock_result
        mock_fn.assert_called_once()

    def test_resolve_s_curve_rows(self):
        """Lines 772-774: calls resolve_s_curve_rows and returns result."""
        svc = _make_svc()
        mock_result = ([], [], "s_curve_label", "s_curve_type", {})
        with patch(
            "concilium.application.services.analytics.cube_projection_views.resolve_s_curve_rows",
            return_value=mock_result,
        ) as mock_fn:
            result = svc._resolve_s_curve_rows(MagicMock(), "mes", 50)
        assert result == mock_result
        mock_fn.assert_called_once()

    def test_resolve_recursos_ativos_rows(self):
        """Lines 782-784: calls resolve_recursos_ativos_rows and returns result."""
        svc = _make_svc()
        mock_result = ([], [], "recursos_label", "recursos_type", {})
        with patch(
            "concilium.application.services.analytics.cube_projection_views.resolve_recursos_ativos_rows",
            return_value=mock_result,
        ) as mock_fn:
            result = svc._resolve_recursos_ativos_rows(MagicMock(), "mes", 50)
        assert result == mock_result
        mock_fn.assert_called_once()


# ---------------------------------------------------------------------------


# Lines 839, 841, 843, 852, 854, 858: raise ValueError on invalid projection params
# ---------------------------------------------------------------------------


class TestConciliumProjectionValidationErrors:
    def _svc_with_contract(self):
        svc = _make_svc()
        return svc

    def test_invalid_categoria_raises(self):
        """Line 839: valid face + granularidade but invalid categoria → ValueError."""
        svc = self._svc_with_contract()
        with pytest.raises(ValueError, match="Categoria inválida"):
            svc.get_cubo_analitico_projection(
                "proj-01",
                face="tempo_natureza",
                granularidade="mes",
                categoria="INVALID_CATEGORY",
            )

    def test_invalid_componente_bdi_raises(self):
        """Line 841: valid face + granularidade but invalid componente_bdi → ValueError."""
        svc = self._svc_with_contract()
        with pytest.raises(ValueError, match="Componente BDI inválido"):
            svc.get_cubo_analitico_projection(
                "proj-01",
                face="tempo_natureza",
                granularidade="mes",
                componente_bdi="INVALID_COMP",
            )

    def test_invalid_abc_thresholds_raises(self):
        """Line 843: abc_threshold_a >= abc_threshold_b → ValueError."""
        svc = self._svc_with_contract()
        with pytest.raises(ValueError, match="Thresholds ABC inválidos"):
            svc.get_cubo_analitico_projection(
                "proj-01",
                face="tempo_natureza",
                granularidade="mes",
                abc_threshold_a=0.9,
                abc_threshold_b=0.5,  # b < a
            )

    def test_invalid_measure_profile_raises(self):
        """Line 852: measure_profile not in allowed_measure_profile → ValueError."""
        svc = self._svc_with_contract()
        with pytest.raises(ValueError, match="Measure profile"):
            svc.get_cubo_analitico_projection(
                "proj-01",
                face="tempo_natureza",
                granularidade="mes",
                measure_profile="INVALID_PROFILE",
            )

    def test_invalid_aggregation_mode_raises(self):
        """Line 854: aggregation_mode not in allowed → ValueError."""
        svc = self._svc_with_contract()
        with pytest.raises(ValueError, match="Aggregation mode"):
            svc.get_cubo_analitico_projection(
                "proj-01",
                face="tempo_natureza",
                granularidade="mes",
                aggregation_mode="INVALID_MODE",
            )


# ---------------------------------------------------------------------------


# Line 481: get_version_history delegation
# ---------------------------------------------------------------------------


class TestConciliumVersionHistory:
    def test_get_version_history_delegates(self):
        """Line 481: get_version_history delegates to project_service."""
        svc = _make_svc()
        svc._dependencies.project_service.get_version_history.return_value = {"v1": {}}
        result = svc.get_version_history("proj-01")
        assert result == {"v1": {}}
        svc._dependencies.project_service.get_version_history.assert_called_once_with("proj-01")


# ---------------------------------------------------------------------------


# Line 655: get_cubo_pool_projection returns early when canonical is None
# ---------------------------------------------------------------------------


class TestConciliumCuboPoolProjectionNone:
    def test_returns_empty_when_canonical_none(self):
        """Line 655: _load_canonical_for_version returns None → early return."""
        svc = _make_svc()
        with patch.object(svc, "_load_canonical_for_version", return_value=(None, "v1")):
            result = svc.get_cubo_pool_projection("proj-01", version="v1", face="instancial")
        assert result["rows"] == []


# ---------------------------------------------------------------------------


# concilium_service/_project_crud.py — ownership passthrough methods
# (get_project_owner, find_projects_by_owner, transfer_ownership_forced,
# create_ownership_transfer_pending, accept_ownership_transfer,
# reject_ownership_transfer) delegate straight to project_service.
# ---------------------------------------------------------------------------


class TestProjectCrudOwnershipDelegation:
    def test_get_project_owner_delegates_to_project_service(self):
        svc = _make_svc()
        svc._dependencies.project_service.get_project_owner.return_value = "user-1"
        result = svc.get_project_owner("proj-1")
        assert result == "user-1"
        svc._dependencies.project_service.get_project_owner.assert_called_once_with("proj-1")

    def test_get_project_owner_returns_none_when_unowned(self):
        svc = _make_svc()
        svc._dependencies.project_service.get_project_owner.return_value = None
        assert svc.get_project_owner("proj-1") is None

    def test_find_projects_by_owner_delegates_to_project_service(self):
        svc = _make_svc()
        svc._dependencies.project_service.find_projects_by_owner.return_value = ["proj-1", "proj-2"]
        result = svc.find_projects_by_owner("owner-1")
        assert result == ["proj-1", "proj-2"]
        svc._dependencies.project_service.find_projects_by_owner.assert_called_once_with("owner-1")

    def test_transfer_ownership_forced_delegates_to_project_service(self):
        svc = _make_svc()
        svc._dependencies.project_service.transfer_ownership_forced.return_value = {"owner_id": "owner-2"}
        result = svc.transfer_ownership_forced("proj-1", "owner-2", "admin-actor")
        assert result == {"owner_id": "owner-2"}
        svc._dependencies.project_service.transfer_ownership_forced.assert_called_once_with(
            "proj-1", "owner-2", "admin-actor"
        )

    def test_create_ownership_transfer_pending_delegates_to_project_service(self):
        svc = _make_svc()
        svc._dependencies.project_service.create_ownership_transfer_pending.return_value = {"token": "tok-1"}
        result = svc.create_ownership_transfer_pending("proj-1", "owner-2", "owner-1")
        assert result == {"token": "tok-1"}
        svc._dependencies.project_service.create_ownership_transfer_pending.assert_called_once_with(
            "proj-1", "owner-2", "owner-1"
        )

    def test_accept_ownership_transfer_delegates_to_project_service(self):
        svc = _make_svc()
        svc._dependencies.project_service.accept_ownership_transfer.return_value = {"owner_id": "owner-2"}
        result = svc.accept_ownership_transfer("proj-1", "tok-1", "owner-2")
        assert result == {"owner_id": "owner-2"}
        svc._dependencies.project_service.accept_ownership_transfer.assert_called_once_with(
            "proj-1", "tok-1", "owner-2"
        )

    def test_reject_ownership_transfer_delegates_to_project_service(self):
        svc = _make_svc()
        svc._dependencies.project_service.reject_ownership_transfer.return_value = {"owner_id": "owner-1"}
        result = svc.reject_ownership_transfer("proj-1", "tok-1", "owner-2")
        assert result == {"owner_id": "owner-1"}
        svc._dependencies.project_service.reject_ownership_transfer.assert_called_once_with(
            "proj-1", "tok-1", "owner-2"
        )

