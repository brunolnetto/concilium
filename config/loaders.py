"""Loaders para dados de catálogo do Concilium.

Estrutura esperada de um catálogo (ex: config/catalogos/mendeslobo/):
    cpus.json              — definições de CPUs (lean: sem composicao_padrao_equipe)
    produtividades.json    — fichas de produtividade calibradas (composicao_padrao_equipe aqui)
    insumos/
        mao_obra.json
        equipamento.json
        material.json
        terceirizado.json  (opcional)
"""

import json
from pathlib import Path
from typing import Any


class LoaderInsumoAgnóstico:
    """Carrega insumos de diretório separado por tipo."""

    TIPOS_PERMITIDOS = ["MAO_OBRA", "EQUIPAMENTO", "MATERIAL", "TERCEIRIZADO"]

    @staticmethod
    def carregar_insumos(caminho_catalogo: Path | str) -> dict[str, Any]:
        """Carrega insumos de {caminho_catalogo}/insumos/*.json.

        Args:
            caminho_catalogo: Path absoluto para o diretório do catálogo.

        Returns:
            dict com chave "insumos" contendo lista de insumos.
        """
        caminho_catalogo = Path(caminho_catalogo)
        dir_insumos = caminho_catalogo / "insumos"

        if dir_insumos.exists() and dir_insumos.is_dir():
            return LoaderInsumoAgnóstico._carregar_de_diretorio(dir_insumos)

        return {"insumos": []}

    @staticmethod
    def _carregar_de_diretorio(dir_insumos: Path) -> dict[str, Any]:
        insumos_totais = []
        for tipo in LoaderInsumoAgnóstico.TIPOS_PERMITIDOS:
            arquivo = dir_insumos / f"{tipo.lower()}.json"
            if not arquivo.exists():
                continue
            try:
                with open(arquivo, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "insumos" in data:
                    insumos_totais.extend(data["insumos"])
                elif isinstance(data, list):
                    insumos_totais.extend(data)
            except Exception as e:
                print(f"⚠️  Erro ao carregar {arquivo}: {e}")
        return {"insumos": insumos_totais}


class LoaderProdutividades:
    """Carrega fichas de produtividade de {caminho_catalogo}/produtividades.json."""

    @staticmethod
    def carregar(caminho_catalogo: Path | str) -> dict[str, Any]:
        """Retorna dict com chave 'produtividades' contendo lista de fichas."""
        caminho_catalogo = Path(caminho_catalogo)
        arquivo = caminho_catalogo / "produtividades.json"
        if not arquivo.exists():
            return {"produtividades": []}
        try:
            with open(arquivo, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "produtividades" in data:
                return data
            if isinstance(data, list):
                return {"produtividades": data}
        except Exception as e:
            print(f"⚠️  Erro ao carregar {arquivo}: {e}")
        return {"produtividades": []}

    @staticmethod
    def carregar_como_mapa(caminho_catalogo: Path | str) -> dict[str, Any]:
        """Retorna dict[id → ficha] para lookup por producao_id."""
        dados = LoaderProdutividades.carregar(caminho_catalogo)
        return {p["id"]: p for p in dados.get("produtividades", []) if "id" in p}
