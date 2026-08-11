"""Repositório de artefatos Producao (ADR-007 + ADR-017 Opção B).

Carrega Producao de {producoes_dir}/{id}.json por ID — diretório injetado no construtor
(no catálogo real, config/catalogos/<id>/produtividades/; producoes/ é layout legado).
Não há índice em catalogos/ — os IDs são derivados dos campos producao_id das CPUs.
"""

from __future__ import annotations

import json
from pathlib import Path

from concilium.domain.models.catalog.producao import Producao


class RepositorioProducao:
    """Acesso a artefatos Producao por ID (ADR-007 / ADR-017)."""

    def __init__(self, producoes_dir: Path | str) -> None:
        self._dir = Path(producoes_dir)

    def obter(self, producao_id: str) -> Producao | None:
        """Retorna Producao ou None se não encontrada."""
        path = self._dir / f"{producao_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Producao.model_validate(data)

    def obter_ou_erro(self, producao_id: str) -> Producao:
        producao = self.obter(producao_id)
        if producao is None:
            raise FileNotFoundError(f"Producao '{producao_id}' não encontrada em {self._dir}")
        return producao

    def salvar(self, producao: Producao) -> None:
        """Persiste um artefato Producao (nunca sobrescreve versões anteriores por ID)."""
        path = self._dir / f"{producao.id}.json"
        path.write_text(producao.model_dump_json(indent=2), encoding="utf-8")

    def listar_ids(self) -> list[str]:
        """Lista todos os IDs disponíveis no diretório injetado."""
        return [p.stem for p in self._dir.glob("*.json")]

    def existe(self, producao_id: str) -> bool:
        return (self._dir / f"{producao_id}.json").exists()
