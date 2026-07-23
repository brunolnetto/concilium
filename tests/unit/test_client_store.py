"""Coverage batch 4 — small missing-line targets across many files."""

from __future__ import annotations

# client_store.py line 50: no secret_hash, no plaintext → return False
# ---------------------------------------------------------------------------


class TestVerifySecretNoCredentials:
    def test_returns_false_when_no_hash_no_plaintext(self):
        """Line 50: entry has neither secret_hash nor secret → False."""
        from concilium.infrastructure.auth.client_store import _verify_secret

        entry = {"secret_hash": "", "secret": ""}
        assert _verify_secret("any_secret", entry) is False


# ---------------------------------------------------------------------------

