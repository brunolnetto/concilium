"""Coverage tests for concilium.infrastructure.settings."""

from __future__ import annotations

import sys

import pytest

import concilium.infrastructure.settings as _mod
from concilium.infrastructure.settings import (
    ApiSettings,
    AuthSettings,
    AzureSettings,
    CampaignSettings,
    ConfigurationError,
    GDriveSettings,
    McpProxySettings,
    S3Settings,
    SharePointSettings,
    StorageSettings,
    UiSettings,
    _check_auth,
    _check_storage,
    _reset_all,
    env_summary,
    get_api,
    get_campaign,
    startup_check,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ui(
    override: str = "", base_url: str = "", host: str = "127.0.0.1", port: int = 8000
) -> tuple[UiSettings, ApiSettings]:
    ui = UiSettings(
        host="127.0.0.1",
        port=8501,
        api_base_url_override=override,
        entrypoint="",
    )
    api = ApiSettings(host=host, port=port, reload=False, base_url=base_url)
    return ui, api


def _make_storage(backend: str = "filesystem", **kwargs) -> StorageSettings:
    from pathlib import Path

    azure = AzureSettings(
        account=kwargs.get("azure_account", ""),
        container=kwargs.get("azure_container", ""),
        key=kwargs.get("azure_key", ""),
        connection_string=kwargs.get("azure_connection_string", ""),
        root_prefix="",
    )
    s3 = S3Settings(
        bucket=kwargs.get("s3_bucket", ""),
        region="us-east-1",
        root_prefix="",
        endpoint_url="",
        addressing_style="virtual",
        access_key_id="",
        secret_access_key="",
        session_token="",
        server_side_encryption="",
    )
    sharepoint = SharePointSettings(
        tenant_id=kwargs.get("sp_tenant_id", ""),
        client_id=kwargs.get("sp_client_id", ""),
        client_secret=kwargs.get("sp_client_secret", ""),
        cert_path=kwargs.get("sp_cert_path", ""),
        drive_id=kwargs.get("sp_drive_id", ""),
        root_path="Concilium/producao",
        cache_dir="",
    )
    gdrive = GDriveSettings(
        root_folder_id=kwargs.get("gdrive_root_folder_id", ""),
        service_account_json="",
        google_credentials_path="",
    )
    return StorageSettings(
        root=Path("/tmp/root"),
        config_root=Path("/tmp/root/config"),
        runtime_config_file=None,
        backend=backend,
        projects_prefix="projetos",
        projects_root=Path("/tmp/root/projetos"),
        benchmark_projects_root=Path("/tmp/root/benchmarks/projetos"),
        azure=azure,
        sharepoint=sharepoint,
        s3=s3,
        gdrive=gdrive,
    )


def _make_auth(**kwargs) -> AuthSettings:
    return AuthSettings(
        enabled=kwargs.get("enabled", False),
        clients_json=kwargs.get("clients_json", ""),
        jwt_private_key_pem=kwargs.get("jwt_private_key_pem", ""),
        jwt_private_key_path=kwargs.get("jwt_private_key_path", ""),
        jwt_public_key_pem=kwargs.get("jwt_public_key_pem", ""),
        jwt_public_key_path=kwargs.get("jwt_public_key_path", ""),
        key_vault_url=kwargs.get("key_vault_url", ""),
        data_path=kwargs.get("data_path", ""),
    )


# ---------------------------------------------------------------------------
# UiSettings.resolved_api_base_url — 5 tests
# ---------------------------------------------------------------------------


def test_ui_resolved_api_base_url_override():
    ui, api = _make_ui(override="http://override:9000", base_url="http://ignored:8000")
    assert ui.resolved_api_base_url(api) == "http://override:9000"


def test_ui_resolved_api_base_url_override_strips_trailing_slash():
    ui, api = _make_ui(override="http://override:9000/")
    assert ui.resolved_api_base_url(api) == "http://override:9000"


def test_ui_resolved_api_base_url_uses_api_base_url():
    ui, api = _make_ui(override="", base_url="http://api:8000")
    assert ui.resolved_api_base_url(api) == "http://api:8000"


def test_ui_resolved_api_base_url_uses_api_base_url_strips_slash():
    ui, api = _make_ui(override="", base_url="http://api:8000/")
    assert ui.resolved_api_base_url(api) == "http://api:8000"


def test_ui_resolved_api_base_url_fallback_to_host_port(monkeypatch):
    _reset_all()
    monkeypatch.setenv("CONCILIUM__API_HOST", "192.168.1.1")
    monkeypatch.setenv("CONCILIUM__API_PORT", "9999")
    monkeypatch.delenv("CONCILIUM__API_BASE_URL", raising=False)
    ui = UiSettings(host="127.0.0.1", port=8501, api_base_url_override="", entrypoint="")
    result = ui.resolved_api_base_url()
    assert result == "http://192.168.1.1:9999"
    _reset_all()


# ---------------------------------------------------------------------------
# get_campaign() — 4 tests
# ---------------------------------------------------------------------------


def test_get_campaign_returns_campaign_settings(monkeypatch):
    _reset_all()
    monkeypatch.delenv("CONCILIUM__CAMPAIGN_CARDINALITY_THRESHOLD", raising=False)
    campaign = get_campaign()
    assert isinstance(campaign, CampaignSettings)


def test_get_campaign_singleton(monkeypatch):
    _reset_all()
    monkeypatch.delenv("CONCILIUM__CAMPAIGN_CARDINALITY_THRESHOLD", raising=False)
    c1 = get_campaign()
    c2 = get_campaign()
    assert c1 is c2


def test_get_campaign_default_threshold(monkeypatch):
    _reset_all()
    monkeypatch.delenv("CONCILIUM__CAMPAIGN_CARDINALITY_THRESHOLD", raising=False)
    campaign = get_campaign()
    assert campaign.cardinality_threshold == 10_000
    _reset_all()


def test_get_campaign_custom_env(monkeypatch):
    _reset_all()
    monkeypatch.setenv("CONCILIUM__CAMPAIGN_CARDINALITY_THRESHOLD", "999")
    monkeypatch.setenv("CONCILIUM__CAMPAIGN_MAX_WORKERS", "2")
    campaign = get_campaign()
    assert campaign.cardinality_threshold == 999
    assert campaign.max_workers == 2
    _reset_all()


# ---------------------------------------------------------------------------
# _reset_all() — 2 tests
# ---------------------------------------------------------------------------


def test_reset_all_invalidates_singletons(monkeypatch):
    monkeypatch.delenv("CONCILIUM__API_HOST", raising=False)
    get_api()
    _reset_all()
    assert _mod._api._api is None
    assert _mod._campaign._campaign is None


def test_reset_all_fresh_instances(monkeypatch):
    _reset_all()
    monkeypatch.setenv("CONCILIUM__API_HOST", "10.0.0.1")
    api1 = get_api()
    _reset_all()
    monkeypatch.setenv("CONCILIUM__API_HOST", "10.0.0.2")
    api2 = get_api()
    assert api1.host != api2.host
    _reset_all()


# ---------------------------------------------------------------------------
# startup_check() — 4 tests
# ---------------------------------------------------------------------------


def test_startup_check_no_error(monkeypatch):
    _reset_all()
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", "filesystem")
    monkeypatch.delenv("CONCILIUM__AUTH_ENABLED", raising=False)
    startup_check()
    _reset_all()


def test_startup_check_raises_azure_missing_account(monkeypatch):
    _reset_all()
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", "azure_blob")
    monkeypatch.delenv("CONCILIUM__AZURE_ACCOUNT", raising=False)
    monkeypatch.delenv("CONCILIUM__AZURE_CONTAINER", raising=False)
    monkeypatch.delenv("CONCILIUM__AZURE_CONNECTION_STRING", raising=False)
    with pytest.raises(ConfigurationError):
        startup_check()
    _reset_all()


def test_startup_check_raises_s3_missing_bucket(monkeypatch):
    _reset_all()
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", "s3")
    monkeypatch.delenv("CONCILIUM__S3_BUCKET", raising=False)
    with pytest.raises(ConfigurationError):
        startup_check()
    _reset_all()


def test_startup_check_raises_auth_no_jwt_key(monkeypatch):
    _reset_all()
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", "filesystem")
    monkeypatch.setenv("CONCILIUM__AUTH_ENABLED", "1")
    monkeypatch.setenv("CONCILIUM__AUTH_CLIENTS", '[{"client_id":"x","client_secret":"y","scopes":["read"]}]')
    monkeypatch.delenv("CONCILIUM__JWT_PRIVATE_KEY_PEM", raising=False)
    monkeypatch.delenv("CONCILIUM__JWT_PRIVATE_KEY_PATH", raising=False)
    monkeypatch.delenv("CONCILIUM__JWT_KEY_VAULT_URL", raising=False)
    with pytest.raises(ConfigurationError):
        startup_check()
    _reset_all()


# ---------------------------------------------------------------------------
# _check_storage() — 10 tests
# ---------------------------------------------------------------------------


def test_check_storage_filesystem_no_errors():
    st = _make_storage(backend="filesystem")
    assert _check_storage(st) == []


def test_check_storage_azure_missing_account():
    st = _make_storage(backend="azure_blob", azure_container="mycontainer")
    errors = _check_storage(st)
    assert any("AZURE_ACCOUNT" in e for e in errors)


def test_check_storage_azure_missing_container():
    st = _make_storage(backend="azure_blob", azure_account="myaccount")
    errors = _check_storage(st)
    assert any("AZURE_CONTAINER" in e for e in errors)


def test_check_storage_azure_missing_connection_string_and_account():
    st = _make_storage(backend="azure_blob")
    errors = _check_storage(st)
    assert any("AZURE_ACCOUNT" in e or "CONNECTION_STRING" in e for e in errors)


def test_check_storage_azure_no_errors_with_account_and_container():
    st = _make_storage(backend="azure_blob", azure_account="acc", azure_container="cont")
    errors = _check_storage(st)
    assert not any("AZURE_CONTAINER" in e for e in errors)
    account_errors = [e for e in errors if "AZURE_ACCOUNT" in e and "CONNECTION_STRING" not in e]
    assert account_errors == []


def test_check_storage_s3_missing_bucket():
    st = _make_storage(backend="s3")
    errors = _check_storage(st)
    assert any("S3_BUCKET" in e for e in errors)


def test_check_storage_s3_no_errors():
    st = _make_storage(backend="s3", s3_bucket="my-bucket")
    errors = _check_storage(st)
    assert errors == []


def test_check_storage_sharepoint_missing_fields():
    st = _make_storage(backend="sharepoint")
    errors = _check_storage(st)
    assert any("SP_TENANT_ID" in e for e in errors)
    assert any("SP_CLIENT_ID" in e for e in errors)
    assert any("SP_DRIVE_ID" in e for e in errors)
    assert any("SP_CLIENT_SECRET" in e or "SP_CERT_PATH" in e for e in errors)


def test_check_storage_gdrive_missing_folder():
    st = _make_storage(backend="gdrive")
    errors = _check_storage(st)
    assert any("GDRIVE_ROOT_FOLDER_ID" in e for e in errors)


def test_check_storage_unknown_backend():
    st = _make_storage(backend="unknown_backend")
    errors = _check_storage(st)
    assert any("unknown_backend" in e for e in errors)


# ---------------------------------------------------------------------------
# _check_auth() — 5 tests
# ---------------------------------------------------------------------------


def test_check_auth_disabled_no_errors():
    auth = _make_auth(enabled=False)
    assert _check_auth(auth) == []


def test_check_auth_enabled_with_pem_key_and_clients():
    auth = _make_auth(
        enabled=True,
        jwt_private_key_pem="-----BEGIN RSA PRIVATE KEY-----\n...",
        clients_json='[{"client_id":"x","client_secret":"y","scopes":["read"]}]',
    )
    errors = _check_auth(auth)
    assert errors == []


def test_check_auth_enabled_with_key_vault_and_clients():
    auth = _make_auth(
        enabled=True,
        key_vault_url="https://concilium-kv.vault.azure.net",
        clients_json='[{"client_id":"x","client_secret":"y","scopes":["read"]}]',
    )
    errors = _check_auth(auth)
    assert errors == []


def test_check_auth_enabled_without_any_jwt_key():
    auth = _make_auth(
        enabled=True,
        clients_json='[{"client_id":"x","client_secret":"y","scopes":["read"]}]',
    )
    errors = _check_auth(auth)
    assert any("JWT" in e for e in errors)


def test_check_auth_enabled_without_clients_json():
    auth = _make_auth(
        enabled=True,
        jwt_private_key_pem="-----BEGIN RSA PRIVATE KEY-----\n...",
        clients_json="",
    )
    errors = _check_auth(auth)
    assert any("AUTH_CLIENTS" in e for e in errors)


# ---------------------------------------------------------------------------
# env_summary() — 7 tests
# ---------------------------------------------------------------------------


def test_env_summary_returns_str(monkeypatch):
    _reset_all()
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", "filesystem")
    monkeypatch.delenv("CONCILIUM__AUTH_ENABLED", raising=False)
    result = env_summary()
    assert isinstance(result, str)
    _reset_all()


def test_env_summary_contains_concilium_settings(monkeypatch):
    _reset_all()
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", "filesystem")
    result = env_summary()
    assert "Concilium Settings" in result
    _reset_all()


def test_env_summary_contains_campaign_threshold(monkeypatch):
    _reset_all()
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", "filesystem")
    monkeypatch.setenv("CONCILIUM__CAMPAIGN_CARDINALITY_THRESHOLD", "10000")
    result = env_summary()
    assert "10,000" in result or "10000" in result
    _reset_all()


def test_env_summary_contains_storage_backend(monkeypatch):
    _reset_all()
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", "filesystem")
    result = env_summary()
    assert "filesystem" in result
    _reset_all()


def test_env_summary_contains_auth_enabled(monkeypatch):
    _reset_all()
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", "filesystem")
    monkeypatch.delenv("CONCILIUM__AUTH_ENABLED", raising=False)
    result = env_summary()
    assert "auth.enabled" in result
    _reset_all()


def test_env_summary_custom_campaign_workers(monkeypatch):
    _reset_all()
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", "filesystem")
    monkeypatch.setenv("CONCILIUM__CAMPAIGN_MAX_WORKERS", "4")
    result = env_summary()
    assert "workers=4" in result
    _reset_all()


def test_env_summary_custom_storage_backend_appears(monkeypatch):
    _reset_all()
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", "s3")
    result = env_summary()
    assert "s3" in result
    _reset_all()


# ---------------------------------------------------------------------------
# Additional edge-case tests to reach 40
# ---------------------------------------------------------------------------


def test_check_storage_sharepoint_no_errors_with_secret():
    st = _make_storage(
        backend="sharepoint",
        sp_tenant_id="tid",
        sp_client_id="cid",
        sp_drive_id="did",
        sp_client_secret="secret",
    )
    errors = _check_storage(st)
    assert errors == []


def test_check_storage_sharepoint_no_errors_with_cert():
    st = _make_storage(
        backend="sharepoint",
        sp_tenant_id="tid",
        sp_client_id="cid",
        sp_drive_id="did",
        sp_cert_path="/path/to/cert.pem",
    )
    errors = _check_storage(st)
    assert errors == []


def test_check_storage_gdrive_no_errors():
    st = _make_storage(backend="gdrive", gdrive_root_folder_id="folder123")
    errors = _check_storage(st)
    assert errors == []


def test_mcp_proxy_settings_uses_client_code(monkeypatch):
    monkeypatch.delenv("CONCILIUM_DEVICE_CODE", raising=False)
    monkeypatch.setenv("CONCILIUM_CLIENT_CODE", "RCODE-NEW")
    settings = McpProxySettings.from_env()
    assert settings.client_code == "RCODE-NEW"


def test_mcp_proxy_settings_falls_back_to_legacy_device_code(monkeypatch):
    """Configs sincronizadas externamente (ex.: Claude Desktop) podem reverter para o
    nome pré-#17 — o proxy deve continuar funcionando sem exigir reconfiguração."""
    monkeypatch.delenv("CONCILIUM_CLIENT_CODE", raising=False)
    monkeypatch.setenv("CONCILIUM_DEVICE_CODE", "RCODE-LEGACY")
    settings = McpProxySettings.from_env()
    assert settings.client_code == "RCODE-LEGACY"


def test_mcp_proxy_settings_prefers_new_name_over_legacy(monkeypatch):
    monkeypatch.setenv("CONCILIUM_CLIENT_CODE", "RCODE-NEW")
    monkeypatch.setenv("CONCILIUM_DEVICE_CODE", "RCODE-LEGACY")
    settings = McpProxySettings.from_env()
    assert settings.client_code == "RCODE-NEW"


def test_mcp_proxy_settings_device_id_detection_failure_falls_back(monkeypatch):
    """Covers lines 367-368: socket.gethostname() raising must not blow up
    from_env(); device_id falls back to 'unknown-device'."""
    import socket

    def _raise():
        raise OSError("no network")

    monkeypatch.setattr(socket, "gethostname", _raise)
    settings = McpProxySettings.from_env()
    assert settings.device_id == "unknown-device"


def test_get_mcp_returns_cached_instance_on_second_call(monkeypatch):
    """Covers the false branch of `if _mcp is None` in get_mcp()."""
    _mod._reset_all()
    from concilium.infrastructure.settings import get_mcp

    first = get_mcp()
    second = get_mcp()
    assert first is second


def test_get_mcp_proxy_returns_cached_instance_on_second_call(monkeypatch):
    """Covers the false branch of `if _mcp_proxy is None` in get_mcp_proxy()."""
    _mod._reset_all()
    from concilium.infrastructure.settings import get_mcp_proxy

    first = get_mcp_proxy()
    second = get_mcp_proxy()
    assert first is second


def test_get_smtp_returns_cached_instance_on_second_call(monkeypatch):
    """Covers the false branch of `if _smtp is None` in get_smtp()."""
    _mod._reset_all()
    from concilium.infrastructure.settings import get_smtp

    first = get_smtp()
    second = get_smtp()
    assert first is second


def test_smtp_password_skips_kv_lookup_when_env_password_set(monkeypatch):
    """Covers the false branch of `if not password` in SmtpSettings.from_env():
    when CONCILIUM__SMTP_PASSWORD is set, the Key Vault lookup must be skipped."""
    from concilium.infrastructure.settings import SmtpSettings

    monkeypatch.setenv("CONCILIUM__SMTP_PASSWORD", "from-env-password")
    settings = SmtpSettings.from_env()
    assert settings.password == "from-env-password"


def test_read_smtp_password_from_kv_no_url_returns_none(monkeypatch):
    """Covers the true branch of `if not kv_url` in _read_smtp_password_from_kv()."""
    from concilium.infrastructure.settings import _read_smtp_password_from_kv

    monkeypatch.delenv("CONCILIUM__JWT_KEY_VAULT_URL", raising=False)
    assert _read_smtp_password_from_kv() is None


def test_read_smtp_password_from_kv_fetches_secret(monkeypatch):
    """Covers lines 920-926: kv_url present → fetch secret via Azure SDK."""
    from unittest.mock import MagicMock

    from concilium.infrastructure.settings import _read_smtp_password_from_kv

    monkeypatch.setenv("CONCILIUM__JWT_KEY_VAULT_URL", "https://fake-vault.vault.azure.net")

    fake_secret = MagicMock()
    fake_secret.value = "  secret-from-kv  "
    fake_client = MagicMock()
    fake_client.get_secret.return_value = fake_secret

    fake_azure_identity = MagicMock()
    fake_azure_identity.DefaultAzureCredential.return_value = MagicMock()
    fake_azure_keyvault_secrets = MagicMock()
    fake_azure_keyvault_secrets.SecretClient.return_value = fake_client

    monkeypatch.setitem(sys.modules, "azure.identity", fake_azure_identity)
    monkeypatch.setitem(sys.modules, "azure.keyvault.secrets", fake_azure_keyvault_secrets)

    result = _read_smtp_password_from_kv()
    assert result == "secret-from-kv"


def test_read_smtp_password_from_kv_exception_returns_none(monkeypatch):
    """Covers the except-branch (line 927-928): any failure during the Azure
    SDK import/call must be swallowed and return None."""
    from unittest.mock import MagicMock

    from concilium.infrastructure.settings import _read_smtp_password_from_kv

    monkeypatch.setenv("CONCILIUM__JWT_KEY_VAULT_URL", "https://fake-vault.vault.azure.net")

    def _raise_import(*_a, **_k):
        raise ImportError("azure sdk not installed")

    fake_azure_identity = MagicMock()
    fake_azure_identity.DefaultAzureCredential.side_effect = _raise_import
    monkeypatch.setitem(sys.modules, "azure.identity", fake_azure_identity)

    result = _read_smtp_password_from_kv()
    assert result is None
