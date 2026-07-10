"""S3 backend de armazenamento via BlobStoragePort."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from concilium.domain.repositories.blob_storage_port import BlobStoragePort
from concilium.infrastructure.settings import get_storage


class S3BlobStorage(BlobStoragePort):
    """BlobStoragePort backed by Amazon S3 (ou S3-compatible).

    Usa boto3 síncrono para aderir à interface atual do domínio.
    """

    def __init__(
        self,
        *,
        bucket: str,
        region: str | None = None,
        root_prefix: str = "",
        endpoint_url: str | None = None,
        addressing_style: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        aws_session_token: str | None = None,
        server_side_encryption: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._root_prefix = root_prefix.strip("/")
        self._server_side_encryption = server_side_encryption
        self._client_kwargs = self._build_client_kwargs(
            region=region,
            endpoint_url=endpoint_url,
            addressing_style=addressing_style,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
        )
        self._session = self._build_session()

    @classmethod
    def from_env(cls) -> S3BlobStorage:
        s3 = get_storage().s3
        bucket = s3.bucket.strip()
        if not bucket:
            raise OSError("CONCILIUM__S3_BUCKET é obrigatório para CONCILIUM__STORE_BACKEND=s3.")

        return cls(
            bucket=bucket,
            region=s3.region.strip() or None,
            root_prefix=s3.root_prefix.strip(),
            endpoint_url=s3.endpoint_url.strip() or None,
            addressing_style=s3.addressing_style.strip() or None,
            aws_access_key_id=s3.access_key_id.strip() or None,
            aws_secret_access_key=s3.secret_access_key.strip() or None,
            aws_session_token=s3.session_token.strip() or None,
            server_side_encryption=s3.server_side_encryption.strip() or None,
        )

    @staticmethod
    def _build_session() -> Any:
        try:
            import aioboto3  # ty: ignore[unresolved-import]
        except ImportError as exc:
            raise ImportError(
                "O pacote 'aioboto3' é necessário para o backend S3. Instale com: pip install 'concilium[s3]'"
            ) from exc
        return aioboto3.Session()

    @staticmethod
    def _build_client_kwargs(
        *,
        region: str | None,
        endpoint_url: str | None,
        addressing_style: str | None,
        aws_access_key_id: str | None,
        aws_secret_access_key: str | None,
        aws_session_token: str | None,
    ) -> Any:
        try:
            from botocore.config import Config as BotoConfig  # ty: ignore[unresolved-import]
        except ImportError as exc:
            raise ImportError(
                "O pacote 'aioboto3' é necessário para o backend S3. Instale com: pip install 'concilium[s3]'"
            ) from exc

        config = None
        if addressing_style:
            config = BotoConfig(s3={"addressing_style": addressing_style})

        return {
            "region_name": region,
            "endpoint_url": endpoint_url,
            "aws_access_key_id": aws_access_key_id,
            "aws_secret_access_key": aws_secret_access_key,
            "aws_session_token": aws_session_token,
            "config": config,
        }

    @staticmethod
    def _run(coro: Any) -> Any:
        """Run async code from sync methods, even if an event loop is already running."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()

    async def _get_object(self, key: str) -> bytes:
        async with self._session.client("s3", **self._client_kwargs) as client:
            response = await client.get_object(Bucket=self._bucket, Key=key)
            body = response["Body"]
            return await body.read()

    async def _put_object(self, key: str, content: bytes) -> None:
        params: dict[str, Any] = {"Bucket": self._bucket, "Key": key, "Body": content}
        if self._server_side_encryption:
            params["ServerSideEncryption"] = self._server_side_encryption
        async with self._session.client("s3", **self._client_kwargs) as client:
            await client.put_object(**params)

    async def _list_objects(self, full_prefix: str) -> list[str]:
        keys: list[str] = []
        async with self._session.client("s3", **self._client_kwargs) as client:
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self._bucket, Prefix=full_prefix):
                for item in page.get("Contents", []):
                    key = item.get("Key")
                    if isinstance(key, str):
                        logical = self._to_logical_key(key)
                        if logical:
                            keys.append(logical)
        return keys

    async def _head_object(self, key: str) -> None:
        async with self._session.client("s3", **self._client_kwargs) as client:
            await client.head_object(Bucket=self._bucket, Key=key)

    def _full_key(self, path: str) -> str:
        safe = path.strip("/")
        if self._root_prefix:
            return f"{self._root_prefix}/{safe}" if safe else self._root_prefix
        return safe

    def _to_logical_key(self, key: str) -> str:
        if not self._root_prefix:
            return key
        strip = f"{self._root_prefix}/"
        if key == self._root_prefix:
            return ""
        return key.removeprefix(strip)

    def ler_blob(self, path: str) -> bytes:
        key = self._full_key(path)
        try:
            return self._run(self._get_object(key))
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code in {"NoSuchKey", "404", "NotFound"}:
                raise FileNotFoundError(f"Blob não encontrado no S3: {path}") from exc
            raise

    def gravar_blob(self, path: str, content: bytes) -> None:
        key = self._full_key(path)
        self._run(self._put_object(key, content))

    def listar_blobs(self, prefix: str) -> list[str]:
        full_prefix = self._full_key(prefix)
        return self._run(self._list_objects(full_prefix))

    def blob_existe(self, path: str) -> bool:
        key = self._full_key(path)
        try:
            self._run(self._head_object(key))
            return True
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def aprovar_versao(self, path: str) -> None:
        # S3 não oferece check-in/lock sem configurações adicionais de object lock.
        return

    async def _presign(self, key: str, ttl_segundos: int) -> str:
        async with self._session.client("s3", **self._client_kwargs) as client:
            return await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=max(60, ttl_segundos),
            )

    def gerar_url_temporaria(self, path: str, ttl_segundos: int = 900, *, scope: str = "anonymous") -> str | None:
        """URL pré-assinada S3 (get_object) com expiração (ADR-093 D4).

        `scope` é ignorado — URLs pré-assinadas S3 não têm essa distinção (ver
        BlobStoragePort.gerar_url_temporaria).
        """
        try:
            return self._run(self._presign(self._full_key(path), ttl_segundos))
        except Exception:  # noqa: BLE001
            return None
