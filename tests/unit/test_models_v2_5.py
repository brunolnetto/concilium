from datetime import UTC, date, datetime

from concilium.domain.models import ConstraintViolation, DecisionVariables
from concilium.domain.models.canonical import CanonicalModel, Coordenadas, Meta, Projeto, RegimeTrabalho


def test_decision_variables_roundtrip():
    dv = DecisionVariables(
        dv1_crew_template={"ativ_1": "template_01"},
        dv2_num_equipes={"ativ_1": {"2026-06": 2}},
        dv3_start_offset={"ativ_1": 5},
        dv4_indirect_policy="standard",
    )

    assert dv.dv1_crew_template["ativ_1"] == "template_01"
    assert dv.dv2_num_equipes["ativ_1"]["2026-06"] == 2
    assert dv.dv3_start_offset["ativ_1"] == 5
    assert dv.dv4_indirect_policy == "standard"


def test_constraint_violation_defaults():
    cv = ConstraintViolation(
        code="VAL-POOL-01",
        status="ERRO",
        magnitude=1.5,
        affected_items=["periodo_3"],
        remediation_hint="reduzir num_equipes no período 3",
    )
    assert cv.code == "VAL-POOL-01"
    assert cv.status == "ERRO"
    assert cv.magnitude == 1.5
    assert "periodo_3" in cv.affected_items
    assert isinstance(cv.timestamp, datetime)


def test_canonical_model_has_decision_variables_field():
    """CanonicalModel deve aceitar decision_variables como campo opcional (v2.5)."""
    can = CanonicalModel(
        meta=Meta(gerado_em=datetime.now(UTC), contexto_id="test"),
        projeto=Projeto(
            id="p1",
            nome="proj",
            tipo_obra="terraplenagem",
            localizacao="x",
            coordenadas=Coordenadas(lat=0.0, lng=0.0),
            regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
            data_inicio=date(2026, 6, 1),
            data_termino=date(2026, 7, 31),
            snapshot_catalogo_id="s",
            snapshot_perfil_id="s",
        ),
    )
    assert can.decision_variables is None


def test_decision_variables_embedded_in_canonical():
    """CanonicalModel deve persitir DecisionVariables quando fornecido."""
    dv = DecisionVariables(dv4_indirect_policy="lean")
    can = CanonicalModel(
        meta=Meta(gerado_em=datetime.now(UTC), contexto_id="test"),
        projeto=Projeto(
            id="p1",
            nome="proj",
            tipo_obra="terraplenagem",
            localizacao="x",
            coordenadas=Coordenadas(lat=0.0, lng=0.0),
            regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
            data_inicio=date(2026, 6, 1),
            data_termino=date(2026, 7, 31),
            snapshot_catalogo_id="s",
            snapshot_perfil_id="s",
        ),
        decision_variables=dv,
    )
    assert can.decision_variables is not None
    assert can.decision_variables.dv4_indirect_policy == "lean"
