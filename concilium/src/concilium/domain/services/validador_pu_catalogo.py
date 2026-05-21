"""ADR-051: Validador de PU em Catálogo (Camada 1 — Estático).

Valida preço unitário teórico vs catalogado para uma CPU isolada,
sem contexto de projeto.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from concilium.domain.constants import FAIXAS_CONVERGENCIA_PU as FAIXAS_CONVERGENCIA  # ADR-056
from concilium.domain.models.canonical import (
    CategoriaConvergencia,
    ValidacaoCatalogoPUItem,
    ValidacaoItem,
)

# ADR-056 §T6: TYPE_CHECKING guard — import só ocorre em type checkers (mypy, IDE),
# nunca em runtime. Elimina a violação domínio→infraestrutura sem perder type safety.
if TYPE_CHECKING:
    from concilium.infrastructure.repositories.insumo import RepositorioInsumo

# FAIXAS_CONVERGENCIA agora vem de domain/constants — alias acima mantém retrocompat.


def _classificar_desvio(desvio_pct: float) -> str:
    """Classifica desvio em status."""
    abs_dev = abs(desvio_pct)
    if abs_dev <= FAIXAS_CONVERGENCIA["verde"]:  # type: ignore[operator]
        return "VERDE"
    if abs_dev <= FAIXAS_CONVERGENCIA["amarelo"]:  # type: ignore[operator]
        return "AMARELO"
    return "VERMELHO"


def _map_categoria_custo(categoria_custo: str) -> str | None:
    if categoria_custo in ["material", "mat"]:
        return "material"
    if categoria_custo in ["diesel", "combustivel", "comb"]:
        return "diesel"
    if categoria_custo in ["mao_obra", "mão_obra", "mão de obra", "mao de obra", "mo"]:
        return "mao_obra"
    if categoria_custo in ["equipamento", "equipamentos", "eq"]:
        return "equipamentos"
    return None


def _resolve_producao_horaria(
    cpu_id: str,
    cpu: dict,
    producoes_lookup: dict,
    validacoes: list,
) -> tuple[float, bool]:
    producao_id_ref = cpu.get("producao_id_ref")
    if not producao_id_ref or producao_id_ref not in producoes_lookup:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CAT-PU-01",
                status="ERRO",
                mensagem=f"CPU '{cpu_id}': producao_id_ref ausente ou não encontrado",
            )
        )
        return 0.0, False
    prod_item = producoes_lookup[producao_id_ref]
    if isinstance(prod_item, dict):
        return float(prod_item.get("valor_horario") or 0.0), True
    return float(prod_item or 0.0), True


def _compute_composicao_custo(
    cpu_id: str,
    composicao: list,
    insumos_lookup: dict,
    validacoes: list,
) -> tuple[float, dict]:
    from concilium.domain.services.conversor_unidades import ConversorUnidades

    custo_hora = 0.0
    detalhes: dict = {}
    for comp_item in composicao:
        insumo_id = comp_item.get("insumo_id")
        coef = comp_item.get("coeficiente", 0.0)
        categoria_custo = (comp_item.get("categoria_custo") or "").strip().lower()
        if insumo_id not in insumos_lookup:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-CAT-PU-02",
                    status="AVISO",
                    mensagem=f"CPU '{cpu_id}': insumo_id='{insumo_id}' não encontrado no catálogo",
                )
            )
            continue
        insumo = insumos_lookup[insumo_id]
        preco = insumo.get("preco_unitario", 0.0)
        unidade_insumo = insumo.get("unidade", "h")
        try:
            coef_adj = ConversorUnidades.resolver_coeficiente_cpu(
                coef, comp_item.get("unidade") or unidade_insumo, unidade_insumo
            )
        except Exception:
            coef_adj = coef
        contribuicao = coef_adj * preco
        custo_hora += contribuicao
        cat_nome = _map_categoria_custo(categoria_custo)
        if cat_nome is None:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-CAT-PU-03",
                    status="AVISO",
                    mensagem=f"CPU '{cpu_id}': categoria_custo desconhecida '{categoria_custo}' em insumo '{insumo_id}'",
                )
            )
            continue
        if cat_nome not in detalhes:
            detalhes[cat_nome] = {"teorico": 0.0}
        detalhes[cat_nome]["teorico"] += contribuicao
    return custo_hora, detalhes


def _lookup_pu_catalogado(
    cpu_id: str,
    cpu: dict,
    pu_teorico: float,
    validacoes: list,
) -> tuple[float | None, float]:
    pu_sbdi = cpu.get("precos_unitarios_sbdi")
    if not isinstance(pu_sbdi, dict):
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CAT-PU-08",
                status="AVISO",
                mensagem=f"CPU '{cpu_id}': precos_unitarios_sbdi não encontrado no catálogo",
            )
        )
        return None, 0.0
    pu_catalogado = pu_sbdi.get("total")
    if isinstance(pu_catalogado, (int, float)) and pu_catalogado > 0:
        pu_catalogado = float(pu_catalogado)
        desvio = ((pu_catalogado - pu_teorico) / pu_teorico * 100.0) if pu_teorico > 0 else 0.0
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CAT-PU-06",
                status="OK",
                mensagem=f"CPU '{cpu_id}': PU catalogado encontrado (desvio = {desvio:.2f}%)",
            )
        )
        return pu_catalogado, desvio
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-CAT-PU-07",
            status="AVISO",
            mensagem=f"CPU '{cpu_id}': precos_unitarios_sbdi.total não definido ou zero",
        )
    )
    return None, 0.0


def _build_detalhes_por_categoria(
    raw_detalhes: dict,
    pu_sbdi: object,
) -> dict:
    pu_sbdi_cat = pu_sbdi if isinstance(pu_sbdi, dict) else {}
    result = {}
    for cat in ["material", "diesel", "mao_obra", "equipamentos"]:
        teorico = raw_detalhes.get(cat, {}).get("teorico", 0.0)
        catalogado = pu_sbdi_cat.get(cat, 0.0) if pu_sbdi else 0.0  # type: ignore[union-attr]
        desvio_cat = ((catalogado - teorico) / teorico * 100.0) if (teorico > 0 and catalogado > 0) else 0.0
        result[cat] = CategoriaConvergencia(
            pu_teorico=round(teorico, 6),
            pu_planejado=round(catalogado, 6),
            desvio_pct=round(desvio_cat, 2),
            status=_classificar_desvio(desvio_cat),  # type: ignore[arg-type]
        )
    return result


def validar_pu_catalogo(
    cpu: dict,
    producoes_lookup: dict,
    insumos_lookup: dict,
    repo: RepositorioInsumo | None = None,
    horas_dia: int = 8,
    dias_semana: int = 6,
) -> ValidacaoCatalogoPUItem:
    """Valida PU teórico vs catalogado para uma CPU."""
    validacoes: list = []
    cpu_id = cpu.get("codigo", "DESCONHECIDO")
    unidade = cpu.get("unidade", "un")

    producao_horaria, ok = _resolve_producao_horaria(cpu_id, cpu, producoes_lookup, validacoes)
    if not ok:
        return ValidacaoCatalogoPUItem(
            cpu_id=cpu_id,
            unidade=unidade,
            producao_horaria=0.0,
            custo_hora_teorico=0.0,
            pu_teorico_sem_bdi=0.0,
            pu_catalogado_sem_bdi=None,
            desvio_pct=0.0,
            status_convergencia="VERMELHO",
            validacoes=validacoes,
        )

    composicao = cpu.get("composicao_completa") or cpu.get("composicao_itens") or []
    custo_hora_teorico, detalhes_raw = _compute_composicao_custo(cpu_id, composicao, insumos_lookup, validacoes)

    if custo_hora_teorico <= 0:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CAT-PU-04",
                status="AVISO",
                mensagem=f"CPU '{cpu_id}': custo_hora_teorico = 0 (composição vazia ou preços zero)",
            )
        )

    if producao_horaria <= 0:
        pu_teorico = 0.0
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CAT-PU-05",
                status="ERRO",
                mensagem=f"CPU '{cpu_id}': producao_horaria inválida {producao_horaria}",
            )
        )
    else:
        pu_teorico = round(custo_hora_teorico / producao_horaria, 6)

    pu_catalogado, desvio_pct = _lookup_pu_catalogado(cpu_id, cpu, pu_teorico, validacoes)
    detalhes = _build_detalhes_por_categoria(detalhes_raw, cpu.get("precos_unitarios_sbdi"))

    status_geral = _classificar_desvio(desvio_pct) if pu_catalogado else "AMARELO"
    if not pu_catalogado:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CAT-PU-09",
                status="AVISO",
                mensagem=f"CPU '{cpu_id}': sem PU catalogado — convergência não pode ser validada",
            )
        )
        status_geral = "AMARELO"

    return ValidacaoCatalogoPUItem(
        cpu_id=cpu_id,
        unidade=unidade,
        producao_horaria=round(producao_horaria, 6),
        custo_hora_teorico=round(custo_hora_teorico, 6),
        pu_teorico_sem_bdi=round(pu_teorico, 6),
        pu_catalogado_sem_bdi=round(pu_catalogado, 6) if pu_catalogado else None,
        desvio_pct=round(desvio_pct, 2),
        status_convergencia=status_geral,  # type: ignore[arg-type]
        detalhes=detalhes,  # type: ignore[arg-type]
        validacoes=validacoes,
    )
