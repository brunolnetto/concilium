"""Porta de abstração para Blob Storage (ADR-033 §D1)."""

from abc import ABC, abstractmethod


class BlobStoragePort(ABC):
    """Interface abstrata para armazenamento de blobs (arquivos brutos).

    Obriga o isolamento do filesystem local e permite acoplar Google Drive,
    SharePoint ou S3 sem alterar o código de domínio.
    """

    @abstractmethod
    def ler_blob(self, path: str) -> bytes:
        """Lê o conteúdo binário de um blob.

        Args:
            path: Caminho ou chave do blob (ex: 'catalogo/insumos.json').

        Raises:
            FileNotFoundError: Se o blob não for encontrado.
        """
        ...

    @abstractmethod
    def gravar_blob(self, path: str, content: bytes) -> None:
        """Grava conteúdo binário em um blob, sobrescrevendo se existir."""
        ...

    @abstractmethod
    def listar_blobs(self, prefix: str) -> list[str]:
        """Lista os caminhos/chaves de todos os blobs com o prefixo dado."""
        ...

    @abstractmethod
    def blob_existe(self, path: str) -> bool:
        """Retorna True se o blob existir no storage."""
        ...

    def aprovar_versao(self, path: str) -> None:
        """Marca o blob como versão aprovada (imutável).

        Local: chmod 444. SharePoint: checkin de versão major.
        Implementação padrão é noop — backends que suportam aprovação devem sobrescrever.
        """
        return

    def gerar_url_temporaria(self, path: str, ttl_segundos: int = 900) -> str | None:
        """Gera uma URL de acesso temporário ao blob (ADR-093 D4).

        Usada para entregar artefatos a agentes/stakeholders remotos sem tráfego
        base64 (Azure SAS, S3 presigned, link de compartilhamento SharePoint/Drive).

        Implementação padrão retorna ``None`` — backends sem suporte a URL assinada
        (ex.: local) sinalizam ausência, e o chamador recai no transporte base64.
        """
        return None
