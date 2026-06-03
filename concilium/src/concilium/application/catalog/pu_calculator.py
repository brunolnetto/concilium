"""
Calculadora de Preço Unitário a partir da composição da equipe e produtividade.

Modelo:
    PU = custo_total_horario / producao.valor_horario

Onde custo_total_horario:
    MÃO DE OBRA   : Σ salario_h × num_pessoas                              [horário: all-in]
                    Σ (salario_mes / horas_mes) × (1 + α) × num_pessoas     [mensal: base+enc]
    EQUIPAMENTO   : Σ preco_unitario_h × num_unidades
    DIESEL        : Σ consumo_litros_hora × preco_diesel × num_unidades
    MATERIAL equipe: Σ consumo_por_hora × preco_unitario

    α = fator de encargos (1.777 CLT horista, 0.06 PJ).
    (1+α) = multiplicador total: 1 + 177.7% = 2.777 — aplicado APENAS sobre salários mensais.
    Taxas horárias (AGIS-FN-*, convenção planilha) já são all-in (~80% enc implícito);
    aplicar (1+alpha) seria dupla contagem. ADR-097 §D1/D3.

Parâmetros configuráveis:
    alpha_clt    : fator de encargos CLT mensal  (default 1.777; total = 1+alpha = 2.777)
    alpha_pj     : fator de encargos PJ    (default 1.06)
    preco_diesel : R$/litro                (default 6.50)
    horas_mes    : horas produtivas/mês    (default 208 — regime 6×8h)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from concilium.domain.constants import (
    ENCARGOS_CLT,
    ENCARGOS_PJ,
    PRECO_DIESEL_REFERENCIA,
    HORAS_MES_REGIME_6x1,
)

# ── Parâmetros default (ADR-056 §T3 — fonte: domain/constants.py) ────────────
DEFAULT_ALPHA_CLT = ENCARGOS_CLT
DEFAULT_ALPHA_PJ = ENCARGOS_PJ
DEFAULT_PRECO_DIESEL = PRECO_DIESEL_REFERENCIA  # alias backward-compat
DEFAULT_HORAS_MES = HORAS_MES_REGIME_6x1  # regime 6×1, 8h/dia


@dataclass
class ParametrosCalculo:
    alpha_clt: float = DEFAULT_ALPHA_CLT
    alpha_pj: float = DEFAULT_ALPHA_PJ
    preco_diesel: float = DEFAULT_PRECO_DIESEL
    horas_mes: float = DEFAULT_HORAS_MES  # fallback se insumo não tiver horas_mes


@dataclass
class BreakdownPU:
    producao_id: str
    valor_horario: float
    custo_mo_h: float = 0.0
    custo_equip_h: float = 0.0
    custo_diesel_h: float = 0.0
    custo_material_h: float = 0.0

    # Erros de integridade referencial
    referencias_faltantes: list[str] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)

    @property
    def custo_total_h(self) -> float:
        return self.custo_mo_h + self.custo_equip_h + self.custo_diesel_h + self.custo_material_h

    @property
    def pu_calculado(self) -> float | None:
        if not self.valor_horario:
            return None
        return round(self.custo_total_h / self.valor_horario, 4)

    @property
    def ok(self) -> bool:
        return not self.referencias_faltantes

    def to_dict(self) -> dict:
        return {
            "producao_id": self.producao_id,
            "valor_horario": self.valor_horario,
            "pu_calculado": self.pu_calculado,
            "breakdown": {
                "mo": round(self.custo_mo_h, 4),
                "equipamento": round(self.custo_equip_h, 4),
                "diesel": round(self.custo_diesel_h, 4),
                "material": round(self.custo_material_h, 4),
                "total_h": round(self.custo_total_h, 4),
            },
            "referencias_faltantes": self.referencias_faltantes,
            "alertas": self.alertas,
            "ok": self.ok,
        }


def _alpha(insumo: dict, params: ParametrosCalculo) -> float:
    """Retorna o fator de encargos (α) para um insumo de mão de obra."""
    attrs = insumo.get("atributos_especificos") or {}
    # 1. Fator local explícito (já inclui os encargos completos: base + complementares)
    enc_local = attrs.get("percentual_encargos_local")
    if enc_local is not None:
        try:
            return 1.0 + float(enc_local)
        except (TypeError, ValueError):
            pass
    # 2. Tipo de contrato
    tipo = str(attrs.get("tipo_contrato") or "CLT").upper()
    return params.alpha_pj if "PJ" in tipo else params.alpha_clt


def _horas_mes(insumo: dict, params: ParametrosCalculo) -> float:
    attrs = insumo.get("atributos_especificos") or {}
    h = attrs.get("horas_mes")
    try:
        return float(h) if h else params.horas_mes
    except (TypeError, ValueError):
        return params.horas_mes


def calcular_pu_composicao_itens(
    cpu: dict,
    insumo_index: dict[str, dict],
    catalog_session: object | None = None,  # ADR-100: CatalogSession para JOIN SQL
) -> dict:
    """
    Calcula PU de insumos fixos (volumétricos) a partir de CPU.composicao_itens.

    PU_fixo = Σ (coeficiente_i × Insumo_i.preco_unitario)

    Retorna:
        {"pu_fixo": float, "refs_faltantes": list[str], "breakdown": list[dict]}
    """
    # Fast path: SQL JOIN via CatalogSession (ADR-100)
    if catalog_session is not None:
        return _calcular_pu_composicao_sql(cpu, catalog_session)

    cpu_codigo = cpu.get("codigo", "?")
    pu_fixo = 0.0
    refs_faltantes: list[str] = []
    breakdown: list[dict] = []

    for item in cpu.get("composicao_itens") or []:
        iid = item.get("insumo_id", "")
        coef = float(item.get("coeficiente") or 0)
        ins = insumo_index.get(iid)
        if ins is None:
            refs_faltantes.append(f"insumo_id '{iid}' não encontrado")
            continue
        preco = float(ins.get("preco_unitario") or 0)
        contrib = coef * preco
        pu_fixo += contrib
        breakdown.append(
            {
                "insumo_id": iid,
                "coeficiente": coef,
                "preco": preco,
                "contribuicao": round(contrib, 4),
                "categoria_custo": item.get("categoria_custo"),
            }
        )

    return {
        "cpu_codigo": cpu_codigo,
        "pu_fixo": round(pu_fixo, 4),
        "refs_faltantes": refs_faltantes,
        "breakdown": breakdown,
    }


def calcular_pu(
    producao: dict,
    insumo_index: dict[str, dict],
    params: ParametrosCalculo | None = None,
    catalog_session: object | None = None,  # ADR-100: CatalogSession para SQL JOINs
) -> BreakdownPU:
    """Calcula PU para uma unica producao a partir da composicao da equipe.

    PU = custo_total_horario / producao.valor_horario
    """
    if params is None:
        params = ParametrosCalculo()

    # Fast path: SQL JOIN via CatalogSession (ADR-100) — substitui 3 loops Python
    if catalog_session is not None:
        return _calcular_pu_sql(producao, params, catalog_session)

    producao_id = producao.get("id") or producao.get("codigo") or "?"
    valor_horario = float(producao.get("valor_horario") or 0)
    bd = BreakdownPU(producao_id=producao_id, valor_horario=valor_horario)

    equipe, funcoes, equipamentos, materiais = _cpu_get_equipe(producao)

    for fn in funcoes:
        fid = fn.get("funcao_id", "")
        num_pessoas = float(fn.get("num_pessoas") or 1)
        ins = insumo_index.get(fid)
        if ins is None:
            bd.referencias_faltantes.append(fid)
            continue
        salario = float(ins.get("preco_unitario") or 0)
        unidade_fn = (ins.get("unidade") or "mes").strip().lower()
        if unidade_fn == "h":
            # Taxa horária já carregada (all-in). A taxa horária negociada/convencional
            # já embute os encargos (~80% estatutário implícito). ADR-097: aplicar
            # (1+alpha) seria dupla contagem — a nota "já inclui encargos" confirma isso.
            # Fe_nec → 1/η_p: tanto skill-05 quanto pu_calculator usam a taxa direta.
            bd.custo_mo_h += salario * num_pessoas
        else:
            # Salário mensal (base pura, sem encargos) — converte para horário e
            # aplica multiplicador total (1 + alpha) = (1 + 1.777) = 2.777 CLT horista.
            hm = _horas_mes(ins, params)
            bd.custo_mo_h += (salario / hm) * (1.0 + _alpha(ins, params)) * num_pessoas

    for eq in equipamentos:
        eid = eq.get("equip_id", "")
        num_un = float(eq.get("num_unidades") or 1)
        ins = insumo_index.get(eid)
        if ins is None:
            bd.referencias_faltantes.append(eid)
            continue
        preco_h = float(ins.get("preco_unitario") or 0)
        bd.custo_equip_h += preco_h * num_un
        # Precedência de consumo: entry da produção → atributos_especificos do insumo
        consumo = float(eq.get("consumo_litros_hora") or 0)
        if not consumo:
            atrib_eq = (ins or {}).get("atributos_especificos") or {}
            consumo = float(atrib_eq.get("consumo_litros_hora") or 0)
            if consumo:
                bd.alertas.append(f"Equipamento '{eid}': consumo_litros_hora lido de atributos_especificos do insumo.")
        bd.custo_diesel_h += consumo * params.preco_diesel * num_un

    for mat in materiais:
        mid = mat.get("insumo_id") or mat.get("material_id") or mat.get("codigo") or ""
        consumo_h = float(mat.get("consumo_por_hora") or mat.get("quantidade_h") or 0)
        ins = insumo_index.get(mid)
        if ins is None and mid:
            bd.referencias_faltantes.append(mid)
            continue
        if ins:
            preco = float(ins.get("preco_unitario") or 0)
            bd.custo_material_h += consumo_h * preco

    return bd


def _calcular_pu_composicao_sql(cpu: dict, session: object) -> dict:
    """ADR-100: calcular_pu_composicao_itens com SQL JOIN vetorizado."""
    cpu_codigo = cpu.get("codigo", "?")
    items = session.get_composicao_com_precos(cpu_codigo)  # type: ignore[attr-defined]
    pu_fixo = 0.0
    refs_faltantes: list[str] = []
    breakdown: list[dict] = []
    for item in items:
        iid = item.get("insumo_id", "")
        coef = float(item.get("coeficiente") or 0)
        preco = float(item.get("preco_unitario") or 0)
        if not iid:
            continue
        if preco == 0 and not item.get("id"):
            refs_faltantes.append(f"insumo_id '{iid}' não encontrado")
            continue
        contrib = coef * preco
        pu_fixo += contrib
        breakdown.append({
            "insumo_id": iid,
            "coeficiente": coef,
            "preco": preco,
            "contribuicao": round(contrib, 4),
            "categoria_custo": item.get("categoria_custo"),
        })
    return {
        "cpu_codigo": cpu_codigo,
        "pu_fixo": round(pu_fixo, 4),
        "refs_faltantes": refs_faltantes,
        "breakdown": breakdown,
    }


def _calcular_pu_sql(producao: dict, params: ParametrosCalculo, session: object) -> "BreakdownPU":
    """ADR-100: calcular_pu com SQL JOINs — substitui 3 loops Python O(n)."""
    prod_id = producao.get("id") or producao.get("codigo") or "?"
    valor_horario = float(producao.get("valor_horario") or 0)
    bd = BreakdownPU(producao_id=prod_id, valor_horario=valor_horario)

    equipe = session.get_equipe_com_precos(prod_id)  # type: ignore[attr-defined]

    # Mão de obra
    for fn in equipe.get("funcoes", []):
        fid = fn.get("funcao_id", "")
        preco = float(fn.get("preco_unitario") or 0)
        num_pessoas = float(fn.get("num_pessoas") or 1)
        if preco <= 0:
            bd.referencias_faltantes.append(fid)
            continue
        unidade = (fn.get("unidade") or "mes").strip().lower()
        if unidade == "h":
            bd.custo_mo_h += preco * num_pessoas
        else:
            hm = _horas_mes(fn, params)
            bd.custo_mo_h += (preco / hm) * (1.0 + _alpha(fn, params)) * num_pessoas

    # Equipamentos + diesel
    for eq in equipe.get("equipamentos", []):
        eid = eq.get("equip_id", "")
        preco_h = float(eq.get("preco_unitario") or 0)
        num_un = float(eq.get("num_unidades") or 1)
        if preco_h <= 0:
            bd.referencias_faltantes.append(eid)
            continue
        bd.custo_equip_h += preco_h * num_un
        consumo = float(eq.get("consumo_efetivo") or eq.get("consumo_litros_hora") or 0)
        if consumo:
            bd.alertas.append(f"Equipamento '{eid}': consumo lido do DB.")
        bd.custo_diesel_h += consumo * params.preco_diesel * num_un

    # Materiais
    for mat in equipe.get("materiais", []):
        consumo_h = float(mat.get("consumo_por_hora") or 0)
        preco = float(mat.get("preco_unitario") or 0)
        bd.custo_material_h += consumo_h * preco

    return bd


def _cpu_get_equipe(producao: dict) -> tuple:
    """Returns (equipe, funcoes, equipamentos, materiais) from producao dict."""
    equipe = producao.get("composicao_padrao_equipe") or producao.get("equipe") or {}
    funcoes = equipe.get("funcoes") or []
    equipamentos = equipe.get("equipamentos") or []
    materiais = equipe.get("materiais") or []
    return equipe, funcoes, equipamentos, materiais


def _build_insumo_index(insumos: list) -> dict:
    idx = {}
    for ins in insumos:
        if ins.get("codigo"):
            idx[ins["codigo"]] = ins
    return idx


def _check_pu_divergencia(bd, prod: dict, tolerancia_pct: float, pu_divergentes: list) -> None:
    if bd.pu_calculado is None:
        return
    cpu_hint = prod.get("_cu_planilha_referencia")
    if cpu_hint is None:
        return
    try:
        ref = float(cpu_hint)
        if ref > 0:
            delta_pct = abs(bd.pu_calculado - ref) / ref * 100
            if delta_pct > tolerancia_pct:
                pu_divergentes.append(
                    {
                        "producao_id": bd.producao_id,
                        "pu_calculado": bd.pu_calculado,
                        "pu_referencia": ref,
                        "delta_pct": round(delta_pct, 2),
                    }
                )
    except (TypeError, ValueError):
        pass


def calcular_catalogo(
    producoes: list[dict],
    insumos: list[dict],
    params: ParametrosCalculo | None = None,
    tolerancia_pct: float = 20.0,
    catalog_session: object | None = None,  # ADR-100
) -> dict:
    """
    Valida integridade referencial + consistência de PU para todo o catálogo.

    Returns dict com:
        - ok: bool
        - total_producoes: int
        - com_composicao: int
        - referencias_faltantes: list
        - pu_divergentes: list (pu_calculado vs _cu_planilha acima da tolerância)
        - sem_valor_horario: list
        - breakdown_por_producao: list[BreakdownPU.to_dict()]
    """
    if params is None:
        params = ParametrosCalculo()

    insumo_index = _build_insumo_index(insumos)
    refs_faltantes: list[dict] = []
    pu_divergentes: list[dict] = []
    sem_valor: list[str] = []
    breakdowns: list[dict] = []
    com_composicao = 0

    for prod in producoes:
        equipe = prod.get("composicao_padrao_equipe") or prod.get("equipe") or {}
        if not (equipe.get("funcoes") or equipe.get("equipamentos")):
            continue
        com_composicao += 1
        bd = calcular_pu(prod, insumo_index, params, catalog_session=catalog_session)
        breakdowns.append(bd.to_dict())
        if bd.referencias_faltantes:
            refs_faltantes.append({"producao_id": bd.producao_id, "faltantes": bd.referencias_faltantes})
        if not bd.valor_horario:
            sem_valor.append(bd.producao_id)
            continue
        _check_pu_divergencia(bd, prod, tolerancia_pct, pu_divergentes)

    ok = not refs_faltantes and not sem_valor
    return {
        "ok": ok,
        "total_producoes": len(producoes),
        "com_composicao": com_composicao,
        "sem_valor_horario": sem_valor,
        "referencias_faltantes": refs_faltantes,
        "pu_divergentes": pu_divergentes,
        "breakdown_por_producao": breakdowns,
    }


def derivar_precos_unitarios_sbdi(
    producao: dict,
    insumo_index: dict[str, dict],
    params: ParametrosCalculo | None = None,
    catalog_session: object | None = None,  # ADR-100
) -> dict:
    """NEP-029 D2: Deriva precos_unitarios_sbdi a partir de parâmetros operacionais.

    Calcula o preço unitário por categoria decompondo o custo horário total da equipe
    (MO + equipamentos + diesel + materiais) pela produtividade horária da CPU.

    Fórmula:
        PU_categoria = custo_categoria_hora / producao.valor_horario

    A categoria de diesel inclui fallback ao campo atributos_especificos.consumo_litros_hora
    do insumo quando o campo não estiver na entry da equipe.

    Args:
        producao: dict do arquivo de produção da CPU (com composicao_padrao_equipe).
        insumo_index: dict{codigo → insumo} com preços de labor, equipamento e material.
        params: ParametrosCalculo (encargos, preco_diesel, horas_mes). None → defaults.

    Returns:
        dict compatível com cpu.precos_unitarios_sbdi, incluindo chave "_meta" com
        rastreabilidade (producao_id, valor_horario, referencias_faltantes, alertas).
        Retorna {} se valor_horario=0 ou equipe vazia.
    """
    bd = calcular_pu(producao, insumo_index, params, catalog_session=catalog_session)
    if not bd.valor_horario or bd.valor_horario <= 0:
        return {}

    vh = bd.valor_horario
    return {
        "mo": round(bd.custo_mo_h / vh, 6),
        "diesel": round(bd.custo_diesel_h / vh, 6),
        "equipamentos": round(bd.custo_equip_h / vh, 6),
        "material": round(bd.custo_material_h / vh, 6),
        "total": round(bd.custo_total_h / vh, 6),
        "_meta": {
            "producao_id": bd.producao_id,
            "valor_horario": vh,
            "referencias_faltantes": bd.referencias_faltantes,
            "alertas": bd.alertas,
        },
    }
