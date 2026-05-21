"""Pipeline completo de resolução CPU — ADR-002.

Fluxo: retrieval -> constraint filter -> score -> confidence -> output

Output sempre é ResolutionOutput — nunca "a resposta direta".
"""

from __future__ import annotations

from concilium.application.resolution.confidence import ConfidenceAssigner
from concilium.application.resolution.constraints import ConstraintFilter
from concilium.application.resolution.models import (
    DEFAULT_SCORING_CONFIG,
    CPUCanonical,
    EliminationLog,
    ResolutionDecision,
    ResolutionOutput,
    ScoringConfig,
)
from concilium.application.resolution.scoring import WeightedScorer
from concilium.application.resolution.storage import ResolutionDecisionStore
from concilium.application.semantic.intent import SemanticIntent

_DEFAULT_RETRIEVAL_TOP_N = 20


class Resolver:
    """Pipeline completo: retrieval -> filter -> score -> confidence -> output.

    Output é sempre ResolutionOutput — nunca "a resposta direta".
    """

    def __init__(
        self,
        catalog: list[CPUCanonical],
        scorer: WeightedScorer | None = None,
        confidence_assigner: ConfidenceAssigner | None = None,
        decision_store: ResolutionDecisionStore | None = None,
        config: ScoringConfig | None = None,
    ) -> None:
        self._catalog = catalog
        self._scorer = scorer or WeightedScorer()
        self._confidence = confidence_assigner or ConfidenceAssigner()
        self._store = decision_store
        self._config = config or DEFAULT_SCORING_CONFIG
        self._filter = ConstraintFilter()

    def resolve(
        self,
        intent: SemanticIntent,
        history: list[ResolutionDecision] | None = None,
    ) -> ResolutionOutput:
        """Executa o pipeline completo de resolução.

        Args:
            intent:  SemanticIntent estruturado.
            history: Histórico de decisões anteriores para historical_prior.

        Returns:
            ResolutionOutput com resolution_status e candidatos rankeados.
        """
        # 1. Candidate retrieval (broad, recall-oriented)
        candidates = self._retrieve_candidates(intent)

        # 2. Constraint filtering (hard gate)
        eligible, eliminated = self._filter_by_constraints(candidates, intent)

        # 3. Se nenhum candidato elegível
        if not eligible:
            return ResolutionOutput(
                scope_item_id=intent.scope_item_id,
                intent=intent,
                candidates=[],
                eliminated=eliminated,
                resolution_status="NO_VALID_CANDIDATES",
                selected_cpu_id=None,
                scoring_config_version=self._config.version,
            )

        # 4. Scoring
        scored = self._scorer.score_all(intent, eligible, self._config, history)

        # 5. Confidence assignment
        with_confidence = self._confidence.assign(scored, self._config)

        # 6. Determinar status e CPU selecionada
        top = with_confidence[0] if with_confidence else None

        if top is None:
            status = "NO_VALID_CANDIDATES"
            selected_cpu_id = None
        elif top.confidence == "HIGH":
            status = "AUTO_SELECTED"
            selected_cpu_id = top.cpu_id
        else:
            status = "NEEDS_REVIEW"
            selected_cpu_id = None  # requer validação humana

        return ResolutionOutput(
            scope_item_id=intent.scope_item_id,
            intent=intent,
            candidates=with_confidence,
            eliminated=eliminated,
            resolution_status=status,  # type: ignore[arg-type]
            selected_cpu_id=selected_cpu_id,
            scoring_config_version=self._config.version,
        )

    def resolve_and_persist(
        self,
        intent: SemanticIntent,
        history: list[ResolutionDecision] | None = None,
    ) -> tuple[ResolutionOutput, ResolutionDecision | None]:
        """Resolve e persiste automaticamente se AUTO_SELECTED.

        Returns:
            (output, decision) onde decision é None se não AUTO_SELECTED.

        Raises:
            RuntimeError: se _store não foi configurado e há candidato AUTO_SELECTED.
        """
        output = self.resolve(intent, history)

        decision = None
        if output.resolution_status == "AUTO_SELECTED" and output.selected_cpu_id:
            top = output.candidates[0]
            decision = ResolutionDecision(
                scope_item_id=intent.scope_item_id,
                selected_cpu_id=output.selected_cpu_id,
                candidate_set=output.candidates,
                eliminated_set=output.eliminated,
                scoring_config_version=self._config.version,
                confidence=top.confidence,
                explanations=top.explanations,
                decision_source="AUTO",
                intent_snapshot=intent,
            )
            if self._store is not None:
                self._store.persist(decision)
            elif output.resolution_status == "AUTO_SELECTED":
                raise RuntimeError(
                    "Resolver.resolve_and_persist: AUTO_SELECTED mas "
                    "decision_store não configurado. Configure um "
                    "ResolutionDecisionStore ou use resolve()."
                )

        return output, decision

    # ── Internos ──────────────────────────────────────────────────────────────

    def _retrieve_candidates(
        self,
        intent: SemanticIntent,
    ) -> list[CPUCanonical]:
        """Broad retrieval: filtra por domain e retorna Top-N por unit match."""
        candidates = [cpu for cpu in self._catalog if intent.domain == "other" or cpu.domain == intent.domain]

        # Filtro por unidade (pré-filtro suave — o hard check está no ConstraintFilter)
        unit_matching = [c for c in candidates if c.unit == intent.unit]
        if unit_matching:
            candidates = unit_matching

        return candidates[:_DEFAULT_RETRIEVAL_TOP_N]

    def _filter_by_constraints(
        self,
        candidates: list[CPUCanonical],
        intent: SemanticIntent,
    ) -> tuple[list[CPUCanonical], list[EliminationLog]]:
        """Aplica hard constraints a cada candidato.

        Returns:
            (elegíveis, log de eliminações com motivos)
        """
        eligible: list[CPUCanonical] = []
        eliminated: list[EliminationLog] = []

        for cpu in candidates:
            is_ok, results = self._filter.is_eligible(intent, cpu)
            if is_ok:
                eligible.append(cpu)
            else:
                failed = [r for r in results if not r.passed]
                for r in failed:
                    eliminated.append(
                        EliminationLog(
                            cpu_id=cpu.cpu_id,
                            constraint_name=r.constraint_name,
                            reason=r.reason or r.constraint_name,
                        )
                    )

        return eligible, eliminated


__all__ = ["Resolver"]
