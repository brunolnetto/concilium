"""Tests for notify_catalog_drafts_pending (ADR-141 F4)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _patched_service():
    mock_service = MagicMock()
    patcher = patch(
        "concilium.application.services.notifications.get_notification_service",
        return_value=mock_service,
    )
    return patcher, mock_service


class TestNotifyCatalogDraftsPending:
    def test_sends_generic_template_with_consolidated_details(self):
        from concilium.application.services.notifications import notify_catalog_drafts_pending

        rascunhos_por_contexto = {
            "mendeslobo": [
                {"version": "v2", "motivo": "rascunho: reajuste INCC", "created_by": "engineer1"},
            ],
            "rfi-r02": [
                {"version": "v5", "motivo": "rascunho: correção diesel", "created_by": "engineer2"},
            ],
        }

        patcher, mock_service = _patched_service()
        mock_service.send.return_value = True
        with patcher:
            result = notify_catalog_drafts_pending("mgr@x.com", rascunhos_por_contexto)

        assert result is True
        mock_service.send.assert_called_once()
        kwargs = mock_service.send.call_args.kwargs
        assert kwargs["to"] == "mgr@x.com"
        assert kwargs["template"] == "notification"
        assert "2" in kwargs["subject"]
        assert kwargs["context"]["cta"] is None
        details = kwargs["context"]["details"]
        assert len(details) == 2
        joined = " ".join(f"{k} {v}" for k, v in details)
        assert "mendeslobo" in joined
        assert "v2" in joined
        assert "engineer1" in joined
        assert "rfi-r02" in joined
        assert "v5" in joined

    def test_returns_false_when_send_fails(self):
        from concilium.application.services.notifications import notify_catalog_drafts_pending

        patcher, mock_service = _patched_service()
        mock_service.send.return_value = False
        with patcher:
            result = notify_catalog_drafts_pending("mgr@x.com", {"mendeslobo": [{"version": "v2", "motivo": "x"}]})

        assert result is False

    def test_subject_counts_total_rascunhos_across_contextos(self):
        from concilium.application.services.notifications import notify_catalog_drafts_pending

        rascunhos_por_contexto = {
            "mendeslobo": [
                {"version": "v2", "motivo": "a"},
                {"version": "v3", "motivo": "b"},
            ],
            "rfi-r02": [
                {"version": "v5", "motivo": "c"},
            ],
        }

        patcher, mock_service = _patched_service()
        with patcher:
            notify_catalog_drafts_pending("mgr@x.com", rascunhos_por_contexto)

        kwargs = mock_service.send.call_args.kwargs
        assert "3" in kwargs["subject"]
