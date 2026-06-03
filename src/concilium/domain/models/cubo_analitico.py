"""CuboAnalitico — cubo analítico 4D do espaço ontológico de planejamento (ADR-058 extensão).

Dimensões: categoria × atividade × tempo × componente_BDI

O `insumo_id` foi intencionalmente excluído porque:
  - Os custos já estão pré-agregados por (categoria, atividade) em EquipeDireta
  - Análise por insumo é responsabilidade exclusiva de CurvaABCInsumo (ADR-058)
  - A remoção reduz o cubo ~30× (de ~1.3M para ~43k células)

Cada célula representa: quanto do preço de venda, em R$, em uma semana específica,
para uma categoria de custo de uma atividade, pertence a um componente do BDI.

Células da categoria "diesel" carregam também `consumo_diesel_L` — o volume físico
consumido na semana em litros. Grandeza física independente do preço: permite
planejamento de abastecimento, rastreamento de emissões e análise de sensibilidade
quando o preço do diesel varia.

    consumo_L_semana = Σ_equip { consumo_litros_hora × horas_dia × dias_semana
                                  × eficiencia × num_equipes × num_unidades }

Invariante por (categoria, atividade, semana):
    sum(célula.valor_rs for comp in COMPONENTES_BDI) ≈ PV_semana(categoria, atividade)

Onde PV_semana = custo_mensal × (num_equipes/SEMANAS_POR_MES) × (1 + BDI_categoria)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Literal

# Componentes BDI ordenados: custo → overhead → margem → tributos
COMPONENTES_BDI = (
    "custo_direto",
    "overhead_ac",
    "overhead_df",
    "overhead_r",
    "overhead_cr",
    "margem_l",
    "tributo_cofins",
    "tributo_iss",
    "tributo_pis",
    "tributo_cssl",
    "tributo_ir",
)

TRIBUTOS_BDI = frozenset({"tributo_cofins", "tributo_iss", "tributo_pis", "tributo_cssl", "tributo_ir"})
OVERHEAD_BDI = frozenset({"overhead_ac", "overhead_df", "overhead_r", "overhead_cr"})
TemporalGranularity = Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"]


def _temporal_bucket_from_week_iso(week_iso: str, granularidade: TemporalGranularity) -> str:
    """Mapeia uma semana ISO para uma janela temporal maior.

    O bucket usa a segunda-feira da semana ISO como âncora para derivar mês,
    bimestre, trimestre, semestre e ano.
    """

    if granularidade == "semana":
        return week_iso

    year_str, week_str = week_iso.split("-W", 1)
    anchor = date.fromisocalendar(int(year_str), int(week_str), 1)

    if granularidade == "mes":
        return f"{anchor.year:04d}-{anchor.month:02d}"

    if granularidade == "bimestre":
        bimestre = ((anchor.month - 1) // 2) + 1
        return f"{anchor.year:04d}-B{bimestre}"

    if granularidade == "trimestre":
        trimestre = ((anchor.month - 1) // 3) + 1
        return f"{anchor.year:04d}-T{trimestre}"

    if granularidade == "semestre":
        semestre = ((anchor.month - 1) // 6) + 1
        return f"{anchor.year:04d}-S{semestre}"

    if granularidade == "ano":
        return f"{anchor.year:04d}"

    raise ValueError(f"Granularidade temporal invalida: {granularidade}")


@dataclass(frozen=True)
class CelulaAnalitica:
    """Elemento atômico do cubo: (categoria, atividade, semana, componente_BDI) → R$.

    Para células com categoria="diesel", `consumo_diesel_L` carrega o volume físico
    em litros consumido naquela semana por aquela atividade. Para todas as demais
    categorias, `consumo_diesel_L` é 0.0.
    """

    categoria: str  # "mao_obra" | "equipamento" | "diesel" | "material"
    atividade_id: str  # EapItem.item_id
    semana_iso: str  # "2026-W23"
    componente_bdi: str  # ver COMPONENTES_BDI
    valor_rs: float  # R$ desta célula no preço de venda
    consumo_diesel_L: float = 0.0  # litros/semana — não-zero apenas para categoria="diesel"

    def is_tributo(self) -> bool:
        return self.componente_bdi in TRIBUTOS_BDI

    def is_overhead(self) -> bool:
        return self.componente_bdi in OVERHEAD_BDI

    def is_margem(self) -> bool:
        return self.componente_bdi == "margem_l"

    def is_custo_direto(self) -> bool:
        return self.componente_bdi == "custo_direto"

    def is_diesel(self) -> bool:
        return self.categoria == "diesel"


@dataclass(frozen=True)
class CuboAnalitico:
    """Cubo analítico 4D (categoria × atividade × tempo × componente_BDI).

    Gerado deterministicamente por CuboAnaliticoBuilder.build() a partir do canonical.
    Imutável após construção. Suporta projeções via slice() e group_by().
    """

    projeto_id: str
    gerado_em: str
    regime_bdi: str  # "pre_reforma" | "transicao" | "pleno_cbs_ibs"
    total_preco_venda: float  # soma de todas as células
    celulas: tuple[CelulaAnalitica, ...]  # ~43k células para projeto típico

    # ── Projeções fundamentais ─────────────────────────────────────────────

    def _aggregate_temporal(self, granularidade: TemporalGranularity, predicate=None) -> dict[str, dict[str, float]]:
        """Agrupa células por janela temporal e componente BDI."""

        result: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for c in self.celulas:
            if predicate is not None and not predicate(c):
                continue
            bucket = _temporal_bucket_from_week_iso(c.semana_iso, granularidade)
            result[bucket][c.componente_bdi] += c.valor_rs
        return {k: dict(v) for k, v in sorted(result.items())}

    def _aggregate_temporal_scalar(self, granularidade: TemporalGranularity, predicate=None) -> dict[str, float]:
        """Agrupa células por janela temporal e soma um único valor por bucket."""

        result: dict[str, float] = defaultdict(float)
        for c in self.celulas:
            if predicate is not None and not predicate(c):
                continue
            bucket = _temporal_bucket_from_week_iso(c.semana_iso, granularidade)
            result[bucket] += c.valor_rs
        return dict(sorted(result.items()))

    def _aggregate_natureza_temporal(self, granularidade: TemporalGranularity) -> dict[str, dict[str, float]]:
        """Agrupa células por janela temporal e separa custo direto vs. indireto."""

        result: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for c in self.celulas:
            bucket = _temporal_bucket_from_week_iso(c.semana_iso, granularidade)
            natureza = "direto" if c.is_custo_direto() else "indireto"
            result[bucket][natureza] += c.valor_rs
        return {k: dict(v) for k, v in sorted(result.items())}

    def exposicao_tributaria_semanal(self) -> dict[str, float]:
        """Total de tributos (ISS+COFINS+PIS+CSSL+IR) por semana ISO.

        Responde: "Em que semanas pago mais impostos?"
        """
        result: dict[str, float] = defaultdict(float)
        for c in self.celulas:
            if c.is_tributo():
                result[_temporal_bucket_from_week_iso(c.semana_iso, "semana")] += c.valor_rs
        return dict(sorted(result.items()))

    def exposicao_tributaria_temporal(self, granularidade: TemporalGranularity = "semana") -> dict[str, float]:
        """Total de tributos por janela temporal maior que semana."""

        return self._aggregate_temporal_scalar(granularidade, predicate=lambda c: c.is_tributo())

    def exposicao_tributaria_por_tipo(self) -> dict[str, float]:
        """Total acumulado por tipo de tributo ao longo do projeto.

        Responde: "Quanto pago de ISS vs. COFINS vs. IR no total?"
        """
        result: dict[str, float] = defaultdict(float)
        for c in self.celulas:
            if c.is_tributo():
                result[c.componente_bdi] += c.valor_rs
        return dict(result)

    def resumo_por_natureza(self) -> dict[str, float]:
        """Resumo global por natureza de custo: direto vs. indireto."""

        indireto = round(self.total_overhead + self.total_margem + self.total_tributos, 2)
        return {
            "direto": self.total_custo_direto,
            "indireto": indireto,
        }

    def resumo_por_natureza_temporal(
        self, granularidade: TemporalGranularity = "semana"
    ) -> dict[str, dict[str, float]]:
        """Resumo por natureza de custo em uma granularidade temporal escolhida."""

        return self._aggregate_natureza_temporal(granularidade)

    def margem_por_atividade(self) -> dict[str, float]:
        """Margem líquida (componente L) por atividade.

        Responde: "Qual atividade contribui mais para a margem do projeto?"
        """
        result: dict[str, float] = defaultdict(float)
        for c in self.celulas:
            if c.is_margem():
                result[c.atividade_id] += c.valor_rs
        return dict(sorted(result.items(), key=lambda kv: kv[1], reverse=True))

    def composicao_preco_temporal(self, granularidade: TemporalGranularity = "semana") -> dict[str, dict[str, float]]:
        """Composição do preço de venda por janela temporal: {periodo → {componente → R$}}.

        Permite gráfico de barras empilhadas por semana, mês, bimestre, trimestre,
        semestre ou ano.
        custo_direto | overhead | margem | tributos
        """
        return self._aggregate_temporal(granularidade)

    def composicao_preco_mensal(self) -> dict[str, dict[str, float]]:
        return self.composicao_preco_temporal("mes")

    def composicao_preco_bimestral(self) -> dict[str, dict[str, float]]:
        return self.composicao_preco_temporal("bimestre")

    def composicao_preco_trimestral(self) -> dict[str, dict[str, float]]:
        return self.composicao_preco_temporal("trimestre")

    def composicao_preco_semestral(self) -> dict[str, dict[str, float]]:
        return self.composicao_preco_temporal("semestre")

    def composicao_preco_anual(self) -> dict[str, dict[str, float]]:
        return self.composicao_preco_temporal("ano")

    def composicao_por_categoria(self) -> dict[str, dict[str, float]]:
        """Para cada categoria de custo, a decomposição agregada em R$.

        Responde: "Na mão de obra, quanto vai a tributos vs. margem vs. custo?"
        """
        result: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for c in self.celulas:
            result[c.categoria][c.componente_bdi] += c.valor_rs
        return {k: dict(v) for k, v in result.items()}

    def consumo_diesel_temporal(self, granularidade: TemporalGranularity = "semana") -> dict[str, float]:
        """Volume de diesel consumido por janela temporal em litros."""

        return self._aggregate_temporal_scalar(
            granularidade,
            predicate=lambda c: c.is_diesel() and c.consumo_diesel_L > 0 and c.componente_bdi == "custo_direto",
        )

    def consumo_diesel_semanal(self) -> dict[str, float]:
        """Volume de diesel consumido por semana em litros (L/semana).

        Agrega todas as atividades — útil para planejamento de abastecimento.
        Responde: "Quanto diesel (em litros) preciso na semana 2026-W25?"
        """
        return self.consumo_diesel_temporal("semana")

    def consumo_diesel_por_atividade(self) -> dict[str, float]:
        """Volume total de diesel por atividade ao longo de toda a campanha (litros).

        Responde: "Qual atividade consome mais combustível?"
        """
        result: dict[str, float] = defaultdict(float)
        for c in self.celulas:
            if c.is_diesel() and c.consumo_diesel_L > 0 and c.componente_bdi == "custo_direto":
                result[c.atividade_id] += c.consumo_diesel_L
        return dict(sorted(result.items(), key=lambda kv: kv[1], reverse=True))

    @property
    def total_consumo_diesel_L(self) -> float:
        """Volume total de diesel consumido no projeto (litros)."""
        return round(
            sum(c.consumo_diesel_L for c in self.celulas if c.is_diesel() and c.componente_bdi == "custo_direto"),
            2,
        )

    def custo_direto_por_atividade_semana(self) -> dict[tuple[str, str], float]:
        """{(atividade_id, semana_iso): R$ de custo direto} — base para EVM."""
        result: dict[tuple[str, str], float] = defaultdict(float)
        for c in self.celulas:
            if c.is_custo_direto():
                result[(c.atividade_id, c.semana_iso)] += c.valor_rs
        return dict(result)

    # ── Slice e group_by genéricos ─────────────────────────────────────────

    def slice(
        self,
        categoria: str | None = None,
        atividade_id: str | None = None,
        semana_iso: str | None = None,
        componente_bdi: str | None = None,
    ) -> CuboAnalitico:
        """Filtra o cubo mantendo apenas células que satisfazem os critérios."""

        def match(c: CelulaAnalitica) -> bool:
            return (
                (categoria is None or c.categoria == categoria)
                and (atividade_id is None or c.atividade_id == atividade_id)
                and (semana_iso is None or c.semana_iso == semana_iso)
                and (componente_bdi is None or c.componente_bdi == componente_bdi)
            )

        filtered = tuple(c for c in self.celulas if match(c))
        return CuboAnalitico(
            projeto_id=self.projeto_id,
            gerado_em=self.gerado_em,
            regime_bdi=self.regime_bdi,
            total_preco_venda=round(sum(c.valor_rs for c in filtered), 2),
            celulas=filtered,
        )

    def group_by(self, *dims: str) -> dict[tuple, float]:
        """Agrega valor_rs por combinação de dimensões.

        Dimensões válidas: "categoria", "atividade_id", "semana_iso", "componente_bdi"

        Exemplo:
            cubo.group_by("semana_iso", "componente_bdi")
            → {("2026-W23", "tributo_iss"): 1234.56, ...}
        """
        result: dict[tuple, float] = defaultdict(float)
        for c in self.celulas:
            key = tuple(getattr(c, d) for d in dims)
            result[key] += c.valor_rs
        return dict(result)

    # ── Sumários ───────────────────────────────────────────────────────────

    @property
    def total_tributos(self) -> float:
        return round(sum(c.valor_rs for c in self.celulas if c.is_tributo()), 2)

    @property
    def total_overhead(self) -> float:
        return round(sum(c.valor_rs for c in self.celulas if c.is_overhead()), 2)

    @property
    def total_margem(self) -> float:
        return round(sum(c.valor_rs for c in self.celulas if c.is_margem()), 2)

    @property
    def total_custo_direto(self) -> float:
        return round(sum(c.valor_rs for c in self.celulas if c.is_custo_direto()), 2)

    @property
    def pct_tributos(self) -> float:
        return round(self.total_tributos / self.total_preco_venda, 6) if self.total_preco_venda > 0 else 0.0

    @property
    def pct_margem(self) -> float:
        return round(self.total_margem / self.total_preco_venda, 6) if self.total_preco_venda > 0 else 0.0

    def to_dict(self) -> dict:
        """Serialização compacta — projeta sumários e top aggregations."""
        return {
            "projeto_id": self.projeto_id,
            "gerado_em": self.gerado_em,
            "regime_bdi": self.regime_bdi,
            "total_preco_venda": self.total_preco_venda,
            "total_custo_direto": self.total_custo_direto,
            "total_overhead": self.total_overhead,
            "total_margem": self.total_margem,
            "total_tributos": self.total_tributos,
            "pct_margem": self.pct_margem,
            "pct_tributos": self.pct_tributos,
            "n_celulas": len(self.celulas),
            "resumo_por_natureza": self.resumo_por_natureza(),
            "resumo_por_natureza_temporal": {
                "semana": self.resumo_por_natureza_temporal("semana"),
                "mes": self.resumo_por_natureza_temporal("mes"),
                "bimestre": self.resumo_por_natureza_temporal("bimestre"),
                "trimestre": self.resumo_por_natureza_temporal("trimestre"),
                "semestre": self.resumo_por_natureza_temporal("semestre"),
                "ano": self.resumo_por_natureza_temporal("ano"),
            },
            "exposicao_tributaria_por_tipo": self.exposicao_tributaria_por_tipo(),
            "margem_por_atividade": self.margem_por_atividade(),
            "total_consumo_diesel_L": self.total_consumo_diesel_L,
            "consumo_diesel_por_atividade": self.consumo_diesel_por_atividade(),
        }
