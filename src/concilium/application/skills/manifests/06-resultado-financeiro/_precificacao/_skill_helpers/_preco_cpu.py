"""Skill 06 (_precificacao) — Planejamento e BDI.

Cálculo de preço por categoria a partir de CPU/composição e produção.
"""

from __future__ import annotations

from typing import Any

from concilium.domain.models.canonical import (
    ValidacaoItem,
)
from concilium.infrastructure.repositories.insumo import RepositorioInsumo

from ._cpu_helpers import _CATEGORIA_MAP, _resolve_insumo_preco  # ty: ignore[unresolved-import]
from ._planejamento_entry import _apply_equip_decomp  # ty: ignore[unresolved-import]


def _compute_preco_cat_from_cpu(
    cpu_model: Any,
    insumo_lookup: dict,
    repo: RepositorioInsumo,
    jurisdicao_id: str | None,
    overrides: dict | None,
    data_base: Any,
    cpu_codigo: str,
    erros_insumo: set,
    validacoes: list,
) -> tuple[dict, set]:
    from concilium.domain.services.conversor_unidades import ConversorUnidades

    preco_cat = {"material": 0.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
    equip_sem_decomp_item: set[str] = set()
    for ci in cpu_model.composicao_completa:
        insumo = insumo_lookup.get(ci.insumo_id)
        if insumo is None:
            erros_insumo.add(ci.insumo_id)
            continue
        categoria_raw = (ci.categoria_custo or "").strip().lower()
        categoria = _CATEGORIA_MAP.get(categoria_raw)
        if categoria is None:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-PLAN-CAT",
                    status="AVISO",
                    mensagem=(
                        f"CPU '{cpu_codigo}' usa categoria_custo desconhecida:"
                        f" '{ci.categoria_custo}'. Item ignorado no planejamento."
                    ),
                )
            )
            continue
        unidade_insumo = insumo.get("unidade")
        unidade_cpu = ci.unidade or unidade_insumo
        try:
            coeficiente_ajustado = ConversorUnidades.resolver_coeficiente_cpu(
                ci.coeficiente, unidade_cpu, unidade_insumo
            )
            preco_insumo = _resolve_insumo_preco(
                repo, ci.insumo_id, jurisdicao_id, overrides, data_base, float(insumo.get("preco_unitario", 0.0) or 0.0)
            )
            contribuicao = coeficiente_ajustado * preco_insumo
        except Exception as e:  # pragma: no cover
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-PLAN-UNIT", status="ERRO", mensagem=f"Erro de conversão na CPU '{cpu_codigo}': {e}"
                )
            )
            preco_insumo = _resolve_insumo_preco(
                repo, ci.insumo_id, jurisdicao_id, overrides, data_base, float(insumo.get("preco_unitario", 0.0) or 0.0)
            )
            contribuicao = ci.coeficiente * preco_insumo
        if categoria == "equipamentos":
            _apply_equip_decomp(ci, insumo, contribuicao, preco_cat, equip_sem_decomp_item)
            continue
        preco_cat[categoria] += contribuicao
    return preco_cat, equip_sem_decomp_item


def _resolve_producao_valida(cpu: dict, prod_lookup: dict, validacoes: list) -> dict | None:
    """Resolve a producao referenciada pelo CPU, validando presença e valor_horario > 0."""
    prod_id = cpu.get("producao_id_ref")
    if not prod_id:
        return None

    producao = prod_lookup.get(prod_id)
    if not producao:
        return None

    producao_horaria = float(producao.get("producao_horaria") or 0.0)
    if producao_horaria <= 0:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PLAN-PROD-HORARIO",
                status="AVISO",
                mensagem=(
                    f"CPU '{cpu.get('codigo')}': producao '{prod_id}' tem producao_horaria=0; "
                    "precificação bottom-up impossível."
                ),
            )
        )
        return None

    return producao


