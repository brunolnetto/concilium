"""Skill 10 — Intervention ROI Matrix.

Avalia intervenções propostas em três dimensões independentes:
ROI, Effort e Risk. Apresenta como matriz de decisão — sem score combinado.

Inputs (via dict 'inputs'):
    intervencoes_propostas: list[dict]  — OBRIGATÓRIO
    effort_catalog: dict  — mapa tipo_perturbação -> {nivel, tipo}
"""

from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import CanonicalModel, ValidacaoItem

# Classificações descritivas de decision_class
_DECISION_CLASSES = {
    # (roi_class, effort_nivel, risk_nivel): decision_class
    ("HIGH", "LOW", "LOW"): "quick_win",
    ("HIGH", "LOW", "MED"): "opportunistic",
    ("HIGH", "LOW", "HIGH"): "opportunistic",
    ("HIGH", "MED", "LOW"): "strategic_move",
    ("HIGH", "MED", "MED"): "strategic_move",
    ("HIGH", "HIGH", "LOW"): "strategic_move",
    ("HIGH", "HIGH", "MED"): "strategic_move",
    ("HIGH", "HIGH", "HIGH"): "risk_averse",
    ("MED", "LOW", "LOW"): "quick_win",
    ("MED", "LOW", "MED"): "balanced_tradeoff",
    ("MED", "MED", "LOW"): "balanced_tradeoff",
    ("MED", "MED", "MED"): "balanced_tradeoff",
    ("MED", "HIGH", "LOW"): "constraint_driven",
    ("LOW", "LOW", "LOW"): "risk_averse",
    ("LOW", "LOW", "MED"): "risk_averse",
    ("LOW", "HIGH", "LOW"): "not_recommended",
    ("LOW", "HIGH", "MED"): "not_recommended",
    ("LOW", "HIGH", "HIGH"): "not_recommended",
}

_DEFAULT_EFFORT_CATALOG: dict[str, dict] = {
    "+10%": {"nivel": "MED", "tipo": "ajuste_configuracao"},
    "+20%": {"nivel": "HIGH", "tipo": "ajuste_configuracao"},
    "regime_6d": {"nivel": "MED", "tipo": "mudanca_regime_trabalho"},
    "regime_9h": {"nivel": "LOW", "tipo": "mudanca_regime_trabalho"},
    "novo_equipamento": {"nivel": "HIGH", "tipo": "contratacao_equipamento"},
    "subcontratacao": {"nivel": "MED", "tipo": "subcontratacao"},
}


def _classify_roi(roi_pp: float) -> str:
    if roi_pp >= 3.0:
        return "HIGH"
    if roi_pp >= 1.0:
        return "MED"
    return "LOW"


def _estimate_roi_heuristic(variavel: str, tipo: str, custo_criticality: object | None) -> tuple[float, int]:
    """Estimativa heurística de ROI e delta_prazo quando simulações não estão disponíveis.

    ``custo_criticality`` aceita tanto o tipo estruturado real (`CostCriticalityResult`,
    ADR-020) quanto um dict legado ou um objeto duck-typed equivalente (ex.: em testes) —
    daí o tipo largo `object | None` em vez do tipo estruturado específico.
    """
    # Heurística simples baseada no tipo de perturbação
    perturbacao_map = {
        "+10%": (1.5, -15),
        "+20%": (2.8, -28),
        "regime_6d": (1.0, -20),
        "regime_9h": (0.5, -10),
        "novo_equipamento": (2.0, -25),
        "subcontratacao": (1.2, -18),
    }
    roi_pp, delta_prazo = perturbacao_map.get(tipo, (0.5, 0))

    # Amplifica ROI para atividades A+ no cost_criticality (ADR-020: tipo estruturado)
    if custo_criticality:
        if isinstance(custo_criticality, dict):
            atividades = custo_criticality.get("atividades", [])
        else:
            atividades = getattr(custo_criticality, "atividades", [])
        if not isinstance(atividades, list):
            atividades = []
        for atv in atividades:
            if isinstance(atv, dict):
                atv_id = str(atv.get("atividade_id", ""))
                atv_cls = atv.get("class", "")
            else:
                atv_id = str(getattr(atv, "atividade_id", ""))
                atv_cls = getattr(atv, "classe", "")
            if variavel in atv_id and atv_cls == "A+":
                roi_pp *= 1.3
                break

    return round(roi_pp, 2), delta_prazo


def _estimate_risk(tipo: str) -> str:
    """Estimativa de risco heurística por tipo de intervenção."""
    high_risk = {"novo_equipamento", "+20%"}
    low_risk = {"regime_9h", "+10%"}
    if tipo in high_risk:
        return "HIGH"
    if tipo in low_risk:
        return "LOW"
    return "MED"


def run_avaliacao_intervencoes(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    perfil: dict[str, Any] | None = None,
) -> SkillResult:
    """Popula 'intervention_assessments' no canônico.

    Pré-condição: cost_criticality_report (09) recomendado mas não obrigatório.
    """
    validacoes: list[ValidacaoItem] = []

    intervencoes: list[dict] = inputs.get("intervencoes_propostas", [])
    if not intervencoes:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ROI-01",
                status="ERRO",
                mensagem="'intervencoes_propostas' é obrigatório e não pode ser vazio",
            )
        )
        return SkillResult(canonical_in, validacoes)

    # Catálogo de effort: inputs override perfil override default
    effort_catalog: dict = _DEFAULT_EFFORT_CATALOG.copy()
    if perfil:
        effort_catalog.update(perfil.get("effort_catalog", {}))
    effort_catalog.update(inputs.get("effort_catalog", {}))

    custo_criticality = canonical_in.cost_criticality_report

    assessments = []
    for intv in intervencoes:
        intv_id = intv.get("intervencao_id", "int-?")
        variavel = intv.get("variavel", "")
        tipo = intv.get("tipo_perturbacao", "")
        descricao = intv.get("descricao", "")

        # ROI — simulações ou heurística
        roi_pp, delta_prazo = _estimate_roi_heuristic(variavel, tipo, custo_criticality)

        # Effort — catálogo externo
        effort = effort_catalog.get(tipo, {"nivel": "MED", "tipo": "desconhecido"})

        # Risk — heurística por tipo
        risk_nivel = _estimate_risk(tipo)
        risk_drivers = []
        if risk_nivel in ("MED", "HIGH"):
            risk_drivers.append("variabilidade_produtividade")
        if "equip" in tipo.lower() or "equipamento" in tipo.lower():
            risk_drivers.append("disponibilidade_equipamento")

        roi_class = _classify_roi(roi_pp)
        effort_nivel = effort.get("nivel", "MED")

        matrix_key = (roi_class, effort_nivel, risk_nivel)
        decision_class = _DECISION_CLASSES.get(matrix_key, "balanced_tradeoff")

        assessments.append(
            {
                "intervencao_id": intv_id,
                "variavel": variavel,
                "descricao": descricao,
                "tipo_perturbacao": tipo,
                "roi_margem_pp": roi_pp,
                "delta_prazo_dias": delta_prazo,
                "effort": effort,
                "risk": {
                    "nivel": risk_nivel,
                    "drivers": risk_drivers,
                },
                "matrix_position": f"{roi_class}_ROI / {effort_nivel}_EFFORT / {risk_nivel}_RISK",
                "decision_class": decision_class,
            }
        )

    novo = canonical_in.model_copy(update={"intervention_assessments": assessments})
    validacoes.append(
        ValidacaoItem(codigo="VAL-ROI-01", status="OK", mensagem=f"{len(assessments)} intervenções avaliadas")
    )
    return SkillResult(novo, validacoes)
