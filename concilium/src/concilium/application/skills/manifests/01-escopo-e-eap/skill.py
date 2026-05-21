"""Skill 00 — Escopo Consolidado.

Inicializa o projeto, define a EAP, decompõe em atividades e define o sequenciamento (DAG).
Consolida as antigas skills 00, 00A e 00B.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import (
    ActivityDag,
    ArestaActivityDag,
    Atividade,
    CanonicalModel,
    Coordenadas,
    EapItem,
    Meta,
    Projeto,
    RegimeTrabalho,
    ValidacaoItem,
)

_TOLERANCIA_ATV = 0.001


def _kahn(nos: list[str], arestas: list[tuple[str, str]]) -> list[str] | None:
    """Ordenação topológica de Kahn estável."""
    in_degree: dict[str, int] = {n: 0 for n in nos}
    succ: dict[str, list[str]] = defaultdict(list)
    for de, para in arestas:
        succ[de].append(para)
        in_degree[para] += 1

    queue = deque(sorted(n for n in nos if in_degree[n] == 0))
    ordem: list[str] = []

    while queue:
        n = queue.popleft()
        ordem.append(n)
        for viz in sorted(succ[n]):
            in_degree[viz] -= 1
            if in_degree[viz] == 0:
                queue.append(viz)
    return ordem if len(ordem) == len(nos) else None


def _build_projeto(inputs: dict) -> Projeto:
    return Projeto(
        id=inputs.get("project_id", str(uuid4())),
        nome=inputs["nome"],
        tipo_obra=inputs["tipo_obra"],
        localizacao=inputs["localizacao"],
        coordenadas=Coordenadas(**inputs["coordenadas"]),
        regime_trabalho=RegimeTrabalho(**inputs["regime_trabalho"]),
        data_inicio=inputs["data_inicio"],
        data_termino=inputs["data_termino"],
        data_base_orcamento=(
            date.fromisoformat(inputs["data_base_orcamento"])
            if isinstance(inputs.get("data_base_orcamento"), str)
            else inputs.get("data_base_orcamento")
        ),
        snapshot_catalogo_id=inputs.get("snapshot_catalogo_id", "default"),
        snapshot_perfil_id=inputs.get("snapshot_perfil_id", "default"),
    )


def _validate_eap_cpus(eap: list, catalogo: dict | None, validacoes: list) -> None:
    if not (catalogo and "cpus" in catalogo):
        return
    cpu_ids = {c["codigo"] for c in catalogo["cpus"]}
    for item in eap:
        if item.cpu_id not in cpu_ids:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-EAP-01",
                    status="ERRO",
                    mensagem=f"EAP item '{item.item_id}' referencia CPU '{item.cpu_id}' inexistente no catálogo do contexto",  # noqa: E501
                )
            )
    if not any(v.codigo == "VAL-EAP-01" for v in validacoes):
        validacoes.append(ValidacaoItem(codigo="VAL-EAP-01", status="OK"))


def _build_atividades_for_item(eap_item: EapItem, raw_ativs: list | None, validacoes: list) -> list:
    if raw_ativs is None:
        return [
            Atividade(
                atividade_id=f"{eap_item.item_id}-atv-1",
                eap_item_id=eap_item.item_id,
                descricao=eap_item.descricao,
                fracao_quantitativo=1.0,
                quantitativo_atividade=eap_item.quantitativo,
                cpu_id=eap_item.cpu_id,
            )
        ]
    atividades = []
    soma_fracoes = 0.0
    for i, raw in enumerate(raw_ativs):
        frac = raw.get("fracao_quantitativo", 0.0)
        if not (0 < frac <= 1):
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-ATV-03",
                    status="ERRO",
                    mensagem=f"Atividade de '{eap_item.item_id}': fração {frac} inválida",
                )
            )
        soma_fracoes += frac
        atividades.append(
            Atividade(
                atividade_id=raw.get("atividade_id", f"{eap_item.item_id}-atv-{i + 1}"),
                eap_item_id=eap_item.item_id,
                descricao=raw.get("descricao", f"Atividade {i + 1}"),
                fracao_quantitativo=frac,
                quantitativo_atividade=round(frac * eap_item.quantitativo, 6),
                cpu_id=eap_item.cpu_id,
            )
        )
    if abs(soma_fracoes - 1.0) > _TOLERANCIA_ATV:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ATV-02",
                status="ERRO",
                mensagem=f"Item '{eap_item.item_id}': soma frações {soma_fracoes} != 1.0",
            )
        )
    return atividades


def _build_all_atividades(eap: list, decomposicao_raw: list, validacoes: list) -> list:
    decomposicao_por_item = {d["eap_item_id"]: d["atividades"] for d in decomposicao_raw if "eap_item_id" in d}
    atividades_out: list = []
    for eap_item in eap:
        raw_ativs = decomposicao_por_item.get(eap_item.item_id)
        atividades_out.extend(_build_atividades_for_item(eap_item, raw_ativs, validacoes))
    return atividades_out


def _build_dag_from_precedencias(nos: list, nos_set: set, precedencias_raw: list, validacoes: list) -> list:
    arestas_validas: list[tuple[str, str]] = []
    for p in precedencias_raw:
        pred, suc = p.get("predecessora", ""), p.get("sucessora", "")
        if pred in nos_set and suc in nos_set:
            arestas_validas.append((pred, suc))
        else:
            validacoes.append(
                ValidacaoItem(codigo="VAL-DAG-01", status="ERRO", mensagem=f"Precedência inválida: {pred} -> {suc}")
            )
    if not any(v.codigo == "VAL-DAG-01" for v in validacoes):
        validacoes.append(ValidacaoItem(codigo="VAL-DAG-01", status="OK"))
    return arestas_validas


def _compute_longest_paths(nos: list, succ_map: dict, pred_map: dict, ordem_topologica: list) -> tuple[dict, dict]:
    longest_path_to = {n: [n] for n in nos}
    start_offset_min = {n: 0 for n in nos}
    for n in ordem_topologica:
        for s in succ_map.get(n, []):
            cand = longest_path_to[n] + [s]
            if len(cand) > len(longest_path_to[s]):
                longest_path_to[s] = cand
        if pred_map.get(n):
            start_offset_min[n] = max(start_offset_min[p] + 1 for p in pred_map[n])
    return longest_path_to, start_offset_min


def _build_activity_dag(nos: list, arestas_validas: list, ordem_topologica: list) -> ActivityDag:
    succ_map: dict = defaultdict(list)
    pred_map: dict = defaultdict(list)
    for a, b in arestas_validas:
        succ_map[a].append(b)
        pred_map[b].append(a)
    longest_path_to, start_offset_min = _compute_longest_paths(nos, succ_map, pred_map, ordem_topologica)
    return ActivityDag(
        nos=nos,
        arestas=[ArestaActivityDag(de=d, para=p) for d, p in arestas_validas],
        ordem_topologica=ordem_topologica,
        critical_path=max(longest_path_to.values(), key=len) if longest_path_to else [],
        start_offset_min=start_offset_min,
    )


def run_escopo_e_eap(
    canonical_in: CanonicalModel | None,
    inputs: dict[str, Any],
    catalogo: dict[str, Any] | None = None,
) -> SkillResult:
    """Executa a inicialização completa do escopo."""
    validacoes: list[ValidacaoItem] = []

    # 1. Inicialização do Projeto (Antiga 00)
    if canonical_in is not None:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ESCOPO-01",
                status="ERRO",
                mensagem="Skill 00 não pode ser invocada com canônico pré-existente",
            )
        )
        return SkillResult(canonical_in, validacoes)

    meta = Meta(gerado_em=datetime.now(UTC), contexto_id=inputs["contexto_id"])
    projeto = _build_projeto(inputs)
    eap = [EapItem(**item) for item in inputs.get("eap", [])]

    _validate_eap_cpus(eap, catalogo, validacoes)
    validacoes.append(ValidacaoItem(codigo="VAL-EAP-02", status="OK"))
    if not eap:
        validacoes.append(ValidacaoItem(codigo="VAL-EAP-03", status="AVISO", mensagem="EAP vazia"))
    else:
        validacoes.append(ValidacaoItem(codigo="VAL-EAP-03", status="OK"))

    # 2. Decomposição em Atividades (Antiga 00A)
    decomposicao_raw = inputs.get("decomposicao", [])
    atividades_out = _build_all_atividades(eap, decomposicao_raw, validacoes)
    validacoes.append(ValidacaoItem(codigo="VAL-ATV-01", status="OK"))

    # 3. Sequenciamento / Activity DAG (Antiga 00B)
    nos = [a.atividade_id for a in atividades_out]
    nos_set = set(nos)
    precedencias_raw = inputs.get("precedencias", [])
    arestas_validas = _build_dag_from_precedencias(nos, nos_set, precedencias_raw, validacoes)

    ordem_topologica = _kahn(nos, arestas_validas)
    if ordem_topologica is None:
        validacoes.append(ValidacaoItem(codigo="VAL-SEQ-01", status="ERRO", mensagem="Ciclo detectado no DAG"))
        return SkillResult(CanonicalModel(meta=meta, projeto=projeto, eap=eap, atividades=atividades_out), validacoes)

    validacoes.append(ValidacaoItem(codigo="VAL-SEQ-01", status="OK"))
    dag = _build_activity_dag(nos, arestas_validas, ordem_topologica)

    prazo_contrato = inputs.get("prazo_contrato")
    if prazo_contrato is not None:
        critical_path_len = len(dag.critical_path) if dag.critical_path else 0
        if critical_path_len > int(prazo_contrato):
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-SEQ-02",
                    status="ERRO",
                    mensagem=f"Caminho crítico ({critical_path_len}) excede prazo contratual ({prazo_contrato}).",
                )
            )
        else:
            validacoes.append(ValidacaoItem(codigo="VAL-SEQ-02", status="OK"))

    canonical = CanonicalModel(meta=meta, projeto=projeto, eap=eap, atividades=atividades_out, activity_dag=dag)
    return SkillResult(canonical, validacoes)
