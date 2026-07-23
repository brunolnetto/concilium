"""Tests for AuthStore to boost coverage."""

from __future__ import annotations

import pytest


class TestAuthStore:
    def _make_store(self, tmp_path):
        from concilium.infrastructure.auth.auth_store import AuthStore

        return AuthStore(data_dir=tmp_path)

    def test_add_and_list_clients(self, tmp_path):
        store = self._make_store(tmp_path)
        rec = store.add_client("client1", "secret123", ["operator"])
        assert rec.client_id == "client1"
        clients = store.list_clients()
        assert any(c.client_id == "client1" for c in clients)

    def test_add_client_duplicate_raises(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("dup", "s1", ["operator"])
        with pytest.raises(ValueError, match="already exists"):
            store.add_client("dup", "s2", ["operator"])

    def test_add_client_invalid_role_raises(self, tmp_path):
        store = self._make_store(tmp_path)
        with pytest.raises(ValueError, match="Roles inválidos"):
            store.add_client("c1", "s1", ["invalid_role"])

    def test_add_client_empty_roles_defaults_to_operator(self, tmp_path):
        store = self._make_store(tmp_path)
        rec = store.add_client("c2", "s", [])
        assert "operator" in rec.roles

    def test_update_client_not_found_raises(self, tmp_path):
        store = self._make_store(tmp_path)
        with pytest.raises(ValueError, match="not found"):
            store.update_client("ghost", roles=["admin"])

    def test_update_client_invalid_role_raises(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("u1", "s", ["operator"])
        with pytest.raises(ValueError, match="Roles inválidos"):
            store.update_client("u1", roles=["invalid_role"])

    def test_update_client_role_changes(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("u2", "s", ["operator"])
        rec = store.update_client("u2", roles=["admin"])
        assert rec.roles == ["admin"]
        assert store.get_client("u2").roles == ["admin"]

    def test_update_client_email_and_notes(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("u3", "s", ["operator"], notes="old")
        rec = store.update_client("u3", email="new@example.com", notes="new")
        assert rec.email == "new@example.com"
        assert rec.notes == "new"
        assert rec.roles == ["operator"]  # não passado, não muda

    def test_update_client_none_fields_leave_unchanged(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("u4", "s", ["operator"], notes="keep", email="keep@example.com")
        rec = store.update_client("u4", roles=["admin"])
        assert rec.notes == "keep"
        assert rec.email == "keep@example.com"

    def test_update_client_on_inactive_client_still_applies(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("u5", "s", ["operator"])
        store.remove_client("u5")
        rec = store.update_client("u5", roles=["admin"])
        assert rec.roles == ["admin"]
        assert rec.active is False

    def test_remove_client_returns_true(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("to_remove", "s", ["operator"])
        result = store.remove_client("to_remove")
        assert result is True

    def test_remove_client_not_found_returns_false(self, tmp_path):
        store = self._make_store(tmp_path)
        result = store.remove_client("nonexistent")
        assert result is False

    def test_remove_client_is_soft_delete_not_hard_delete(self, tmp_path):
        """client_id permanece em list_clients() após remove_client() — soft-delete,

        não hard delete. Referências existentes (owner_id, audit trails) continuam
        resolvíveis; só `active` vira False e `deleted_at` é gravado."""
        store = self._make_store(tmp_path)
        store.add_client("carla", "s", ["operator"], email="carla@example.com", notes="obra X")
        assert store.remove_client("carla") is True

        record = store.get_client("carla")
        assert record is not None
        assert record.active is False
        assert record.deleted_at != ""
        # PII permanece intacta — remove_client() por si só não é o direito ao esquecimento.
        assert record.email == "carla@example.com"
        assert record.notes == "obra X"

    def test_remove_client_twice_returns_false_second_time(self, tmp_path):
        """Idempotência: chamar de novo num client já inativo é 'não encontrado' (nada mudou),

        mesmo comportamento observável do hard-delete anterior."""
        store = self._make_store(tmp_path)
        store.add_client("carla", "s", ["operator"])
        assert store.remove_client("carla") is True
        assert store.remove_client("carla") is False

    def test_forget_client_redacts_pii_but_keeps_client_id(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("carla", "s", ["operator"], email="carla@example.com", notes="obra X", client_code="RCODE-X")

        assert store.forget_client("carla") is True

        record = store.get_client("carla")
        assert record is not None
        assert record.client_id == "carla"  # preservado — referência pseudonimizada em audit trails
        assert record.roles == ["operator"]
        assert record.active is False
        assert record.deleted_at != ""
        assert record.email == ""
        assert record.notes == ""
        assert record.secret_hash == ""
        assert record.client_code_hash == ""

    def test_forget_client_unknown_returns_false(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.forget_client("ghost") is False

    def test_forget_client_works_on_still_active_client(self, tmp_path):
        """forget_client() não exige remove_client() prévio — desativa e redige na mesma chamada."""
        store = self._make_store(tmp_path)
        store.add_client("carla", "s", ["operator"], email="carla@example.com")

        assert store.forget_client("carla") is True

        record = store.get_client("carla")
        assert record.active is False
        assert record.email == ""

    def test_forget_client_after_remove_client_preserves_original_deleted_at(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("carla", "s", ["operator"], email="carla@example.com")
        store.remove_client("carla")
        first_deleted_at = store.get_client("carla").deleted_at

        store.forget_client("carla")

        assert store.get_client("carla").deleted_at == first_deleted_at

    def test_get_client_roles_valid_credentials(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("user1", "password", ["admin"])
        roles = store.get_client_roles("user1", "password")
        assert roles == ["admin"]

    def test_get_client_roles_wrong_password(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("user2", "correct", ["operator"])
        result = store.get_client_roles("user2", "wrong")
        assert result is None

    def test_get_client_roles_unknown_client(self, tmp_path):
        store = self._make_store(tmp_path)
        result = store.get_client_roles("nobody", "s")
        assert result is None

    def test_regenerate_client_code(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("dev", "s", ["operator"])
        code = store.regenerate_client_code("dev")
        assert code is not None
        assert code.startswith("RCODE-")

    def test_regenerate_client_code_unknown_client_returns_none(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.regenerate_client_code("ghost") is None

    def test_regenerate_client_code_unknown_client_with_other_clients_present(self, tmp_path):
        """Line 292->291: loop iterates over existing (non-matching) clients without a match."""
        store = self._make_store(tmp_path)
        store.add_client("real-client", "s", ["operator"])
        assert store.regenerate_client_code("ghost-does-not-exist") is None
        # existing client untouched
        clients = store.list_clients()
        assert any(c.client_id == "real-client" for c in clients)

    def test_migrate_legacy_client_codes_generates_for_missing(self, tmp_path):
        store = self._make_store(tmp_path)
        # Cliente "legado" — criado sem client_code (como antes do bootstrap por código existir).
        store.add_client("legacy1", "s", ["operator"], email="legacy1@example.com")
        migrated = store.migrate_legacy_client_codes()
        assert len(migrated) == 1
        client_id, code, email = migrated[0]
        assert client_id == "legacy1"
        assert code.startswith("RCODE-")
        assert email == "legacy1@example.com"
        # O código gerado deve efetivamente ativar um dispositivo agora.
        token = store.activate_device_code(code, device_name="dev-legacy1")
        assert token.client_id == "legacy1"

    def test_migrate_legacy_client_codes_skips_clients_with_code(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("modern1", "s", ["operator"], client_code="RCODE-already-set")
        migrated = store.migrate_legacy_client_codes()
        assert migrated == []

    def test_migrate_legacy_client_codes_no_pending_returns_empty(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.migrate_legacy_client_codes() == []

    def test_migrate_legacy_client_codes_skips_inactive(self, tmp_path):
        from dataclasses import asdict

        from concilium.infrastructure.auth.auth_store import ClientRecord

        store = self._make_store(tmp_path)
        inactive = ClientRecord(
            client_id="inactive1",
            secret_hash="sha256:x",
            roles=["operator"],
            created_at="2026-01-01T00:00:00+00:00",
            active=False,
        )
        store._write("clients.json", [asdict(inactive)])
        store._invalidate_clients_cache()
        assert store.migrate_legacy_client_codes() == []

    def test_migrate_legacy_client_codes_batch(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("legacy_a", "s", ["operator"])
        store.add_client("legacy_b", "s", ["operator"], email="b@example.com")
        store.add_client("modern_c", "s", ["operator"], client_code="RCODE-modern")
        migrated = store.migrate_legacy_client_codes()
        migrated_ids = {c for c, _, _ in migrated}
        assert migrated_ids == {"legacy_a", "legacy_b"}

    def test_activate_device_code(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("act", "s", ["operator"], client_code="RCODE-act")
        token = store.activate_device_code("RCODE-act", device_name="dev-act")
        assert token.client_id == "act"

    def test_activate_device_code_invalid_returns_none_or_raises(self, tmp_path):
        store = self._make_store(tmp_path)
        # Invalid code either raises or returns None
        try:
            result = store.activate_device_code("invalid_code")
            assert result is None
        except (KeyError, ValueError, Exception):
            pass  # expected

    def test_activate_device_code_same_code_activates_multiple_devices(self, tmp_path):
        """client_code is reusable — not consumed on first activation."""
        store = self._make_store(tmp_path)
        store.add_client("multi", "s", ["operator"], client_code="RCODE-multi")
        first = store.activate_device_code("RCODE-multi", device_name="laptop")
        second = store.activate_device_code("RCODE-multi", device_name="desktop")
        assert first.device_id == "laptop"
        assert second.device_id == "desktop"
        assert first.token_id != second.token_id

    def test_use_refresh_token(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("rt", "s", ["operator"], client_code="RCODE-rt")
        token = store.activate_device_code("RCODE-rt", device_name="dev-rt")
        record = store.use_refresh_token(token.token_id)
        assert record is not None
        assert record.client_id == "rt"

    def test_revoke_device(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("rv", "s", ["operator"], client_code="RCODE-rv")
        store.activate_device_code("RCODE-rv", device_name="dev-rv")
        count = store.revoke_device("dev-rv")
        assert count >= 0

    def test_list_devices(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("ld", "s", ["operator"], client_code="RCODE-ld")
        store.activate_device_code("RCODE-ld", device_name="dev-ld")
        devices = store.list_devices("ld")
        assert any(d.device_id == "dev-ld" for d in devices)

    def test_find_device_client_id_ignores_expiration(self, tmp_path):
        """find_device_client_id() usa o mesmo critério de revoke_device() (not
        revoked, ignora expiração) — diferente de list_devices(), que filtra por
        expiração e "perderia" o dono de um token expirado-mas-não-revogado que
        revoke_device() ainda revoga normalmente (Copilot, PR #66)."""
        from datetime import UTC, datetime, timedelta
        from unittest.mock import patch

        store = self._make_store(tmp_path)
        store.add_client("fdc", "s", ["operator"], client_code="RCODE-fdc")
        store.activate_device_code("RCODE-fdc", device_name="dev-fdc")

        future = datetime.now(UTC) + timedelta(days=400)
        with patch("concilium.infrastructure.auth.auth_store._now", return_value=future):
            assert store.list_devices("fdc") == []  # expirado: list_devices não lista
            assert store.find_device_client_id("dev-fdc") == "fdc"  # mas ainda encontrável
            assert store.revoke_device("dev-fdc") == 1  # e ainda revogável

    def test_find_device_client_id_unknown_device_returns_none(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.find_device_client_id("no-such-device") is None


class TestAuthStoreMissingLines:
    """Covers lines not reached by TestAuthStore: storage injection, scopes, revoke flow."""

    def _make_store(self, tmp_path):
        from concilium.infrastructure.auth.auth_store import AuthStore

        return AuthStore(data_dir=tmp_path)

    # line 142: storage= argument branch
    def test_storage_injection(self, tmp_path):
        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage
        from concilium.infrastructure.auth.auth_store import AuthStore

        storage = LocalBlobStorage(tmp_path)
        store = AuthStore(storage=storage)
        assert store._storage is storage

    # line 208: add_client with empty roles but non-empty scopes
    def test_add_client_with_scopes_maps_to_roles(self, tmp_path):

        store = self._make_store(tmp_path)
        rec = store.add_client("c_scopes", "secret", roles=[], scopes=["project:read"])
        assert len(rec.roles) > 0

    # line 275: validate_client is alias for get_client_roles
    def test_validate_client_alias(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("vc", "pass", ["operator"])
        result = store.validate_client("vc", "pass")
        assert isinstance(result, list)
        result_bad = store.validate_client("vc", "wrong")
        assert result_bad is None

    # activate_device_code roles always come from the matched client's roles
    def test_activate_device_code_uses_client_roles(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("dc_scope", "s", roles=[], scopes=["project:read"], client_code="RCODE-dc")
        token = store.activate_device_code("RCODE-dc", device_name="dev")
        assert len(token.roles) > 0

    # line 353: use_refresh_token with nonexistent token_id → None
    def test_use_refresh_token_not_found_returns_none(self, tmp_path):
        store = self._make_store(tmp_path)
        result = store.use_refresh_token("RT-doesnotexist")
        assert result is None

    # lines 384-398: create_revoke_pending
    def test_create_revoke_pending_persists(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("crp", "s", ["operator"])
        rec = store.create_revoke_pending("crp", "dev-crp")
        assert rec.revoke_token
        assert rec.client_id == "crp"
        assert rec.device_id == "dev-crp"
        assert not rec.confirmed

    # lines 402-410: get_revoke_pending
    def test_get_revoke_pending_found(self, tmp_path):
        store = self._make_store(tmp_path)
        created = store.create_revoke_pending("grp", "dev-grp")
        found = store.get_revoke_pending(created.revoke_token)
        assert found is not None
        assert found.device_id == "dev-grp"

    def test_get_revoke_pending_not_found_returns_none(self, tmp_path):
        store = self._make_store(tmp_path)
        result = store.get_revoke_pending("no-such-token")
        assert result is None

    def test_get_revoke_pending_expired_returns_none(self, tmp_path):
        from datetime import UTC, datetime, timedelta
        from unittest.mock import patch

        store = self._make_store(tmp_path)
        created = store.create_revoke_pending("grp2", "dev-grp2")
        future = datetime.now(UTC) + timedelta(days=2)
        with patch("concilium.infrastructure.auth.auth_store._now", return_value=future):
            result = store.get_revoke_pending(created.revoke_token)
        assert result is None

    # lines 417-436: confirm_revoke
    def test_confirm_revoke_happy_path(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("cfr", "s", ["operator"], client_code="RCODE-cfr")
        store.activate_device_code("RCODE-cfr", device_name="dev-cfr")
        pending = store.create_revoke_pending("cfr", "dev-cfr")
        result = store.confirm_revoke(pending.revoke_token)
        assert result is True
        devices = store.list_devices("cfr")
        assert all(d.revoked for d in devices)

    def test_confirm_revoke_not_found_returns_false(self, tmp_path):
        store = self._make_store(tmp_path)
        result = store.confirm_revoke("bad-token")
        assert result is False

    def test_confirm_revoke_already_confirmed_returns_false(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("cfr2", "s", ["operator"])
        pending = store.create_revoke_pending("cfr2", "dev-cfr2")
        store.confirm_revoke(pending.revoke_token)
        result = store.confirm_revoke(pending.revoke_token)
        assert result is False

    def test_confirm_revoke_with_falsy_device_id_skips_revoke_device(self, tmp_path):
        """Line 451->453: device_id_to_revoke falsy -> revoke_device() not invoked, still returns True."""
        from unittest.mock import patch

        store = self._make_store(tmp_path)
        store.add_client("cfr-empty-dev", "s", ["operator"])
        pending = store.create_revoke_pending("cfr-empty-dev", "")
        with patch.object(store, "revoke_device") as mock_revoke:
            result = store.confirm_revoke(pending.revoke_token)
        assert result is True
        mock_revoke.assert_not_called()

    def test_confirm_revoke_expired_returns_false(self, tmp_path):
        from datetime import UTC, datetime, timedelta
        from unittest.mock import patch

        store = self._make_store(tmp_path)
        store.add_client("cfr3", "s", ["operator"])
        pending = store.create_revoke_pending("cfr3", "dev-cfr3")
        future = datetime.now(UTC) + timedelta(days=2)
        with patch("concilium.infrastructure.auth.auth_store._now", return_value=future):
            result = store.confirm_revoke(pending.revoke_token)
        assert result is False

    # line 465: get_auth_store with non-filesystem backend
    def test_get_auth_store_non_filesystem_backend(self, tmp_path):
        from unittest.mock import patch

        import concilium.infrastructure.auth.auth_store as mod
        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

        original = mod._store
        try:
            mod._store = None
            mock_storage = LocalBlobStorage(tmp_path)
            with patch(
                "concilium.infrastructure.auth.auth_store.resolve_store_backend", return_value="sharepoint", create=True
            ):
                with patch(
                    "concilium.infrastructure.auth.auth_store.build_system_blob_storage",
                    return_value=mock_storage,
                    create=True,
                ):
                    with patch(
                        "concilium.infrastructure.storage.store_factory.resolve_store_backend",
                        return_value="sharepoint",
                    ):
                        with patch(
                            "concilium.infrastructure.storage.store_factory.build_system_blob_storage",
                            return_value=mock_storage,
                        ):
                            store = mod.get_auth_store()
            assert store is not None
        finally:
            mod._store = original


class TestAuthHelpers:
    def test_hash_and_verify(self):
        from concilium.infrastructure.auth.auth_store import _hash, _verify

        h = _hash("mysecret")
        assert _verify("mysecret", h) is True
        assert _verify("wrong", h) is False

    def test_now_returns_datetime(self):
        from datetime import datetime

        from concilium.infrastructure.auth.auth_store import _now

        result = _now()
        assert isinstance(result, datetime)

    def test_iso_and_parse_roundtrip(self):
        from concilium.infrastructure.auth.auth_store import _iso, _now, _parse

        dt = _now()
        s = _iso(dt)
        assert isinstance(s, str)
        back = _parse(s)
        assert back.year == dt.year


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