def _resolve_beta_praticabilidade(item_id: str, sched_por_item: dict | None) -> float:
    """ADR-172: β_i = média de η_p (praticabilidade: clima×calendário×jornada, já calculada
    por semana em `DistribuicaoSemanal.eta_p`, skill 04) ponderada por `num_equipes`, só sobre
    semanas ativas do cronograma já construído deste item.

    1.0 (sem correção) quando o item não tem cronograma associado ou não há semanas ativas —
    nunca um valor inventado (mesma filosofia do `causa_dominante`, ADR-162 D1).
    """
    sa = (sched_por_item or {}).get(item_id)
    dist = getattr(sa, "distribuicao_semanal", None) if sa else None
    if not dist:
        return 1.0
    peso_total = 0.0
    soma_ponderada = 0.0
    for d in dist.values():
        num_equipes = float(getattr(d, "num_equipes", 0.0) or 0.0)
        if num_equipes <= 0:
            continue
        eta_p = float(getattr(d, "eta_p", 1.0) or 0.0)
        soma_ponderada += eta_p * num_equipes
        peso_total += num_equipes
    if peso_total <= 0:
        return 1.0
    beta = soma_ponderada / peso_total
    return beta if beta > 0 else 1.0


def _compute_preco_cat_from_production(
    cpu: dict,
    prod_lookup: dict,
    insumo_lookup: dict,
    preco_diesel: float,
    alpha_clt: float,
    alpha_mensalista: float,
    validacoes: list,
    catalog_session: object | None = None,  # ADR-100
) -> tuple[dict | None, float]:
    """NEP-032 D1: deriva preco_cat da composição da equipe × produtividade (bottom-up canônico).

    Fórmula: PU_categoria = custo_categoria_hora / producao.producao_horaria

    Onde custo_categoria_hora é calculado por pu_calculator.calcular_pu():
      MO:         Σ (salario/horas_mes × α × num_pessoas)
      Diesel:     Σ (consumo_L_h × preco_diesel × num_unidades)
      Equipamento: Σ (preco_h × num_unidades)  [parte não-MO/não-diesel]
      Material:   Σ (consumo_h × preco × num_materiais)

    Emite VAL-PLAN-SBDI-LEGADO se o CPU ainda tiver precos_unitarios_sbdi
    hard-coded (campo agora depreciado — não é usado no cálculo).

    Retorna também `producao.producao_horaria` (ADR-162 D1: ρ_i, produtividade catalogada
    usada por causa_dominante em skill-06/_consolidacao) — 0.0 quando não resolvível.
    """
    from concilium.application.catalog.pu_calculator import ParametrosCalculo, derivar_precos_unitarios_sbdi
    from concilium.domain.constants import ENCARGOS_PJ, HORAS_MES_REGIME_6x1

    producao = _resolve_producao_valida(cpu, prod_lookup, validacoes)
    if producao is None:
        return None, 0.0

    params = ParametrosCalculo(
        alpha_clt=alpha_clt,
        alpha_pj=ENCARGOS_PJ,
        preco_diesel=preco_diesel,
        horas_mes=HORAS_MES_REGIME_6x1,
    )

    sbdi = derivar_precos_unitarios_sbdi(producao, insumo_lookup, params, catalog_session=catalog_session)
    if not sbdi or float(sbdi.get("total", 0.0) or 0.0) <= 0:
        return None, 0.0

    if cpu.get("precos_unitarios_sbdi"):
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PLAN-SBDI-LEGADO",
                status="INFO",
                mensagem=f"CPU '{cpu.get('codigo')}': precos_unitarios_sbdi é campo depreciado — ignorado (bottom-up via equipe).",
            )
        )

    preco_cat = {
        "mao_obra": float(sbdi.get("mo", sbdi.get("mao_obra", 0.0)) or 0.0),
        "diesel": float(sbdi.get("diesel", 0.0) or 0.0),
        "equipamentos": float(sbdi.get("equipamentos", 0.0) or 0.0),
        "material": float(sbdi.get("material", 0.0) or 0.0),
    }

    return preco_cat, float(producao.get("producao_horaria") or 0.0)


