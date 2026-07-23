"""Coverage sweep 2 — medium missing-line files (8-25 lines)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

# ─── overrides API routes ─────────────────────────────────────────────────────


class TestOverridesRoutes:
    def _svc(self):
        return MagicMock()

    def test_list_overrides_ok(self):
        from concilium.presentation.api.routes.overrides import list_overrides

        svc = self._svc()
        svc.list_overrides.return_value = {"skill-01": {"x": 1}}
        result = list_overrides("proj-1", service=svc)
        assert "skill-01" in result

    def test_list_overrides_not_found(self):
        from concilium.presentation.api.routes.overrides import list_overrides

        svc = self._svc()
        svc.list_overrides.side_effect = FileNotFoundError("nope")
        with pytest.raises(HTTPException) as exc:
            list_overrides("proj-1", service=svc)
        assert exc.value.status_code == 404

    def test_upsert_override_ok(self):
        from concilium.presentation.api.routes.overrides import upsert_override

        svc = self._svc()
        svc.upsert_override.return_value = {"skill-01": {"new": True}}
        req = MagicMock()
        req.skill_id = "skill-01"
        req.inputs = {"new": True}
        result = upsert_override("proj-1", req, x_user="eng", service=svc)
        assert "skill-01" in result

    def test_upsert_override_not_found(self):
        from concilium.presentation.api.routes.overrides import upsert_override

        svc = self._svc()
        svc.upsert_override.side_effect = FileNotFoundError("nope")
        req = MagicMock()
        req.skill_id = "skill-01"
        req.inputs = {}
        with pytest.raises(HTTPException) as exc:
            upsert_override("proj-1", req, x_user="eng", service=svc)
        assert exc.value.status_code == 404

    def test_delete_override_ok(self):
        from concilium.presentation.api.routes.overrides import delete_override

        svc = self._svc()
        svc.delete_override.return_value = {"deleted": "skill-01"}
        result = delete_override("proj-1", "skill-01", x_user="eng", service=svc)
        assert result["deleted"] == "skill-01"

    def test_delete_override_not_found(self):
        from concilium.presentation.api.routes.overrides import delete_override

        svc = self._svc()
        svc.delete_override.side_effect = FileNotFoundError("nope")
        with pytest.raises(HTTPException) as exc:
            delete_override("proj-1", "skill-01", x_user="eng", service=svc)
        assert exc.value.status_code == 404



