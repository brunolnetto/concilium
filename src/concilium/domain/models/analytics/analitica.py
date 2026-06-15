"""Modelos analíticos do espaço ontológico (ADR-058).

Expõem a riqueza do canonical em três dimensões:
    1. Insumo individual — CurvaABCInsumo (ABC por insumo_id, não por atividade)
    2. Tempo — SCurve (curva S de custo acumulado semana a semana)
    3. Equipamento semanal — AgregacaoSemanalEquipamentos (frota ativa por semana)

Todos os tipos são frozen — artefatos imutáveis gerados pelos builders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# ── ADR-058 D1: Insumo tipado por atividade ──────────────────────────────────


@dataclass(frozen=True)
class InsumoDetalheAtividade:
    """Linha de custo rastreável de um insumo dentro de uma atividade.

    Substitui `InsumoComponenteAtividade.itens: list[dict]` com schema tipado.
    Permite rastrear cada funcao_id / equip_id até o custo que contribuiu ao resultado.
    """

    insumo_id: str  # funcao_id ou equip_id do catálogo
    descricao: str
    categoria: str  # "MAO_OBRA" | "EQUIPAMENTO" | "DIESEL" | "MATERIAL"
    num_unidades: float  # pessoas (MO) ou unidades (EQ/MAT)
    custo_unitario_mensal: float
    permanencia_meses: float
    custo_total: float  # = custo_unitario_mensal × num_unidades × permanencia_meses

    def to_dict(self) -> dict:
        import dataclasses

        return dataclasses.asdict(self)


# ── ADR-058 D2: Curva ABC por insumo ─────────────────────────────────────────


@dataclass(frozen=True)
class ItemCurvaABC:
    """Um insumo no ranking ABC acumulado por custo total no projeto."""

    insumo_id: str
    descricao: str
    categoria: str  # "MAO_OBRA" | "EQUIPAMENTO" | "DIESEL" | "MATERIAL"
    custo_total: float  # custo absoluto (R$)
    pct_custo: float  # fração deste insumo no total (0–1)
    pct_custo_acumulado: float  # fração acumulada até este item (0–1)
    classe: Literal["A", "B", "C"]  # A: 0–80%, B: 80–95%, C: 95–100%
    atividades: tuple[str, ...]  # item_ids que usam este insumo

    @property
    def descricao_classe(self) -> str:
        mapping = {"A": "Crítico (80% do custo)", "B": "Importante (15%)", "C": "Comum (5%)"}
        return mapping[self.classe]


@dataclass(frozen=True)
class CurvaABCInsumo:
    """Curva ABC completa por insumo para um projeto (ADR-058 D2).

    Agrega todos os custos de `equipes_diretas.funcoes` e `.equipamentos` por
    `insumo_id`, ordena por custo descrescente e classifica em A / B / C.

    Invariante: sum(item.pct_custo for item in itens) ≈ 1.0
    """

    projeto_id: str
    gerado_em: str
    total_custo_direto: float
    itens: tuple[ItemCurvaABC, ...]  # ordenados por custo_total desc

    # Sumários por classe
    total_a: float  # custo dos itens classe A
    total_b: float  # custo dos itens classe B
    total_c: float  # custo dos itens classe C
    n_itens_a: int
    n_itens_b: int
    n_itens_c: int

    @property
    def pct_a(self) -> float:
        return round(self.total_a / self.total_custo_direto, 4) if self.total_custo_direto > 0 else 0.0

    def to_dict(self) -> dict:
        import dataclasses

        def _conv(obj):
            if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                return {k: _conv(v) for k, v in dataclasses.asdict(obj).items()}
            if isinstance(obj, (list, tuple)):
                return [_conv(v) for v in obj]
            return obj

        return _conv(self)


# ── ADR-058 D3: Agregação semanal de equipamentos ────────────────────────────


@dataclass(frozen=True)
class AgregacaoSemanalEquipamentos:
    """Equipamentos ativos e custos consolidados em uma semana ISO."""

    semana_iso: str  # "2026-W23"
    semana_offset: int  # 0-indexed offset from project start
    equipamentos_ativos: dict[str, int]  # {equip_id: n_unidades}
    n_equipamentos_unicos: int
    n_equipes_totais: int  # sum de num_equipes across all activities this week
    custo_direto_semana: float
    custo_indireto_semana: float
    custo_total_semana: float


# ── ADR-058 D4: S-Curve de custo acumulado ───────────────────────────────────


@dataclass(frozen=True)
class SCurve:
    """Curva S de custo acumulado semana a semana (ADR-058 D4).

    A S-curve é o instrumento central de controle temporal de custo (Earned Value).
    Expõe a trajetória planejada de desembolso ao longo do projeto.

    Invariante: custo_acumulado[-1] ≈ venda_total_com_bdi do resultado.
    """

    projeto_id: str
    gerado_em: str
    total_custo_direto: float
    total_custo_indireto: float
    total_projeto: float

    semanas_iso: tuple[str, ...]  # ordenadas
    custo_semanal: tuple[float, ...]  # R$ por semana
    custo_acumulado: tuple[float, ...]  # R$ acumulado por semana
    pct_acumulado: tuple[float, ...]  # fração 0–1 acumulada

    agregacao_semanal: tuple[AgregacaoSemanalEquipamentos, ...]

    def to_dict(self) -> dict:
        import dataclasses

        def _conv(obj):
            if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                return {k: _conv(v) for k, v in dataclasses.asdict(obj).items()}
            if isinstance(obj, (list, tuple)):
                return [_conv(v) for v in obj]
            return obj

        return _conv(self)
