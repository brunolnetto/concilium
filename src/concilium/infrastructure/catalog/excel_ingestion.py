"""Pipeline de Ingestão de Catálogo via Excel (ADR-033 §D2).

Lê planilhas de referência (Source of Truth humana), aplica validações de domínio
(ADR-032, detecção de ciclo DFS) e grava instâncias versionadas no BlobStorage.
"""

import json
from datetime import date

from concilium.domain.repositories.blob_storage_port import BlobStoragePort
from concilium.domain.validations.circular_deps import validar_sem_ciclos
from concilium.domain.validations.cpu_insumo import ValidadorCPUInsumo


class ExcelIngestionPipeline:
    """Coordena a leitura do Excel, validação pesada e gravação em blob."""

    def __init__(self, storage: BlobStoragePort):
        self.storage = storage

    def parse_planilha(self, excel_bytes: bytes) -> dict[str, list[dict]]:
        """Lê os bytes do Excel e extrai as entidades brutas.

        Na implementação real, usaria pandas/openpyxl para ler as abas 'Insumos',
        'CPUs' e 'Jurisdição'.
        """
        # TODO: Implementar parser real com pandas
        # return parse_excel_to_dict(excel_bytes)

        # Mock do retorno para manter o fluxo
        return {"insumos": [], "cpus": [], "jurisdicoes": []}

    def processar_catalogo(self, data_base: date, versao_tag: str, excel_bytes: bytes) -> str:
        """Executa o pipeline completo de ingestão.

        1. Parse do arquivo físico
        2. Construção de modelos brutos
        3. Validação cruzada (Insumos vs CPUs)
        4. Detecção de dependência circular
        5. Geração e persistência de blobs JSON

        Args:
            data_base: Data de vigência desta versão da planilha
            versao_tag: Identificador da versão (ex: '2026-05-rev1')
            excel_bytes: Arquivo físico

        Returns:
            O prefixo de caminho salvo no blob storage.
        """
        # 1. Parsing
        dados_brutos = self.parse_planilha(excel_bytes)

        # 2. Validação base e cruzada (ADR-032 D1)
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        validador = ValidadorCPUInsumo(RepositorioInsumo(dados_brutos))
        erros_fatais = []
        for cpu in dados_brutos.get("cpus", []):
            for erro in validador.validar_cpu_completa(cpu):
                if erro.status == "ERRO":
                    erros_fatais.append(erro)

        # Interromper se houver erros impeditivos
        if erros_fatais:
            raise ValueError(f"Planilha inválida. Foram encontrados {len(erros_fatais)} erros críticos.")

        # 3. Detecção de ciclos em CPUs (ADR-032 D5)
        # validar_sem_ciclos levanta ValueError se achar loop
        validar_sem_ciclos(dados_brutos)

        # 4. Transformação para Modelos Versionados (simplificado)
        # Aqui, no mundo real, leríamos o histórico prévio do BlobStorage
        # para anexar a nova 'VersaoInsumo' no modelo existente.
        for _i in dados_brutos["insumos"]:
            # Mock de mapeamento para versão
            pass

        for _c in dados_brutos["cpus"]:
            # Mock de mapeamento
            pass

        # 5. Persistência no Blob Storage (ADR-033 D1)
        catalogo_final = {
            "versao": versao_tag,
            "data_base": data_base.isoformat(),
            "insumos": dados_brutos["insumos"],  # Na real: [iv.model_dump() for iv in insumos_versionados]
            "cpus": dados_brutos["cpus"],
        }

        blob_path = f"catalogos/snapshots/{versao_tag}/catalogo.json"

        payload = json.dumps(catalogo_final, indent=2, ensure_ascii=False).encode("utf-8")
        self.storage.gravar_blob(blob_path, payload)

        return blob_path
