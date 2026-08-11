"""Porta de abstração para Blob Storage (ADR-033 §D1)."""

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any

# Default de `ler_blobs_batch` para backends sem batching real: paraleliza via
# thread pool em vez de sequencial puro — sem isto, qualquer backend que não
# sobrescreva o método (S3, Azure, GDrive, LocalBlobStorage) perderia o
# paralelismo que o chamador (`_fetch_all_parallel`) já dava antes de existir
# este método. Teto conservador — I/O-bound, não vale abrir muito mais que
# isto por padrão (backends com necessidade real ajustam sobrescrevendo).
_DEFAULT_BATCH_WORKERS = 3


class StorageUnavailableError(Exception):
    """Backend de storage indisponível de forma persistente (não é 'blob não existe').

    Levantada por implementações concretas quando uma falha de infraestrutura
    (auth, throttling esgotado, timeout, 5xx) impede a operação — distinta de
    FileNotFoundError, que sinaliza ausência legítima do blob. Rotas de leitura
    não precisam de try/except: o handler global em app.py converte para 503
    com Retry-After.
    """


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

    def ler_blobs_batch(self, paths: list[str]) -> dict[str, bytes]:
        """Lê vários blobs de uma vez — otimização para backends onde 1 leitura
        por arquivo é caro (round-trip de rede por chamada, ex.: SharePoint/Graph).

        Implementação padrão: `ler_blob` paralelizado via thread pool pequeno
        — correta para qualquer backend, só não ganha o benefício extra de uma
        chamada em lote de verdade. Backends que suportam isso nativamente
        (SharePoint via Graph `$batch`) devem sobrescrever.

        Paths que falharem (não encontrados, erro transitório) são simplesmente
        omitidos do dict de retorno — não levanta exceção por item individual;
        o chamador decide o que fazer com paths ausentes.
        """
        if not paths:
            return {}
        result: dict[str, bytes] = {}
        with ThreadPoolExecutor(max_workers=min(_DEFAULT_BATCH_WORKERS, len(paths))) as pool:
            futures = {pool.submit(self.ler_blob, path): path for path in paths}
            for future in futures:
                path = futures[future]
                try:
                    result[path] = future.result()
                except Exception:
                    continue
        return result

    def deletar_blob(self, path: str) -> None:
        """Remove um blob do storage.

        Implementação padrão é noop — backends sem suporte a delete devem sobrescrever.
        Backends que suportam delete (SharePoint, S3, Azure) devem implementar.

        Raises:
            FileNotFoundError: Se o blob não existir (implementações podem omitir).
        """
        return

    def aprovar_versao(self, path: str) -> None:
        """Marca o blob como versão aprovada (imutável).

        Local: chmod 444. SharePoint: checkin de versão major.
        Implementação padrão é noop — backends que suportam aprovação devem sobrescrever.
        """
        return

    def gerar_url_temporaria(self, path: str, ttl_segundos: int = 900, *, scope: str = "anonymous") -> str | None:
        """Gera uma URL de acesso temporário ao blob (ADR-093 D4).

        Usada para entregar artefatos a agentes/stakeholders remotos sem tráfego
        base64 (Azure SAS, S3 presigned, link de compartilhamento SharePoint/Drive).

        `scope` só tem efeito no backend SharePoint ("anonymous" | "organization" |
        "users" — ver Graph API `createLink`); demais backends ignoram o parâmetro,
        pois seus mecanismos de URL assinada (SAS/presigned) não têm essa distinção.

        Implementação padrão retorna ``None`` — backends sem suporte a URL assinada
        (ex.: local) sinalizam ausência para o chamador decidir (ex.: entrega manual).
        """
        return None

    def health_check(self) -> dict[str, Any]:
        """Verifica a conectividade e disponibilidade do backend de storage.

        Implementação padrão — backends concretos devem sobrescrever com uma
        verificação real (ex.: GET no drive, HEAD no bucket, stat no filesystem).
        """
        return {"status": "ok", "backend": "unknown"}
