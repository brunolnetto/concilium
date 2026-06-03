"""Testes — SemanticIntent, Dimension, ExtractionConfidence, SemanticParseError."""

import pytest
from pydantic import ValidationError

from concilium.application.semantic.intent import (
    Dimension,
    ExtractionConfidence,
    SemanticIntent,
    SemanticParseError,
)

# ── Construção válida ─────────────────────────────────────────────────────────


def test_semantic_intent_construcao_completa():
    """SemanticIntent válido com todos os campos deve ser construído sem erros."""
    intent = SemanticIntent(
        raw_text="Escavação e transporte material 1a categoria, DMT 2000m, m3",
        scope_item_id="item-01",
        domain="earthwork",
        activity_type="cut_fill",
        unit="m3",
        dimensions=[Dimension(name="dmt", value=2000.0, unit="m")],
        qualifiers=[],
        materials=[],
        extraction_confidence=ExtractionConfidence(
            domain=0.9,
            activity_type=0.95,
            unit=0.99,
            dimensions=0.85,
            materials=0.0,
        ),
    )
    assert intent.unit == "m3"
    assert intent.domain == "earthwork"
    assert intent.activity_type == "cut_fill"
    assert len(intent.dimensions) == 1
    assert intent.dimensions[0].name == "dmt"
    assert intent.raw_text.startswith("Escavação")


def test_semantic_intent_campo_raw_text_preservado():
    """raw_text deve ser preservado intacto — incluindo caracteres especiais."""
    raw = "Coletor DN300 em manilha cerâmica — abertura, assentamento, reaterro"
    intent = SemanticIntent(
        raw_text=raw,
        scope_item_id="item-coletor",
        domain="drainage",
        activity_type="pipe_collector",
        unit="m",
        extraction_confidence=ExtractionConfidence(domain=0.9, activity_type=0.9, unit=0.9, dimensions=0.5),
    )
    assert intent.raw_text == raw


def test_semantic_intent_dimension_value_helper():
    """dimension_value e has_dimension devem funcionar corretamente."""
    intent = SemanticIntent(
        raw_text="base BGTC 15cm",
        scope_item_id="bgtc-01",
        domain="pavement",
        activity_type="base_course",
        unit="m3",
        dimensions=[Dimension(name="thickness", value=15.0, unit="cm")],
        extraction_confidence=ExtractionConfidence(domain=0.8, activity_type=0.8, unit=0.9, dimensions=0.8),
    )
    assert intent.has_dimension("thickness")
    assert intent.dimension_value("thickness") == 15.0
    assert not intent.has_dimension("dmt")
    assert intent.dimension_value("dmt") is None


def test_semantic_intent_missing_attributes_explicito():
    """missing_attributes deve listar campos ausentes explicitamente."""
    intent = SemanticIntent(
        raw_text="Algum serviço de pavimento sem espessura",
        scope_item_id="item-sem-esp",
        domain="pavement",
        activity_type="base_course",
        unit="m3",
        missing_attributes=["thickness"],
        extraction_confidence=ExtractionConfidence(domain=0.7, activity_type=0.7, unit=0.9, dimensions=0.2),
    )
    assert "thickness" in intent.missing_attributes


def test_semantic_intent_campo_extra_forbid():
    """SemanticIntent com campo desconhecido deve rejeitar (extra='forbid')."""
    with pytest.raises(ValidationError):
        SemanticIntent(
            raw_text="x",
            scope_item_id="s",
            domain="earthwork",
            activity_type="cut_fill",
            unit="m3",
            extraction_confidence=ExtractionConfidence(domain=0.5, activity_type=0.5, unit=0.5, dimensions=0.5),
            campo_desconhecido="x",  # deve falhar
        )


# ── SemanticParseError ────────────────────────────────────────────────────────


def test_semantic_parse_error_missing_unit():
    """SemanticParseError deve ter reason e raw_text acessíveis."""
    err = SemanticParseError("Serviço de terraplanagem", "missing_unit", missing=["unit"])
    assert err.reason == "missing_unit"
    assert "missing_unit" in str(err)
    assert err.missing == ["unit"]


def test_semantic_parse_error_mensagem_trunca_texto_longo():
    """raw_text longo deve ser truncado a 120 chars na exceção."""
    texto_longo = "x" * 200
    err = SemanticParseError(texto_longo, "missing_unit")
    assert len(err.raw_text) == 120


def test_semantic_parse_error_eh_exception():
    """SemanticParseError deve ser propagável como Exception."""
    with pytest.raises(SemanticParseError) as exc_info:
        raise SemanticParseError("texto bruto", "ambiguous_activity")
    assert exc_info.value.reason == "ambiguous_activity"


# ── ExtractionConfidence ──────────────────────────────────────────────────────


def test_extraction_confidence_values_validos():
    """Confiança entre 0.0 e 1.0 é válida."""
    conf = ExtractionConfidence(domain=1.0, activity_type=0.0, unit=0.5, dimensions=0.75)
    assert conf.domain == 1.0
    assert conf.activity_type == 0.0


def test_extraction_confidence_valor_fora_do_range():
    """Confiança fora de [0, 1] deve falhar na validação."""
    with pytest.raises(ValidationError):
        ExtractionConfidence(
            domain=1.5,  # > 1.0 — inválido
            activity_type=0.0,
            unit=0.5,
            dimensions=0.75,
        )
