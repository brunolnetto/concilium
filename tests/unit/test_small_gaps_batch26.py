"""Coverage batch 26 — auth_store, report_markdown_sections small gaps
+ pragma annotations for double-checked locking singletons."""

from __future__ import annotations

from unittest.mock import patch

# ---------------------------------------------------------------------------
# auth_store.py line 349->348: use_refresh_token loop → token_id not found
# auth_store.py line 372->371: revoke_device loop → device_id mismatch on some tokens
# auth_store.py line 406->405: get_revoke_pending loop → token not found
# auth_store.py line 423->422: confirm_revoke loop → token not found
# ---------------------------------------------------------------------------


def _setup_store_with_token(tmp_path, client_id="cli-1", device_id="dev-1"):
    """Create AuthStore, register a client, and issue one refresh token."""
    from concilium.infrastructure.auth.auth_store import AuthStore

    store = AuthStore(data_dir=tmp_path)
    client_code = f"RCODE-{client_id}"
    store.add_client(client_id, "secret", ["operator"], client_code=client_code)
    rt = store.activate_device_code(client_code, device_name=device_id)
    return store, rt


class TestAuthStoreRefreshTokenLoopMisses:
    def test_use_refresh_token_returns_none_when_no_match(self, tmp_path):
        """Line 349->348: token_id loop False branch → no match → returns None."""
        store, rt = _setup_store_with_token(tmp_path)
        # Real token exists but we query a different id → loop iterates, no match
        result = store.use_refresh_token("RT-NONEXISTENT-TOKEN-ID")
        assert result is None

    def test_revoke_device_covers_mismatch_branch(self, tmp_path):
        """Line 372->371: two tokens with different device_ids → loop hits False for non-target."""
        from concilium.infrastructure.auth.auth_store import AuthStore

        store = AuthStore(data_dir=tmp_path)
        store.add_client("c1", "s1", ["operator"], client_code="RCODE-c1")

        # Issue token for device-A and device-B via the same reusable client_code
        store.activate_device_code("RCODE-c1", device_name="dev-A")
        store.activate_device_code("RCODE-c1", device_name="dev-B")

        # Revoking device-A: the loop hits dev-B's token → if device_id==dev-A: False
        count = store.revoke_device("dev-A")
        assert count >= 1  # at least one token was revoked


class TestAuthStoreRevokePendingLoopMisses:
    def test_get_revoke_pending_returns_none_when_token_not_found(self, tmp_path):
        """Line 406->405: loop iterates existing records, none match → return None."""
        store, _ = _setup_store_with_token(tmp_path)
        # Create a real revoke pending record
        store.create_revoke_pending("cli-1", "dev-1")
        # Query with a different token
        result = store.get_revoke_pending("NONEXISTENT-REVOKE-TOKEN")
        assert result is None

    def test_confirm_revoke_returns_false_when_token_not_found(self, tmp_path):
        """Line 423->422: loop iterates, none match → found=False → return False."""
        store, _ = _setup_store_with_token(tmp_path)
        store.create_revoke_pending("cli-1", "dev-1")
        # Confirm with wrong token → loop finds no match → return False
        result = store.confirm_revoke("WRONG-TOKEN")
        assert result is False


# ---------------------------------------------------------------------------
# report_markdown_sections.py line 418->438:
# top_neg empty (no rows with economia < 0) → if top_neg: False → line 438
# ---------------------------------------------------------------------------


class TestRenderPoolEconomiaOrigemNoNegRows:
    def test_top_neg_empty_skips_sobrecusto_section(self):
        """Line 418->438: no negative economia rows → if top_neg: False → skip to ---."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import (
            render_pool_economia_origem,
        )

        # Return eco rows with economia > 0 only (no negatives for top_neg)
        eco_rows = [{"atividade_id": "ACT-01", "custo_autonomo": 1000.0, "economia": 500.0}]
        eco_proj = {"rows": eco_rows, "operator_meta": {}}
        causa_proj = {"rows": []}

        with patch(
            "concilium.application.services.analytics.cubo_pool_projection.resolve_cubo_pool_projection",
            return_value=eco_proj,
        ) as mock_fn:
            # First call → eco_proj, second call → causa_proj
            mock_fn.side_effect = [eco_proj, causa_proj]

            canonical = object()  # just needs to be non-None
            result = render_pool_economia_origem(canonical)

        # Section header present (eco_rows non-empty), "---" present, but no "Sobrecusto"
        full_text = "\n".join(result)
        assert "Economia por Compartilhamento" in full_text
        assert "---" in full_text
        assert "Sobrecusto" not in full_text
