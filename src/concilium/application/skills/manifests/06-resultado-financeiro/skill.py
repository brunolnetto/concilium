"""Skill 06 — Resultado Financeiro (Consolidado, NEP-041 Fase 4).

Unifica o cluster financeiro em uma única skill gate:
  1. Precificação unitária (antiga 06)     → seção `planejamento`
  2. Custos indiretos (antiga 07)          → seção `indiretos`
  3. Consolidação financeira (antiga 08)   → seção `resultado`

Os três estágios são executados em sequência (06→07→08), preservando o fluxo de
dados exato: 08 depende das saídas de 06 e 07. Cada estágio produz seções
canônicas disjuntas, threaded pelo canônico. Comportamento numericamente idêntico
ao pipeline de 3 skills anterior.

A lógica de cada estágio permanece intacta nos sub-pacotes _precificacao/,
_indiretos/ e _consolidacao/ (cópias fiéis das skills originais, sem colisão de
nomes de helper).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import CanonicalModel

_HERE = Path(__file__).resolve().parent


def _load_estagio(subdir: str, func_name: str):
    """Carrega a run function de um sub-pacote de estágio via importlib."""
    spec = importlib.util.spec_from_file_location(f"resultado_financeiro_{subdir}", _HERE / subdir / "skill.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return getattr(mod, func_name)


_run_precificacao = _load_estagio("_precificacao", "run_precificacao_unitaria")
_run_indiretos = _load_estagio("_indiretos", "run_custos_indiretos")
_run_consolidacao = _load_estagio("_consolidacao", "run_consolidacao_financeira")


def run_resultado_financeiro(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    catalogo: dict[str, Any] | None = None,
    perfil: dict[str, Any] | None = None,
    catalog_session: object | None = None,
) -> SkillResult:
    """Executa precificação + indiretos + consolidação em um passo (NEP-041 F4).

    Estágio 1 (precificação): popula `planejamento` (PU + BDI por categoria).
    Estágio 2 (indiretos): popula `indiretos` (custos indiretos por categoria).
    Estágio 3 (consolidação): popula `resultado` (margem, venda, ponto_equilibrio).

    Ordem 06→07→08 preserva o fluxo de dados: consolidação depende das duas
    saídas anteriores. Validações de todos os estágios são consolidadas.
    """
    catalogo = catalogo or {}
    perfil = perfil or {}
    validacoes: list = []

    # Estágio 1 — Precificação unitária (gate: sem planejamento não há receita)
    res_pre = _run_precificacao(canonical_in, inputs, catalogo, perfil, catalog_session)
    validacoes.extend(res_pre.validacoes)
    if res_pre.has_errors:
        # Falha de gate: aborta antes de consolidar (preserva semântica ADR-022)
        return SkillResult(res_pre.canonical, validacoes)
    canonical = res_pre.canonical

    # Estágio 2 — Custos indiretos
    res_ind = _run_indiretos(canonical, inputs, catalogo, perfil)
    validacoes.extend(res_ind.validacoes)
    canonical = res_ind.canonical

    # Estágio 3 — Consolidação financeira
    res_con = _run_consolidacao(canonical, inputs, perfil)
    validacoes.extend(res_con.validacoes)
    canonical = res_con.canonical

    return SkillResult(canonical, validacoes)
