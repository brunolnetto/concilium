"""Auth data store — device codes, refresh tokens, client registry (ADR-094).

Storage strategy:
  Device codes     → in-memory only (1h TTL; ephemeral by design)
  Refresh tokens   → BlobStoragePort (90d TTL, revocable, persists across restarts)
  Clients          → BlobStoragePort (additive to CONCILIUM__AUTH_CLIENTS env var)

Backend: usa o mesmo CONCILIUM__STORE_BACKEND da aplicação (SharePoint, S3, filesystem…).
Blobs são gravados com prefixo "auth/" para isolar dos dados de projeto.
Filesystem local (CONCILIUM__AUTH_DATA_PATH) é mantido como fallback e para dev.

Thread-safety: internal threading.Lock protects all mutations.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
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
    secret_hash: str  # "sha256:<hex>"
    roles: list[str]  # ADR-099: ex. ["operator"], ["service-ci"]
    created_at: str  # ISO-8601
    active: bool = True
    notes: str = ""
    scopes: list[str] = field(default_factory=list)  # legado ADR-094, ignorado se roles presente
    email: str = ""  # ADR-123: endereço de email do usuário para notificações
    client_code_hash: str = ""  # "sha256:<hex>" — código reutilizável de bootstrap (1 por usuário, N dispositivos)


def _client_record(raw: dict) -> ClientRecord:
    """Constrói ClientRecord a partir de um dict cru do JSON store.

    Backward-compat: arquivos gravados antes do campo 'email' existir (ADR-123)
    não o têm — default "". Usa dict.setdefault em vez de merge por ** (`{**{...},
    **raw}`) porque o merge de um dict literal com um dict `Unknown` faz o type
    checker inferir um tipo de valor unificado (`str | Unknown`) para o resultado,
    o que quebra a checagem por-campo do ** unpacking no construtor.
    """
    raw = dict(raw)
    raw.setdefault("email", "")
    return ClientRecord(**raw)


def _resolve_effective_roles(roles: list[str], scopes: list[str] | None) -> list[str]:
    """Mapeia scopes legados para roles se necessário; default para 'operator'."""
    from concilium.infrastructure.auth.permission_guard import LEGACY_SCOPE_TO_ROLE

    effective_roles = list(roles)
    if not effective_roles and scopes:
        effective_roles = list({LEGACY_SCOPE_TO_ROLE.get(s, "operator") for s in scopes})
    if not effective_roles:
        effective_roles = ["operator"]
    return effective_roles


def _validate_roles(effective_roles: list[str]) -> None:
    """Raises ValueError se algum role não estiver em VALID_ROLES."""
    from concilium.infrastructure.auth.permission_guard import VALID_ROLES

    invalid = [r for r in effective_roles if r not in VALID_ROLES]
    if invalid:
        raise ValueError(f"Roles inválidos: {invalid}. Válidos: {sorted(VALID_ROLES)}")


@dataclass
class RevokePendingRecord:
    """Solicitação de revogação de dispositivo aguardando confirmação (ADR-123 F3)."""

    revoke_token: str  # token opaco para URL de confirmação
    client_id: str
    device_id: str
    requested_at: str  # ISO-8601
    expires_at: str  # ISO-8601 (+24h)
    confirmed: bool = False


@dataclass
class RefreshTokenRecord:
    token_id: str  # "RT-<hex>"
    client_id: str
    device_id: str
    device_name: str
    roles: list[str]  # ADR-099
    issued_at: str  # ISO-8601
    expires_at: str  # ISO-8601
    revoked: bool = False
    last_used_at: str = ""
    scopes: list[str] = field(default_factory=list)  # legado


def _client_code_matches(r: ClientRecord, client_code: str) -> bool:
    return bool(r.active and r.client_code_hash and _verify(client_code, r.client_code_hash))


def _build_refresh_token_record(client: ClientRecord, device_name: str, ttl: timedelta) -> RefreshTokenRecord:
    device_id = device_name or client.client_id
    token_id = "RT-" + secrets.token_hex(32)
    return RefreshTokenRecord(
        token_id=token_id,
        client_id=client.client_id,
        device_id=device_id,
        device_name=device_name or device_id,
        roles=client.roles,
        issued_at=_iso(_now()),
        expires_at=_iso(_now() + ttl),
    )


# ── Store ─────────────────────────────────────────────────────────────────────


class AuthStore:
    """Thread-safe auth data store backed by JSON files.

    Usage::

        store = get_auth_store()

        # Admin: create client com um client_code reutilizável de bootstrap
        client_code = "RCODE-" + secrets.token_hex(16).upper()
        store.add_client("bruno", "secret123", ["mcp:read", "pipeline:run"], client_code=client_code)

        # User (proxy): activate client_code em qualquer dispositivo → refresh token
        # próprio daquele dispositivo, persistido localmente. O client_code nunca é
        # consumido: pode ser reutilizado em quantos dispositivos o usuário quiser.
        rt = store.activate_device_code(client_code, device_name="macbook-bruno")

        # User (proxy): exchange refresh token → access token via token_service
        token_record = store.use_refresh_token(rt.token_id)

        # Admin: revoke device
        store.revoke_device("macbook-bruno")
    """

    REFRESH_TOKEN_TTL = timedelta(days=90)

    def __init__(
        self,
        data_dir: Path | None = None,
        storage=None,  # BlobStoragePort | None
        prefix: str = "auth",
    ) -> None:
        self._prefix = prefix.strip("/")
        if storage is not None:
            self._storage = storage
        else:
            from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

            if data_dir is None:
                raw = get_auth().data_path.strip()
                data_dir = Path(raw).expanduser().resolve() if raw else Path.home() / ".concilium" / "auth"
            self._storage = LocalBlobStorage(root_dir=data_dir)
        self._lock = threading.Lock()
        self._clients_cache: list[dict] | None = None
        self._clients_cache_at: float = 0.0

    # ── Storage helpers ───────────────────────────────────────────────────────

    def _blob(self, name: str) -> str:
        return f"{self._prefix}/{name}" if self._prefix else name

    def _read(self, name: str) -> list[dict]:
        try:
            return json.loads(self._storage.ler_blob(self._blob(name)))
        except FileNotFoundError:
            return []

    def _write(self, name: str, records: list[dict]) -> None:
        self._storage.gravar_blob(
            self._blob(name),
            json.dumps(records, indent=2, ensure_ascii=False).encode(),
        )

    _CLIENTS_TTL = 30.0  # seconds; clients.json muda apenas em operações admin

    def _read_clients(self) -> list[dict]:
        """Lê clients.json com cache TTL de 30s para evitar round-trips ao SharePoint."""
        now = time.monotonic()
        if self._clients_cache is not None and now - self._clients_cache_at < self._CLIENTS_TTL:
            return self._clients_cache
        data = self._read("clients.json")
        self._clients_cache = data
        self._clients_cache_at = now
        return data

    def _invalidate_clients_cache(self) -> None:
        self._clients_cache = None
        self._clients_cache_at = 0.0

    # ── Client management ─────────────────────────────────────────────────────

    def add_client(
        self,
        client_id: str,
        secret: str,
        roles: list[str],
        notes: str = "",
        scopes: list[str] | None = None,  # legado — convertido para roles
        email: str = "",  # ADR-123: endereço de email para notificações
        client_code: str = "",  # código de bootstrap reutilizável (ver activate_device_code)
    ) -> ClientRecord:
        """Register a new client. Raises ValueError if client_id already exists."""
        effective_roles = _resolve_effective_roles(roles, scopes)
        _validate_roles(effective_roles)

        with self._lock:
            existing = [ClientRecord(**r) for r in self._read_clients()]
            if any(r.client_id == client_id for r in existing):
                raise ValueError(f"Client '{client_id}' already exists.")
            record = ClientRecord(
                client_id=client_id,
                secret_hash=_hash(secret),
                roles=effective_roles,
                created_at=_iso(_now()),
                notes=notes,
                email=email,
                client_code_hash=_hash(client_code) if client_code else "",
            )
            existing.append(record)
            self._write("clients.json", [asdict(r) for r in existing])
            self._invalidate_clients_cache()
            return record

    def list_clients(self) -> list[ClientRecord]:
        with self._lock:
            records = self._read_clients()
            # Backward-compat: JSON files sem campo 'email' recebem default ""
            return [_client_record(r) for r in records]

    def remove_client(self, client_id: str) -> bool:
        """Deactivates a client. Returns True if found."""
        with self._lock:
            raw = self._read_clients()
            records = [_client_record(r) for r in raw]
            before = len(records)
            records = [r for r in records if r.client_id != client_id]
            if len(records) == before:
                return False
            self._write("clients.json", [asdict(r) for r in records])
            self._invalidate_clients_cache()
            return True

    def get_client_roles(self, client_id: str, secret: str) -> list[str] | None:
        """Validate credentials and return roles. None if invalid.

        Precedence: file store (ADR-099) → env var CONCILIUM__AUTH_CLIENTS (ADR-094 historical).
        Historical clients with 'scopes' are mapped to equivalent roles.
        """
        with self._lock:
            raw = self._read_clients()
            records = [_client_record(r) for r in raw]
        for r in records:
            if r.client_id == client_id and r.active and _verify(secret, r.secret_hash):
                return r.roles
        # Fallback: env-var store (ADR-094 historical) → map scopes to roles
        from concilium.infrastructure.auth.client_store import validate_client as _env_validate
        from concilium.infrastructure.auth.permission_guard import LEGACY_SCOPE_TO_ROLE

        scopes = _env_validate(client_id, secret)
        if scopes is None:
            return None
        return list({LEGACY_SCOPE_TO_ROLE.get(s, "operator") for s in scopes})

    def validate_client(self, client_id: str, secret: str) -> list[str] | None:
        """Legado ADR-094: alias para get_client_roles()."""
        return self.get_client_roles(client_id, secret)

    # ── Client code (bootstrap reutilizável, 1 por usuário / N dispositivos) ────

    def regenerate_client_code(self, client_id: str) -> str | None:
        """Generate and persist a new client_code for client_id, replacing any previous one.

        Returns the plaintext code (shown once), or None if client_id doesn't exist.
        """
        code = "RCODE-" + secrets.token_hex(16).upper()
        with self._lock:
            raw = self._read_clients()
            records = [ClientRecord(**r) for r in raw]
            for r in records:
                if r.client_id == client_id:
                    r.client_code_hash = _hash(code)
                    self._write("clients.json", [asdict(x) for x in records])
                    self._invalidate_clients_cache()
                    return code
        return None

    def migrate_legacy_client_codes(self) -> list[tuple[str, str, str]]:
        """Gera client_code para todo client ativo criado antes do bootstrap por código (ADR-099 F...).

        Clients registrados antes da introdução de client_code_hash não conseguem ativar
        nenhum dispositivo novo (activate_device_code() sempre rejeita — não há hash para
        comparar). Roda uma vez para migrar todos de uma vez em lote, em vez de descobrir
        e corrigir usuário por usuário conforme cada um reporta o problema.

        Returns:
            Lista de (client_id, client_code, email) para cada client migrado — o código é
            mostrado apenas aqui (não fica recuperável depois). Lista vazia se não há
            clients pendentes.
        """
        migrated: list[tuple[str, str, str]] = []
        with self._lock:
            raw = self._read_clients()
            records = [ClientRecord(**r) for r in raw]
            for r in records:
                if r.active and not r.client_code_hash:
                    code = "RCODE-" + secrets.token_hex(16).upper()
                    r.client_code_hash = _hash(code)
                    migrated.append((r.client_id, code, r.email))
            if migrated:
                self._write("clients.json", [asdict(x) for x in records])
                self._invalidate_clients_cache()
        return migrated

    def activate_device_code(self, client_code: str, device_name: str = "") -> RefreshTokenRecord | None:
        """Exchange a per-user client_code for a new refresh token bound to device_name.

        Unlike the legacy per-device single-use code, client_code is never consumed:
        the same code can activate any number of devices, each getting its own
        refresh token keyed by device_name. Returns None if the code doesn't match
        any active client.
        """
        with self._lock:
            records = [ClientRecord(**r) for r in self._read_clients()]
            client = next((r for r in records if _client_code_matches(r, client_code)), None)
            if client is None:
                return None

            rt = _build_refresh_token_record(client, device_name, self.REFRESH_TOKEN_TTL)
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
            t
            for t in tokens
            if not t.revoked and _parse(t.expires_at) >= now and (client_id is None or t.client_id == client_id)
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

    # ── Revoke pending (ADR-123 F3) ───────────────────────────────────────────

    REVOKE_PENDING_TTL = timedelta(hours=24)

    def create_revoke_pending(self, client_id: str, device_id: str) -> RevokePendingRecord:
        """Cria um pedido de revogação pendente com token opaco. Persiste em revoke_pending.json."""
        revoke_token = secrets.token_urlsafe(32)
        now = _now()
        record = RevokePendingRecord(
            revoke_token=revoke_token,
            client_id=client_id,
            device_id=device_id,
            requested_at=_iso(now),
            expires_at=_iso(now + self.REVOKE_PENDING_TTL),
            confirmed=False,
        )
        with self._lock:
            existing = [RevokePendingRecord(**r) for r in self._read("revoke_pending.json")]
            existing.append(record)
            self._write("revoke_pending.json", [asdict(r) for r in existing])
        return record

    def get_revoke_pending(self, revoke_token: str) -> RevokePendingRecord | None:
        """Busca um pedido de revogação pelo token. Retorna None se não encontrado ou expirado."""
        with self._lock:
            records = [RevokePendingRecord(**r) for r in self._read("revoke_pending.json")]
        now = _now()
        for rec in records:
            if rec.revoke_token == revoke_token:
                if _parse(rec.expires_at) < now:
                    return None  # expirado
                return rec
        return None

    def confirm_revoke(self, revoke_token: str) -> bool:
        """Confirma a revogação: marca como confirmado e revoga o dispositivo.

        Returns True se encontrado e válido (não expirado, não já confirmado).
        """
        with self._lock:
            records = [RevokePendingRecord(**r) for r in self._read("revoke_pending.json")]
            now = _now()
            found = False
            device_id_to_revoke: str | None = None
            for rec in records:
                if rec.revoke_token == revoke_token:
                    if _parse(rec.expires_at) < now or rec.confirmed:
                        return False
                    rec.confirmed = True
                    device_id_to_revoke = rec.device_id
                    found = True
                    break
            if not found:
                return False
            self._write("revoke_pending.json", [asdict(r) for r in records])

        if device_id_to_revoke:
            self.revoke_device(device_id_to_revoke)
        return True


# ── Singleton ─────────────────────────────────────────────────────────────────

_store: AuthStore | None = None
_store_lock = threading.Lock()


def get_auth_store() -> AuthStore:
    """Return the process-wide AuthStore singleton.

    Usa o mesmo CONCILIUM__STORE_BACKEND da aplicação. Para filesystem
    (dev/CI), grava em CONCILIUM__AUTH_DATA_PATH ou ~/.concilium/auth/.
    Para SharePoint/S3/Azure, grava em {root_path}/auth/.
    """
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:  # pragma: no cover
                from concilium.infrastructure.storage.store_factory import (
                    build_blob_storage,
                    resolve_store_backend,
                )

                backend = resolve_store_backend()
                if backend == "filesystem":
                    _store = AuthStore()  # usa data_dir local (CONCILIUM__AUTH_DATA_PATH)
                else:
                    _store = AuthStore(storage=build_blob_storage(), prefix="auth")
    assert _store is not None  # double-checked locking sempre atribui antes daqui
    return _store
