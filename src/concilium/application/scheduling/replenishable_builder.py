"""ADR-139 F4 — Builder catálogo→``ReplenishableResource`` (produtor-consumidor).

Fecha também a lacuna registrada na ADR-128 F4 ("capacidade pura, sem fonte real de
projeto/escopo"): até aqui nenhum código de produção construía ``ReplenishableResource``
— apenas testes. Este builder deriva os fluxos semanais a partir do catálogo:

  - ``producao_por_semana``  ← ``Producao.materiais_gerados[].geracao_por_hora`` × horas/semana
  - ``consumo_por_semana``   ← ``composicao_padrao_equipe.materiais[].consumo_por_hora`` × horas/semana
  - ``disponibilidade``      ← ``Insumo.atributos_especificos.disponibilidade`` (ADR-128) quando
    declarada; para material de geração interna sem declaração, pilha vazia sem
    reabastecimento externo (``estoque_inicial=0.0``, ``taxa_reabastecimento_max=None``).

O *pareamento* atividade→``Producao`` (qual frente produz/consome qual estoque) é dado de
projeto/escopo (ADR-139 D5) — o chamador o materializa em ``producoes_por_atividade``.

Aceita tanto modelos Pydantic (``Producao``/``Insumo``) quanto dicts crus do bundle de
catálogo — o runtime de skills trabalha com dicts, e catálogos legados (ex.: ``rfi-r02``)
carregam campos fora dos Literals estritos do modelo.

Semântica de emissão (ADR-128 D1: ausência de ``DisponibilidadeConsumivel`` = irrestrito):
um insumo só vira recurso restrito quando (a) alguma atividade o produz internamente, ou
(b) é consumido E tem ``disponibilidade`` declarada no catálogo. Consumo de insumo sem
qualquer restrição declarada permanece irrestrito e não gera recurso.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from concilium.application.scheduling.models import ReplenishableResource
from concilium.domain.models.catalog.catalogo import Insumo
from concilium.domain.models.catalog.disponibilidade_consumivel import DisponibilidadeConsumivel
from concilium.domain.models.catalog.producao import Producao

_CAMPOS_DISPONIBILIDADE = (
    "capacidade_armazenamento",
    "estoque_inicial",
    "taxa_reabastecimento_max",
    "lead_time_reabastecimento_dias",
    "deficit_provisionado_externamente",  # ADR-151
)


def _producao_as_dict(producao: Producao | dict[str, Any]) -> dict[str, Any]:
    return producao.model_dump() if isinstance(producao, Producao) else producao


def _insumo_as_dict(insumo: Insumo | dict[str, Any]) -> dict[str, Any]:
    return insumo.model_dump() if isinstance(insumo, Insumo) else insumo


def _equipe(producao: dict[str, Any]) -> dict[str, Any]:
    return producao.get("composicao_padrao_equipe") or producao.get("equipe") or {}


def _disponibilidade_declarada(insumo: dict[str, Any] | None) -> DisponibilidadeConsumivel | None:
    if insumo is None:
        return None
    declarada = (insumo.get("atributos_especificos") or {}).get("disponibilidade")
    if declarada is None:
        return None
    if isinstance(declarada, DisponibilidadeConsumivel):
        return declarada
    return DisponibilidadeConsumivel(**{k: declarada[k] for k in _CAMPOS_DISPONIBILIDADE if k in declarada})


def _horas_da_atividade(activity_id: str, horas_semana: float | dict[str, float]) -> float:
    if isinstance(horas_semana, dict):
        if activity_id not in horas_semana:
            raise ValueError(
                f"horas_semana não declara a atividade '{activity_id}' — o pareamento de projeto "
                f"(ADR-139 D5) deve cobrir toda atividade produtora/consumidora"
            )
        return horas_semana[activity_id]
    return horas_semana


def build_replenishable_resources(
    producoes_por_atividade: dict[str, Producao | dict[str, Any]],
    insumos_por_id: dict[str, Insumo | dict[str, Any]],
    horas_semana: float | dict[str, float] = 40.0,
    disponibilidade_overrides: dict[str, DisponibilidadeConsumivel] | None = None,
) -> list[ReplenishableResource]:
    """Deriva os ``ReplenishableResource`` de um pareamento atividade→``Producao``.

    Args:
        producoes_por_atividade: pareamento de projeto (ADR-139 D5) — cada atividade do
            schedule apontando para a ``Producao`` (modelo ou dict de catálogo) que
            descreve sua física (geração/consumo de material).
        insumos_por_id: catálogo de insumos (modelos ou dicts) referenciáveis pelos fluxos.
        horas_semana: horas de operação por semana ativa — valor único ou por atividade
            (default 40.0 = 8 h/dia × 5 dias, o padrão de ``ProdutividadeDetalhada``).
        disponibilidade_overrides: capacidade logística real de projeto/escopo (ADR-128 F5,
            ``Escopo.logistica_consumiveis``), chaveada por ``insumo_id``. Tem prioridade
            sobre a declaração de catálogo quando ambas existem para o mesmo insumo, e
            permite que um insumo sem NENHUMA restrição de catálogo (ex.: diesel,
            raramente ``GERACAO_INTERNA`` e raramente com ``disponibilidade`` declarada)
            ainda assim vire um recurso restrito — fecha a lacuna registrada em ADR-128 F4
            ("sem fonte real de projeto/escopo").

    Raises:
        ValueError: VAL-PROD-GERACAO-01 — ``materiais_gerados`` referenciando insumo
            inexistente ou com ``origem_material != "GERACAO_INTERNA"`` (defesa em
            profundidade; a mesma regra vale no QA de catálogo via ``ValidadorCPUInsumo``).
    """
    insumos = {insumo_id: _insumo_as_dict(ins) for insumo_id, ins in insumos_por_id.items()}
    producao_flows: dict[str, dict[str, float]] = defaultdict(dict)
    consumo_flows: dict[str, dict[str, float]] = defaultdict(dict)

    for activity_id, producao_raw in producoes_por_atividade.items():
        producao = _producao_as_dict(producao_raw)
        horas = _horas_da_atividade(activity_id, horas_semana)
        for gerado in producao.get("materiais_gerados") or []:
            insumo_id = gerado["insumo_id"]
            insumo = insumos.get(insumo_id)
            if insumo is None or insumo.get("origem_material") != "GERACAO_INTERNA":
                origem = insumo.get("origem_material") if insumo is not None else "<insumo inexistente>"
                raise ValueError(
                    f"VAL-PROD-GERACAO-01: materiais_gerados de '{producao.get('id')}' (atividade "
                    f"'{activity_id}') referencia '{insumo_id}' com origem_material="
                    f"{origem!r}, esperado 'GERACAO_INTERNA'"
                )
            atual = producao_flows[insumo_id].get(activity_id, 0.0)
            producao_flows[insumo_id][activity_id] = atual + float(gerado["geracao_por_hora"]) * horas
        for consumido in _equipe(producao).get("materiais") or []:
            insumo_id = consumido["insumo_id"]
            atual = consumo_flows[insumo_id].get(activity_id, 0.0)
            consumo_flows[insumo_id][activity_id] = atual + float(consumido["consumo_por_hora"]) * horas

    resources: list[ReplenishableResource] = []
    for insumo_id in sorted(set(producao_flows) | set(consumo_flows)):
        declarada = _disponibilidade_declarada(insumos.get(insumo_id))
        override = (disponibilidade_overrides or {}).get(insumo_id)
        produzido_internamente = insumo_id in producao_flows
        if declarada is None and override is None and not produzido_internamente:
            # ADR-128 D1 / F5: sem restrição de catálogo, sem override de projeto e sem
            # produção interna — irrestrito, não vira recurso (contrato de regressão zero).
            continue
        disponibilidade = override or declarada or DisponibilidadeConsumivel(estoque_inicial=0.0)
        resources.append(
            ReplenishableResource(
                resource_id=insumo_id,
                disponibilidade=disponibilidade,
                consumo_por_semana=dict(consumo_flows.get(insumo_id, {})),
                producao_por_semana=dict(producao_flows.get(insumo_id, {})),
            )
        )
    return resources
