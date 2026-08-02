"""ADR-173 F4 — Amortização/elegibilidade de custo de RH (EPI/TREINAMENTO/EXAME/BENEFICIO).

Extraído de `_dimensionamento.py`/`_mob.py` (ADR-166 D2/D3), onde vivia duplicado
implicitamente entre os dois helpers privados de skill-06. Módulo de domínio
compartilhado — reusado por skill-06 (bottom-up por headcount agregado) e pelo
cálculo de custo real por indivíduo (`roster_custo_mo.py`, ADR-173 F5), sem
reescrever a lógica de amortização/elegibilidade uma terceira vez.

Comportamento idêntico ao pré-extração (ADR-166) — só mudou o local do código.
"""

from __future__ import annotations

from concilium.domain.constants import SEMANAS_POR_MES

# ADR-166 D2/D3: dias/mês para amortizar custo de RH e converter benefício diário em mensal.
DIAS_POR_MES = SEMANAS_POR_MES * 7


def rh_insumos_por_tipo(catalogo: dict | None) -> tuple[list[dict], list[dict], list[dict]]:
    """ADR-166 D2: separa insumos EPI (MATERIAL prefixo `EPI-`)/TREINAMENTO/EXAME
    ativos do catálogo — a base de dado para a composição QSMS bottom-up."""
    if not catalogo:
        return [], [], []
    epis: list[dict] = []
    treinamentos: list[dict] = []
    exames: list[dict] = []
    for ins in catalogo.get("insumos", []):
        if ins.get("status") == "descontinuado":
            continue
        tipo = ins.get("tipo")
        codigo = ins.get("codigo", "")
        if tipo == "MATERIAL" and codigo.startswith("EPI-"):
            epis.append(ins)
        elif tipo == "TREINAMENTO":
            treinamentos.append(ins)
        elif tipo == "EXAME":
            exames.append(ins)
    return epis, treinamentos, exames


def custo_mensal_rh_por_funcao(funcao_id: str, *grupos_insumos: list[dict]) -> float:
    """ADR-166 D2: soma o custo mensal amortizado (preço ÷ vida_util_dias × dias/mês) dos
    itens aplicáveis a `funcao_id` — comuns (`funcoes_aplicaveis` None) + específicos
    (`funcao_id` presente na lista)."""
    total = 0.0
    for grupo in grupos_insumos:
        for ins in grupo:
            atributos = ins.get("atributos_especificos") or {}
            aplicaveis = atributos.get("funcoes_aplicaveis")
            if aplicaveis is not None and funcao_id not in aplicaveis:
                continue
            vida_util = atributos.get("vida_util_dias")
            if not vida_util:
                continue
            total += ins.get("preco_unitario", 0.0) / vida_util * DIAS_POR_MES
    return total


def beneficios_ativos(catalogo: dict | None) -> list[dict]:
    """ADR-166 D3: insumos BENEFICIO ativos do catálogo."""
    if not catalogo:
        return []
    return [
        ins
        for ins in catalogo.get("insumos", [])
        if ins.get("tipo") == "BENEFICIO" and ins.get("status") != "descontinuado"
    ]


def tipo_contrato_por_funcao(catalogo: dict | None) -> dict[str, str]:
    """Mapa funcao_id (código de Insumo MAO_OBRA) -> tipo_contrato, do catálogo."""
    if not catalogo:
        return {}
    out: dict[str, str] = {}
    for ins in catalogo.get("insumos", []):
        if ins.get("tipo") != "MAO_OBRA":
            continue
        tc = (ins.get("atributos_especificos") or {}).get("tipo_contrato")
        if tc:
            out[ins["codigo"]] = tc
    return out


def custo_mensal_beneficio_por_funcao(funcao_id: str, beneficios: list[dict], tipo_contrato: str | None) -> float:
    """ADR-166 D3: soma o custo mensal dos benefícios aplicáveis a uma função —
    diária (café/almoço/jantar) convertida por dias/mês, mensal direto.
    `aplicavel_tipo_contrato` exclui a função só quando o regime é positivamente
    conhecido e não está na lista (regime desconhecido/None recebe o benefício —
    default seguro, não penaliza função sem tipo_contrato cadastrado)."""
    total = 0.0
    for ins in beneficios:
        atributos = ins.get("atributos_especificos") or {}
        aplicavel_contrato = atributos.get("aplicavel_tipo_contrato")
        if aplicavel_contrato is not None and tipo_contrato is not None and tipo_contrato not in aplicavel_contrato:
            continue
        periodicidade = atributos.get("periodicidade_beneficio")
        preco = ins.get("preco_unitario", 0.0)
        if periodicidade == "diaria":
            total += preco * DIAS_POR_MES
        elif periodicidade == "mensal":
            total += preco
    return total
