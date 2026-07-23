"""ADR-094 — Testes unitários da camada de autenticação JWT.

Cobre:
- TestJwtConfig        — geração de chave ephemeral + leitura de env vars
- TestClientStore      — validate_client (plaintext, hash, credencial errada)
- TestTokenService     — issue_token + decode_token (round-trip, exp, issuer)
- TestTokenRoute       — POST /auth/token (200, 401)
- TestJWTMiddleware    — bypass em paths isentos, 401 sem header, 401 token ruim, 200 válido
- TestScopeGuard       — check_scope em modo local (no-op) e modo auth ativo
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

# Garante src no path
_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_clients_env(clients: dict) -> str:
    return json.dumps(clients)


def _sha256_secret(secret: str) -> str:
    return "sha256:" + hashlib.sha256(secret.encode()).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Module-level fixtures para performance
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def rsa_keypair():
    """Gera chaves RSA uma única vez para toda a suite de testes."""
    from concilium.infrastructure.auth.jwt_config import _generate_ephemeral

    return _generate_ephemeral()


@pytest.fixture(scope="module")
def mock_jwt_env(rsa_keypair):
    """Environment com chaves RSA pré-geradas."""
    return {
        "CONCILIUM__JWT_PRIVATE_KEY_PEM": rsa_keypair.private_pem.decode(),
        "CONCILIUM__JWT_PUBLIC_KEY_PEM": rsa_keypair.public_pem.decode(),
    }


@pytest.fixture(autouse=True)
def clear_key_cache():
    """Limpa cache de chaves após cada teste para evitar state leaking."""
    yield
    from concilium.infrastructure.auth.jwt_config import load_key_pair

    load_key_pair.cache_clear()


@pytest.fixture(scope="module")
def clients_env():
    """Environment padrão com clientes para testes."""
    clients = {"eng-01": {"secret": "senha123", "roles": ["operator"]}}
    return _make_clients_env(clients)


@pytest.fixture(scope="module")
def fastapi_client(mock_jwt_env, clients_env):
    """TestClient FastAPI compartilhado para performance."""
    from fastapi.testclient import TestClient

    from concilium.infrastructure.auth.jwt_config import load_key_pair
    from concilium.presentation.api.app import create_app

    env = {**mock_jwt_env, "CONCILIUM__AUTH_CLIENTS": clients_env}
    with patch.dict(os.environ, env):
        load_key_pair.cache_clear()  # Force load with our keys
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


@pytest.fixture(scope="module")
def fastapi_client_with_auth(mock_jwt_env, clients_env):
    """TestClient FastAPI com autenticação habilitada."""
    from fastapi.testclient import TestClient

    from concilium.infrastructure.auth.jwt_config import load_key_pair
    from concilium.presentation.api.app import create_app

    env = {
        **mock_jwt_env,
        "CONCILIUM__AUTH_ENABLED": "1",
        "CONCILIUM__AUTH_CLIENTS": clients_env,
    }
    with patch.dict(os.environ, env):
        load_key_pair.cache_clear()  # Force load with our keys
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c, env


# ─────────────────────────────────────────────────────────────────────────────
# TestJwtConfig — Isolado para testar geração ephemeral
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.usefixtures("clear_key_cache")  # Usa fixture mas sem autouse
class TestJwtConfig:
    """Testes de geração de chaves - isolados porque testam comportamento ephemeral."""

    def test_generates_ephemeral_keys_when_no_env(self):
        clean_env = {k: v for k, v in os.environ.items() if "CONCILIUM__JWT" not in k}
        with patch.dict(os.environ, clean_env, clear=True):
            import warnings

            from concilium.infrastructure.auth.jwt_config import load_key_pair

            load_key_pair.cache_clear()
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                pair = load_key_pair()
            assert pair.private_pem.startswith(b"-----BEGIN RSA PRIVATE KEY-----")
            assert pair.public_pem.startswith(b"-----BEGIN PUBLIC KEY-----")
            assert any("ephemeral" in str(x.message).lower() for x in w)

    def test_reads_pem_from_env_vars(self, rsa_keypair):
        """Reutiliza keypair do módulo para performance."""
        from concilium.infrastructure.auth.jwt_config import load_key_pair

        env_override = {
            "CONCILIUM__JWT_PRIVATE_KEY_PEM": rsa_keypair.private_pem.decode(),
            "CONCILIUM__JWT_PUBLIC_KEY_PEM": rsa_keypair.public_pem.decode(),
        }
        with patch.dict(os.environ, env_override):
            load_key_pair.cache_clear()
            pair = load_key_pair()
        assert pair.private_pem == rsa_keypair.private_pem
        assert pair.public_pem == rsa_keypair.public_pem


# ─────────────────────────────────────────────────────────────────────────────
# TestClientStore
# ─────────────────────────────────────────────────────────────────────────────


class TestClientStore:
    def test_valid_plaintext_secret(self):
        from concilium.infrastructure.auth.client_store import validate_client

        clients = {"agente": {"secret": "s3cr3t", "roles": ["operator"]}}
        with patch.dict(os.environ, {"CONCILIUM__AUTH_CLIENTS": _make_clients_env(clients)}):
            roles = validate_client("agente", "s3cr3t")
        assert roles == ["operator"]

    def test_valid_hashed_secret(self):
        from concilium.infrastructure.auth.client_store import validate_client

        clients = {
            "ci": {
                "secret_hash": _sha256_secret("runner-pass"),
                "roles": ["operator", "engineer"],
            }
        }
        with patch.dict(os.environ, {"CONCILIUM__AUTH_CLIENTS": _make_clients_env(clients)}):
            roles = validate_client("ci", "runner-pass")
        assert set(roles) == {"operator", "engineer"}

    def test_wrong_secret_returns_none(self):
        from concilium.infrastructure.auth.client_store import validate_client

        clients = {"agente": {"secret": "correct", "roles": ["operator"]}}
        with patch.dict(os.environ, {"CONCILIUM__AUTH_CLIENTS": _make_clients_env(clients)}):
            result = validate_client("agente", "wrong")
        assert result is None

    def test_unknown_client_id_returns_none(self):
        from concilium.infrastructure.auth.client_store import validate_client

        with patch.dict(os.environ, {"CONCILIUM__AUTH_CLIENTS": "{}"}):
            result = validate_client("ghost", "any")
        assert result is None

    def test_empty_env_returns_none(self):
        from concilium.infrastructure.auth.client_store import validate_client

        clean = {k: v for k, v in os.environ.items() if k != "CONCILIUM__AUTH_CLIENTS"}
        with patch.dict(os.environ, clean, clear=True):
            result = validate_client("any", "any")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# TestTokenService — Usa chaves pré-geradas para performance
# ─────────────────────────────────────────────────────────────────────────────


class TestTokenService:
    """Testes de JWT token service - reutiliza chaves RSA."""

    def test_round_trip(self, mock_jwt_env):
        from concilium.infrastructure.auth.jwt_config import load_key_pair
        from concilium.infrastructure.auth.token_service import decode_token, issue_token

        with patch.dict(os.environ, mock_jwt_env):
            load_key_pair.cache_clear()
            token = issue_token("eng-01", ["operator"], ttl=timedelta(hours=1))
            claims = decode_token(token)

        assert claims["sub"] == "eng-01"
        assert set(claims["roles"]) == {"operator"}
        assert claims["iss"] == "concilium-auth"
        assert claims["org"] == "mendesloboconstrucao"

    def test_round_trip_with_device_id(self, mock_jwt_env):
        """Fluxo de device (ADR-138 sessions): device_id opcional vira claim do JWT."""
        from concilium.infrastructure.auth.jwt_config import load_key_pair
        from concilium.infrastructure.auth.token_service import decode_token, issue_token

        with patch.dict(os.environ, mock_jwt_env):
            load_key_pair.cache_clear()
            token = issue_token("eng-01", ["operator"], ttl=timedelta(hours=1), device_id="falcon-falcon")
            claims = decode_token(token)

        assert claims["device_id"] == "falcon-falcon"

    def test_round_trip_without_device_id_omits_claim(self, mock_jwt_env):
        """Fluxos sem device (client_id/secret direto, token/issue) não ganham claim."""
        from concilium.infrastructure.auth.jwt_config import load_key_pair
        from concilium.infrastructure.auth.token_service import decode_token, issue_token

        with patch.dict(os.environ, mock_jwt_env):
            load_key_pair.cache_clear()
            token = issue_token("eng-01", ["operator"], ttl=timedelta(hours=1))
            claims = decode_token(token)

        assert "device_id" not in claims

    def test_expired_token_raises(self, mock_jwt_env):
        import jwt as _jwt

        from concilium.infrastructure.auth.jwt_config import load_key_pair
        from concilium.infrastructure.auth.token_service import decode_token, issue_token

        with patch.dict(os.environ, mock_jwt_env):
            load_key_pair.cache_clear()
            token = issue_token("eng-01", ["operator"], ttl=timedelta(seconds=-1))
            with pytest.raises(_jwt.ExpiredSignatureError):
                decode_token(token)

    def test_tampered_token_raises(self, mock_jwt_env):
        import jwt as _jwt

        from concilium.infrastructure.auth.jwt_config import load_key_pair
        from concilium.infrastructure.auth.token_service import decode_token, issue_token

        with patch.dict(os.environ, mock_jwt_env):
            load_key_pair.cache_clear()
            token = issue_token("eng-01", ["operator"], ttl=timedelta(hours=1))
            tampered = token[:-5] + "XXXXX"
            with pytest.raises(_jwt.PyJWTError):
                decode_token(tampered)


# ─────────────────────────────────────────────────────────────────────────────
# TestTokenRoute — Usa FastAPI client compartilhado
# ─────────────────────────────────────────────────────────────────────────────


class TestTokenRoute:
    """Testes de /auth/token endpoint - reutiliza cliente FastAPI."""

    def test_valid_credentials_returns_token(self, fastapi_client, clients_env):
        with patch.dict(os.environ, {"CONCILIUM__AUTH_CLIENTS": clients_env}):
            resp = fastapi_client.post("/auth/token", json={"client_id": "eng-01", "client_secret": "senha123"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 8 * 3600

    def test_invalid_credentials_returns_401(self, fastapi_client, clients_env):
        with patch.dict(os.environ, {"CONCILIUM__AUTH_CLIENTS": clients_env}):
            resp = fastapi_client.post("/auth/token", json={"client_id": "eng-01", "client_secret": "errado"})
        assert resp.status_code == 401

    def test_unknown_client_returns_401(self, fastapi_client, clients_env):
        with patch.dict(os.environ, {"CONCILIUM__AUTH_CLIENTS": clients_env}):
            resp = fastapi_client.post("/auth/token", json={"client_id": "fantasma", "client_secret": "qualquer"})
        assert resp.status_code == 401

    def test_ttl_days_applied(self, fastapi_client, clients_env):
        with patch.dict(os.environ, {"CONCILIUM__AUTH_CLIENTS": clients_env}):
            resp = fastapi_client.post(
                "/auth/token",
                json={"client_id": "eng-01", "client_secret": "senha123", "ttl_days": 30},
            )
        assert resp.status_code == 200
        assert resp.json()["expires_in"] == 30 * 86400


# ─────────────────────────────────────────────────────────────────────────────
# TestJWTMiddleware — Usa FastAPI client com auth compartilhado
# ─────────────────────────────────────────────────────────────────────────────


class TestJWTMiddleware:
    """Testes de JWT middleware - reutiliza cliente FastAPI com auth."""

    def test_health_bypasses_auth(self, fastapi_client_with_auth):
        client, env = fastapi_client_with_auth
        with patch.dict(os.environ, env):
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_auth_token_endpoint_bypasses_auth(self, fastapi_client_with_auth):
        client, env = fastapi_client_with_auth
        with patch.dict(os.environ, env):
            resp = client.post(
                "/auth/token",
                json={"client_id": "eng-01", "client_secret": "senha123"},
            )
        assert resp.status_code == 200

    def test_missing_bearer_returns_401(self, fastapi_client_with_auth):
        client, env = fastapi_client_with_auth
        with patch.dict(os.environ, env):
            resp = client.get("/catalog/reload", headers={})
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, fastapi_client_with_auth):
        client, env = fastapi_client_with_auth
        with patch.dict(os.environ, env):
            resp = client.get("/health", headers={"Authorization": "Bearer invalid.token.here"})
        # /health is in skip paths — still 200
        assert resp.status_code == 200

    def test_valid_token_passes_through(self, fastapi_client_with_auth, mock_jwt_env):
        client, env = fastapi_client_with_auth
        from concilium.infrastructure.auth.jwt_config import load_key_pair
        from concilium.infrastructure.auth.token_service import issue_token

        with patch.dict(os.environ, {**env, **mock_jwt_env}):
            load_key_pair.cache_clear()
            token = issue_token("eng-01", ["operator"], ttl=timedelta(hours=1))
            resp = client.get("/health", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# TestScopeGuard
# ─────────────────────────────────────────────────────────────────────────────


class TestScopeGuard:
    """check_scope lê o cache TOOL_PERMISSIONS (ADR-117: populado em runtime das tags @permission).

    A fixture autouse simula a população que build_server faz, derivando do source.
    avancar_pipeline foi removida (ADR-116) — usa disparar_pipeline (mesma perm project:run).
    """

    @pytest.fixture(autouse=True)
    def _populate_cache(self):
        import ast
        import glob as _glob
        import os as _os

        from concilium.infrastructure.auth.permission_guard import TOOL_PERMISSIONS

        root = _os.path.join(_os.path.dirname(__file__), "..", "..", "..", "..")
        mapping: dict[str, str] = {}
        for f in sorted(_glob.glob(_os.path.join(root, "src/concilium/presentation/mcp/tools/*.py"))):
            tree = ast.parse(open(f, encoding="utf-8").read())
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not any(
                    (isinstance(d, ast.Attribute) and d.attr == "tool")
                    or (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "tool")
                    for d in node.decorator_list
                ):
                    continue
                for d in node.decorator_list:
                    if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "permission":
                        if d.args and isinstance(d.args[0], ast.Constant):
                            mapping[node.name] = d.args[0].value
        saved = dict(TOOL_PERMISSIONS)
        TOOL_PERMISSIONS.clear()
        TOOL_PERMISSIONS.update(mapping)
        yield
        TOOL_PERMISSIONS.clear()
        TOOL_PERMISSIONS.update(saved)

    def test_no_op_when_auth_disabled(self):
        from concilium.presentation.mcp.guards.scope_guard import check_scope

        clean = {k: v for k, v in os.environ.items() if k != "CONCILIUM__AUTH_ENABLED"}
        with patch.dict(os.environ, clean, clear=True):
            check_scope("disparar_pipeline")  # deve passar sem erro

    def test_passes_with_correct_scope(self):
        from concilium.presentation.mcp.guards.scope_guard import check_scope, set_roles

        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}):
            set_roles(["operator"])
            check_scope("disparar_pipeline")  # operator tem project:run

    def test_raises_with_missing_scope(self):
        from concilium.presentation.mcp.guards.scope_guard import check_scope, set_roles

        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}):
            set_roles(["auditor"])
            with pytest.raises(PermissionError, match="project:run"):
                check_scope("disparar_pipeline")

    def test_unmapped_tool_passes_regardless(self):
        from concilium.presentation.mcp.guards.scope_guard import check_scope, set_roles

        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}):
            set_roles([])  # sem nenhum role
            check_scope("ferramenta_nao_mapeada")  # deve passar

    def test_error_message_lists_missing_permission(self):
        from concilium.presentation.mcp.guards.scope_guard import check_scope, set_roles

        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}):
            set_roles([])
            with pytest.raises(PermissionError) as exc_info:
                check_scope("disparar_pipeline")
            assert "project:run" in str(exc_info.value)
            assert "Permissão" in str(exc_info.value)

    @pytest.mark.parametrize(
        "tool,required_permission",
        [
            ("listar_projetos", "project:read"),
            ("auditar_plano", "artifacts:read"),
            ("explorar_pool_recursos", "project:read"),
            ("obter_artefato", "artifacts:download"),  # ADR-116 F5: baixar_bundle_zip→obter_artefato
            ("criar_projeto", "project:create"),  # ADR-116 F5: criar_projeto_formulario→criar_projeto
            ("disparar_pipeline", "project:run"),
        ],
    )
    def test_tool_permission_map_completeness(self, tool, required_permission):
        from concilium.infrastructure.auth.permission_guard import TOOL_PERMISSIONS

        assert TOOL_PERMISSIONS.get(tool) == required_permission



# ─── presentation/mcp/guards/scope_guard.py (3 missing: 77, 79-80) ────────────


class TestScopeGuard2:
    def test_set_scopes_converts_to_roles(self):
        from concilium.presentation.mcp.guards.scope_guard import _current_roles, set_scopes

        set_scopes(["mcp:read", "pipeline:run"])
        roles = list(_current_roles.get())
        assert "auditor" in roles or "operator" in roles

    def test_set_scopes_unknown_defaults_to_operator(self):
        from concilium.presentation.mcp.guards.scope_guard import _current_roles, set_scopes

        set_scopes(["unknown:scope"])
        roles = list(_current_roles.get())
        assert "operator" in roles

    def test_check_scope_no_auth(self):
        from concilium.presentation.mcp.guards.scope_guard import check_scope

        with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=False):
            check_scope("listar_projetos")  # should not raise (looks up TOOL_PERMISSIONS)



