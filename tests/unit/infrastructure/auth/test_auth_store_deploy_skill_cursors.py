"""Tests for AuthStore.mark_deploy_seen / mark_skill_version_seen (ADR-144 D3).

TDD: escritos antes da implementação. Dois cursores distintos em
`ClientRecord`: `last_deploy_seen` (avança quando `ping()` entrega o aviso) e
`last_skill_version_seen` (só avança quando `obter_instrucoes_atualizadas()`
é de fato chamada — ver ADR-144 D3/A7, o motivo de serem dois campos, não um).
"""

from __future__ import annotations


class TestClientRecordDefaults:
    def _make_store(self, tmp_path):
        from concilium.infrastructure.auth.auth_store import AuthStore

        return AuthStore(data_dir=tmp_path)

    def test_new_client_has_empty_cursors_by_default(self, tmp_path):
        store = self._make_store(tmp_path)
        rec = store.add_client("c1", "s", ["operator"])
        assert rec.last_deploy_seen == ""
        assert rec.last_skill_version_seen == 0

    def test_backward_compat_for_legacy_records_without_cursor_fields(self, tmp_path):
        """Registros gravados antes destes campos existirem não têm as chaves no JSON."""
        import json

        store = self._make_store(tmp_path)
        store.add_client("legacy1", "s", ["operator"])

        # Simula um registro legado: remove as chaves novas do JSON gravado.
        # AuthStore(data_dir=...) usa prefixo "auth/" por padrão (ver __init__).
        raw_path = tmp_path / "auth" / "clients.json"
        records = json.loads(raw_path.read_text(encoding="utf-8"))
        for r in records:
            r.pop("last_deploy_seen", None)
            r.pop("last_skill_version_seen", None)
        raw_path.write_text(json.dumps(records), encoding="utf-8")
        store._invalidate_clients_cache()

        rec = store.get_client("legacy1")
        assert rec is not None
        assert rec.last_deploy_seen == ""
        assert rec.last_skill_version_seen == 0


class TestMarkDeploySeen:
    def _make_store(self, tmp_path):
        from concilium.infrastructure.auth.auth_store import AuthStore

        return AuthStore(data_dir=tmp_path)

    def test_updates_last_deploy_seen(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("c1", "s", ["operator"])

        store.mark_deploy_seen("c1", "2026-07-20T14:32:00+00:00")

        rec = store.get_client("c1")
        assert rec is not None
        assert rec.last_deploy_seen == "2026-07-20T14:32:00+00:00"

    def test_does_not_affect_skill_cursor(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("c1", "s", ["operator"])

        store.mark_deploy_seen("c1", "2026-07-20T14:32:00+00:00")

        rec = store.get_client("c1")
        assert rec is not None
        assert rec.last_skill_version_seen == 0

    def test_unknown_client_id_is_a_noop(self, tmp_path):
        store = self._make_store(tmp_path)
        store.mark_deploy_seen("ghost", "2026-07-20T14:32:00+00:00")  # não deve lançar
        assert store.get_client("ghost") is None


class TestMarkSkillVersionSeen:
    def _make_store(self, tmp_path):
        from concilium.infrastructure.auth.auth_store import AuthStore

        return AuthStore(data_dir=tmp_path)

    def test_updates_last_skill_version_seen(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("c1", "s", ["operator"])

        store.mark_skill_version_seen("c1", 3)

        rec = store.get_client("c1")
        assert rec is not None
        assert rec.last_skill_version_seen == 3

    def test_does_not_affect_deploy_cursor(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("c1", "s", ["operator"])

        store.mark_skill_version_seen("c1", 3)

        rec = store.get_client("c1")
        assert rec is not None
        assert rec.last_deploy_seen == ""

    def test_unknown_client_id_is_a_noop(self, tmp_path):
        store = self._make_store(tmp_path)
        store.mark_skill_version_seen("ghost", 3)  # não deve lançar
        assert store.get_client("ghost") is None
