"""Skill 13 — Replanejamento e Cenários (Consolidado, NEP-041 Fase 2).

Unifica o antigo 13-assessor-replanejamento (sugestões de reparo) e o
14-explorador-cenarios (exploração do espaço de planos) em uma única skill.

Ambos os estágios produzem seções canônicas disjuntas e complementares:
- `replan_suggestions`  — sugestões priorizadas de reparo (assessor)
- `plan_space_result`   — repair_path + oportunidades (explorador, ADR-021)

A skill sempre roda; o status de entrada determina o comportamento interno de
cada estágio (repair vs. scan de oportunidades), não a execução da skill.
"""

from __future__ import annotations

from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import CanonicalModel

try:
    # Hyphenated manifest dir: ty cannot resolve these relative imports statically
    # (only work at runtime via the synthetic package set up in skills/__init__.py).
    from ._assessor import run_assessor_replanejamento  # ty: ignore[unresolved-import]
    from ._explorador import run_explorador_cenarios  # ty: ignore[unresolved-import]
except ImportError:
    import importlib.util
    from pathlib import Path

    _here = Path(__file__).resolve().parent

    def _load_local(mod_name: str, attr: str):
        spec = importlib.util.spec_from_file_location(mod_name, _here / f"{mod_name}.py")
        if spec is None or spec.loader is None:
            raise ImportError(f"Não foi possível carregar spec para {mod_name}.py em {_here}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, attr)

    run_assessor_replanejamento = _load_local("_assessor", "run_assessor_replanejamento")
    run_explorador_cenarios = _load_local("_explorador", "run_explorador_cenarios")


def run_replanejamento_e_cenarios(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    perfil: dict[str, Any] | None = None,
) -> SkillResult:
    """Executa exploração de cenários + assessoria de replanejamento em um passo.

    Estágio 1 (explorador): popula `plan_space_result` (repair_path + oportunidades).
    Estágio 2 (assessor): popula `replan_suggestions` (sugestões priorizadas).

    As seções são disjuntas; a ordem não cria dependência de dados (ADR-021/NEP-041).
    Validações de ambos os estágios são consolidadas no resultado final.
    """
    # Estágio 1 — Exploração do espaço de planos
    res_exp = run_explorador_cenarios(canonical_in, inputs, perfil)
    canonical = res_exp.canonical
    validacoes = list(res_exp.validacoes)

    # Estágio 2 — Assessoria de replanejamento (sobre o canônico já enriquecido)
    res_ass = run_assessor_replanejamento(canonical, inputs, perfil)
    canonical = res_ass.canonical
    validacoes.extend(res_ass.validacoes)

    return SkillResult(canonical, validacoes)
