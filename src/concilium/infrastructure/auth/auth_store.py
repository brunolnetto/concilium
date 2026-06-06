"""Auth data store — device codes, refresh tokens, client registry (ADR-094).

Storage strategy:
  Device codes     → in-memory only (1h TTL; ephemeral by design)
  Refresh tokens   → JSON file (90d TTL, revocable, persists across restarts)
  Clients (file)   → JSON file (additive to CONCILIUM__AUTH_CLIENTS env var)

Data directory: CONCILIUM__AUTH_DATA_PATH  (default: ~/.concilium/auth/)

Thread-safety: internal threading.Lock protects all mutations.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from concilium.infrastructure.settings import get_auth


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _hash(secret: str) -> str:
    return "sha256:" + hashlib.sha256(secret.encode()).hexdigest()


def _verify(provided: str, stored_hash: str) -> bool:
    return hmac.compare_digest(stored_hash, _hash(provided))


# ── Data records ──────────────────────────────────────────────────────────────

@dataclass
class ClientRecord:
    client_id: str
    secret_hash: str          # "sha256:<hex>"
    roles: list[str]          # ADR-099: ex. ["operator"], ["service-ci"]
    created_at: str           # ISO-8601
    active: bool = True
    notes: str = ""
    scopes: list[str] = field(default_factory=list)  # legado ADR-094, ignorado se roles presente


@dataclass
class DeviceCodeRecord:
    code: str                 # "RCODE-<hex>"
    client_id: str
    device_id: str
    device_name: str
    roles: list[str]          # ADR-099
    expires_at: str           # ISO-8601
    used: bool = False
    scopes: list[str] = field(default_factory=list)  # legado


@dataclass
class RefreshTokenRecord:
    token_id: str             # "RT-<hex>"
    client_id: str
    device_id: str
    device_name: str
    roles: list[str]          # ADR-099
    issued_at: str            # ISO-8601
    expires_at: str           # ISO-8601
    revoked: bool = False
    last_used_at: str = ""
    scopes: list[str] = field(default_factory=list)  # legado


# ── Store ─────────────────────────────────────────────────────────────────────

class AuthStore:
    """Thread-safe auth data store backed by JSON files.

    Usage::

        store = get_auth_store()

        # Admin: create client
        store.add_client("bruno", "secret123", ["mcp:read", "pipeline:run"])

        # Admin: create device code for client
        code = store.create_device_code("bruno", "macbook-bruno", "macbook-bruno", ...)

        # User (proxy): activate device code once → refresh token persisted locally
        rt = store.activate_device_code(code.code)

        # User (proxy): exchange refresh token → access token via token_service
        token_record = store.use_refresh_token(rt.token_id)

        # Admin: revoke device
        store.revoke_device("macbook-bruno")
    """

    REFRESH_TOKEN_TTL = timedelta(days=90)
    DEVICE_CODE_TTL = timedelta(hours=1)

    def __init__(self, data_dir: Path | None = None) -> None:
        if data_dir is None:
            raw = get_auth().data_path.strip()
            data_dir = Path(raw).expanduser().resolve() if raw else Path.home() / ".concilium" / "auth"
        self._dir = data_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._device_codes: dict[str, DeviceCodeRecord] = {}  # in-memory only

    # ── File helpers ──────────────────────────────────────────────────────────

    def _path(self, name: str) -> Path:
        return self._dir / name

    def _read(self, name: str) -> list[dict]:
        p = self._path(name)
        if not p.exists():
            return []
        return json.loads(p.read_text(encoding="utf-8"))

    def _write(self, name: str, records: list[dict]) -> None:
        p = self._path(name)
        p.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
        p.chmod(0o600)

    # ── Client management ─────────────────────────────────────────────────────

    def add_client(
        self,
        client_id: str,
        secret: str,
        roles: list[str],
        notes: str = "",
        scopes: list[str] | None = None,  # legado — convertido para roles
    ) -> ClientRecord:
        """Register a new client. Raises ValueError if client_id already exists."""
        from concilium.infrastructure.auth.permission_guard import (
            LEGACY_SCOPE_TO_ROLE, VALID_ROLES,
        )
        # Mapeia scopes legados para roles se necessário
        effective_roles = list(roles)
        if not effective_roles and scopes:
            effective_roles = list({LEGACY_SCOPE_TO_ROLE.get(s, "operator") for s in scopes})
        if not effective_roles:
            effective_roles = ["operator"]
        # Valida roles
        invalid = [r for r in effective_roles if r not in VALID_ROLES]
        if invalid:
            raise ValueError(f"Roles inválidos: {invalid}. Válidos: {sorted(VALID_ROLES)}")

        with self._lock:
            existing = [ClientRecord(**r) for r in self._read("clients.json")]
            if any(r.client_id == client_id for r in existing):
                raise ValueError(f"Client '{client_id}' already exists.")
            record = ClientRecord(
                client_id=client_id,
                secret_hash=_hash(secret),
                roles=effective_roles,
                created_at=_iso(_now()),
                notes=notes,
            )
            existing.append(record)
            self._write("clients.json", [asdict(r) for r in existing])
            return record

    def list_clients(self) -> list[ClientRecord]:
        with self._lock:
            return [ClientRecord(**r) for r in self._read("clients.json")]

    def remove_client(self, client_id: str) -> bool:
        """Deactivates a client. Returns True if found."""
        with self._lock:
            records = [ClientRecord(**r) for r in self._read("clients.json")]
            before = len(records)
            records = [r for r in records if r.client_id != client_id]
            if len(records) == before:
                return False
            self._write("clients.json", [asdict(r) for r in records])
            return True

    def get_client_roles(self, client_id: str, secret: str) -> list[str] | None:
        """Validate credentials and return roles. None if invalid.

        Precedence: file store (ADR-099) → env var CONCILIUM__AUTH_CLIENTS (ADR-094 legacy).
        Legacy clients with 'scopes' are mapped to equivalent roles.
        """
        with self._lock:
            records = [ClientRecord(**r) for r in self._read("clients.json")]
        for r in records:
            if r.client_id == client_id and r.active and _verify(secret, r.secret_hash):
                return r.roles
        # Fallback: env-var store (ADR-094 legacy) → map scopes to roles
        from concilium.infrastructure.auth.client_store import validate_client as _env_validate
        from concilium.infrastructure.auth.permission_guard import LEGACY_SCOPE_TO_ROLE
        scopes = _env_validate(client_id, secret)
        if scopes is None:
            return None
        return list({LEGACY_SCOPE_TO_ROLE.get(s, "operator") for s in scopes})

    def validate_client(self, client_id: str, secret: str) -> list[str] | None:
        """Legado ADR-094: alias para get_client_roles()."""
        return self.get_client_roles(client_id, secret)

    # ── Device codes ──────────────────────────────────────────────────────────

    def create_device_code(
        self,
        client_id: str,
        device_id: str,
        device_name: str,
        roles: list[str] | None = None,
        scopes: list[str] | None = None,  # legado
    ) -> DeviceCodeRecord:
        """Create a single-use device code for a client.

        roles defaults to the client's roles from the file store.
        """
        from concilium.infrastructure.auth.permission_guard import LEGACY_SCOPE_TO_ROLE

        effective_roles = list(roles or [])
        if not effective_roles and scopes:
            effective_roles = list({LEGACY_SCOPE_TO_ROLE.get(s, "operator") for s in scopes})
        if not effective_roles:
            clients = {r.client_id: r for r in self.list_clients()}
            if client_id in clients:
                effective_roles = clients[client_id].roles
            else:
                effective_roles = ["operator"]

        code = "RCODE-" + secrets.token_hex(16).upper()
        record = DeviceCodeRecord(
            code=code,
            client_id=client_id,
            device_id=device_id,
            device_name=device_name,
            roles=effective_roles,
            expires_at=_iso(_now() + self.DEVICE_CODE_TTL),
        )
        with self._lock:
            self._device_codes[code] = record
        return record

    def activate_device_code(self, code: str) -> RefreshTokenRecord | None:
        """Consume a device code and persist a new refresh token.

        Returns None if the code is invalid, already used, or expired.
        """
        with self._lock:
            rec = self._device_codes.get(code)
            if rec is None or rec.used or _parse(rec.expires_at) < _now():
                return None
            rec.used = True

            token_id = "RT-" + secrets.token_hex(32)
            rt = RefreshTokenRecord(
                token_id=token_id,
                client_id=rec.client_id,
                device_id=rec.device_id,
                device_name=rec.device_name,
                roles=rec.roles,
                issued_at=_iso(_now()),
                expires_at=_iso(_now() + self.REFRESH_TOKEN_TTL),
            )
            tokens = [RefreshTokenRecord(**r) for r in self._read("refresh_tokens.json")]
            tokens.append(rt)
            self._write("refresh_tokens.json", [asdict(t) for t in tokens])
            return rt

    # ── Refresh tokens ────────────────────────────────────────────────────────

    def use_refresh_token(self, token_id: str) -> RefreshTokenRecord | None:
        """Validate and touch a refresh token. Returns None if invalid/expired/revoked."""
        with self._lock:
            tokens = [RefreshTokenRecord(**r) for r in self._read("refresh_tokens.json")]
            for t in tokens:
                if t.token_id == token_id and not t.revoked and _parse(t.expires_at) >= _now():
                    t.last_used_at = _iso(_now())
                    self._write("refresh_tokens.json", [asdict(tok) for tok in tokens])
                    return t
        return None

    def list_devices(self, client_id: str | None = None) -> list[RefreshTokenRecord]:
        """List active (non-revoked, non-expired) devices, optionally filtered by client."""
        with self._lock:
            tokens = [RefreshTokenRecord(**r) for r in self._read("refresh_tokens.json")]
        now = _now()
        return [
            t for t in tokens
            if not t.revoked
            and _parse(t.expires_at) >= now
            and (client_id is None or t.client_id == client_id)
        ]

    def revoke_device(self, device_id: str) -> int:
        """Revoke all active refresh tokens for a device. Returns count revoked."""
        with self._lock:
            tokens = [RefreshTokenRecord(**r) for r in self._read("refresh_tokens.json")]
            count = sum(1 for t in tokens if t.device_id == device_id and not t.revoked)
            for t in tokens:
                if t.device_id == device_id:
                    t.revoked = True
            if count:
                self._write("refresh_tokens.json", [asdict(t) for t in tokens])
        return count


# ── Singleton ─────────────────────────────────────────────────────────────────

_store: AuthStore | None = None
_store_lock = threading.Lock()


def get_auth_store() -> AuthStore:
    """Return the process-wide AuthStore singleton."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = AuthStore()
    return _store
