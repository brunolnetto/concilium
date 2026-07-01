"""ADR-017 §D5 — CatalogUpdater: aplica PropostaAtualizacao com versionamento.

Regras invariantes:
- Producao: nunca sobrescreve — cria nova versão (PROD-001 -> PROD-002)
  CPUs continuam referenciando a versão anterior até migração explícita.
- Insumo: atualiza custo_unitario in-place com registro de auditoria.
- Classe de cobertura: atualiza capacidade_cobertura in-place no insumo.

Nenhuma alteração direta ao catálogo sem PropostaAtualizacao APROVADA.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from concilium.domain.models.catalog.producao import AuditoriaProducao, OrigemProducao, QualidadeProducao
from concilium.domain.models.project.observacao import PropostaAtualizacao
from concilium.infrastructure.repositories.producao import RepositorioProducao


@dataclass
class CatalogUpdateResult:
    sucesso: bool
    novo_artefato_id: str | None
    versao_anterior: str | None
    nota: str


class CatalogUpdater:
    """Aplica propostas de atualização aprovadas ao catálogo com trilha de auditoria."""

    def __init__(
        self,
        producoes_dir: Path | str,
        insumos_dir: Path | str,
    ) -> None:
        self._repo_producao = RepositorioProducao(producoes_dir)
        self._insumos_dir = Path(insumos_dir)

    def apply_update(
        self,
        proposta: PropostaAtualizacao,
        aprovador: str,
        nota: str = "",
    ) -> CatalogUpdateResult:
        if proposta.status != "APROVADA":
            raise ValueError(f"Proposta {proposta.proposta_id} não está APROVADA (status={proposta.status})")

        if proposta.tipo_artefato == "producao":
            return self._update_producao(proposta, aprovador, nota)
        if proposta.tipo_artefato in ("insumo", "cobertura"):
            return self._update_insumo(proposta, aprovador, nota)
        raise ValueError(f"tipo_artefato '{proposta.tipo_artefato}' não suportado por CatalogUpdater")

    def _update_producao(
        self,
        proposta: PropostaAtualizacao,
        aprovador: str,
        nota: str,
    ) -> CatalogUpdateResult:
        producao_atual = self._repo_producao.obter_ou_erro(proposta.artefato_id)

        # Incrementa versão: PROD-001 -> PROD-002
        partes = producao_atual.id.rsplit("-PROD-", maxsplit=1)
        codigo_base = partes[0]
        num_versao = int(partes[1]) + 1 if len(partes) == 2 else 2
        novo_id = f"{codigo_base}-PROD-{num_versao:03d}"

        novo_valor = {proposta.campo: proposta.valor_proposto}

        nova_producao = producao_atual.model_copy(
            update={
                "id": novo_id,
                **novo_valor,
                "origem": OrigemProducao(
                    tipo="calibrado_contra_obra_real",
                    fonte_id=proposta.observacoes[0] if proposta.observacoes else proposta.proposta_id,
                    data_calibracao=datetime.now(),
                    referencia=f"Proposta {proposta.proposta_id} — {proposta.justificativa[:80]}",
                ),
                "qualidade": QualidadeProducao(
                    confianca_pct=int(proposta.confianca_estimada * 100),
                    intervalo_confianca=producao_atual.qualidade.intervalo_confianca,
                    quantidade_amostras=proposta.n_obras_suporte,
                    desvio_padrao=producao_atual.qualidade.desvio_padrao,
                ),
                "auditoria": AuditoriaProducao(
                    criado_por=producao_atual.auditoria.criado_por,
                    data_criacao=producao_atual.auditoria.data_criacao,
                    ultima_modificacao=datetime.now(),
                    modificado_por=aprovador,
                    versao=f"{num_versao}.0",
                ),
            }
        )

        self._repo_producao.salvar(nova_producao)

        return CatalogUpdateResult(
            sucesso=True,
            novo_artefato_id=nova_producao.id,
            versao_anterior=producao_atual.id,
            nota=(
                f"Versão {nova_producao.auditoria.versao} criada: {nova_producao.id}. "
                f"CPUs ainda referenciam {producao_atual.id}. "
                f"Atualizar producao_id manualmente se desejado. " + (nota or "")
            ),
        )

    def _update_insumo(
        self,
        proposta: PropostaAtualizacao,
        aprovador: str,
        nota: str,
    ) -> CatalogUpdateResult:
        """Atualiza insumo in-place (custo_unitario ou capacidade_cobertura)."""
        insumo_id = proposta.artefato_id
        insumo_data, arquivo_path = self._find_insumo(insumo_id)

        if insumo_data is None:
            return CatalogUpdateResult(
                sucesso=False,
                novo_artefato_id=None,
                versao_anterior=None,
                nota=f"Insumo '{insumo_id}' não encontrado em {self._insumos_dir}",
            )

        # Aplica mudança
        if proposta.campo == "preco_unitario":
            auditoria = insumo_data.setdefault("auditoria_custo", [])
            auditoria.append(
                {
                    "data": datetime.now().date().isoformat(),
                    "custo_anterior": proposta.valor_atual,
                    "custo_novo": proposta.valor_proposto,
                    "aprovador": aprovador,
                    "justificativa": proposta.justificativa,
                    "proposta_id": proposta.proposta_id,
                }
            )
            insumo_data["preco_unitario"] = proposta.valor_proposto

        elif proposta.campo == "capacidade_cobertura":
            cls = insumo_data.setdefault("classe_compartilhamento", {})
            cls["capacidade_cobertura"] = proposta.valor_proposto

        else:
            insumo_data[proposta.campo] = proposta.valor_proposto

        # Persiste arquivo
        todos = json.loads(arquivo_path.read_text(encoding="utf-8"))  # type: ignore[union-attr]
        todos_list = todos if isinstance(todos, list) else todos.get("insumos", [])
        for i, item in enumerate(todos_list):
            if item.get("codigo") == insumo_id:
                todos_list[i] = insumo_data
                break
        if isinstance(todos, list):
            arquivo_path.write_text(json.dumps(todos_list, ensure_ascii=False, indent=2), encoding="utf-8")  # type: ignore[union-attr]
        else:
            arquivo_path.write_text(json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8")  # type: ignore[union-attr]

        return CatalogUpdateResult(
            sucesso=True,
            novo_artefato_id=insumo_id,
            versao_anterior=None,
            nota=f"Insumo '{insumo_id}' atualizado: {proposta.campo} = {proposta.valor_proposto}. " + (nota or ""),
        )

    def _find_insumo(self, insumo_id: str) -> tuple[dict[str, Any] | None, Path | None]:
        for json_file in self._insumos_dir.glob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                items = data if isinstance(data, list) else data.get("insumos", [])
                for item in items:
                    if item.get("codigo") == insumo_id:
                        return item, json_file
            except Exception:  # pragma: no cover
                continue
        return None, None
