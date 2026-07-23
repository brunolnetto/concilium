"""Tests for infrastructure/deploy/deploy_log_store.py (ADR-144 D1).

TDD: escritos antes da implementação. `DeployLogStore` guarda só a última
promoção (D1 opção "MVP sem histórico completo") — ping() (D2/D3) só precisa
comparar contra a mais recente, não uma lista.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def storage(tmp_path):
    from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

    return LocalBlobStorage(tmp_path)


class TestDeployLogEntry:
    def test_fields(self):
        from concilium.infrastructure.deploy.deploy_log_store import DeployLogEntry

        entry = DeployLogEntry(
            image_tag="90caf8ae",
            api_revision="concilium-api--0000091",
            mcp_revision="concilium-mcp--0000097",
            promoted_at="2026-07-20T14:32:00+00:00",
            resumo="ADR-144: notificação de deploy embutida em ping()",
        )
        assert entry.image_tag == "90caf8ae"
        assert entry.api_revision == "concilium-api--0000091"
        assert entry.mcp_revision == "concilium-mcp--0000097"
        assert entry.promoted_at == "2026-07-20T14:32:00+00:00"
        assert entry.resumo == "ADR-144: notificação de deploy embutida em ping()"


class TestDeployLogStoreLoad:
    def test_returns_none_when_nothing_saved(self, storage):
        from concilium.infrastructure.deploy.deploy_log_store import DeployLogStore

        store = DeployLogStore(storage)
        assert store.load_latest() is None

    def test_returns_saved_entry(self, storage):
        from concilium.infrastructure.deploy.deploy_log_store import DeployLogEntry, DeployLogStore

        store = DeployLogStore(storage)
        entry = DeployLogEntry(
            image_tag="90caf8ae",
            api_revision="concilium-api--0000091",
            mcp_revision="concilium-mcp--0000097",
            promoted_at="2026-07-20T14:32:00+00:00",
            resumo="resumo curto",
        )
        store.save_latest(entry)

        loaded = store.load_latest()
        assert loaded == entry

    def test_save_overwrites_previous_entry(self, storage):
        """D1: só a última promoção é mantida — não é um histórico append-only."""
        from concilium.infrastructure.deploy.deploy_log_store import DeployLogEntry, DeployLogStore

        store = DeployLogStore(storage)
        first = DeployLogEntry(
            image_tag="aaa",
            api_revision="api--1",
            mcp_revision="mcp--1",
            promoted_at="2026-07-20T10:00:00+00:00",
            resumo="primeiro deploy",
        )
        second = DeployLogEntry(
            image_tag="bbb",
            api_revision="api--2",
            mcp_revision="mcp--2",
            promoted_at="2026-07-20T14:32:00+00:00",
            resumo="segundo deploy",
        )
        store.save_latest(first)
        store.save_latest(second)

        loaded = store.load_latest()
        assert loaded == second

    def test_empty_blob_returns_none(self, storage):
        """Mesmo padrão de CheckpointStore: blob vazio (ex.: apagado) trata como None."""
        from concilium.infrastructure.deploy.deploy_log_store import DeployLogStore

        store = DeployLogStore(storage)
        storage.gravar_blob("deploy/latest.json", b"")
        assert store.load_latest() is None
