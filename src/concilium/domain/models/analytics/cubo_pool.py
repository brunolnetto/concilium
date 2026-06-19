"""Cubo de Pool Instancial — ADR-086.

Lente exploratória honesta sobre a decomposição composicional-temporal do pool de
recursos (ADR-071→085). Irmão do ``CuboAnalitico`` (ADR-069), com eixos próprios e
**separação rígida entre verdade física e imputação causal**:

- **Física** (este cubo, grão ``CelulaPoolInstancial``): o que cada slot do pool *fez* em
  cada semana — estado prod/idle/off, atividade servida, custo por componente.
- **Causal** (``CustoParticionadoItem``, ADR-083/084): a quem o custo é *imputado*.

O cubo é uma **projeção derivada** — não recomputa a economia idle/off (lê os segmentos já
decididos pelo ADR-085), e a soma dos custos das células reconcilia com ``custo_total_contrato``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

EstadoSlot = Literal["prod", "idle", "off"]

_COMPONENTES = ("mo", "eq", "comb", "mat")


def bucket_periodo(semana_iso: str, granularidade: str) -> str:
    """Bucket temporal de uma chave de semana. Suporta ISO (``2026-W23``) e seq (``S001``).

    Granularidades: ``semana`` (chave crua) · ``mes`` · ``trimestre`` · ``ano``.
    Para chaves sequenciais (Snnn), aproxima mês/trimestre/ano por blocos de 4,33/13/52 semanas.
    """
    s = str(semana_iso).strip()
    if granularidade == "semana" or not s:
        return s
    # ISO: 2026-Www
    if "-W" in s:
        try:
            from datetime import date

            year_str, week_str = s.split("-W")
            anchor = date.fromisocalendar(int(year_str), int(week_str), 1)
            if granularidade == "mes":
                return f"{anchor.year}-{anchor.month:02d}"
            if granularidade == "trimestre":
                return f"{anchor.year}-T{(anchor.month - 1) // 3 + 1}"
            if granularidade == "ano":
                return f"{anchor.year}"
        except Exception:
            return s
        return s
    # Sequencial Snnn
    if s.startswith("S") and s[1:].isdigit():
        n = int(s[1:])
        if granularidade == "mes":
            return f"M{(n - 1) // 4 + 1:02d}"
        if granularidade == "trimestre":
            return f"T{(n - 1) // 13 + 1}"
        if granularidade == "ano":
            return f"A{(n - 1) // 52 + 1}"
    return s


@dataclass(frozen=True)
class CelulaPoolInstancial:
    """Grão atômico físico: o que um slot do pool fez numa semana (ADR-086 D1)."""

    contrato_id: str
    tipo_id: str
    instancia_numero: int
    semana_iso: str
    estado: EstadoSlot
    atividade_id: str | None  # apenas quando estado == "prod"
    custo_mo: float = 0.0
    custo_eq: float = 0.0
    custo_comb: float = 0.0
    custo_mat: float = 0.0

    @property
    def custo_total(self) -> float:
        return round(self.custo_mo + self.custo_eq + self.custo_comb + self.custo_mat, 2)

    @property
    def instancia_id(self) -> str:
        return f"{self.tipo_id}-{self.instancia_numero:02d}"


@dataclass(frozen=True)
class CuboPoolInstancial:
    """Container do cubo de pool — células físicas + proveniência causal/estrutural (ADR-086 D2)."""

    projeto_id: str
    gerado_em: str
    celulas: tuple[CelulaPoolInstancial, ...] = field(default_factory=tuple)

    # ── Query primitives ──────────────────────────────────────────────────────
    def slice(
        self,
        *,
        contrato_id: str | None = None,
        tipo_id: str | None = None,
        instancia_numero: int | None = None,
        atividade_id: str | None = None,
        estado: EstadoSlot | None = None,
        semana_iso: str | None = None,
    ) -> CuboPoolInstancial:
        """Filtra células por qualquer combinação de dimensões."""

        def keep(c: CelulaPoolInstancial) -> bool:
            return (
                (contrato_id is None or c.contrato_id == contrato_id)
                and (tipo_id is None or c.tipo_id == tipo_id)
                and (instancia_numero is None or c.instancia_numero == instancia_numero)
                and (atividade_id is None or c.atividade_id == atividade_id)
                and (estado is None or c.estado == estado)
                and (semana_iso is None or c.semana_iso == semana_iso)
            )

        return CuboPoolInstancial(
            projeto_id=self.projeto_id,
            gerado_em=self.gerado_em,
            celulas=tuple(c for c in self.celulas if keep(c)),
        )

    def group_by(self, *dims: str, measure: str = "custo_total") -> dict[tuple, float]:
        """Agrega ``measure`` por dimensões. measure ∈ custo_total|custo_{mo,eq,comb,mat}|semanas."""
        out: dict[tuple, float] = {}
        for c in self.celulas:
            key = tuple(getattr(c, d, "") for d in dims)
            out[key] = out.get(key, 0.0) + _measure_value(c, measure)
        return {k: round(v, 2) for k, v in out.items()}

    # ── Totais e invariantes (ADR-086 H1/H3) ─────────────────────────────────
    @property
    def custo_total(self) -> float:
        return round(sum(c.custo_total for c in self.celulas), 2)

    def custo_por_estado(self) -> dict[str, float]:
        out = {"prod": 0.0, "idle": 0.0, "off": 0.0}
        for c in self.celulas:
            out[c.estado] += c.custo_total
        return {k: round(v, 2) for k, v in out.items()}

    def custo_por_componente(self) -> dict[str, float]:
        out = {"mo": 0.0, "eq": 0.0, "comb": 0.0, "mat": 0.0}
        for c in self.celulas:
            out["mo"] += c.custo_mo
            out["eq"] += c.custo_eq
            out["comb"] += c.custo_comb
            out["mat"] += c.custo_mat
        return {k: round(v, 2) for k, v in out.items()}

    def semanas_por_estado(self) -> dict[str, int]:
        out = {"prod": 0, "idle": 0, "off": 0}
        for c in self.celulas:
            out[c.estado] += 1
        return out

    # ── Projeções físicas (ADR-086 D4) ────────────────────────────────────────
    def utilizacao_temporal(self, granularidade: str = "mes") -> dict[tuple[str, str], int]:
        """{(periodo, estado): n_slot_semanas} — distribuição de estados no tempo."""
        out: dict[tuple[str, str], int] = {}
        for c in self.celulas:
            k = (bucket_periodo(c.semana_iso, granularidade), c.estado)
            out[k] = out.get(k, 0) + 1
        return out

    def custo_estado_componente(self) -> dict[tuple[str, str], float]:
        """{(estado, componente): valor_rs} — onde cada R$ é consumido, honestamente."""
        out: dict[tuple[str, str], float] = {}
        for c in self.celulas:
            for comp in _COMPONENTES:
                v = getattr(c, f"custo_{comp}")
                if v:
                    k = (c.estado, comp)
                    out[k] = out.get(k, 0.0) + v
        return {k: round(v, 2) for k, v in out.items()}

    def ciclo_vida_instancias(self) -> dict[str, dict[str, float]]:
        """{instancia_id: {prod_w, idle_w, off_w, custo_mo/eq/comb/mat, custo_total, mob, demob}}."""
        out: dict[str, dict] = {}
        for c in self.celulas:
            iid = c.instancia_id
            d = out.setdefault(
                iid,
                {
                    "tipo_id": c.tipo_id,
                    "contrato_id": c.contrato_id,
                    "prod_w": 0,
                    "idle_w": 0,
                    "off_w": 0,
                    "custo_mo": 0.0,
                    "custo_eq": 0.0,
                    "custo_comb": 0.0,
                    "custo_mat": 0.0,
                    "semana_mob": None,
                    "semana_demob": None,
                },
            )
            d[f"{c.estado}_w"] += 1
            d["custo_mo"] += c.custo_mo
            d["custo_eq"] += c.custo_eq
            d["custo_comb"] += c.custo_comb
            d["custo_mat"] += c.custo_mat
            if c.estado in ("prod", "idle"):
                if d["semana_mob"] is None or c.semana_iso < d["semana_mob"]:
                    d["semana_mob"] = c.semana_iso
                if d["semana_demob"] is None or c.semana_iso > d["semana_demob"]:
                    d["semana_demob"] = c.semana_iso
        for d in out.values():
            d["custo_total"] = round(d["custo_mo"] + d["custo_eq"] + d["custo_comb"] + d["custo_mat"], 2)
            for comp in _COMPONENTES:
                d[f"custo_{comp}"] = round(d[f"custo_{comp}"], 2)
        return out

    def atividade_instancia(self) -> dict[tuple[str, str], dict]:
        """{(atividade_id, instancia_id): {semana_inicio, semana_fim, machine_weeks, custo}}.

        Apenas semanas produtivas (física: quais slots serviram cada atividade e quando).
        """
        out: dict[tuple[str, str], dict] = {}
        for c in self.celulas:
            if c.estado != "prod" or not c.atividade_id:
                continue
            k = (c.atividade_id, c.instancia_id)
            d = out.setdefault(
                k, {"semana_inicio": c.semana_iso, "semana_fim": c.semana_iso, "machine_weeks": 0, "custo": 0.0}
            )
            d["semana_inicio"] = min(d["semana_inicio"], c.semana_iso)
            d["semana_fim"] = max(d["semana_fim"], c.semana_iso)
            d["machine_weeks"] += 1
            d["custo"] += c.custo_total
        for d in out.values():
            d["custo"] = round(d["custo"], 2)
        return out


def _measure_value(c: CelulaPoolInstancial, measure: str) -> float:
    if measure == "custo_total":
        return c.custo_total
    if measure == "semanas":
        return 1.0
    if measure in ("custo_mo", "custo_eq", "custo_comb", "custo_mat"):
        return getattr(c, measure)
    return c.custo_total


# ---------------------------------------------------------------------------
# ADR-106 F8 — CuboPoolFace: face de ocupação de recursos do pool
# ---------------------------------------------------------------------------

EstadoOcupacao = Literal["mobilizando", "ativo", "idle", "desmobilizando", "off"]


@dataclass(frozen=True)
class CelulaOcupacaoPool:
    """Grão da face de ocupação do pool (ADR-106 F8).

    Dimensões: item_id × semana × tipo_recurso.
    Medidas: horas_ativas, horas_idle, custo_ativo, custo_idle, estado.
    """

    item_id: str  # atividade ou contrato que gera a demanda
    semana: str  # semana ISO ou sequencial (S001, S002, ...)
    tipo_recurso: str  # tipo_id do recurso (ex: EQUIP-ESCAV-22T, FUNC-OPER)
    horas_ativas: float = 0.0
    horas_idle: float = 0.0
    custo_ativo: float = 0.0
    custo_idle: float = 0.0
    estado: EstadoOcupacao = "ativo"

    @property
    def utilizacao(self) -> float:
        """Fração de horas ativas em relação ao total disponível. Range [0, 1]."""
        total = self.horas_ativas + self.horas_idle
        return round(self.horas_ativas / total, 4) if total > 0 else 0.0

    @property
    def custo_total(self) -> float:
        return round(self.custo_ativo + self.custo_idle, 2)


@dataclass(frozen=True)
class CuboPoolFace:
    """Face de ocupação do pool por semana e tipo de recurso (ADR-106 F8).

    Dimensões: item_id × semana × tipo_recurso.
    Medidas: horas_ativas, horas_idle, custo_ativo, custo_idle, estado.

    É uma face complementar ao ``CuboPoolInstancial`` (ADR-086): enquanto
    o cubo instancial rastreia o estado físico de cada slot individualmente,
    esta face agrega por tipo de recurso e atividade — mais adequada para
    relatórios de ocupação e análise de gargalos.
    """

    projeto_id: str
    gerado_em: str
    celulas: tuple[CelulaOcupacaoPool, ...] = field(default_factory=tuple)

    def por_semana(self) -> dict[str, list[CelulaOcupacaoPool]]:
        """Agrupa células por semana."""
        out: dict[str, list[CelulaOcupacaoPool]] = {}
        for c in self.celulas:
            out.setdefault(c.semana, []).append(c)
        return out

    def por_tipo_recurso(self) -> dict[str, list[CelulaOcupacaoPool]]:
        """Agrupa células por tipo_recurso."""
        out: dict[str, list[CelulaOcupacaoPool]] = {}
        for c in self.celulas:
            out.setdefault(c.tipo_recurso, []).append(c)
        return out

    def custo_total_ativo(self) -> float:
        return round(sum(c.custo_ativo for c in self.celulas), 2)

    def custo_total_idle(self) -> float:
        return round(sum(c.custo_idle for c in self.celulas), 2)

    def semanas(self) -> list[str]:
        """Lista ordenada de semanas presentes."""
        return sorted({c.semana for c in self.celulas})

    def tipos_recurso(self) -> list[str]:
        """Lista ordenada de tipos de recurso presentes."""
        return sorted({c.tipo_recurso for c in self.celulas})


# ---------------------------------------------------------------------------
# ADR-107 D5 — Dimensão tipo_combustivel no cubo analítico
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CelulaCombustivel:
    """Célula de breakdown de combustível por tipo (ADR-107 D5).

    Permite drill-down por tipo_combustivel no cubo analítico.
    Dimensões: item_id × semana × tipo_combustivel.
    """

    item_id: str  # atividade EAP ou equipe
    semana: str
    tipo_combustivel: str  # TipoCombustivel value (ex: "diesel_s10", "eletrico", "cng")
    custo: float = 0.0
    volume_litros: float = 0.0  # volume consumido (L, kWh, kg — unidade por tipo)


@dataclass(frozen=True)
class CuboCombustivelFace:
    """Face de combustível do cubo analítico (ADR-107 D5).

    Permite consultas como:
      - Qual o custo por tipo de combustível neste projeto?
      - Como mudaria a margem se o diesel subisse 15%?
    """

    projeto_id: str
    gerado_em: str
    celulas: tuple[CelulaCombustivel, ...] = field(default_factory=tuple)

    def custo_por_tipo(self) -> dict[str, float]:
        """Agrega custo total por tipo de combustível."""
        out: dict[str, float] = {}
        for c in self.celulas:
            out[c.tipo_combustivel] = out.get(c.tipo_combustivel, 0.0) + c.custo
        return {k: round(v, 2) for k, v in out.items()}

    def tipos_presentes(self) -> list[str]:
        """Lista de tipos de combustível presentes no projeto."""
        return sorted({c.tipo_combustivel for c in self.celulas})
