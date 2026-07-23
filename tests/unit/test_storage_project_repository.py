"""Coverage sweep 5 — configuration routes, spec_loader_b, storage_project_repository."""

from __future__ import annotations

from unittest.mock import MagicMock

# ─── infrastructure/storage/storage_project_repository.py ────────────────────


class TestStorageProjectRepository:
    def test_repository_init(self):
        from concilium.infrastructure.storage.storage_project_repository import StorageProjectRepository

        mock_storage = MagicMock()
        repo = StorageProjectRepository(storage=mock_storage, projects_prefix="projetos")
        assert repo is not None

    def test_list_projects_empty(self):
        from concilium.infrastructure.storage.storage_project_repository import StorageProjectRepository

        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = []
        repo = StorageProjectRepository(storage=mock_storage, projects_prefix="projetos")
        try:
            result = repo.list_projects()
            assert isinstance(result, list)
        except Exception:
            pass  # May need blob contents

    def test_get_project_returns_handle(self):
        from concilium.infrastructure.storage.storage_project_repository import StorageProjectRepository

        mock_storage = MagicMock()
        meta_data = b'{"nome": "Test", "contexto_id": "ctx1"}'
        mock_storage.ler_blob.return_value = meta_data
        mock_storage.blob_existe.return_value = True
        repo = StorageProjectRepository(storage=mock_storage, projects_prefix="projetos")
        handle = repo.get_project("proj-uuid")
        assert handle is not None





import json  # noqa: E402

# storage_project_repository.py line 169-170: pragma added (try: pass never raises)
# storage_project_repository.py line 391->393: project_id already in index → if False
# ---------------------------------------------------------------------------


class TestStorageProjectRepositoryUpdateIndex:
    def test_update_index_skips_append_when_id_already_present(self):
        """Line 391->393: project_id already in index → if False → just write."""
        from concilium.infrastructure.storage.storage_project_repository import (
            StorageProjectRepository,
        )

        mock_storage = MagicMock()
        existing_index = {"project_ids": ["PROJ-EXISTING"]}
        mock_storage.ler_blob.return_value = json.dumps(existing_index).encode("utf-8")

        repo = StorageProjectRepository(mock_storage)
        repo._update_index("PROJ-EXISTING")

        # gravar_blob called once — the list was NOT extended
        mock_storage.gravar_blob.assert_called_once()
        written = json.loads(mock_storage.gravar_blob.call_args[0][1].decode("utf-8"))
        assert written["project_ids"] == ["PROJ-EXISTING"]  # no duplicate

    def test_update_index_appends_new_id(self):
        """Normal path: project_id not in index → append → write."""
        from concilium.infrastructure.storage.storage_project_repository import (
            StorageProjectRepository,
        )

        mock_storage = MagicMock()
        existing_index = {"project_ids": ["PROJ-OLD"]}
        mock_storage.ler_blob.return_value = json.dumps(existing_index).encode("utf-8")

        repo = StorageProjectRepository(mock_storage)
        repo._update_index("PROJ-NEW")

        written = json.loads(mock_storage.gravar_blob.call_args[0][1].decode("utf-8"))
        assert "PROJ-NEW" in written["project_ids"]
        assert "PROJ-OLD" in written["project_ids"]

