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
import sys
import types
from pathlib import Path
from typing import Any

from concilium.application.scheduling.skill06_p18c_consumption_preview import (
    build_p18_skill06_preview,
)
from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import CanonicalModel, ValidacaoItem

_HERE = Path(__file__).resolve().parent


def _load_estagio(subdir: str, func_name: str):
    """Carrega a run function de um sub-pacote de estágio via importlib.

    Registra um pacote sintético apontando para o diretório do estágio (mesma
    técnica de ``_ensure_skill_package`` em concilium/application/skills/__init__.py)
    para que os imports relativos dentro de ``{subdir}/skill.py``
    (``from ._skill_helpers_x import ...``) resolvam normalmente.
    """
    stage_dir = _HERE / subdir
    path = stage_dir / "skill.py"
    pkg_name = f"_concilium_resultado_financeiro_stage_{subdir.lstrip('_')}"
    mod_name = f"{pkg_name}.skill"

    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(stage_dir)]
        pkg.__package__ = pkg_name
        sys.modules[pkg_name] = pkg

    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Não foi possível carregar spec para estágio: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(mod_name, None)
        raise
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
    inputs = inputs or {}
    validacoes: list = []

    # P18-C3 is explicitly opt-in. Always invalidate a stale preview before
    # running any downstream stage; legacy finance remains the default path.
    enabled = inputs.get("p18_consumption_preview_enabled", False)
    canonical_start = canonical_in.model_copy(update={"p18_consumption_preview": None})
    if type(enabled) is not bool:
        return SkillResult(canonical_start, [ValidacaoItem(
            codigo="VAL-P18-CONSUMPTION-PREVIEW",
            status="ERRO",
            mensagem="p18_consumption_preview_enabled must be an explicit boolean.",
        )])

    # Estágio 1 — Precificação unitária (gate: sem planejamento não há receita)
    res_pre = _run_precificacao(canonical_start, inputs, catalogo, perfil, catalog_session)
    validacoes.extend(res_pre.validacoes)
    if res_pre.has_errors:
        # Falha de gate: aborta antes de consolidar (preserva semântica ADR-022)
        return SkillResult(res_pre.canonical, validacoes)
    canonical = res_pre.canonical

    # Estágio 2 — Custos indiretos
    res_ind = _run_indiretos(canonical, inputs, catalogo, perfil)
    validacoes.extend(res_ind.validacoes)
    canonical = res_ind.canonical

    # Optional P18-C3 projection is a separate sidecar. It only consumes the
    # exact Skill05 P16 witness + final Skill04 schedule + resolved catalog.
    # A missing/forged source blocks this opt-in request, never falling back to
    # legacy MAT/COMB estimates and never materializing a financial GO.
    if enabled:
        try:
            preview_record = build_p18_skill06_preview(canonical, catalogo)
        except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError) as exc:
            validacoes.append(ValidacaoItem(
                codigo="VAL-P18-CONSUMPTION-PREVIEW",
                status="ERRO",
                mensagem=f"Physical consumption preview failed closed: {exc}",
            ))
            return SkillResult(
                canonical.model_copy(update={"p18_consumption_preview": None}),
                validacoes,
            )
        canonical = canonical.model_copy(update={"p18_consumption_preview": preview_record})
        validacoes.append(ValidacaoItem(
            codigo="VAL-P18-CONSUMPTION-PREVIEW",
            status="AVISO",
            mensagem=(
                "P18 source-backed physical-consumption preview recorded separately; "
                "legacy price/margin was not overridden and this is not PROJECT_GO."
            ),
        ))

    # Estágio 3 — Consolidação financeira
    res_con = _run_consolidacao(canonical, inputs, perfil)
    validacoes.extend(res_con.validacoes)
    canonical = res_con.canonical

    return SkillResult(canonical, validacoes)
