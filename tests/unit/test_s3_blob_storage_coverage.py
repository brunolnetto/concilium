"""Coverage tests for S3BlobStorage async methods and _run ThreadPoolExecutor path.

Covers lines: 111-114, 117-121, 124-134, 137-138, 188-189.

aioboto3/aiobotocore are NOT installed in CI — we stub the entire import chain
before importing the module under test.
"""

from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Stub aioboto3 / aiobotocore so the module can be imported without them.
# ---------------------------------------------------------------------------


def _install_stubs() -> None:
    for name in ("aiobotocore", "aioboto3", "botocore", "botocore.config"):
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)

    # botocore.config.Config stub
    botocore_config = sys.modules.get("botocore.config")
    if not hasattr(botocore_config, "Config"):
        botocore_config.Config = MagicMock(return_value=None)  # type: ignore[union-attr]

    # aioboto3.Session stub
    aioboto3_mod = sys.modules["aioboto3"]
    if not hasattr(aioboto3_mod, "Session"):
        aioboto3_mod.Session = MagicMock  # type: ignore[union-attr]


_install_stubs()

from concilium.infrastructure.adapters.blob_storage.s3 import S3BlobStorage  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_s3(*, root_prefix: str = "", sse: str | None = None) -> S3BlobStorage:
    """Build an S3BlobStorage bypassing __init__ so no real AWS session is created."""
    s3 = S3BlobStorage.__new__(S3BlobStorage)
    s3._bucket = "test-bucket"
    s3._root_prefix = root_prefix.strip("/")
    s3._server_side_encryption = sse
    s3._client_kwargs = {}
    s3._session = MagicMock()
    return s3


