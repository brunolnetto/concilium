"""Tests for: backtracking_pe models, jwt_config, cpu_mapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ─── infrastructure/auth/jwt_config.py ────────────────────────────────────────


class TestReadPem:
    def test_read_pem_from_env_var(self, monkeypatch):
        from concilium.infrastructure.auth.jwt_config import _read_pem

        monkeypatch.setenv("CONCILIUM__JWT_PRIVATE_KEY_PEM", "-----BEGIN RSA PRIVATE KEY-----\ntest\n")
        auth_mock = MagicMock()
        auth_mock.jwt_private_key_pem = ""
        auth_mock.jwt_private_key_path = ""
        auth_mock.jwt_public_key_pem = ""
        auth_mock.jwt_public_key_path = ""
        auth_mock.key_vault_url = ""
        with patch("concilium.infrastructure.auth.jwt_config.get_auth", return_value=auth_mock):
            result = _read_pem("CONCILIUM__JWT_PRIVATE_KEY_PEM", "CONCILIUM__JWT_PRIVATE_KEY_PATH", kv_secret="x")
        assert result is not None
        assert b"RSA" in result

    def test_read_pem_from_path(self, tmp_path, monkeypatch):
        from concilium.infrastructure.auth.jwt_config import _read_pem

        pem_file = tmp_path / "key.pem"
        pem_file.write_bytes(b"-----BEGIN RSA PRIVATE KEY-----\nfakepem\n")
        monkeypatch.delenv("CONCILIUM__JWT_PRIVATE_KEY_PEM", raising=False)
        auth_mock = MagicMock()
        auth_mock.jwt_private_key_pem = ""
        auth_mock.jwt_private_key_path = str(pem_file)
        auth_mock.key_vault_url = ""
        with patch("concilium.infrastructure.auth.jwt_config.get_auth", return_value=auth_mock):
            result = _read_pem("CONCILIUM__JWT_PRIVATE_KEY_PEM", "CONCILIUM__JWT_PRIVATE_KEY_PATH", kv_secret="x")
        assert result == pem_file.read_bytes()

    def test_read_pem_key_vault_no_url_returns_none(self, monkeypatch):
        from concilium.infrastructure.auth.jwt_config import _read_pem

        monkeypatch.delenv("CONCILIUM__JWT_PRIVATE_KEY_PEM", raising=False)
        auth_mock = MagicMock()
        auth_mock.jwt_private_key_pem = ""
        auth_mock.jwt_private_key_path = ""
        auth_mock.key_vault_url = ""
        with patch("concilium.infrastructure.auth.jwt_config.get_auth", return_value=auth_mock):
            result = _read_pem("CONCILIUM__JWT_PRIVATE_KEY_PEM", "CONCILIUM__JWT_PRIVATE_KEY_PATH", kv_secret="x")
        assert result is None

    def test_read_from_key_vault_import_error(self, monkeypatch):
        from concilium.infrastructure.auth.jwt_config import _read_from_key_vault

        auth_mock = MagicMock()
        auth_mock.key_vault_url = "https://myvault.vault.azure.net"
        with (
            patch("concilium.infrastructure.auth.jwt_config.get_auth", return_value=auth_mock),
            patch.dict("sys.modules", {"azure.identity": None, "azure.keyvault.secrets": None}),
        ):
            import warnings

            with warnings.catch_warnings(record=True):
                result = _read_from_key_vault("jwt-private-key")
        assert result is None

    def test_read_from_key_vault_exception_warns(self, monkeypatch):
        from concilium.infrastructure.auth.jwt_config import _read_from_key_vault

        auth_mock = MagicMock()
        auth_mock.key_vault_url = "https://myvault.vault.azure.net"
        azure_identity_mock = MagicMock()
        azure_secrets_mock = MagicMock()
        secret_client_mock = MagicMock()
        secret_client_mock.get_secret.side_effect = Exception("auth failed")
        azure_secrets_mock.SecretClient.return_value = secret_client_mock
        with (
            patch("concilium.infrastructure.auth.jwt_config.get_auth", return_value=auth_mock),
            patch.dict(
                "sys.modules",
                {
                    "azure.identity": azure_identity_mock,
                    "azure.keyvault.secrets": azure_secrets_mock,
                },
            ),
        ):
            import warnings

            with warnings.catch_warnings(record=True):
                result = _read_from_key_vault("jwt-private-key")
        assert result is None

    def test_read_from_key_vault_success_returns_encoded_secret(self, monkeypatch):
        from concilium.infrastructure.auth.jwt_config import _read_from_key_vault

        auth_mock = MagicMock()
        auth_mock.key_vault_url = "https://myvault.vault.azure.net"
        azure_identity_mock = MagicMock()
        azure_secrets_mock = MagicMock()
        secret_client_mock = MagicMock()
        secret_value = MagicMock()
        secret_value.value = "-----BEGIN RSA PRIVATE KEY-----\nfake\n"
        secret_client_mock.get_secret.return_value = secret_value
        azure_secrets_mock.SecretClient.return_value = secret_client_mock
        with (
            patch("concilium.infrastructure.auth.jwt_config.get_auth", return_value=auth_mock),
            patch.dict(
                "sys.modules",
                {
                    "azure.identity": azure_identity_mock,
                    "azure.keyvault.secrets": azure_secrets_mock,
                },
            ),
        ):
            result = _read_from_key_vault("jwt-private-key")
        assert result == secret_value.value.encode()

    def test_read_from_key_vault_empty_secret_returns_none(self, monkeypatch):
        from concilium.infrastructure.auth.jwt_config import _read_from_key_vault

        auth_mock = MagicMock()
        auth_mock.key_vault_url = "https://myvault.vault.azure.net"
        azure_identity_mock = MagicMock()
        azure_secrets_mock = MagicMock()
        secret_client_mock = MagicMock()
        secret_value = MagicMock()
        secret_value.value = "   "
        secret_client_mock.get_secret.return_value = secret_value
        azure_secrets_mock.SecretClient.return_value = secret_client_mock
        with (
            patch("concilium.infrastructure.auth.jwt_config.get_auth", return_value=auth_mock),
            patch.dict(
                "sys.modules",
                {
                    "azure.identity": azure_identity_mock,
                    "azure.keyvault.secrets": azure_secrets_mock,
                },
            ),
        ):
            result = _read_from_key_vault("jwt-private-key")
        assert result is None



