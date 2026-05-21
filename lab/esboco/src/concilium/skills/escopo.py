"""Skill 00 — Escopo. Inicializa canônico com meta, projeto, eap.

Inputs (via dict 'inputs'):
    nome: str
    tipo_obra: 'terraplenagem' | 'pavimentacao' | 'saneamento'
    localizacao: str
    coordenadas: {lat, lng}
    data_inicio, data_termino: ISO date
    regime_trabalho: {dias_semana, horas_dia}
    versao_referencia_id: str
    perfil_id, jurisdicao_id, snapshot_catalogo_id, snapshot_perfil_id: str
    eap: list de itens da EAP

Output:
    CanonicalModel com seções meta, projeto, eap populadas.
    Lista de validações.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from concilium.models.canonical import (
    CanonicalModel,
    Coordenadas,
    EapItem,
    Meta,
    Projeto,
    RegimeTrabalho,
    ValidacaoItem,
)


class SkillResult:
    def __init__(self, canonical: CanonicalModel, validacoes: list[ValidacaoItem]):
        self.canonical = canonical
        self.validacoes = validacoes
        self.has_errors = any(v.status == "ERRO" for v in validacoes)


def run_escopo(
    canonical_in: CanonicalModel | None,
    inputs: dict[str, Any],
    catalogo: dict[str, Any] | None = None,
) -> SkillResult:
    """Cria canônico inicial do projeto.

    canonical_in deve ser None aqui (skill 00 sempre cria do zero).
    catalogo pode ser usado para validar EAP.cpu_id (VAL-EAP-01).
    """
    validacoes: list[ValidacaoItem] = []

    if canonical_in is not None:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ESCOPO-01",
                status="ERRO",
                mensagem="Skill 00 não pode ser invocada com canônico pré-existente",
            )
        )
        return SkillResult(canonical_in, validacoes)

    meta = Meta(
        gerado_em=datetime.now(UTC),
        perfil_construtora_id=inputs["perfil_id"],
        jurisdicao_id=inputs["jurisdicao_id"],
    )

    projeto = Projeto(
        id=inputs.get("project_id", str(uuid4())),
        nome=inputs["nome"],
        tipo_obra=inputs["tipo_obra"],
        localizacao=inputs["localizacao"],
        coordenadas=Coordenadas(**inputs["coordenadas"]),
        regime_trabalho=RegimeTrabalho(**inputs["regime_trabalho"]),
        data_inicio=inputs["data_inicio"],
        data_termino=inputs["data_termino"],
        versao_referencia_id=inputs["versao_referencia_id"],
        snapshot_catalogo_id=inputs["snapshot_catalogo_id"],
        snapshot_perfil_id=inputs["snapshot_perfil_id"],
    )

    eap = [EapItem(**item) for item in inputs.get("eap", [])]

    # VAL-EAP-01: toda CPU referenciada existe no catálogo
    if catalogo and "cpus" in catalogo:
        cpu_ids = {c["codigo"] for c in catalogo["cpus"]}
        for item in eap:
            if item.cpu_id not in cpu_ids:
                validacoes.append(
                    ValidacaoItem(
                        codigo="VAL-EAP-01",
                        status="ERRO",
                        mensagem=f"EAP item '{item.item_id}' referencia CPU '{item.cpu_id}' que não existe no catálogo",
                    )
                )
        if not any(v.codigo == "VAL-EAP-01" for v in validacoes):
            validacoes.append(ValidacaoItem(codigo="VAL-EAP-01", status="OK"))

    # VAL-EAP-02: quantitativos positivos (já validado pelo Pydantic gt=0)
    validacoes.append(ValidacaoItem(codigo="VAL-EAP-02", status="OK"))

    # VAL-EAP-03: pelo menos 1 item
    if not eap:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-EAP-03",
                status="AVISO",
                mensagem="EAP vazia — orçamento sem serviços",
            )
        )
    else:
        validacoes.append(ValidacaoItem(codigo="VAL-EAP-03", status="OK"))

    canonical = CanonicalModel(meta=meta, projeto=projeto, eap=eap)
    return SkillResult(canonical, validacoes)
