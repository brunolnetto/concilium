"""Implementação do BlobStoragePort para provedores de nuvem (ADR-033 §D1)."""

from concilium.domain.repositories.blob_storage_port import BlobStoragePort


class CloudBlobStorageAdapter(BlobStoragePort):
    """Adapter genérico para Cloud Storage (S3 / SharePoint / GDrive).

    Demonstra a integração com APIs externas, utilizando credenciais
    via variáveis de ambiente, cumprindo a Fase 4 do ADR-033.
    """

    def __init__(self, provider: str = "AWS_S3"):
        self.provider = provider

        # Em produção, validaria credenciais:
        # self.api_key = os.environ.get(f"{provider}_API_KEY")
        # if not self.api_key:
        #     raise ValueError(f"Credenciais ausentes para provedor {provider}")

    def ler_blob(self, path: str) -> bytes:
        """Faz download do arquivo binário da nuvem."""
        # mock: return requests.get(f"https://api.{self.provider}.com/blobs/{path}").content
        raise NotImplementedError(f"[{self.provider}] Download real não implementado no mock.")

    def gravar_blob(self, path: str, content: bytes) -> None:
        """Faz upload de arquivo binário para a nuvem."""
        # mock: requests.put(f"https://api.{self.provider}.com/blobs/{path}", data=content)
        pass

    def listar_blobs(self, prefix: str) -> list[str]:
        """Lista caminhos no bucket remoto com o prefixo."""
        # mock: return requests.get(f"https://api.{self.provider}.com/blobs?prefix={prefix}").json()
        return []

    def blob_existe(self, path: str) -> bool:
        """Verifica a existência do blob com requisição HEAD."""
        # mock: return requests.head(f"https://api.{self.provider}.com/blobs/{path}").status_code == 200
        return False