def _make_client_cm(mock_client: AsyncMock) -> MagicMock:
    """Return an async context manager that yields mock_client."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# _get_object (lines 111-114)
# ---------------------------------------------------------------------------


def test_get_object_returns_body_bytes() -> None:
    s3 = _make_s3()

    mock_body = AsyncMock()
    mock_body.read = AsyncMock(return_value=b"hello world")

    mock_client = AsyncMock()
    mock_client.get_object = AsyncMock(return_value={"Body": mock_body})

    s3._session.client = MagicMock(return_value=_make_client_cm(mock_client))

    result = asyncio.run(s3._get_object("some/key"))

    assert result == b"hello world"
    mock_client.get_object.assert_awaited_once_with(Bucket="test-bucket", Key="some/key")
    mock_body.read.assert_awaited_once()


# ---------------------------------------------------------------------------
# _put_object (lines 117-121)
# ---------------------------------------------------------------------------


def test_put_object_without_sse() -> None:
    s3 = _make_s3(sse=None)

    mock_client = AsyncMock()
    mock_client.put_object = AsyncMock(return_value={})

    s3._session.client = MagicMock(return_value=_make_client_cm(mock_client))

    asyncio.run(s3._put_object("dir/file.bin", b"data"))

    call_kwargs = mock_client.put_object.call_args.kwargs
    assert call_kwargs["Bucket"] == "test-bucket"
    assert call_kwargs["Key"] == "dir/file.bin"
    assert call_kwargs["Body"] == b"data"
    assert "ServerSideEncryption" not in call_kwargs


def test_put_object_with_sse() -> None:
    s3 = _make_s3(sse="aws:kms")

    mock_client = AsyncMock()
    mock_client.put_object = AsyncMock(return_value={})

    s3._session.client = MagicMock(return_value=_make_client_cm(mock_client))

    asyncio.run(s3._put_object("dir/file.bin", b"encrypted"))

    call_kwargs = mock_client.put_object.call_args.kwargs
    assert call_kwargs["ServerSideEncryption"] == "aws:kms"


# ---------------------------------------------------------------------------
# _list_objects (lines 124-134)
# ---------------------------------------------------------------------------


def _make_async_paginator(pages: list[dict]) -> MagicMock:
    """Build a mock paginator whose paginate() returns an async iterator of pages."""

    async def _aiter():
        for page in pages:
            yield page

    paginator = MagicMock()
    paginator.paginate = MagicMock(return_value=_aiter())
    return paginator


def test_list_objects_with_contents() -> None:
    s3 = _make_s3(root_prefix="")

    pages = [
        {"Contents": [{"Key": "a/b.json"}, {"Key": "a/c.json"}]},
        {"Contents": [{"Key": "a/d.json"}]},
    ]

    mock_client = AsyncMock()
    mock_client.get_paginator = MagicMock(return_value=_make_async_paginator(pages))

    s3._session.client = MagicMock(return_value=_make_client_cm(mock_client))

    result = asyncio.run(s3._list_objects("a/"))

    assert sorted(result) == ["a/b.json", "a/c.json", "a/d.json"]
    mock_client.get_paginator.assert_called_once_with("list_objects_v2")


def test_list_objects_empty_pages() -> None:
    s3 = _make_s3()

    pages = [{"Contents": []}, {}]

    mock_client = AsyncMock()
    mock_client.get_paginator = MagicMock(return_value=_make_async_paginator(pages))

    s3._session.client = MagicMock(return_value=_make_client_cm(mock_client))

    result = asyncio.run(s3._list_objects("prefix/"))

    assert result == []


def test_list_objects_filters_non_string_keys() -> None:
    s3 = _make_s3()

    pages = [
        {"Contents": [{"Key": None}, {"Key": 123}, {"Key": "valid/key.txt"}]},
    ]

    mock_client = AsyncMock()
    mock_client.get_paginator = MagicMock(return_value=_make_async_paginator(pages))

    s3._session.client = MagicMock(return_value=_make_client_cm(mock_client))

    result = asyncio.run(s3._list_objects(""))

    assert result == ["valid/key.txt"]


def test_list_objects_strips_root_prefix() -> None:
    s3 = _make_s3(root_prefix="prod")

    pages = [
        {"Contents": [{"Key": "prod/data/file.json"}, {"Key": "prod"}]},
    ]

    mock_client = AsyncMock()
    mock_client.get_paginator = MagicMock(return_value=_make_async_paginator(pages))

    s3._session.client = MagicMock(return_value=_make_client_cm(mock_client))

    result = asyncio.run(s3._list_objects("prod/"))

    # "prod" -> _to_logical_key returns "" (falsy, filtered out)
    # "prod/data/file.json" -> "data/file.json"
    assert result == ["data/file.json"]


# ---------------------------------------------------------------------------
# _head_object (lines 137-138)
# ---------------------------------------------------------------------------


def test_head_object_calls_client() -> None:
    s3 = _make_s3()

    mock_client = AsyncMock()
    mock_client.head_object = AsyncMock(return_value={})

    s3._session.client = MagicMock(return_value=_make_client_cm(mock_client))

    asyncio.run(s3._head_object("some/key"))

    mock_client.head_object.assert_awaited_once_with(Bucket="test-bucket", Key="some/key")


# ---------------------------------------------------------------------------
# gerar_url_temporaria / _presign (lines 188-189)
# ---------------------------------------------------------------------------


def test_gerar_url_temporaria_returns_url_on_success() -> None:
    s3 = _make_s3()

    mock_client = AsyncMock()
    mock_client.generate_presigned_url = AsyncMock(return_value="https://example.com/signed")

    s3._session.client = MagicMock(return_value=_make_client_cm(mock_client))

    url = s3.gerar_url_temporaria("some/path.json", ttl_segundos=300)

    assert url == "https://example.com/signed"


def test_gerar_url_temporaria_returns_none_on_error() -> None:
    s3 = _make_s3()

    mock_client = AsyncMock()
    mock_client.generate_presigned_url = AsyncMock(side_effect=RuntimeError("S3 error"))

    s3._session.client = MagicMock(return_value=_make_client_cm(mock_client))

    url = s3.gerar_url_temporaria("some/path.json")

    assert url is None


def test_presign_uses_max_60_for_low_ttl() -> None:
    """ExpiresIn must be at least 60 (max(60, ttl_segundos))."""
    s3 = _make_s3()

    mock_client = AsyncMock()
    mock_client.generate_presigned_url = AsyncMock(return_value="https://example.com/url")

    s3._session.client = MagicMock(return_value=_make_client_cm(mock_client))

    s3.gerar_url_temporaria("file.bin", ttl_segundos=10)

    call_kwargs = mock_client.generate_presigned_url.call_args.kwargs
    assert call_kwargs["ExpiresIn"] == 60


# ---------------------------------------------------------------------------
# _run ThreadPoolExecutor path (lines 107-108)
# Triggered when _run is called from within a running event loop.
# ---------------------------------------------------------------------------


def test_run_threadpool_executor_path() -> None:
    """When _run is called inside a running loop, it uses ThreadPoolExecutor."""

    async def _returns_42() -> int:
        return 42

    async def _nested() -> int:
        # At this point asyncio.get_running_loop() succeeds, so _run must
        # fall into the ThreadPoolExecutor branch (lines 107-108).
        return S3BlobStorage._run(_returns_42())

    result = asyncio.run(_nested())
    assert result == 42


def test_run_no_running_loop_uses_asyncio_run() -> None:
    """When there is no running loop, _run uses asyncio.run directly."""

    async def _returns_hello() -> str:
        return "hello"

    # Called from a plain sync context -- no running loop.
    result = S3BlobStorage._run(_returns_hello())
    assert result == "hello"
