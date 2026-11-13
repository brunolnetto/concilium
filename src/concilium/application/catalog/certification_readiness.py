"""Catalog certification readiness: what each CPU still lacks for a P23 GO.

For every CPU of a resolved catalog this reports the catalog-side evidence the
certificate needs, using the *same* predicates as the pipeline:

* V5 / productivity provenance — ``production_calibration_gaps`` (the rule the
  P23 witness builder applies);
* P18 exact consumption — ``build_activity_goods_from_catalog`` run on a
  one-activity project (the real builder, so the verdict cannot drift);
* V2 basis — ``derive_catalog_cost_envelope`` on the same project.

It never edits the catalog: calibration samples, confidence, source ids and
per-unit consumption must come from field data or reference tables. The
report is the data request.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from concilium.application.scheduling.catalog_cost_envelope import derive_catalog_cost_envelope
from concilium.application.scheduling.formalism_certification_service import production_calibration_gaps
from concilium.application.scheduling.skill04_consumption_preview import build_activity_goods_from_catalog
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    Cronograma,
    DistribuicaoSemanal,
    EapItem,
    Meta,
    Projeto,
    RegimeTrabalho,
    ScheduledActivityCanonical,
)

_AGIS_PLACEHOLDER = "MA-AGIS-CPU-"


def _rows(value: object) -> list[Mapping[str, object]]:
    """Mapping rows of a catalog list field; anything else is treated as empty."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [row for row in value if isinstance(row, Mapping)]
_CONSUMABLE_ROWS = frozenset({"MATERIAL", "DIESEL", "COMBUSTIVEL"})


@dataclass(frozen=True)
class CpuReadiness:
    codigo: str
    producao_id: str | None
    v5_gaps: tuple[str, ...]
    p18_situacao: str
    p18_erro: str | None
    ccat_erro: str | None
    acoes: tuple[str, ...] = field(default=())

    @property
    def pronta(self) -> bool:
        return not self.v5_gaps and self.p18_erro is None and self.ccat_erro is None


def _one_activity_project(cpu: Mapping[str, object]) -> CanonicalModel:
    unit = str(cpu.get("unidade") or "un")
    activity = ScheduledActivityCanonical(
        activity_id="A",
        start_week=0,
        end_week=0,
        duration_weeks=1,
        distribuicao_semanal={
            "2026-W02": DistribuicaoSemanal(num_equipes=1, qtd_executada=1.0, qtd_acumulada=1.0, pct=1.0)
        },
    )
    return CanonicalModel(
        meta=Meta(gerado_em=datetime(2026, 1, 1, tzinfo=UTC), contexto_id="certification-readiness"),
        projeto=Projeto(
            id="certification-readiness",
            nome="certification readiness",
            tipo_obra="terraplenagem",
            localizacao="audit",
            coordenadas=Coordenadas(lat=0, lng=0),
            regime_trabalho=RegimeTrabalho(dias_semana=6, horas_dia=8),
            data_inicio=date(2026, 1, 5),
            data_termino=date(2026, 1, 11),
            snapshot_catalogo_id="audit",
            snapshot_perfil_id="audit",
        ),
        eap=[EapItem(item_id="A", cpu_id=str(cpu["codigo"]), unidade=unit, quantitativo=1.0)],
        cronograma=Cronograma(scheduled_activities=[activity], is_feasible=True),
    )


def _p18_situacao(cpu: Mapping[str, object], production: Mapping[str, object] | None) -> str:
    rows = _rows(cpu.get("composicao_itens"))
    consumables = [r for r in rows if r.get("categoria_custo") in _CONSUMABLE_ROWS]
    if any(str(r.get("insumo_id", "")).startswith(_AGIS_PLACEHOLDER) for r in consumables):
        return "PLACEHOLDER_AGIS"
    if consumables:
        return "BOM_POR_UNIDADE"
    if cpu.get("consumiveis_declarados"):
        return "DECLARADO_NENHUM"
    team = production.get("composicao_padrao_equipe") if isinstance(production, Mapping) else None
    if isinstance(team, Mapping) and (
        any(e.get("consumo_litros_hora") for e in _rows(team.get("equipamentos")))
        or team.get("materiais")
    ):
        return "CONSUMO_SO_HORARIO"
    return "SEM_BOM"


