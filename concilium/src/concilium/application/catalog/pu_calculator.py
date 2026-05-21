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

from dataclasses import dataclass, field

from concilium.domain.constants import ENCARGOS_CLT, ENCARGOS_PJ, HORAS_MES_REGIME_6x1

# ── Parâmetros default (ADR-056 §T3 — fonte: domain/constants.py) ────────────
DEFAULT_ALPHA_CLT = ENCARGOS_CLT
DEFAULT_ALPHA_PJ = ENCARGOS_PJ
DEFAULT_PRECO_DIESEL = 6.50  # R$/L
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


def _cpu_get_equipe(producao: dict) -> tuple:
    """Returns (equipe, funcoes, equipamentos, materiais) from producao dict."""
    _equipe, funcoes, equipamentos, materiais = _cpu_get_equipe(producao)
    _cpu_process_funcoes(funcoes, insumo_index, result, params)
    _cpu_process_equipamentos(equipamentos, insumo_index, result, params)
    _cpu_process_materiais(materiais, insumo_index, result)
    return result


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

    insumo_index = {ins["codigo"]: ins for ins in insumos if ins.get("codigo")}

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
            refs_faltantes.append(
                {
                    "producao_id": bd.producao_id,
                    "faltantes": bd.referencias_faltantes,
                }
            )

        if not bd.valor_horario:
            sem_valor.append(bd.producao_id)
            continue

        # Verifica consistência vs _cu_planilha (se presente nas CPUs correspondentes)
        # A produção pode ter `_cu_planilha` herdado; verificamos via alertas
        if bd.pu_calculado is not None:
            for cpu_hint in (prod.get("_cu_planilha_referencia"),):
                if cpu_hint is None:
                    break
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

    return {
        "ok": not refs_faltantes and not sem_valor,
        "total_producoes": len(producoes),
        "com_composicao": com_composicao,
        "sem_valor_horario": sem_valor,
        "referencias_faltantes": refs_faltantes,
        "pu_divergentes": pu_divergentes,
        "breakdown_por_producao": breakdowns,
    }
