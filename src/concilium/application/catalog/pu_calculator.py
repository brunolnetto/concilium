"""
Calculadora de Preço Unitário a partir da composição da equipe e produtividade.

Modelo:
    PU = custo_total_horario / producao.valor_horario

Onde custo_total_horario:
    MÃO DE OBRA   : Σ (salario_mensal / horas_mes) × α × num_pessoas
    EQUIPAMENTO   : Σ preco_unitario_h × num_unidades
    DIESEL        : Σ consumo_litros_hora × preco_diesel × num_unidades
    MATERIAL equipe: Σ consumo_por_hora × preco_unitario

Parâmetros configuráveis:
    alpha_clt    : fator de encargos CLT   (default 1.777)
    alpha_pj     : fator de encargos PJ    (default 1.06)
    preco_diesel : R$/litro                (default 6.50)
    horas_mes    : horas produtivas/mês    (default 208 — regime 6×8h)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from concilium.domain.constants import (
    ENCARGOS_CLT,
    ENCARGOS_PJ,
    PRECO_DIESEL_REFERENCIA,
    HORAS_MES_REGIME_6x1,
)

if TYPE_CHECKING:
    from concilium.infrastructure.clients.fuel import FuelPriceClient

logger = logging.getLogger(__name__)

FontePrecoDiesel = Literal["fuel_api", "fallback_constante"]

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


def resolver_preco_diesel_uf(
    uf: str | None,
    fuel_client: FuelPriceClient | None,
) -> tuple[float, FontePrecoDiesel]:
    """ADR-129 D3: resolve preço de diesel via `FuelPriceClient`, por UF.

    Reconecta o `FuelPriceClient` (`infrastructure/clients/fuel.py`) — antes
    desconectado — como fonte real de preço regional de diesel, no lugar da
    constante nacional única `PRECO_DIESEL_REFERENCIA`.

    Fallback (rede de segurança, preserva o comportamento anterior):
        - `uf` ausente (None) — não há UF para consultar;
        - `fuel_client` ausente (None) — chamador optou por não usar a API externa;
        - qualquer exceção na consulta (API fora do ar, timeout, UF sem preço
          publicado) — indisponibilidade da fonte externa não deve quebrar o
          cálculo de PU.

    Args:
        uf: sigla da UF (ex.: "CE", "SP"). Aceita qualquer caixa.
        fuel_client: instância de `FuelPriceClient` (injetável para testes) ou
            `None` para pular a consulta e usar direto a constante nacional.

    Returns:
        Tupla `(preco, fonte)` onde `fonte` é `"fuel_api"` quando o preço veio
        da API externa, ou `"fallback_constante"` quando caiu para
        `PRECO_DIESEL_REFERENCIA`.
    """
    if uf and fuel_client is not None:
        try:
            preco = fuel_client.get_price_str(uf.strip().lower(), "diesel")
            return preco, "fuel_api"
        except Exception:
            logger.warning(
                "FuelPriceClient indisponível para UF=%s; usando fallback PRECO_DIESEL_REFERENCIA.", uf
            )
    return PRECO_DIESEL_REFERENCIA, "fallback_constante"


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
    # ADR-163 D3: composição item-a-item (mesmo formato de calcular_pu_composicao_itens),
    # populada só quando o insumo é resolvido (referências faltantes não geram item).
    itens: list[dict] = field(default_factory=list)

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

    def to_dict(self, detalhado: bool = False) -> dict:
        result = {
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
        if detalhado:
            result["itens"] = self.itens
        return result


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
) -> dict:
    """
    Calcula PU de insumos fixos (volumétricos) a partir de CPU.composicao_itens.

    PU_fixo = Σ (coeficiente_i × Insumo_i.preco_unitario)

    Retorna:
        {"pu_fixo": float, "refs_faltantes": list[str], "breakdown": list[dict]}
    """
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


def _converter_rental_unit(
    preco_original: float,
    rental_unit: str | None,
    producao_horaria: float = 1.0,
    horas_dia: float = 8.0,
    horas_mes: float = 193.6,
) -> float:
    """NEP-031 L1: Converte preco de aluguel para custo por hora produtiva.

    Args:
        preco_original: Preco na unidade original (R$/hora, R$/dia ou R$/mes)
        rental_unit: Unidade de aluguel ("hora_produtiva", "dia_calendario", "mes", None)
        producao_horaria: Fator de producao horaria (eta_p, ex: 0.8 = 80% utilizacao)
        horas_dia: Horas de trabalho por dia calendario (default: 8h)
        horas_mes: Horas de trabalho por mes (default: 193.6h = 22 dias x 8.8h)

    Returns:
        Custo por hora produtiva (R$/h_produtiva)

    Conversoes:
        - hora_produtiva (None/default): preco ja esta em R$/h produtiva -> sem conversao
        - dia_calendario: (preco / horas_dia) / producao_horaria
          Ex: R$800/dia com eta_p=0.8 -> (800/8)/0.8 = R$125/h_produtiva
        - mes: (preco / horas_mes) / producao_horaria
          Ex: R$15500/mes com eta_p=0.8 -> (15500/193.6)/0.8 = R$100/h_produtiva
    """
    if not rental_unit or rental_unit == "hora_produtiva":
        return preco_original

    if rental_unit == "dia_calendario":
        # R$/dia -> R$/h_calendario -> R$/h_produtiva
        custo_hora_calendario = preco_original / horas_dia
        return custo_hora_calendario / producao_horaria if producao_horaria > 0 else custo_hora_calendario

    if rental_unit == "mes":
        # R$/mes -> R$/h_calendario -> R$/h_produtiva
        custo_hora_calendario = preco_original / horas_mes
        return custo_hora_calendario / producao_horaria if producao_horaria > 0 else custo_hora_calendario

    # Fallback: unidade desconhecida, retorna sem conversao
    return preco_original


def calcular_pu(
    producao: dict,
    insumo_index: dict[str, dict],
    params: ParametrosCalculo | None = None,
    catalog_session: object | None = None,
) -> BreakdownPU:
    """Calcula PU para uma unica producao a partir da composicao da equipe.

    PU = custo_total_horario / producao.valor_horario
    """
    if params is None:
        params = ParametrosCalculo()
    producao_id = producao.get("id") or producao.get("codigo") or "?"
    valor_horario = float(producao.get("valor_horario") or 0)
    bd = BreakdownPU(producao_id=producao_id, valor_horario=valor_horario)

    equipe, funcoes, equipamentos, materiais = _cpu_get_equipe(producao)

    _acumular_custo_mo(bd, funcoes, insumo_index, params)
    _acumular_custo_equipamentos(bd, equipamentos, insumo_index, params)
    _acumular_custo_materiais(bd, materiais, insumo_index)

    return bd


def _acumular_custo_mo(
    bd: BreakdownPU, funcoes: list, insumo_index: dict[str, dict], params: ParametrosCalculo
) -> None:
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
            # Taxa horária já carregada (convenção planilha AGIS: inclui encargos).
            # Uso direto sem multiplicar por alpha para evitar dupla contagem.
            contrib = salario * num_pessoas
            bd.custo_mo_h += contrib
        else:
            # Salário mensal — converte para horário e aplica fator de encargos
            hm = _horas_mes(ins, params)
            contrib = (salario / hm) * _alpha(ins, params) * num_pessoas
            bd.custo_mo_h += contrib
        bd.itens.append(
            {
                "insumo_id": fid,
                "categoria": "mo",
                "preco_unitario": salario,
                "quantidade": num_pessoas,
                "contribuicao_h": round(contrib, 4),
            }
        )


def _preco_h_equipamento(eq: dict, ins: dict) -> float:
    # ADR-132: preco_h_unitario na entry de composição sobrepõe preco_unitario do
    # insumo do catálogo, permitindo preços por-atividade sem duplicar insumos no catálogo.
    # Já armazenado em R$/h para evitar ambiguidade de horas_mes entre regimes.
    preco_h_override = eq.get("preco_h_unitario")
    if preco_h_override is not None and float(preco_h_override) > 0:
        return float(preco_h_override)
    preco_raw = float(ins.get("preco_unitario") or 0)
    rental_unit = ins.get("rental_unit")
    producao_h = float(eq.get("producao_horaria") or 1.0)
    return _converter_rental_unit(preco_raw, rental_unit, producao_h)


def _consumo_diesel_equipamento(bd: BreakdownPU, eq: dict, eid: str, ins: dict | None) -> float:
    # Precedência de consumo: entry da produção → atributos_especificos do insumo
    consumo = float(eq.get("consumo_litros_hora") or 0)
    if not consumo:
        atrib_eq = (ins or {}).get("atributos_especificos") or {}
        consumo = float(atrib_eq.get("consumo_litros_hora") or 0)
        if consumo:
            bd.alertas.append(f"Equipamento '{eid}': consumo_litros_hora lido de atributos_especificos do insumo.")
    return consumo


def _acumular_custo_equipamentos(
    bd: BreakdownPU, equipamentos: list, insumo_index: dict[str, dict], params: ParametrosCalculo
) -> None:
    for eq in equipamentos:
        eid = eq.get("equip_id", "")
        num_un = float(eq.get("num_unidades") or 1)
        ins = insumo_index.get(eid)
        if ins is None:
            bd.referencias_faltantes.append(eid)
            continue
        preco_h = _preco_h_equipamento(eq, ins)
        contrib_equip = preco_h * num_un
        bd.custo_equip_h += contrib_equip
        bd.itens.append(
            {
                "insumo_id": eid,
                "categoria": "equipamento",
                "preco_unitario": preco_h,
                "quantidade": num_un,
                "contribuicao_h": round(contrib_equip, 4),
            }
        )
        consumo = _consumo_diesel_equipamento(bd, eq, eid, ins)
        if consumo:
            contrib_diesel = consumo * params.preco_diesel * num_un
            bd.custo_diesel_h += contrib_diesel
            bd.itens.append(
                {
                    "insumo_id": eid,
                    "categoria": "diesel",
                    "preco_unitario": params.preco_diesel,
                    "quantidade": consumo * num_un,
                    "contribuicao_h": round(contrib_diesel, 4),
                }
            )


def _material_id_e_consumo(mat: dict) -> tuple[str, float]:
    mid = mat.get("insumo_id") or mat.get("material_id") or mat.get("codigo") or ""
    consumo_h = float(mat.get("consumo_por_hora") or mat.get("quantidade_h") or 0)
    return mid, consumo_h


def _acumular_custo_materiais(bd: BreakdownPU, materiais: list, insumo_index: dict[str, dict]) -> None:
    for mat in materiais:
        mid, consumo_h = _material_id_e_consumo(mat)
        ins = insumo_index.get(mid)
        if ins is None and mid:
            bd.referencias_faltantes.append(mid)
            continue
        if ins:
            preco = float(ins.get("preco_unitario") or 0)
            contrib = consumo_h * preco
            bd.custo_material_h += contrib
            bd.itens.append(
                {
                    "insumo_id": mid,
                    "categoria": "material",
                    "preco_unitario": preco,
                    "quantidade": consumo_h,
                    "contribuicao_h": round(contrib, 4),
                }
            )


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
        bd = calcular_pu(prod, insumo_index, params)
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
    catalog_session: object | None = None,
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
