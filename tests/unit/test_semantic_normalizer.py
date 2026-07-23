"""Coverage batch B — targets runtime.py, 04-cronograma, 05-equipes-e-alocacao,
06-resultado-financeiro/_precificacao, 07-diagnostico-criticidade, and semantic/normalizer edge cases.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch

from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    Meta,
    Projeto,
    RegimeTrabalho,
)


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")

def _make_proj(data_inicio="2026-06-01", data_termino="2026-07-31"):
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=-3.0, lng=-38.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 7, 31),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )

def _minimal_canonical(**kw):
    return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), **kw)

def _load_skill_module(skill_id: str) -> object:
    import concilium.application.skills as _skills_pkg

    return _skills_pkg._load_skill_module(skill_id)


# ══ semantic/normalizer.py ════════════════════════════════════════════════════


class TestNormalizerEdgeCases:
    def test_vocabulary_loader_no_yaml_flag(self, tmp_path):
        """When _HAS_YAML is False and file exists → return {} (line 72)."""
        from concilium.application.semantic.normalizer import VocabularyLoader

        # Create a units.yaml in tmp_path so path.exists() is True
        (tmp_path / "units.yaml").write_text("m3:\n  aliases: [cubic_meter]\n", encoding="utf-8")
        loader = VocabularyLoader(tmp_path)
        import concilium.application.semantic.normalizer as norm_mod

        with patch.object(norm_mod, "_HAS_YAML", False):
            result = loader.load("units")
        assert result == {}

    def test_unit_aliases_non_dict_info(self, tmp_path):
        """unit_aliases with non-dict info value → continue (line 84)."""
        from concilium.application.semantic.normalizer import VocabularyLoader

        # Create units.yaml where one entry has a non-dict value (string)
        yaml_content = "m3:\n  aliases:\n    - cubic_meter\nbad_unit: not_a_dict\n"
        (tmp_path / "units.yaml").write_text(yaml_content, encoding="utf-8")
        loader = VocabularyLoader(tmp_path)
        result = loader.unit_aliases()
        # "bad_unit" should be skipped; "m3" should be mapped
        assert "bad_unit" not in result
        assert "m3" in result

    def test_activity_aliases_non_dict_domain(self, tmp_path):
        """activity_aliases with non-dict domain value → continue (line 96)."""
        from concilium.application.semantic.normalizer import VocabularyLoader

        # activities.yaml where one domain maps to a string (not dict)
        yaml_content = (
            "bad_domain: not_a_dict\ngood_domain:\n  cut_fill:\n    aliases_pt: [escavacao]\n    aliases_en: [cut]\n"
        )
        (tmp_path / "activities.yaml").write_text(yaml_content, encoding="utf-8")
        loader = VocabularyLoader(tmp_path)
        result = loader.activity_aliases()
        # bad_domain skipped; good_domain entries present
        assert "escavacao" in result or "cut_fill" in result

    def test_activity_aliases_non_dict_info(self, tmp_path):
        """activity_aliases with non-dict activity info → continue (line 99)."""
        from concilium.application.semantic.normalizer import VocabularyLoader

        yaml_content = (
            "domain1:\n  good_act:\n    aliases_pt: [boa_atividade]\n    aliases_en: []\n  bad_act: just_a_string\n"
        )
        (tmp_path / "activities.yaml").write_text(yaml_content, encoding="utf-8")
        loader = VocabularyLoader(tmp_path)
        result = loader.activity_aliases()
        # bad_act skipped; good_act present
        assert "boa_atividade" in result
        assert "bad_act" not in result

    def test_activity_optional_dims_not_found(self, tmp_path):
        """activity_optional_dims for unknown type → return [] (line 120)."""
        from concilium.application.semantic.normalizer import VocabularyLoader

        loader = VocabularyLoader(tmp_path)
        result = loader.activity_optional_dims("UNKNOWN_ACTIVITY_TYPE_XYZ")
        assert result == []

    def test_attribute_normalizer_exception_fallback(self):
        """normalizer function raises → except Exception → normalized = raw_value (lines 147-148)."""
        from concilium.application.semantic.normalizer import AttributeNormalizer

        n = AttributeNormalizer()
        # "thickness" is in ATTRIBUTE_REGISTRY; passing object() will cause normalizer to raise TypeError
        # resolve_alias("thickness") should return "thickness" (not None), so we enter the try block
        name, val = n.normalize("thickness", object(), "")
        assert name == "thickness"
        # raw_value (the object) is returned since the normalizer threw
        assert not isinstance(val, (int, float))

    def test_infer_activity_type_prefix_match(self):
        """CPU code is a prefix-match (not exact) → return act (line 249)."""
        from concilium.application.semantic.normalizer import _infer_activity_type

        # "ESCO-CARGA-1CAT-DMT2000" is in the map; append suffix for prefix-match
        result = _infer_activity_type("ESCO-CARGA-1CAT-DMT2000-EXTENDED")
        assert result == "cut_fill"

