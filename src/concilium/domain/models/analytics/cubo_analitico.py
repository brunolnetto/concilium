"""CuboAnalitico — cubo analítico do espaço ontológico de planejamento (ADR-087).

Hierarquia dimensional: {natureza}.{atividade}.{categoria_insumo}.{propriedade}
  - natureza:        direto | indireto
  - atividade:       EapItem.item_id
  - categoria_insumo: mao_obra | equipamento | material | verba
  - propriedade:     salario_encargos | aluguel | combustivel | manutencao | consumivel | fixo

Diesel é `equipamento.combustivel` (ADR-087/088/089):
  - valor_rs: custo monetário (R$), BDI_diesel = 4% (fornecimento de mercadoria)
  - valor_fisico: volume em litros (L), unidade_fisica = "L"

Backward compatibility:
  - CelulaAnalitica.categoria: property que retorna "diesel" para
    (equipamento.combustivel), e a categoria_insumo para as demais.
  - CelulaAnalitica.consumo_diesel_L: property que retorna valor_fisico
    para células (equipamento.combustivel), 0.0 para outras.

Invariante por (categoria_insumo, propriedade, atividade, semana):
    sum(célula.valor_rs for comp in COMPONENTES_BDI) ≈ PV_semana

Onde PV_semana = custo_prop_semanal × (1 + BDI_(categoria_insumo, propriedade))
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

# Propriedades válidas por categoria_insumo (ADR-087 §1.2)
PROPRIEDADES_POR_CATEGORIA: dict[str, tuple[str, ...]] = {
    "mao_obra": ("salario_encargos",),
    "equipamento": ("aluguel", "combustivel", "manutencao"),
    "material": ("consumivel",),
    "verba": ("fixo",),
}


def _temporal_bucket_from_week_iso(week_iso: str, granularidade: TemporalGranularity) -> str:
    """Mapeia uma semana ISO para uma janela temporal maior."""
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
    """Elemento atômico do cubo — ADR-087 hierarquia dimensional.

    Campos principais (nova hierarquia):
        natureza:        "direto" | "indireto"
        atividade_id:    EapItem.item_id
        categoria_insumo:"mao_obra" | "equipamento" | "material" | "verba"
        propriedade:     sub-dimensão da categoria (ver PROPRIEDADES_POR_CATEGORIA)
        semana_iso:      "2026-W23"
        componente_bdi:  ver COMPONENTES_BDI
        valor_rs:        R$ desta célula no preço de venda
        valor_fisico:    grandeza física (L para combustivel, 0 para outros)
        unidade_fisica:  "L" | "h" | "" (vazio para células puramente monetárias)

    Backward compatibility (properties derivadas):
        categoria:       mapeia para "diesel"|"mao_obra"|"equipamento"|"material"
        consumo_diesel_L:retorna valor_fisico quando propriedade="combustivel"
    """

    # ── ADR-087: hierarquia dimensional ──────────────────────────────────────
    natureza: Literal["direto", "indireto"]
    atividade_id: str
    categoria_insumo: Literal["mao_obra", "equipamento", "material", "verba"]
    propriedade: str  # aluguel | combustivel | manutencao | salario_encargos | consumivel | fixo
    semana_iso: str  # "2026-W23"
    componente_bdi: str  # ver COMPONENTES_BDI
    valor_rs: float
    valor_fisico: float = 0.0  # grandeza física (L para combustivel, etc.)
    unidade_fisica: str = ""  # "L" | "h" | ""

    # ── Backward compatibility properties ────────────────────────────────────

    @property
    def categoria(self) -> str:
        """Mapeia para o modelo legado de 4 categorias (ADR-069 / ADR-090).

        ADR-090: diesel é material.combustivel (não mais equipamento.combustivel).
        material.combustivel → "diesel"  (backward compat)
        material.consumivel  → "material"
        equipamento.*        → "equipamento"
        mao_obra.*           → "mao_obra"
        verba.*              → "material"
        """
        if self.categoria_insumo == "material" and self.propriedade == "combustivel":
            return "diesel"
        if self.categoria_insumo == "verba":
            return "material"
        return self.categoria_insumo

    @property
    def consumo_diesel_L(self) -> float:
        """Volume de combustível em litros (backward compat com ADR-069)."""
        if self.categoria_insumo == "material" and self.propriedade == "combustivel" and self.unidade_fisica == "L":
            return self.valor_fisico
        return 0.0

    # ── Predicados semânticos ────────────────────────────────────────────────

    def is_tributo(self) -> bool:
        return self.componente_bdi in TRIBUTOS_BDI

    def is_overhead(self) -> bool:
        return self.componente_bdi in OVERHEAD_BDI

    def is_margem(self) -> bool:
        return self.componente_bdi == "margem_l"

    def is_custo_direto(self) -> bool:
        return self.componente_bdi == "custo_direto"

    def is_diesel(self) -> bool:
        """True se esta célula representa combustível — ADR-090: material.combustivel."""
        return self.categoria_insumo == "material" and self.propriedade == "combustivel"

    def is_equipamento(self) -> bool:
        """True para qualquer sub-propriedade de equipamento (incluindo combustivel)."""
        return self.categoria_insumo == "equipamento"

    def is_mao_obra(self) -> bool:
        return self.categoria_insumo == "mao_obra"


@dataclass(frozen=True)
class CuboAnalitico:
    """Cubo analítico — ADR-087 hierarquia dimensional.

    Gerado deterministicamente por CuboAnaliticoBuilder.build() a partir do canonical.
    Imutável após construção. Suporta projeções via slice() e group_by().
    """

    projeto_id: str
    gerado_em: str
    regime_bdi: str  # "pre_reforma" | "transicao" | "pleno_cbs_ibs"
    total_preco_venda: float
    celulas: tuple[CelulaAnalitica, ...]

    # ── Projeções fundamentais ─────────────────────────────────────────────

    def _aggregate_temporal(self, granularidade: TemporalGranularity, predicate=None) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for c in self.celulas:
            if predicate is not None and not predicate(c):
                continue
            bucket = _temporal_bucket_from_week_iso(c.semana_iso, granularidade)
            result[bucket][c.componente_bdi] += c.valor_rs
        return {k: dict(v) for k, v in sorted(result.items())}

    def _aggregate_temporal_scalar(self, granularidade: TemporalGranularity, predicate=None) -> dict[str, float]:
        result: dict[str, float] = defaultdict(float)
        for c in self.celulas:
            if predicate is not None and not predicate(c):
                continue
            bucket = _temporal_bucket_from_week_iso(c.semana_iso, granularidade)
            result[bucket] += c.valor_rs
        return dict(sorted(result.items()))

    def _aggregate_natureza_temporal(self, granularidade: TemporalGranularity) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for c in self.celulas:
            bucket = _temporal_bucket_from_week_iso(c.semana_iso, granularidade)
            # Usa c.natureza (campo canônico) em vez de is_custo_direto() para classificar
            # corretamente células de indireto adicionadas pelo enriquecimento financeiro.
            natureza = c.natureza  # "direto" | "indireto"
            result[bucket][natureza] += c.valor_rs
        return {k: dict(v) for k, v in sorted(result.items())}

    def exposicao_tributaria_semanal(self) -> dict[str, float]:
        result: dict[str, float] = defaultdict(float)
        for c in self.celulas:
            if c.is_tributo():
                result[_temporal_bucket_from_week_iso(c.semana_iso, "semana")] += c.valor_rs
        return dict(sorted(result.items()))

    def exposicao_tributaria_temporal(self, granularidade: TemporalGranularity = "semana") -> dict[str, float]:
        return self._aggregate_temporal_scalar(granularidade, predicate=lambda c: c.is_tributo())

    def exposicao_tributaria_por_tipo(self) -> dict[str, float]:
        result: dict[str, float] = defaultdict(float)
        for c in self.celulas:
            if c.is_tributo():
                result[c.componente_bdi] += c.valor_rs
        return dict(result)

    def resumo_por_natureza(self) -> dict[str, float]:
        indireto = round(self.total_overhead + self.total_margem + self.total_tributos, 2)
        return {"direto": self.total_custo_direto, "indireto": indireto}

    def resumo_por_natureza_temporal(
        self, granularidade: TemporalGranularity = "semana"
    ) -> dict[str, dict[str, float]]:
        return self._aggregate_natureza_temporal(granularidade)

    def margem_por_atividade(self) -> dict[str, float]:
        result: dict[str, float] = defaultdict(float)
        for c in self.celulas:
            if c.is_margem():
                result[c.atividade_id] += c.valor_rs
        return dict(sorted(result.items(), key=lambda kv: kv[1], reverse=True))

    def composicao_preco_temporal(self, granularidade: TemporalGranularity = "semana") -> dict[str, dict[str, float]]:
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
        """Backward compat — usa c.categoria (property ADR-087)."""
        result: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for c in self.celulas:
            result[c.categoria][c.componente_bdi] += c.valor_rs
        return {k: dict(v) for k, v in result.items()}

    def composicao_por_hierarquia(self) -> dict[tuple[str, str], dict[str, float]]:
        """ADR-087: decomposição por (categoria_insumo, propriedade) × componente_bdi."""
        result: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for c in self.celulas:
            result[(c.categoria_insumo, c.propriedade)][c.componente_bdi] += c.valor_rs
        return {k: dict(v) for k, v in sorted(result.items())}

    def consumo_diesel_temporal(self, granularidade: TemporalGranularity = "semana") -> dict[str, float]:
        result: dict[str, float] = defaultdict(float)
        for c in self.celulas:
            if c.is_diesel() and c.consumo_diesel_L > 0 and c.componente_bdi == "custo_direto":
                bucket = _temporal_bucket_from_week_iso(c.semana_iso, granularidade)
                result[bucket] += c.consumo_diesel_L
        return dict(sorted(result.items()))

    def consumo_diesel_semanal(self) -> dict[str, float]:
        return self.consumo_diesel_temporal("semana")

    def consumo_diesel_por_atividade(self) -> dict[str, float]:
        result: dict[str, float] = defaultdict(float)
        for c in self.celulas:
            if c.is_diesel() and c.consumo_diesel_L > 0 and c.componente_bdi == "custo_direto":
                result[c.atividade_id] += c.consumo_diesel_L
        return dict(sorted(result.items(), key=lambda kv: kv[1], reverse=True))

    @property
    def total_consumo_diesel_L(self) -> float:
        return round(
            sum(c.consumo_diesel_L for c in self.celulas if c.is_diesel() and c.componente_bdi == "custo_direto"),
            2,
        )

    def custo_direto_por_atividade_semana(self) -> dict[tuple[str, str], float]:
        result: dict[tuple[str, str], float] = defaultdict(float)
        for c in self.celulas:
            if c.is_custo_direto():
                result[(c.atividade_id, c.semana_iso)] += c.valor_rs
        return dict(result)

    # ── Slice e group_by ──────────────────────────────────────────────────────

    def slice(
        self,
        categoria: str | None = None,
        atividade_id: str | None = None,
        semana_iso: str | None = None,
        componente_bdi: str | None = None,
        # ADR-087: novos filtros hierárquicos
        natureza: str | None = None,
        categoria_insumo: str | None = None,
        propriedade: str | None = None,
    ) -> CuboAnalitico:
        def match(c: CelulaAnalitica) -> bool:
            return (
                (categoria is None or c.categoria == categoria)  # backward compat
                and (atividade_id is None or c.atividade_id == atividade_id)
                and (semana_iso is None or c.semana_iso == semana_iso)
                and (componente_bdi is None or c.componente_bdi == componente_bdi)
                and (natureza is None or c.natureza == natureza)  # ADR-087
                and (categoria_insumo is None or c.categoria_insumo == categoria_insumo)
                and (propriedade is None or c.propriedade == propriedade)
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
        """Agrega valor_rs por dimensões.

        Dimensões válidas (histórico + ADR-087):
            "categoria", "atividade_id", "semana_iso", "componente_bdi",
            "natureza", "categoria_insumo", "propriedade"
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
