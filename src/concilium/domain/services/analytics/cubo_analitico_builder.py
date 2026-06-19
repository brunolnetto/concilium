"""CuboAnaliticoBuilder — ADR-087/088/089.

Constrói CuboAnalitico a partir do canonical seguindo a hierarquia dimensional:
  {natureza}.{atividade}.{categoria_insumo}.{propriedade}

Mapeamento (ADR-087 D2 + ADR-089 D1):
  custo_mao_obra_mensal          → (mao_obra,    salario_encargos) → BDI mao_obra
  custo_equipamentos_mensal      → (equipamento, aluguel)          → BDI servicos
  custo_combustivel_total_mensal → (equipamento, combustivel)      → BDI diesel  ← 4%
  custo_material_mensal          → (material,    consumivel)       → BDI material

Diesel como propriedade de equipamento preserva:
  - BDI = 4% (ADR-089: fornecimento de mercadoria, sem tributos de serviço)
  - Grandeza física (L/semana) via valor_fisico + unidade_fisica="L"

Seleção de caminho (pool vs. autônomo — ADR-086):
  - Com pool: _build_from_pool — fonte única de custo R$, backward compat garantido
  - Sem pool: _build_autonomous — custo_*_mensal × permanência schedule
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from concilium.domain.constants import SEMANAS_POR_MES
from concilium.domain.models.analytics.cubo_analitico import CelulaAnalitica, CuboAnalitico
from concilium.domain.models.financial.bdi import DEFAULT_BDI_TABELA, TabelaBdi

# ADR-087/089: mapeamento (campo_equipe, categoria_insumo, propriedade, cat_bdi, unidade_fisica)
# A coluna cat_bdi referencia o campo na TabelaBdi para obter BDI e decomposição.
# ADR-090: combustivel → (material, combustivel) com BDI_material (4%).
# Diesel = insumo físico consumido = mesma natureza econômica de areia/brita.
_PROP_BDI_MAP: list[tuple[str, str, str, str, str]] = [
    # campo_equipe_direta           cat_insumo      propriedade          cat_bdi    unidade
    ("custo_mao_obra_mensal", "mao_obra", "salario_encargos", "mao_obra", ""),
    ("custo_equipamentos_mensal", "equipamento", "aluguel", "servicos", ""),
    ("custo_combustivel_total_mensal", "material", "combustivel", "material", "L"),
    ("custo_material_mensal", "material", "consumivel", "material", ""),
]

# Mapeamento pool → hierarquia dimensional (ADR-090)
_POOL_TO_PROP: dict[str, tuple[str, str, str]] = {
    "mo": ("mao_obra", "salario_encargos", ""),
    "eq": ("equipamento", "aluguel", ""),
    "comb": ("material", "combustivel", "L"),  # ADR-090: combustivel = material
    "mat": ("material", "consumivel", ""),
}


def _cab_compute_diesel_consumo(equipe: object, horas_semana: float) -> float:
    """L/semana a 100% eficiência — grandeza física do ativo (não custo)."""
    consumo_L_hora_base = sum(
        (eq.consumo_litros_hora or 0.0) * eq.num_unidades for eq in equipe.equipamentos if eq.consumo_litros_hora
    )
    return consumo_L_hora_base * horas_semana


def _cab_campo_custo(
    cat_insumo: str,
    propriedade: str,
    custo_mensal: float,
    fator_semanal: float,
    eficiencia: float,
    consumo_L_100pct: float,
    n_equipes: int,
) -> tuple[float, float]:
    """Returns (custo_semana_base, valor_fisico) para a propriedade."""
    if propriedade == "combustivel":
        # ADR-090: diesel = material.combustivel, modulado por eficiência (sem consumo parado)
        return custo_mensal * fator_semanal * eficiencia, consumo_L_100pct * eficiencia * n_equipes
    return custo_mensal * fator_semanal, 0.0


def _cab_collect_celulas_semana(
    equipe: object,
    atividade_id: str,
    semana_iso: str,
    dist: object,
    consumo_L_semana_100pct: float,
    bdi: dict[tuple[str, str], float],
    decomp: dict[tuple[str, str], dict[str, float]],
    min_val: float,
) -> list:
    """Retorna CelulaAnalitica para (equipe, semana) — ADR-087 hierarquia."""
    n_equipes = dist.num_equipes
    if n_equipes <= 0:
        return []
    eficiencia = float(getattr(dist, "eficiencia", 1.0) or 1.0)
    fator_semanal = n_equipes / SEMANAS_POR_MES
    result = []
    for campo, cat_insumo, propriedade, cat_bdi, unidade in _PROP_BDI_MAP:
        custo_mensal = float(getattr(equipe, campo, 0.0) or 0.0)
        if custo_mensal <= 0:
            continue
        custo_semana_base, valor_fisico = _cab_campo_custo(
            cat_insumo,
            propriedade,
            custo_mensal,
            fator_semanal,
            eficiencia,
            consumo_L_semana_100pct,
            n_equipes,
        )
        bdi_key = (cat_insumo, propriedade)
        pv_semana = custo_semana_base * (1.0 + bdi.get(bdi_key, 0.0))
        for comp, pct in (decomp.get(bdi_key) or {}).items():
            valor = pv_semana * pct
            if valor >= min_val:
                cel_vf = round(valor_fisico, 3) if (unidade == "L" and comp == "custo_direto") else 0.0
                result.append(
                    CelulaAnalitica(
                        natureza="direto",
                        atividade_id=atividade_id,
                        categoria_insumo=cat_insumo,
                        propriedade=propriedade,
                        semana_iso=semana_iso,
                        componente_bdi=comp,
                        valor_rs=round(valor, 2),
                        valor_fisico=cel_vf,
                        unidade_fisica=unidade if (unidade and comp == "custo_direto") else "",
                    )
                )
    return result


class CuboAnaliticoBuilder:
    """Constrói CuboAnalitico sem iteração de insumos individuais.

    Quando pool de recursos presente → _build_from_pool (invariância construtiva ADR-086).
    Sem pool → _build_autonomous (fallback).
    """

    _using_default: bool
    _tabela: TabelaBdi
    _regime: str
    _min: float
    _horas_dia: int
    _dias_semana: int
    _horas_semana: int

    def __init__(
        self,
        tabela_bdi: TabelaBdi | None = None,
        regime_version: str = "pre_reforma",
        min_valor_rs: float = 0.01,
        horas_dia: int = 8,
        dias_semana: int = 6,
    ) -> None:
        self._using_default = tabela_bdi is None
        self._tabela = tabela_bdi or DEFAULT_BDI_TABELA
        self._regime = regime_version
        self._min = min_valor_rs
        self._horas_dia = horas_dia
        self._dias_semana = dias_semana
        self._horas_semana = horas_dia * dias_semana

        # ADR-089/090: BDI e decomposição indexados por (categoria_insumo, propriedade)
        # ADR-090: combustivel usa BDI_material (= 4%), mesma taxa de insumos físicos.
        # Equipment (aluguel/manutencao) segue perfil de serviços para decomposição completa.
        self._bdi: dict[tuple[str, str], float] = {
            ("mao_obra", "salario_encargos"): self._tabela.mao_obra.bdi_total,
            ("equipamento", "aluguel"): self._tabela.servicos.bdi_total,
            ("equipamento", "manutencao"): self._tabela.servicos.bdi_total,
            ("material", "consumivel"): self._tabela.material.bdi_total,
            ("material", "combustivel"): self._tabela.material.bdi_total,  # ADR-090
        }
        self._decomp: dict[tuple[str, str], dict[str, float]] = {
            ("mao_obra", "salario_encargos"): self._tabela.mao_obra.decomposicao_no_preco(),
            ("equipamento", "aluguel"): self._tabela.servicos.decomposicao_no_preco(),
            ("equipamento", "manutencao"): self._tabela.servicos.decomposicao_no_preco(),
            ("material", "consumivel"): self._tabela.material.decomposicao_no_preco(),
            ("material", "combustivel"): self._tabela.material.decomposicao_no_preco(),  # ADR-090
        }

    def build(self, canonical_in: Any) -> CuboAnalitico:
        """Seleciona caminho pool (preferencial) ou autônomo (fallback)."""
        if self._using_default:
            tabela_efetiva = getattr(canonical_in, "tabela_bdi_efetiva", None)
            if tabela_efetiva is not None:
                return CuboAnaliticoBuilder(
                    tabela_bdi=tabela_efetiva,
                    regime_version=self._regime,
                    min_valor_rs=self._min,
                    horas_dia=self._horas_dia,
                    dias_semana=self._dias_semana,
                ).build(canonical_in)

        contratos = getattr(canonical_in, "contratos_recurso", None) or []
        instancias = getattr(canonical_in, "instancias_recurso", None) or []
        if contratos and instancias:
            return self._build_from_pool(canonical_in)
        return self._build_autonomous(canonical_in)

    def _build_from_pool(self, canonical_in: Any) -> CuboAnalitico:
        """Deriva CuboAnalitico do CuboPoolInstancial — invariância construtiva ADR-086."""
        from concilium.domain.services.analytics.cubo_pool_builder import CuboPoolInstancialBuilder

        projeto_id = str(getattr(getattr(canonical_in, "projeto", None), "nome", "?"))
        cubo_pool = CuboPoolInstancialBuilder().build(canonical_in)

        if not cubo_pool.celulas:
            return self._build_autonomous(canonical_in)

        # Agrega custos produtivos por (atividade, semana) usando _POOL_TO_PROP
        cost_map: dict[tuple[str, str], dict[str, float]] = {}
        for cell in cubo_pool.celulas:
            if cell.estado != "prod" or not cell.atividade_id:
                continue
            k = (cell.atividade_id, cell.semana_iso)
            d = cost_map.setdefault(k, {"mo": 0.0, "eq": 0.0, "comb": 0.0, "mat": 0.0})
            d["mo"] += cell.custo_mo
            d["eq"] += cell.custo_eq
            d["comb"] += cell.custo_comb
            d["mat"] += cell.custo_mat

        diesel_L_map = self._build_diesel_L_map(canonical_in)

        celulas: list[CelulaAnalitica] = []
        for (atividade_id, semana_iso), costs in cost_map.items():
            for pool_key, (cat_insumo, propriedade, unidade) in _POOL_TO_PROP.items():
                custo_sem = costs.get(pool_key, 0.0)
                if custo_sem <= 0:
                    continue
                bdi_key = (cat_insumo, propriedade)
                pv_sem = custo_sem * (1.0 + self._bdi.get(bdi_key, 0.0))
                consumo_L = diesel_L_map.get((atividade_id, semana_iso), 0.0)
                for comp, pct in (self._decomp.get(bdi_key) or {}).items():
                    valor = pv_sem * pct
                    if valor >= self._min:
                        cel_vf = round(consumo_L, 3) if (unidade == "L" and comp == "custo_direto") else 0.0
                        celulas.append(
                            CelulaAnalitica(
                                natureza="direto",
                                atividade_id=atividade_id,
                                categoria_insumo=cat_insumo,
                                propriedade=propriedade,
                                semana_iso=semana_iso,
                                componente_bdi=comp,
                                valor_rs=round(valor, 2),
                                valor_fisico=cel_vf,
                                unidade_fisica=unidade if (unidade and comp == "custo_direto") else "",
                            )
                        )

        # Enriquecimento financeiro: escalar ao PUxQ e adicionar indireto
        celulas = self._enrich_with_financial_data(canonical_in, celulas)

        total = round(sum(c.valor_rs for c in celulas if c.natureza == "direto"), 2)
        return CuboAnalitico(
            projeto_id=projeto_id,
            gerado_em=datetime.now(UTC).isoformat(),
            regime_bdi=self._regime,
            total_preco_venda=total,
            celulas=tuple(celulas),
        )

    def _enrich_with_financial_data(self, canonical_in: Any, celulas: list[CelulaAnalitica]) -> list[CelulaAnalitica]:
        """Escala células diretas ao custo PUxQ e adiciona células de indireto.

        O pool captura apenas a fatia rastreável (estado=prod); o planejamento contém
        o custo completo (overhead de quantização, praticabilidade, etc.).
        Escalamos por atividade para preservar a distribuição temporal do pool.
        """
        # 1. Escalar células diretas ao custo PUxQ por atividade
        plan_total_by_item: dict[str, float] = {}
        for item in getattr(canonical_in, "planejamento", None) or []:
            item_id = str(getattr(item, "item_id", "") or "")
            subtotal = getattr(item, "subtotal", None)
            sem_bdi = getattr(subtotal, "sem_bdi", None) if subtotal else None
            total_rs = float(getattr(sem_bdi, "total", 0.0) or 0.0) if sem_bdi else 0.0
            if item_id and total_rs > 0:
                plan_total_by_item[item_id] = total_rs

        if plan_total_by_item and celulas:
            pool_total_by_item: dict[str, float] = {}
            for c in celulas:
                if c.natureza == "direto" and c.componente_bdi == "custo_direto":
                    pool_total_by_item[c.atividade_id] = pool_total_by_item.get(c.atividade_id, 0.0) + c.valor_rs
            scale_factors: dict[str, float] = {
                item_id: plan_val / pool_total_by_item[item_id]
                for item_id, plan_val in plan_total_by_item.items()
                if pool_total_by_item.get(item_id, 0.0) > 0
            }
            celulas = [
                CelulaAnalitica(
                    natureza=c.natureza,
                    atividade_id=c.atividade_id,
                    categoria_insumo=c.categoria_insumo,
                    propriedade=c.propriedade,
                    semana_iso=c.semana_iso,
                    componente_bdi=c.componente_bdi,
                    valor_rs=round(c.valor_rs * scale_factors.get(c.atividade_id, 1.0), 2),
                    valor_fisico=c.valor_fisico,
                    unidade_fisica=c.unidade_fisica,
                )
                for c in celulas
            ]

        # 2. Adicionar células de indireto de indiretos_semanal
        projeto = getattr(canonical_in, "projeto", None)
        data_inicio_str = str(getattr(projeto, "data_inicio", "") or "") if projeto else ""
        ind_sem = getattr(canonical_in, "indiretos_semanal", None) or []
        if ind_sem and data_inicio_str:
            try:
                from datetime import date, timedelta

                data_inicio = date.fromisoformat(data_inicio_str)
                for item in ind_sem:
                    semana_offset = getattr(item, "semana", None)
                    if semana_offset is None:
                        continue
                    custo_sem = float(getattr(item, "custo_semanal", 0.0) or 0.0)
                    if custo_sem <= self._min:
                        continue
                    cat = str(getattr(item, "categoria", "ADM") or "ADM")
                    dt = data_inicio + timedelta(weeks=int(semana_offset))
                    iso = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
                    celulas.append(
                        CelulaAnalitica(
                            natureza="indireto",
                            atividade_id=f"IND-{cat}",
                            categoria_insumo="verba",  # Literal válido; natureza='indireto' diferencia
                            propriedade=cat.lower(),
                            semana_iso=iso,
                            componente_bdi="custo_direto",
                            valor_rs=round(custo_sem, 2),
                            valor_fisico=0.0,
                            unidade_fisica="",
                        )
                    )
            except Exception:
                pass  # enriquecimento de indireto é best-effort

        return celulas

    def _build_autonomous(self, canonical_in: Any) -> CuboAnalitico:
        """Fallback autônomo: custo_*_mensal × schedule."""
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

    def _build_diesel_L_map(self, canonical_in: Any) -> dict[tuple[str, str], float]:
        """Litros de diesel por (atividade, semana) — grandeza física do ativo."""
        cronograma = canonical_in.cronograma
        if not cronograma:
            return {}
        sched_lookup = {sa.activity_id: sa for sa in cronograma.scheduled_activities}
        result: dict[tuple[str, str], float] = {}
        for equipe in canonical_in.equipes_diretas or []:
            sa = sched_lookup.get(equipe.item_id)
            if not sa or not sa.distribuicao_semanal:
                continue
            consumo_base = _cab_compute_diesel_consumo(equipe, self._horas_semana)
            if consumo_base <= 0:
                continue
            for semana_iso, dist in sa.distribuicao_semanal.items():
                n = getattr(dist, "num_equipes", 0) or 0
                if n <= 0:
                    continue
                efic = float(getattr(dist, "eficiencia", 1.0) or 1.0)
                k = (equipe.item_id, semana_iso)
                result[k] = result.get(k, 0.0) + consumo_base * efic * n
        return result

    @staticmethod
    def _empty(projeto_id: str) -> CuboAnalitico:
        return CuboAnalitico(
            projeto_id=projeto_id,
            gerado_em=datetime.now(UTC).isoformat(),
            regime_bdi="pre_reforma",
            total_preco_venda=0.0,
            celulas=(),
        )
