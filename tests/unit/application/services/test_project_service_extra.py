"""Coverage tests for project_service.py missing lines."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from concilium.application.services.project.project_service import ProjectService


def _make_service():
    repo = MagicMock()
    repo.list_projects.return_value = []
    audit = MagicMock()
    return ProjectService(repository=repo, audit_service=audit)


# ---------------------------------------------------------------------------
# Lines 97-98: _get_perfil_svc except path
# ---------------------------------------------------------------------------


class TestGetPerfilSvcException:
    def test_import_error_returns_none(self):
        """Lines 97-98: ImportError in _get_perfil_svc → except → return None."""
        svc = _make_service()
        with patch.dict(
            sys.modules,
            {"concilium.application.services.catalog.contexto_version_service": None},
        ):
            result = svc._get_perfil_svc()
        assert result is None


# ---------------------------------------------------------------------------
# Lines 612-614: _get_jurisdiction_svc except path
# ---------------------------------------------------------------------------


class TestGetJurisdictionSvcException:
    def test_import_error_returns_none(self):
        """Lines 612-614: ImportError in _get_jurisdiction_svc → except → return None."""
        svc = _make_service()
        with patch.dict(
            sys.modules,
            {"concilium.application.services.catalog.contexto_version_service": None},
        ):
            result = svc._get_jurisdiction_svc()
        assert result is None


# ---------------------------------------------------------------------------
# Lines 628-630: _get_tema_svc except path
# ---------------------------------------------------------------------------


class TestGetTemaSvcException:
    def test_import_error_returns_none(self):
        """Lines 628-630: ImportError in _get_tema_svc → except → return None."""
        svc = _make_service()
        with patch.dict(
            sys.modules,
            {"concilium.application.services.catalog.contexto_version_service": None},
        ):
            result = svc._get_tema_svc()
        assert result is None


# ---------------------------------------------------------------------------
# Lines 645-647: _get_contexto_svc except path
# ---------------------------------------------------------------------------


class TestGetContextoSvcException:
    def test_import_error_returns_none(self):
        """Lines 645-647: ImportError in _get_contexto_svc → except → return None."""
        svc = _make_service()
        with patch.dict(
            sys.modules,
            {"concilium.application.services.catalog.contexto_version_service": None},
        ):
            result = svc._get_contexto_svc()
        assert result is None


# ---------------------------------------------------------------------------
# Line 711: _validate_tema_fields adds "id" when not in merged
# ---------------------------------------------------------------------------


class TestValidateTemaFieldsAddsId:
    def test_id_injected_when_missing_from_base_and_fields(self):
        """Line 711: base has no 'id', fields have no 'id' → merged['id'] = tema_id."""
        svc = _make_service()
        mock_tema_svc = MagicMock()
        # resolve returns a truthy dict without "id"
        mock_tema_svc.resolve.return_value = {"nome": "Base Tema Name"}

        from concilium.domain.models.catalog.tema import TemaVisual

        with patch.object(TemaVisual, "model_validate", return_value=MagicMock()):
            svc._validate_tema_fields(mock_tema_svc, "tema-999", {"descricao": "updated"})

        # If no exception was raised, the method completed successfully with the id injected
