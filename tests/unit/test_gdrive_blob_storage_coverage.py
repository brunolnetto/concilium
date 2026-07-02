"""Tests for missing coverage lines in GoogleDriveBlobStorage.

Targets lines: 77, 80, 90-105, 114-116, 130-134, 217-218
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from concilium.infrastructure.adapters.blob_storage.gdrive import GoogleDriveBlobStorage


@pytest.fixture
def gdrive():
    g = GoogleDriveBlobStorage.__new__(GoogleDriveBlobStorage)
    g._root_folder_id = "root-id"
    g._folder_cache = {}
    g._svc = MagicMock()
    return g


# ── _files() and _permissions() ───────────────────────────────────────────────


def test_files_returns_service_files(gdrive):
    """Line 77: _files() delegates to _service().files()."""
    mock_svc = MagicMock()
    mock_files = MagicMock()
    mock_svc.files.return_value = mock_files

    with patch.object(gdrive, "_service", return_value=mock_svc):
        result = gdrive._files()

    assert result is mock_files
    mock_svc.files.assert_called_once()


def test_permissions_returns_service_permissions(gdrive):
    """Line 80: _permissions() delegates to _service().permissions()."""
    mock_svc = MagicMock()
    mock_perms = MagicMock()
    mock_svc.permissions.return_value = mock_perms

    with patch.object(gdrive, "_service", return_value=mock_svc):
        result = gdrive._permissions()

    assert result is mock_perms
    mock_svc.permissions.assert_called_once()


# ── _resolve_folder() ─────────────────────────────────────────────────────────


def test_resolve_folder_empty_segments_returns_root(gdrive):
    """Lines 90-92: empty segments key '' found in cache returns root_folder_id."""
    gdrive._folder_cache = {"": "root-id"}
    result = gdrive._resolve_folder([], create=False)
    assert result == "root-id"


def test_resolve_folder_all_segments_cached(gdrive):
    """Lines 90-92: full key present in cache → returns immediately without loop."""
    gdrive._folder_cache = {"": "root-id", "a/b": "cached-fid"}
    result = gdrive._resolve_folder(["a", "b"], create=False)
    assert result == "cached-fid"


def test_resolve_folder_partial_segment_cached(gdrive):
    """Lines 98-100: partial acc_key hit → sets parent from cache and continues."""
    gdrive._folder_cache = {"": "root-id", "a": "fid-a"}

    child_fid = "fid-b"
    with patch.object(gdrive, "_find_child", return_value=child_fid):
        result = gdrive._resolve_folder(["a", "b"], create=False)

    assert result == child_fid
    assert gdrive._folder_cache["a/b"] == child_fid


def test_resolve_folder_child_not_found_create_false_returns_none(gdrive):
    """Lines 102-104: _find_child returns None and create=False → None."""
    gdrive._folder_cache = {}

    with patch.object(gdrive, "_find_child", return_value=None):
        result = gdrive._resolve_folder(["missing"], create=False)

    assert result is None


def test_resolve_folder_child_not_found_create_true_creates_folder(gdrive):
    """Lines 104-115: _find_child returns None and create=True → creates folder, caches, returns fid."""
    gdrive._folder_cache = {}

    new_fid = "new-folder-id"
    mock_files = MagicMock()
    mock_files.create.return_value.execute.return_value = {"id": new_fid}

    with (
        patch.object(gdrive, "_find_child", return_value=None),
        patch.object(gdrive, "_files", return_value=mock_files),
    ):
        result = gdrive._resolve_folder(["newdir"], create=True)

    assert result == new_fid
    assert gdrive._folder_cache["newdir"] == new_fid
    mock_files.create.assert_called_once()
    call_kwargs = mock_files.create.call_args
    call_kwargs.kwargs.get("body") or call_kwargs[1].get("body") or call_kwargs[0][0]
    # Verify create was called with the segment name
    assert "newdir" in str(call_kwargs)


def test_resolve_folder_child_found_uses_existing_fid(gdrive):
    """Lines 101, 114-116: _find_child returns fid → cached and used as parent."""
    gdrive._folder_cache = {}
    existing_fid = "existing-fid"

    with patch.object(gdrive, "_find_child", return_value=existing_fid):
        result = gdrive._resolve_folder(["found"], create=False)

    assert result == existing_fid
    assert gdrive._folder_cache["found"] == existing_fid


def test_resolve_folder_multi_segment_creates_nested(gdrive):
    """Lines 104-116: multiple missing segments with create=True → creates each, caches all."""
    gdrive._folder_cache = {}

    def make_create(seg_fid):
        m = MagicMock()
        m.execute.return_value = {"id": seg_fid}
        return m

    created = iter(["fid-a", "fid-b"])

    mock_files = MagicMock()
    mock_files.create.side_effect = lambda **kw: MagicMock(execute=MagicMock(return_value={"id": next(created)}))

    with (
        patch.object(gdrive, "_find_child", return_value=None),
        patch.object(gdrive, "_files", return_value=mock_files),
    ):
        result = gdrive._resolve_folder(["a", "b"], create=True)

    assert result == "fid-b"
    assert gdrive._folder_cache["a"] == "fid-a"
    assert gdrive._folder_cache["a/b"] == "fid-b"


# ── _file_id() ────────────────────────────────────────────────────────────────


def test_file_id_folder_not_found_returns_none(gdrive):
    """Lines 131-133: _resolve_folder returns None → _file_id returns None."""
    with patch.object(gdrive, "_resolve_folder", return_value=None), patch.object(gdrive, "_find_child") as mock_find:
        result = gdrive._file_id("missing/folder/file.txt")

    assert result is None
    mock_find.assert_not_called()


def test_file_id_folder_found_child_found(gdrive):
    """Lines 131, 134: folder resolved, child found → returns child id."""
    with (
        patch.object(gdrive, "_resolve_folder", return_value="folder-id"),
        patch.object(gdrive, "_find_child", return_value="file-id"),
    ):
        result = gdrive._file_id("some/folder/file.txt")

    assert result == "file-id"


def test_file_id_folder_found_child_not_found(gdrive):
    """Line 134: folder resolved but file absent → returns None."""
    with (
        patch.object(gdrive, "_resolve_folder", return_value="folder-id"),
        patch.object(gdrive, "_find_child", return_value=None),
    ):
        result = gdrive._file_id("some/folder/missing.txt")

    assert result is None


def test_file_id_passes_create_folders_flag(gdrive):
    """_file_id forwards create_folders to _resolve_folder."""
    with (
        patch.object(gdrive, "_resolve_folder", return_value="fid") as mock_resolve,
        patch.object(gdrive, "_find_child", return_value="child-fid"),
    ):
        gdrive._file_id("a/b/c.txt", create_folders=True)

    mock_resolve.assert_called_once_with(["a", "b"], create=True)


# ── gerar_url_temporaria() ────────────────────────────────────────────────────


def test_gerar_url_temporaria_file_not_found_returns_none(gdrive):
    """Lines 206-208: _file_id returns None → gerar_url_temporaria returns None."""
    with patch.object(gdrive, "_file_id", return_value=None):
        result = gdrive.gerar_url_temporaria("nonexistent/file.txt")

    assert result is None


def test_gerar_url_temporaria_success_with_webcontent_link(gdrive):
    """Lines 217-218: happy path returns webContentLink."""
    mock_files = MagicMock()
    mock_files.get.return_value.execute.return_value = {
        "webContentLink": "https://drive.example.com/download?id=fid",
        "webViewLink": "https://drive.example.com/view?id=fid",
    }

    mock_perms = MagicMock()
    # First create (with expiration) succeeds
    mock_perms.create.return_value.execute.return_value = {}

    with (
        patch.object(gdrive, "_file_id", return_value="fid"),
        patch.object(gdrive, "_files", return_value=mock_files),
        patch.object(gdrive, "_permissions", return_value=mock_perms),
    ):
        result = gdrive.gerar_url_temporaria("some/file.txt")

    assert result == "https://drive.example.com/download?id=fid"
    mock_perms.create.assert_called_once()


def test_gerar_url_temporaria_fallback_permission_on_expiration_error(gdrive):
    """Lines 217-218: expiration create raises → fallback create without expiration."""
    mock_files = MagicMock()
    mock_files.get.return_value.execute.return_value = {
        "webContentLink": None,
        "webViewLink": "https://drive.example.com/view?id=fid",
    }

    mock_perms = MagicMock()
    # First call (with expiry) raises, second call (plain) succeeds
    mock_perms.create.side_effect = [
        MagicMock(execute=MagicMock(side_effect=Exception("expiry not supported"))),
        MagicMock(execute=MagicMock(return_value={})),
    ]

    with (
        patch.object(gdrive, "_file_id", return_value="fid"),
        patch.object(gdrive, "_files", return_value=mock_files),
        patch.object(gdrive, "_permissions", return_value=mock_perms),
    ):
        result = gdrive.gerar_url_temporaria("some/file.txt")

    assert result == "https://drive.example.com/view?id=fid"
    assert mock_perms.create.call_count == 2


def test_gerar_url_temporaria_outer_exception_returns_none(gdrive):
    """Lines 221-222: outer exception → returns None."""
    with patch.object(gdrive, "_file_id", side_effect=Exception("network error")):
        result = gdrive.gerar_url_temporaria("some/file.txt")

    assert result is None


def test_gerar_url_temporaria_fallback_create_raises_returns_none(gdrive):
    """Outer except catches when both permission creates fail."""
    mock_perms = MagicMock()
    mock_perms.create.return_value.execute.side_effect = Exception("both fail")

    with (
        patch.object(gdrive, "_file_id", return_value="fid"),
        patch.object(gdrive, "_files", MagicMock()),
        patch.object(gdrive, "_permissions", return_value=mock_perms),
    ):
        result = gdrive.gerar_url_temporaria("some/file.txt")

    assert result is None