_ACOES_P18 = {
    "PLACEHOLDER_AGIS": "remodelar o lote MA-AGIS-CPU-* em materiais físicos com coeficiente por unidade (ADR-138 §D7)",
    "CONSUMO_SO_HORARIO": (
        "informar coeficientes por unidade entregue com fonte (ex.: composição SICRO) — L/h não é convertido "
        "sem horas observadas"
    ),
    "SEM_BOM": (
        "informar BOM por unidade entregue, ou declarar consumiveis_declarados=NENHUM com justificativa e fonte"
    ),
}


def audit_catalog(catalog: Mapping[str, object]) -> list[CpuReadiness]:
    cpus = _rows(catalog.get("cpus"))
    productions = {str(p["id"]): p for p in _rows(catalog.get("producoes")) if isinstance(p.get("id"), str)}
    result: list[CpuReadiness] = []
    for cpu in sorted(cpus, key=lambda c: str(c.get("codigo"))):
        production_id = cpu.get("producao_id_ref")
        production = productions.get(str(production_id or ""))
        v5 = tuple(production_calibration_gaps(production))
        canonical = _one_activity_project(cpu)
        p18_error = ccat_error = None
        try:
            build_activity_goods_from_catalog(canonical, catalog)
        except ValueError as exc:
            p18_error = str(exc).removeprefix("A: ").removeprefix("A/")
        try:
            derive_catalog_cost_envelope(canonical, catalog)
        except ValueError as exc:
            ccat_error = str(exc).removeprefix("A: ").removeprefix("A/")
        situacao = _p18_situacao(cpu, production)
        acoes: list[str] = []
        if v5:
            acoes.append("produtividade: " + "; ".join(v5))
        if p18_error is not None:
            acoes.append("consumo (P18): " + _ACOES_P18.get(situacao, p18_error))
        if ccat_error is not None:
            acoes.append("C^cat: " + ccat_error)
        result.append(
            CpuReadiness(
                codigo=str(cpu.get("codigo")),
                producao_id=str(production_id) if production_id else None,
                v5_gaps=v5,
                p18_situacao=situacao,
                p18_erro=p18_error,
                ccat_erro=ccat_error,
                acoes=tuple(acoes),
            )
        )
    return result


def render_markdown(catalog_id: str, rows: Sequence[CpuReadiness]) -> str:
    total = len(rows)
    ready = [r for r in rows if r.pronta]
    v5_ok = sum(1 for r in rows if not r.v5_gaps)
    p18_ok = sum(1 for r in rows if r.p18_erro is None)
    ccat_ok = sum(1 for r in rows if r.ccat_erro is None)
    gap_counts = Counter(g.split(" (")[0].split("=")[0] for r in rows for g in r.v5_gaps)
    p18_counts = Counter(r.p18_situacao for r in rows if r.p18_erro is not None)
    lines = [
        f"# Prontidão de certificação do catálogo `{catalog_id}`",
        "",
        "Gerado por `scripts/catalog/audit_certification_readiness.py` com os mesmos predicados do pipeline "
        "(P23 V5, P18, C^cat). Nada é preenchido automaticamente: este relatório é a solicitação de dados.",
        "",
        "| Critério | CPUs aptas | de |",
        "|---|---|---|",
        f"| V5 — produtividade calibrada | {v5_ok} | {total} |",
        f"| P18 — consumo físico exato | {p18_ok} | {total} |",
        f"| V2 — C^cat derivável | {ccat_ok} | {total} |",
        f"| **Todas** | **{len(ready)}** | {total} |",
        "",
        "## Lacunas de produtividade (V5)",
        "",
        "| Lacuna | CPUs |",
        "|---|---|",
        *[f"| {gap} | {n} |" for gap, n in gap_counts.most_common()],
        "",
        "## Lacunas de consumo (P18)",
        "",
        "| Situação | CPUs | Ação |",
        "|---|---|---|",
        *[f"| {s} | {n} | {_ACOES_P18.get(s, '-')} |" for s, n in p18_counts.most_common()],
        "",
        "## Por CPU",
        "",
        "| CPU | Produção | Pronta | Ações |",
        "|---|---|---|---|",
        *[
            f"| {r.codigo} | {r.producao_id or '-'} | {'sim' if r.pronta else 'não'} | "
            f"{'<br>'.join(a.replace('|', '/') for a in r.acoes) or '-'} |"
            for r in rows
        ],
        "",
    ]
    return "\n".join(lines)
