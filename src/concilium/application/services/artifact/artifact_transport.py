"""ADR-093 D4 — Transporte adaptativo de artefatos por ambiente.

Abstrai *como* um blob (artefato binário ou bundle zip) é entregue ao consumidor:

- **Local (default):** base64 inline quando abaixo do limite; acima, devolve o
  caminho em disco (ou base64 best-effort para blobs em memória sem caminho).
- **Azure Blob (produção, ADR-096):** upload para o Blob Storage + URL pré-assinada
  com TTL. Stub até a infraestrutura do ADR-096 existir.

A fronteira é a mesma em ambos: ``deliver(nome, data, mime)`` → dict com ``encoding``
e o payload correspondente (``conteudo_base64`` | ``caminho`` | ``url``). Trocar de
ambiente é trocar a implementação do transporte — nenhum chamador muda.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

_MB = 1024 * 1024


@runtime_checkable
class ArtifactTransport(Protocol):
    """Porta de entrega de um blob de artefato."""

    def deliver(self, *, nome: str, data: bytes, mime: str, source_path: Path | None = None) -> dict[str, Any]:
        """Entrega ``data`` e devolve os campos de transporte (encoding + payload)."""
        ...


class LocalBase64Transport:
    """Entrega local: base64 inline abaixo de ``max_mb``; senão, caminho em disco."""

    def __init__(self, max_mb: float = 10.0) -> None:
        self.max_mb = max_mb

    def deliver(self, *, nome: str, data: bytes, mime: str, source_path: Path | None = None) -> dict[str, Any]:
        size = len(data)
        size_mb = round(size / _MB, 3)
        if size <= self.max_mb * _MB:
            return {
                "encoding": "base64",
                "tamanho_mb": size_mb,
                "conteudo_base64": base64.b64encode(data).decode("ascii"),
            }
        if source_path is not None:
            return {
                "encoding": "path",
                "tamanho_mb": size_mb,
                "caminho": str(source_path),
                "aviso": (
                    f"Arquivo de {size_mb} MB excede o limite inline de {self.max_mb} MB; "
                    "leia pelo caminho ou configure transporte Azure (ADR-096) para URL pré-assinada."
                ),
            }
        # Blob em memória (bundle) sem caminho: base64 best-effort com aviso.
        return {
            "encoding": "base64",
            "tamanho_mb": size_mb,
            "conteudo_base64": base64.b64encode(data).decode("ascii"),
            "aviso": (
                f"Bundle de {size_mb} MB acima do limite recomendado de {self.max_mb} MB; "
                "em produção use transporte Azure (ADR-096) para URL pré-assinada."
            ),
        }


class BlobStorageTransport:
    """Entrega via qualquer ``BlobStoragePort`` (Azure Blob, SharePoint, GDrive, S3).

    Faz upload do blob e devolve uma URL temporária (SAS / presigned / sharing link)
    quando o backend suporta; caso contrário recai em base64 inline. Único ponto de
    integração entre o serviço de artefatos (ADR-093) e os adapters de storage
    (ADR-033/047/096) — trocar de nuvem é trocar o `port` injetado.
    """

    def __init__(self, port: Any, *, prefixo: str = "entregas", ttl_segundos: int = 900) -> None:
        self.port = port
        self.prefixo = prefixo.strip("/")
        self.ttl_segundos = ttl_segundos

    def deliver(self, *, nome: str, data: bytes, mime: str, source_path: Path | None = None) -> dict[str, Any]:
        size_mb = round(len(data) / _MB, 3)
        key = f"{self.prefixo}/{nome}" if self.prefixo else nome
        try:
            self.port.gravar_blob(key, data)
            url = self.port.gerar_url_temporaria(key, self.ttl_segundos)
        except Exception as exc:  # noqa: BLE001 — degrada para base64 inline
            return {
                "encoding": "base64",
                "tamanho_mb": size_mb,
                "conteudo_base64": base64.b64encode(data).decode("ascii"),
                "aviso": f"Falha ao entregar via storage remoto ({exc}); usando base64 inline.",
            }
        if url:
            return {
                "encoding": "url",
                "tamanho_mb": size_mb,
                "url": url,
                "expira_em_segundos": self.ttl_segundos,
                "blob_path": key,
            }
        # Backend gravou mas não gera URL assinada (ex.: local) → base64.
        return {
            "encoding": "base64",
            "tamanho_mb": size_mb,
            "conteudo_base64": base64.b64encode(data).decode("ascii"),
            "blob_path": key,
            "aviso": "Backend sem URL pré-assinada; conteúdo entregue inline.",
        }


def _blob_port_from_env(escolha: str) -> Any:
    """Instancia o adapter de BlobStoragePort para o backend escolhido."""
    if escolha in ("azure", "azure_blob", "blob"):
        from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

        return AzureBlobStorage.from_env()
    if escolha in ("sharepoint", "sp"):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointBlobStorage

        return SharePointBlobStorage.from_env()
    if escolha in ("gdrive", "google_drive", "drive"):
        from concilium.infrastructure.adapters.blob_storage.gdrive import GoogleDriveBlobStorage

        return GoogleDriveBlobStorage.from_env()
    if escolha == "s3":
        from concilium.infrastructure.adapters.blob_storage.s3 import S3BlobStorage

        return S3BlobStorage.from_env()
    raise ValueError(f"Backend de transporte desconhecido: {escolha!r}")


def get_transport(nome: str | None = None, *, max_mb: float = 10.0) -> ArtifactTransport:
    """Seleciona o transporte por nome ou via env ``CONCILIUM__ARTIFACT_TRANSPORT``.

    Valores: ``local`` (default) | ``azure_blob`` | ``sharepoint`` | ``gdrive`` | ``s3``.
    Backends remotos entregam via URL temporária; local entrega base64/caminho.
    """
    from concilium.infrastructure.settings import get_runtime

    escolha = (nome or get_runtime().artifact_transport or "local").strip().lower()
    if escolha in ("local", ""):
        return LocalBase64Transport(max_mb=max_mb)
    return BlobStorageTransport(_blob_port_from_env(escolha))


__all__ = [
    "ArtifactTransport",
    "LocalBase64Transport",
    "BlobStorageTransport",
    "get_transport",
]
