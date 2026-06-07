"""ADR-080: Helpers de custo diferenciado de permanência por instância.

Funções expostas:
  ``calcular_custo_contrato_por_instancia`` — custo de uma instância de pool
    usando taxa ativa (c_unit) para semanas ativas e taxa ociosa (c_idle) para
    standby, incluindo mob/demob.

Semântica:
  custo = c_unit × active_weeks
        + rate_standby × standby_weeks     (rate = c_idle se c_idle>0, else c_unit)
        + c_mob + c_demob
"""

from __future__ import annotations


def calcular_custo_contrato_por_instancia(
    active_weeks: int,
    standby_weeks: int,
    custo_unit_semanal: float,
    custo_idle_semanal: float,
    custo_mob: float,
    custo_demob: float,
) -> float:
    """Custo total de uma instância de pool para seu ciclo de vida.

    ADR-080 §B — Taxa Ociosa Diferenciada:
    - Semanas ativas: cobradas a ``custo_unit_semanal`` (inclui MO + EQ + combustível)
    - Semanas standby: cobradas a ``custo_idle_semanal`` (apenas aluguel de equipamento)
      - Fallback: quando ``custo_idle_semanal == 0``, usa ``custo_unit_semanal`` (legado)

    ADR-080 §C — Desmobilização Antecipada Efetiva:
    - O chamador passa ``standby_weeks=0`` e ``custo_demob`` para refletir early demob
    - Quando trailing standby é eliminado, ``standby_weeks=0``, custo_demob é pago

    ADR-080 §A — Mobilização Tardia:
    - O chamador ajusta ``active_weeks`` e ``standby_weeks`` com base na janela real
      [semana_mobilizacao_i, semana_desmobilizacao_i] em vez do span global do contrato

    Compatibilidade retroativa (ADR-079):
    - ``custo_idle_semanal=0`` → standby cobrado a taxa plena (comportamento anterior)
    """
    rate_standby = custo_idle_semanal if custo_idle_semanal > 0 else custo_unit_semanal
    return custo_unit_semanal * active_weeks + rate_standby * standby_weeks + custo_mob + custo_demob


def calcular_custo_instancia_composicional(
    prod_weeks: int,
    idle_weeks: int,
    c_mo: float,
    c_eq: float,
    c_comb: float,
    c_mat: float,
    c_idle_eq: float,
    c_demob_efetivo: float = 0.0,
) -> dict[str, float]:
    """ADR-085 D3: custo instancial composicional por componente.

    Generaliza ``calcular_custo_contrato_por_instancia`` (ADR-080, escalar) para tratar
    cada componente com sua dinâmica de ociosidade própria, consistente com a operação:

    - **Semanas produtivas** (``prod_weeks``): todos os componentes à taxa plena
      (MO + EQ + combustível + material).
    - **Semanas ociosas** (``idle_weeks``, dentro do ciclo de vida [mob, demob] sem
      atividade): mão-de-obra **integral** (CLT não permite taxa reduzida), equipamento à
      **taxa de locação reduzida** ``c_idle_eq``, combustível e material **zerados**
      (sem operação → sem consumo).
    - **Semanas off** (fora do ciclo de vida — mobilização tardia / desmob antecipada):
      custo zero; o chamador simplesmente não as inclui em prod nem idle.
    - ``c_demob_efetivo``: custo de desmobilização incorrido apenas quando a desmob
      antecipada é aplicada à instância (ADR-085 D3 / ADR-080 §C).

    Retrocompatível: quando ``c_idle_eq`` reflete a taxa cheia de EQ, o resultado recai no
    comportamento sem desconto de ociosidade.

    Retorna um dict com os componentes e o total, para popular ``InstanciaRecurso``.
    """
    ativo_mo = c_mo * prod_weeks
    ativo_eq = c_eq * prod_weeks
    ativo_comb = c_comb * prod_weeks
    ativo_mat = c_mat * prod_weeks
    idle_mo = c_mo * idle_weeks  # MO integral durante ociosidade (CLT)
    idle_eq = c_idle_eq * idle_weeks  # EQ à taxa de locação reduzida
    total = ativo_mo + ativo_eq + ativo_comb + ativo_mat + idle_mo + idle_eq + c_demob_efetivo
    return {
        "ativo_mo": round(ativo_mo, 2),
        "ativo_eq": round(ativo_eq, 2),
        "ativo_comb": round(ativo_comb, 2),
        "ativo_mat": round(ativo_mat, 2),
        "idle_mo": round(idle_mo, 2),
        "idle_eq": round(idle_eq, 2),
        "demob": round(c_demob_efetivo, 2),
        "total": round(total, 2),
    }
