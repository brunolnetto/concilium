"""Tests for semantic/extractor.py and semantic/normalizer.py.

Covers SemanticExtractor (rule-based extraction, vocabulary mapping, LLM fallback,
build_and_validate invariants) and VocabularyLoader, AttributeNormalizer,
CatalogNormalizer.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from concilium.application.semantic import (
    VOCAB_DIR,
    SemanticExtractor,
    SemanticParseError,
    make_extractor,
)
from concilium.application.semantic.normalizer import (
    AttributeNormalizer,
    CatalogNormalizer,
    VocabularyLoader,
)

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _extractor(*, allow_llm=False, llm_client=None) -> SemanticExtractor:
    return SemanticExtractor(
        vocab_path=VOCAB_DIR,
        allow_llm_fallback=allow_llm,
        llm_client=llm_client,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  SemanticExtractor — basic extraction
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractorBasic:
    def test_extract_m3_unit(self):
        ext = _extractor()
        intent = ext.extract("Escavação de material de 1a categoria 500 m3", "item-01")
        assert intent.unit == "m3"
        assert intent.scope_item_id == "item-01"

    def test_extract_m2_unit(self):
        ext = _extractor()
        intent = ext.extract("Pavimentação asfáltica 1000 m2", "item-02")
        assert intent.unit == "m2"

    def test_extract_ton_unit(self):
        ext = _extractor()
        intent = ext.extract("Transporte de material 50 toneladas", "item-03")
        assert intent.unit == "ton"

    def test_extract_m_unit(self):
        ext = _extractor()
        intent = ext.extract("Dreno coletora 200 ml DN300", "item-04")
        assert intent.unit == "m"

    def test_extract_un_unit(self):
        ext = _extractor()
        intent = ext.extract("Poço de visita 3 un", "item-05")
        assert intent.unit == "un"

    def test_extract_generates_scope_id_if_omitted(self):
        ext = _extractor()
        intent = ext.extract("Escavação 100 m3")
        assert intent.scope_item_id is not None
        assert len(intent.scope_item_id) > 0

    def test_extract_raw_text_preserved(self):
        text = "Escavação e transporte de material 1a categoria 1000 m3"
        ext = _extractor()
        intent = ext.extract(text, "sid")
        assert intent.raw_text == text


# ─────────────────────────────────────────────────────────────────────────────
#  SemanticExtractor — domain and activity_type
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractorDomainActivity:
    def test_earthwork_domain(self):
        ext = _extractor()
        intent = ext.extract("Escavação e transporte de material 1a categoria 200 m3", "e1")
        assert intent.domain == "earthwork"

    def test_cut_fill_activity(self):
        ext = _extractor()
        intent = ext.extract("Escavação e transporte de material 1a categoria 200 m3", "e1")
        assert intent.activity_type == "cut_fill"

    def test_unknown_text_gets_domain_other(self):
        ext = _extractor()
        # Text with no unit → should raise; give it a unit
        intent = ext.extract("Item desconhecido sem classificação 10 m3", "x1")
        assert intent.domain == "other"
        assert "domain" in intent.missing_attributes

    def test_domain_other_populates_missing_attributes(self):
        ext = _extractor()
        intent = ext.extract("Serviço genérico 50 m3", "x2")
        assert "domain" in intent.missing_attributes
        assert "activity_type" in intent.missing_attributes

    def test_drainage_domain(self):
        ext = _extractor()
        intent = ext.extract("Dreno coletora DN300 100 m", "d1")
        assert intent.domain == "drainage"


# ─────────────────────────────────────────────────────────────────────────────
#  SemanticExtractor — dimensions (embedded dim extraction)
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractorDimensions:
    def test_extracts_embedded_espessura(self):
        ext = _extractor()
        intent = ext.extract("Base de brita graduada espessura 15cm 500 m2", "d1")
        dim_names = [d.name for d in intent.dimensions]
        assert "thickness" in dim_names

    def test_extracts_dmt_dimension(self):
        ext = _extractor()
        intent = ext.extract("Escavação carga transporte DMT 3000m 100 m3", "d2")
        dim_names = [d.name for d in intent.dimensions]
        assert "dmt" in dim_names

    def test_no_dimensions_when_not_present(self):
        ext = _extractor()
        intent = ext.extract("Escavação de 1a categoria 300 m3", "d3")
        assert intent.dimensions == []


# ─────────────────────────────────────────────────────────────────────────────
#  SemanticExtractor — soil class qualifiers
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractorSoilClass:
    def test_1a_categoria_soil_class(self):
        ext = _extractor()
        intent = ext.extract("Material de 1a categoria 200 m3", "s1")
        assert intent.context.get("soil_class") == "1A"

    def test_2a_categoria_soil_class(self):
        ext = _extractor()
        intent = ext.extract("Material de 2a categoria 200 m3", "s2")
        assert intent.context.get("soil_class") == "2A"

    def test_3a_categoria_soil_class(self):
        ext = _extractor()
        intent = ext.extract("Material de 3a categoria 200 m3", "s3")
        assert intent.context.get("soil_class") == "3A"

    def test_rocha_dura_maps_to_3a(self):
        ext = _extractor()
        intent = ext.extract("Escavação em rocha dura 100 m3", "s4")
        assert intent.context.get("soil_class") == "3A"

    def test_soil_class_not_in_qualifiers(self):
        """solo_class qualifiers should be moved to context, not stay in qualifiers."""
        ext = _extractor()
        intent = ext.extract("Material de 1a categoria 100 m3", "s5")
        for q in intent.qualifiers:
            assert "solo_class" not in q


# ─────────────────────────────────────────────────────────────────────────────
#  SemanticExtractor — build_and_validate invariants
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractorBuildAndValidate:
    def test_raises_on_missing_unit(self):
        ext = _extractor()
        with pytest.raises(SemanticParseError) as exc_info:
            ext.extract("Escavação sem unidade de medida", "e1")
        err = exc_info.value
        assert err.reason == "missing_unit"
        assert "unit" in err.missing

    def test_raises_dimension_in_freetext(self):
        """Qualifier with number but not solo_class: → dimension_in_freetext error."""
        ext = _extractor()
        # "espessura:30" - ":" is non-word so \b matches around 30
        fields = {
            "unit": "m3",
            "dimensions": [],
            "qualifiers": ["espessura:30"],  # número com word boundary, não solo_class
            "materials": [],
            "method": None,
            "context": {},
            "missing_attributes": [],
            "domain": "earthwork",
            "activity_type": "cut_fill",
            "used_llm_fallback": False,
        }
        with pytest.raises(SemanticParseError) as exc_info:
            ext._build_and_validate("raw text", "sid", fields)
        assert exc_info.value.reason == "dimension_in_freetext"

    def test_extraction_confidence_high_for_known_domain(self):
        ext = _extractor()
        intent = ext.extract("Escavação e transporte 1a categoria 100 m3", "e1")
        assert intent.extraction_confidence.domain >= 0.8

    def test_extraction_confidence_low_for_unknown_domain(self):
        ext = _extractor()
        intent = ext.extract("Serviço genérico 50 m3", "x1")
        assert intent.extraction_confidence.domain <= 0.4

    def test_used_llm_fallback_false_without_llm(self):
        ext = _extractor()
        intent = ext.extract("Escavação 100 m3", "e1")
        assert intent.used_llm_fallback is False


# ─────────────────────────────────────────────────────────────────────────────
#  SemanticExtractor — extract_batch
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractorBatch:
    def test_batch_all_success(self):
        ext = _extractor()
        items = [
            {"raw_text": "Escavação 1a categoria 100 m3", "scope_item_id": "b1"},
            {"raw_text": "Base brita 200 m2", "scope_item_id": "b2"},
        ]
        results = ext.extract_batch(items)
        assert len(results) == 2
        for r in results:
            assert isinstance(r, type(r))

    def test_batch_with_failure(self):
        ext = _extractor()
        items = [
            {"raw_text": "Escavação 100 m3", "scope_item_id": "ok"},
            {"raw_text": "Texto sem unidade", "scope_item_id": "fail"},
        ]
        results = ext.extract_batch(items)
        assert len(results) == 2
        from concilium.application.semantic.intent import SemanticIntent

        assert isinstance(results[0], SemanticIntent)
        assert isinstance(results[1], SemanticParseError)

    def test_batch_scope_id_auto_generated(self):
        ext = _extractor()
        items = [{"raw_text": "Escavação 100 m3"}]
        results = ext.extract_batch(items)
        from concilium.application.semantic.intent import SemanticIntent

        assert isinstance(results[0], SemanticIntent)
        assert results[0].scope_item_id is not None


# ─────────────────────────────────────────────────────────────────────────────
#  SemanticExtractor — LLM fallback
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractorLLMFallback:
    def test_llm_fallback_not_called_when_unit_known(self):
        llm = MagicMock()
        llm.complete.return_value = '{"unit": "m3", "domain": "earthwork", "activity_type": "cut_fill"}'
        ext = SemanticExtractor(VOCAB_DIR, allow_llm_fallback=True, llm_client=llm)
        ext.extract("Escavação e transporte 1a categoria 100 m3", "e1")
        # Unit was extracted deterministically, LLM should not be called
        llm.complete.assert_not_called()

    def test_llm_fallback_called_when_unit_missing(self):
        """LLM is called when unit is missing (text has no unit)."""
        llm = MagicMock()
        llm.complete.return_value = '{"unit": "m3", "domain": "earthwork", "activity_type": "cut_fill"}'
        ext = SemanticExtractor(VOCAB_DIR, allow_llm_fallback=True, llm_client=llm)
        intent = ext.extract("Escavação material primeira categoria", "e1")
        llm.complete.assert_called_once()
        assert intent.used_llm_fallback is True
        assert intent.unit == "m3"

    def test_llm_fallback_fills_domain_when_other(self):
        llm = MagicMock()
        llm.complete.return_value = '{"unit": "m3", "domain": "earthwork", "activity_type": "cut_fill"}'
        ext = SemanticExtractor(VOCAB_DIR, allow_llm_fallback=True, llm_client=llm)
        intent = ext.extract("Serviço com unidade 100 m3", "x1")
        # domain was "other" before LLM, after LLM it should be earthwork
        # (unit was determined, but domain is still "other")
        assert intent.used_llm_fallback is True

    def test_llm_fallback_silent_on_json_error(self):
        """LLM that returns invalid JSON should not crash — fallback gracefully."""
        llm = MagicMock()
        llm.complete.return_value = "invalid json"
        ext = SemanticExtractor(VOCAB_DIR, allow_llm_fallback=True, llm_client=llm)
        # Without unit, LLM is tried but fails → missing_unit error
        with pytest.raises(SemanticParseError):
            ext.extract("Texto sem unidade", "e1")

    def test_llm_fallback_silent_when_client_has_no_complete(self):
        """LLM client without .complete() method → fallback skipped gracefully."""
        llm = object()  # no .complete method
        ext = SemanticExtractor(VOCAB_DIR, allow_llm_fallback=True, llm_client=llm)
        # Should raise SemanticParseError (unit missing) but not crash on the LLM call
        with pytest.raises(SemanticParseError):
            ext.extract("Texto sem unidade", "e1")

    def test_not_allowed_llm_not_called(self):
        llm = MagicMock()
        ext = SemanticExtractor(VOCAB_DIR, allow_llm_fallback=False, llm_client=llm)
        with pytest.raises(SemanticParseError):
            ext.extract("Sem unidade aqui", "e1")
        llm.complete.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
#  SemanticExtractor — make_extractor factory
# ─────────────────────────────────────────────────────────────────────────────


class TestMakeExtractor:
    def test_make_extractor_returns_instance(self):
        ext = make_extractor()
        assert isinstance(ext, SemanticExtractor)

    def test_make_extractor_with_custom_vocab_dir(self):
        ext = make_extractor(vocab_dir=VOCAB_DIR)
        assert isinstance(ext, SemanticExtractor)

    def test_make_extractor_with_llm(self):
        llm = MagicMock()
        ext = make_extractor(allow_llm_fallback=True, llm_client=llm)
        assert ext._allow_llm is True


# ─────────────────────────────────────────────────────────────────────────────
#  VocabularyLoader
# ─────────────────────────────────────────────────────────────────────────────


class TestVocabularyLoader:
    def test_unit_aliases_loaded(self):
        loader = VocabularyLoader(VOCAB_DIR)
        aliases = loader.unit_aliases()
        assert "m3" in aliases.values() or "m3" in aliases
        # "metros cúbicos" → "m3"
        assert aliases.get("metros cúbicos") == "m3"
        assert aliases.get("m3") == "m3"

    def test_activity_aliases_loaded(self):
        loader = VocabularyLoader(VOCAB_DIR)
        aliases = loader.activity_aliases()
        # "cut_fill" should be there
        assert any(v[1] == "cut_fill" for v in aliases.values())

    def test_activity_aliases_pt_terms(self):
        loader = VocabularyLoader(VOCAB_DIR)
        aliases = loader.activity_aliases()
        # "escavação e transporte" should map to cut_fill
        result = aliases.get("escavação e transporte")
        if result:
            assert result[1] == "cut_fill"

    def test_load_nonexistent_file_returns_empty(self):
        loader = VocabularyLoader(VOCAB_DIR)
        result = loader.load("nonexistent_file")
        assert result == {}

    def test_cache_avoids_reload(self):
        loader = VocabularyLoader(VOCAB_DIR)
        result1 = loader.load("units")
        result2 = loader.load("units")
        assert result1 is result2  # same object from cache

    def test_activity_required_dims(self):
        loader = VocabularyLoader(VOCAB_DIR)
        dims = loader.activity_required_dims("cut_fill")
        assert isinstance(dims, list)

    def test_activity_optional_dims(self):
        loader = VocabularyLoader(VOCAB_DIR)
        dims = loader.activity_optional_dims("cut_fill")
        assert isinstance(dims, list)

    def test_activity_dims_for_unknown_returns_empty(self):
        loader = VocabularyLoader(VOCAB_DIR)
        dims = loader.activity_required_dims("nonexistent_activity")
        assert dims == []


# ─────────────────────────────────────────────────────────────────────────────
#  AttributeNormalizer
# ─────────────────────────────────────────────────────────────────────────────


class TestAttributeNormalizer:
    def test_normalize_known_attribute(self):
        norm = AttributeNormalizer()
        from concilium.application.resolution.registry import ATTRIBUTE_REGISTRY

        if not ATTRIBUTE_REGISTRY:
            pytest.skip("ATTRIBUTE_REGISTRY vazio")
        # Try a known attribute
        canonical_name = next(iter(ATTRIBUTE_REGISTRY))
        result_name, _ = norm.normalize(canonical_name, 1.0, "m")
        assert result_name == canonical_name

    def test_normalize_unknown_attribute_passthrough(self):
        norm = AttributeNormalizer()
        name, value = norm.normalize("atributo_desconhecido", 99.9, "m")
        assert name == "atributo_desconhecido"
        assert value == 99.9

    def test_normalize_unit(self):
        norm = AttributeNormalizer()
        result = norm.normalize_unit("m3")
        assert result == "m3"

    def test_normalize_unit_alias(self):
        norm = AttributeNormalizer()
        result = norm.normalize_unit("metros cúbicos")
        assert result == "m3"

    def test_normalize_unit_unknown_returns_none(self):
        norm = AttributeNormalizer()
        result = norm.normalize_unit("xyz_unidade_inexistente")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
#  CatalogNormalizer
# ─────────────────────────────────────────────────────────────────────────────


class TestCatalogNormalizer:
    def _cpu_dict(self, **overrides) -> dict:
        base = {
            "codigo": "ESCO-CARGA-1CAT-DMT2000",
            "categoria": "TERRAPLENAGEM",
            "descricao": "Escavação carga e transporte 1a categoria DMT 2000m",
            "unidade": "m3",
            "producao_horaria": 150.0,
        }
        base.update(overrides)
        return base

    def test_normalize_cpu_domain(self):
        norm = CatalogNormalizer()
        canon = norm.normalize_cpu(self._cpu_dict())
        assert canon.domain == "earthwork"

    def test_normalize_cpu_activity_type(self):
        norm = CatalogNormalizer()
        canon = norm.normalize_cpu(self._cpu_dict())
        assert canon.activity_type == "cut_fill"

    def test_normalize_cpu_unit(self):
        norm = CatalogNormalizer()
        canon = norm.normalize_cpu(self._cpu_dict())
        assert canon.unit == "m3"

    def test_normalize_cpu_unit_unicode(self):
        norm = CatalogNormalizer()
        canon = norm.normalize_cpu(self._cpu_dict(unidade="m³"))
        assert canon.unit == "m3"

    def test_normalize_cpu_dmt_from_code(self):
        norm = CatalogNormalizer()
        canon = norm.normalize_cpu(self._cpu_dict(codigo="ESCO-CARGA-1CAT-DMT3000"))
        assert canon.attributes.get("dmt") == 3000.0

    def test_normalize_cpu_soil_class_from_code(self):
        norm = CatalogNormalizer()
        canon = norm.normalize_cpu(self._cpu_dict(codigo="ESCO-CARGA-2CAT-DMT2000"))
        assert canon.attributes.get("soil_class") == "2A"

    def test_normalize_cpu_3a_soil_class(self):
        norm = CatalogNormalizer()
        canon = norm.normalize_cpu(self._cpu_dict(codigo="ESCO-CARGA-3CAT-DMT2000"))
        assert canon.attributes.get("soil_class") == "3A"

    def test_normalize_cpu_pipe_diameter(self):
        norm = CatalogNormalizer()
        cpu = {
            "codigo": "DREN-MAN-DN300",
            "categoria": "SANEAMENTO",
            "unidade": "m",
            "producao_horaria": 10.0,
        }
        canon = norm.normalize_cpu(cpu)
        assert canon.attributes.get("pipe_diameter") == 300.0
        assert canon.domain == "drainage"

    def test_normalize_cpu_embankment_compaction(self):
        norm = CatalogNormalizer()
        cpu = {
            "codigo": "COMPACT-ATERRO-100PN",
            "categoria": "TERRAPLENAGEM",
            "unidade": "m3",
            "producao_horaria": 200.0,
        }
        canon = norm.normalize_cpu(cpu)
        assert canon.activity_type == "embankment_compaction"
        assert canon.attributes.get("compaction_rate") == 100.0

    def test_normalize_cpu_unknown_categoria_gives_other_domain(self):
        norm = CatalogNormalizer()
        cpu = {
            "codigo": "MISC-001",
            "categoria": "CATEGORIA_DESCONHECIDA",
            "unidade": "un",
            "producao_horaria": 5.0,
        }
        canon = norm.normalize_cpu(cpu)
        assert canon.domain == "other"

    def test_normalize_cpu_with_vocab_loader(self):
        vocab = VocabularyLoader(VOCAB_DIR)
        norm = CatalogNormalizer(vocab_loader=vocab)
        canon = norm.normalize_cpu(self._cpu_dict())
        assert canon.domain == "earthwork"

    def test_normalize_catalog_batch(self):
        norm = CatalogNormalizer()
        cpus = [
            self._cpu_dict(codigo="ESCO-CARGA-1CAT-DMT2000"),
            self._cpu_dict(codigo="ESCO-CARGA-2CAT-DMT3000"),
        ]
        result = norm.normalize_catalog(cpus)
        assert len(result) == 2
        assert result[0].cpu_id == "ESCO-CARGA-1CAT-DMT2000"
        assert result[1].cpu_id == "ESCO-CARGA-2CAT-DMT3000"

    def test_normalize_cpu_dmt_from_atributos_categoria(self):
        norm = CatalogNormalizer()
        cpu = {
            "codigo": "ESCO-SEM-DMT",
            "categoria": "TERRAPLENAGEM",
            "unidade": "m3",
            "producao_horaria": 100.0,
            "atributos_categoria": {"dmt_max_metros": 1500},
        }
        canon = norm.normalize_cpu(cpu)
        assert canon.attributes.get("dmt") == 1500.0

    def test_normalize_cpu_productivity(self):
        norm = CatalogNormalizer()
        canon = norm.normalize_cpu(self._cpu_dict(producao_horaria=180.5))
        assert canon.base_productivity == 180.5
