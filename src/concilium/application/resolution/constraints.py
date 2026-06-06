"""Hard constraints da camada de resolução — ADR-002.

ConstraintFilter é o gate determinístico.
CPU é elegível SOMENTE se todos os hard constraints passam.
Falha em qualquer constraint -> CPU descartada.
"""

from __future__ import annotations

from dataclasses import dataclass

from concilium.application.resolution.models import CPUCanonical
from concilium.application.resolution.registry import ATTRIBUTE_REGISTRY
from concilium.application.semantic.intent import SemanticIntent

# Mapeamento de unidades compatíveis (para sub-unidades de mesma dimensão)
_UNIT_COMPAT: dict[str, set[str]] = {
    "m3": {"m3"},
    "m2": {"m2"},
    "m": {"m"},
    "ton": {"ton"},
    "un": {"un"},
    "cm": {"cm", "mm"},  # comprimento sub (não são unidades de itens EAP)
    "mm": {"mm", "cm"},
}


@dataclass
class ConstraintResult:
    """Resultado de verificação de um único hard constraint."""

    constraint_name: str
    passed: bool
    reason: str | None = None  # obrigatório se passed=False


class ConstraintFilter:
    """Gate determinístico: elimina CPUs incompatíveis antes do scoring.

    Cada método ``check_*`` retorna um ConstraintResult.
    ``is_eligible`` roda todos os checks e retorna (elegível, detalhes).
    """

    def check_unit_compatibility(
        self,
        intent: SemanticIntent,
        cpu: CPUCanonical,
    ) -> ConstraintResult:
        """Unit mismatch é hard failure — m2 ≠ m3, ponto final."""
        compat = _UNIT_COMPAT.get(intent.unit, {intent.unit})
        if cpu.unit not in compat:
            return ConstraintResult(
                constraint_name="unit_compatibility",
                passed=False,
                reason=(f"Unidade do intent ({intent.unit!r}) incompatível com CPU ({cpu.unit!r})"),
            )
        return ConstraintResult(constraint_name="unit_compatibility", passed=True)

    def check_domain_compatibility(
        self,
        intent: SemanticIntent,
        cpu: CPUCanonical,
    ) -> ConstraintResult:
        """Domain/categoria incompatível -> descartado."""
        if intent.domain == "other":
            # domain desconhecido -> não filtra por domain (pode ser qualquer)
            return ConstraintResult(constraint_name="domain_compatibility", passed=True)
        if intent.domain != cpu.domain:
            return ConstraintResult(
                constraint_name="domain_compatibility",
                passed=False,
                reason=(f"Domain do intent ({intent.domain!r}) incompatível com CPU ({cpu.domain!r})"),
            )
        return ConstraintResult(constraint_name="domain_compatibility", passed=True)

    def check_required_attributes(
        self,
        intent: SemanticIntent,
        cpu: CPUCanonical,
    ) -> ConstraintResult:
        """CPU requer atributos que o intent não forneceu -> inelegível."""
        if not cpu.required_attributes:
            return ConstraintResult(constraint_name="required_attributes", passed=True)

        intent_dim_names = {d.name for d in intent.dimensions}
        intent_dim_names.update(intent.context.keys())

        missing = [attr for attr in cpu.required_attributes if attr not in intent_dim_names]
        if missing:
            return ConstraintResult(
                constraint_name="required_attributes",
                passed=False,
                reason=(f"CPU requer atributos ausentes no intent: {missing}"),
            )
        return ConstraintResult(constraint_name="required_attributes", passed=True)

    def check_structural_compatibility(
        self,
        intent: SemanticIntent,
        cpu: CPUCanonical,
    ) -> ConstraintResult:
        """Compatibilidade estrutural por categoria.

        - earthwork com DMT: verifica se o DMT do intent está dentro da faixa da CPU.
        - pavement/drainage: sem restrição estrutural adicional (handled by scoring).
        """
        if cpu.activity_type == "cut_fill" and "dmt" in cpu.attributes:
            cpu_dmt = cpu.attributes.get("dmt")
            intent_dmt = intent.dimension_value("dmt")
            if intent_dmt is not None and cpu_dmt is not None:
                # cpu_dmt é o limite superior (dmt_max_metros)
                # Tolerância 20% do ATTRIBUTE_REGISTRY
                tol = ATTRIBUTE_REGISTRY["dmt"].tolerance_pct
                upper = float(cpu_dmt) * (1 + tol)
                if intent_dmt > upper:
                    return ConstraintResult(
                        constraint_name="structural_compatibility",
                        passed=False,
                        reason=(
                            f"DMT do intent ({intent_dmt}m) excede "
                            f"limite da CPU ({cpu_dmt}m + {tol:.0%} tol = {upper}m)"
                        ),
                    )

        return ConstraintResult(constraint_name="structural_compatibility", passed=True)

    def is_eligible(
        self,
        intent: SemanticIntent,
        cpu: CPUCanonical,
    ) -> tuple[bool, list[ConstraintResult]]:
        """Roda todos os checks. CPU elegível somente se todos passam.

        Returns:
            (elegível, lista de ConstraintResult com detalhes).
        """
        results = [
            self.check_unit_compatibility(intent, cpu),
            self.check_domain_compatibility(intent, cpu),
            self.check_required_attributes(intent, cpu),
            self.check_structural_compatibility(intent, cpu),
        ]
        eligible = all(r.passed for r in results)
        return eligible, results


__all__ = ["ConstraintFilter", "ConstraintResult"]
