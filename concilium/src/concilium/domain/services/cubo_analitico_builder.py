"""CuboAnaliticoBuilder — materializa o cubo 4D a partir do canonical (ADR-058 ext.).

Dimensões: categoria × atividade × tempo × componente_BDI

Complexidade: O(N_atividades × N_semanas) para MO/EQ/MAT — custos pré-agregados.
Para diesel: O(N_atividades × N_equipamentos × N_semanas) — itera equipe.equipamentos
para somar consumo_litros_hora × regime × eficiencia por semana. A iteração é sobre
equipamentos por atividade (pequeno loop), não sobre insumos individuais do catálogo.

Mapeamento de categorias do EquipeDireta → TabelaBdi:
    mao_obra    → tabela.mao_obra
    equipamento → tabela.servicos   (ADR-023: equipamentos usam BDI de serviços)
    diesel      → tabela.diesel
    material    → tabela.material

Diesel em litros:
    consumo_L_semana = Σ_equip { consumo_litros_hora × horas_dia × dias_semana
                                  × eficiencia × num_equipes × num_unidades }
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from concilium.domain.constants import SEMANAS_POR_MES
from concilium.domain.models.bdi import DEFAULT_BDI_TABELA, TabelaBdi
from concilium.domain.models.cubo_analitico import CelulaAnalitica, CuboAnalitico

# Mapeamento: campo em EquipeDireta → categoria canônica do cubo → categoria da TabelaBdi
_CUSTO_CAMPOS: list[tuple[str, str, str]] = [
    ("custo_mao_obra_mensal", "mao_obra", "mao_obra"),
    ("custo_equipamentos_mensal", "equipamento", "servicos"),  # ADR-023
    ("custo_combustivel_total_mensal", "diesel", "diesel"),
    ("custo_material_mensal", "material", "material"),
]


def _cab_compute_diesel_consumo(equipe: object, horas_semana: float) -> float:
    """Computes base diesel consumption in L/week at 100% efficiency."""
    consumo_L_hora_base = sum(
        (eq.consumo_litros_hora or 0.0) * eq.num_unidades for eq in equipe.equipamentos if eq.consumo_litros_hora
    )
    return consumo_L_hora_base * horas_semana


def _cab_campo_custo(
    cat: str, custo_mensal: float, fator_semanal: float, eficiencia: float, consumo_L_100pct: float, n_equipes: int
) -> tuple:
    """Returns (custo_semana_base, consumo_L) for a cost field category."""
    if cat == "diesel":
        return custo_mensal * fator_semanal * eficiencia, consumo_L_100pct * eficiencia * n_equipes
    return custo_mensal * fator_semanal, 0.0


def _cab_collect_celulas_semana(
    equipe: object,
    atividade_id: str,
    semana_iso: str,
    dist: object,
    consumo_L_semana_100pct: float,
    bdi: dict,
    decomp: dict,
    min_val: float,
) -> list:
    """Returns CelulaAnalitica list for a single (equipe, semana) combination."""
    from concilium.domain.models.cubo_analitico import CelulaAnalitica

    n_equipes = dist.num_equipes
    if n_equipes <= 0:
        return []
    eficiencia = float(getattr(dist, "eficiencia", 1.0) or 1.0)
    fator_semanal = n_equipes / SEMANAS_POR_MES
    result = []
    for campo, cat, _ in _CUSTO_CAMPOS:
        custo_mensal = float(getattr(equipe, campo, 0.0) or 0.0)
        if custo_mensal <= 0:
            continue
        custo_semana_base, consumo_L = _cab_campo_custo(
            cat, custo_mensal, fator_semanal, eficiencia, consumo_L_semana_100pct, n_equipes
        )
        pv_semana = custo_semana_base * (1.0 + bdi[cat])
        for comp, pct in decomp[cat].items():
            valor = pv_semana * pct
            if valor >= min_val:
                cel_consumo_L = round(consumo_L, 3) if (cat == "diesel" and comp == "custo_direto") else 0.0
                result.append(
                    CelulaAnalitica(
                        categoria=cat,
                        atividade_id=atividade_id,
                        semana_iso=semana_iso,
                        componente_bdi=comp,
                        valor_rs=round(valor, 2),
                        consumo_diesel_L=cel_consumo_L,
                    )
                )
    return result


class CuboAnaliticoBuilder:
    """Constrói CuboAnalitico sem iteração de insumos individuais.

    Args:
        tabela_bdi: TabelaBdi efetiva (se None, usa DEFAULT_BDI_TABELA).
        regime_version: "pre_reforma" | "transicao" | "pleno_cbs_ibs"
        min_valor_rs: células com valor < min_valor_rs são descartadas (ruído).
    """

    def __init__(
        self,
        tabela_bdi: TabelaBdi | None = None,
        regime_version: str = "pre_reforma",
        min_valor_rs: float = 0.01,
        horas_dia: int = 8,
        dias_semana: int = 6,
    ) -> None:
        self._tabela = tabela_bdi or DEFAULT_BDI_TABELA
        self._regime = regime_version
        self._min = min_valor_rs
        self._horas_semana = horas_dia * dias_semana  # horas produtivas/semana (regime padrão)
        # Pré-computar decomposições (11 componentes × 4 categorias = 44 valores)
        self._decomp: dict[str, dict[str, float]] = {
            "mao_obra": self._tabela.mao_obra.decomposicao_no_preco(),
            "equipamento": self._tabela.servicos.decomposicao_no_preco(),
            "diesel": self._tabela.diesel.decomposicao_no_preco(),
            "material": self._tabela.material.decomposicao_no_preco(),
        }
        self._bdi: dict[str, float] = {
            "mao_obra": self._tabela.mao_obra.bdi_total,
            "equipamento": self._tabela.servicos.bdi_total,
            "diesel": self._tabela.diesel.bdi_total,
            "material": self._tabela.material.bdi_total,
        }

    def build(self, canonical_in: Any) -> CuboAnalitico:
        """Materializa o cubo 4D a partir de canonical_in."""
        projeto_id = str(getattr(getattr(canonical_in, "projeto", None), "nome", "?"))
        cronograma = canonical_in.cronograma

        if not cronograma or not cronograma.scheduled_activities:
            return self._empty(projeto_id)

        sched_lookup = {sa.activity_id: sa for sa in cronograma.scheduled_activities}
        celulas: list[CelulaAnalitica] = []

        for equipe in canonical_in.equipes_diretas or []:
            sa = sched_lookup.get(equipe.item_id)
            if not sa or not sa.distribuicao_semanal:
                continue

            atividade_id = equipe.item_id
            consumo_L_semana_100pct = _cab_compute_diesel_consumo(equipe, self._horas_semana)

            for semana_iso, dist in sa.distribuicao_semanal.items():
                celulas.extend(
                    _cab_collect_celulas_semana(
                        equipe,
                        atividade_id,
                        semana_iso,
                        dist,
                        consumo_L_semana_100pct,
                        self._bdi,
                        self._decomp,
                        self._min,
                    )
                )

        total = round(sum(c.valor_rs for c in celulas), 2)
        return CuboAnalitico(
            projeto_id=projeto_id,
            gerado_em=datetime.now(UTC).isoformat(),
            regime_bdi=self._regime,
            total_preco_venda=total,
            celulas=tuple(celulas),
        )

    @staticmethod
    def _empty(projeto_id: str) -> CuboAnalitico:
        return CuboAnalitico(
            projeto_id=projeto_id,
            gerado_em=datetime.now(UTC).isoformat(),
            regime_bdi="pre_reforma",
            total_preco_venda=0.0,
            celulas=(),
        )
