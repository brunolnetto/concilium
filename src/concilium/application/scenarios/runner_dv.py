"""DV (Decision Variables) space scenarios for the runner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from concilium.application.scenarios.config import ScenarioConfig

if TYPE_CHECKING:
    from concilium.domain.models.canonical import CanonicalModel
    from concilium.domain.models.project.decision_variables import DecisionVariables


@dataclass
class DVResult:
    """Result of a DV scenario execution."""

    config: ScenarioConfig
    canonical: CanonicalModel | None
    status: str  # "OK" | "INFEASIBLE" | "ERRO"
    erro: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "config_id": self.config.id,
            "config_nome": self.config.nome,
            "status": self.status,
            "erro": self.erro,
        }


def generate_dv_variations(
    base_decisions: DecisionVariables | None,
    dv2_options: list[dict[str, dict[str, int]]] | None = None,
    dv4_options: list[str] | None = None,
) -> list[ScenarioConfig]:
    """Gera cenários variando APENAS no espaço DV1-DV4 (DEC-29).

    Args:
        base_decisions: DecisionVariables de referência. Se None, usa defaults.
        dv2_options:    Lista de valores alternativos para dv2_num_equipes.
        dv4_options:    Lista de valores alternativos para dv4_indirect_policy.

    Returns:
        Lista de ScenarioConfig onde cada config tem decision_variables preenchido.
    """
    from concilium.domain.models.project.decision_variables import DecisionVariables

    _valid_policies = {"lean", "standard", "robust"}
    if dv4_options:
        invalid = set(dv4_options) - _valid_policies
        if invalid:
            raise ValueError(f"DEC-29: dv4_indirect_policy inválido: {invalid}. Permitidos: {_valid_policies}")

    base = base_decisions or DecisionVariables()

    configs: list[ScenarioConfig] = []
    configs.append(
        ScenarioConfig(
            nome="base_dv",
            descricao="Cenário base — variáveis de decisão inalteradas",
            decision_variables=base,
        )
    )

    for i, dv2 in enumerate(dv2_options or []):
        dv = DecisionVariables(
            dv1_crew_template=base.dv1_crew_template,
            dv2_num_equipes=dv2,
            dv3_start_offset=base.dv3_start_offset,
            dv4_indirect_policy=base.dv4_indirect_policy,
        )
        configs.append(
            ScenarioConfig(
                nome=f"dv2_var_{i + 1}",
                descricao=f"Variação DV2 #{i + 1}: {dv2}",
                decision_variables=dv,
            )
        )

    for policy in dv4_options or []:
        dv = DecisionVariables(
            dv1_crew_template=base.dv1_crew_template,
            dv2_num_equipes=base.dv2_num_equipes,
            dv3_start_offset=base.dv3_start_offset,
            dv4_indirect_policy=policy,  # type: ignore[arg-type]
        )
        configs.append(
            ScenarioConfig(
                nome=f"dv4_{policy}",
                descricao=f"Política de indiretos: {policy}",
                decision_variables=dv,
            )
        )

    return configs


def run_dv_scenario(
    config: ScenarioConfig,
    canonical_in: CanonicalModel,
    catalogo: dict[str, Any] | None = None,
    perfil: dict[str, Any] | None = None,
    extra_inputs: dict[str, Any] | None = None,
) -> DVResult:
    """Executa um cenário no modo DV usando PlanningLoop.

    Args:
        config:         ScenarioConfig com decision_variables preenchido.
        canonical_in:   Estado canônico de entrada.
        catalogo:       Catálogo de insumos/CPUs (opcional).
        perfil:         Perfil construtora (opcional).
        extra_inputs:   Inputs adicionais para skills individuais (opcional).

    Returns:
        DVResult com canonical, status e métricas.
    """
    from concilium.application.optimizer.loop import adjust_schedule

    if config.decision_variables is None:
        raise ValueError(
            "run_dv_scenario requer config.decision_variables. Use run_scenario() para o modo legado (deltas)."
        )

    try:
        can, feasible, violations = adjust_schedule(
            canonical_in=canonical_in,
            decision_variables=config.decision_variables,
            catalogo=catalogo,
            perfil=perfil,
            extra_inputs=extra_inputs,
        )
        status = "OK" if feasible else "INFEASIBLE"
        erro = None
        if not feasible:
            erro_items = [f"{v.code}: {v.remediation_hint or v.code}" for v in violations if v.status == "ERRO"]
            erro = "; ".join(erro_items) if erro_items else "Restrições hard não satisfeitas"

        return DVResult(
            config=config,
            canonical=can,
            status=status,
            erro=erro,
        )
    except Exception as e:
        return DVResult(
            config=config,
            canonical=None,
            status="ERRO",
            erro=str(e),
        )
