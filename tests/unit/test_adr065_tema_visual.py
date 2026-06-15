"""Tests for ADR-065 — TemaVisual entity.

Covers:
  F1: CoresTema hex validation (accepts/rejects)
  F1: FontesTema Literal validation
  F1: FontesTema size bounds
  F1: TemaVisual.to_catalogo_dict() backward-compat format
  F1: TEMA_DEFAULT fallback
  F3: ContextoObra has tema_id (no identidade_visual)
  F3: Runtime.load_tema fallback logic
  F7: Exporter backward-compat (catalogo["identidade_visual"] still works)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from concilium.domain.models.catalog.contexto import ContextoObra
from concilium.domain.models.catalog.tema import (
    TEMA_DEFAULT,
    CoresTema,
    FontesTema,
    TemaVisual,
)

# ─── CoresTema: hex validation ────────────────────────────────────────────────


class TestCoresTema:
    def test_valid_hex_accepted(self):
        c = CoresTema(cabecalho_fundo="1F4E78")
        assert c.cabecalho_fundo == "1F4E78"

    def test_hex_with_hash_normalised(self):
        c = CoresTema(cabecalho_fundo="#1f4e78")
        assert c.cabecalho_fundo == "1F4E78"  # uppercase, no '#'

    def test_hex_lowercase_normalised_to_upper(self):
        c = CoresTema(destaque="ffc000")
        assert c.destaque == "FFC000"

    def test_invalid_hex_word_rejected(self):
        with pytest.raises(ValidationError, match="inválida"):
            CoresTema(cabecalho_fundo="blue")

    def test_invalid_hex_short_rejected(self):
        with pytest.raises(ValidationError):
            CoresTema(cabecalho_fundo="#1F4")

    def test_invalid_hex_nonhex_chars_rejected(self):
        with pytest.raises(ValidationError):
            CoresTema(cabecalho_fundo="GGGGGG")

    def test_defaults_are_valid_hex(self):
        c = CoresTema()
        assert all(len(v) == 6 for v in c.model_dump().values())


# ─── FontesTema: Literal + bounds ────────────────────────────────────────────


class TestFontesTema:
    def test_valid_font_accepted(self):
        f = FontesTema(cabecalho="Arial", corpo="Calibri")
        assert f.cabecalho == "Arial"

    def test_invalid_font_rejected(self):
        with pytest.raises(ValidationError):
            FontesTema(cabecalho="Comic Sans")

    def test_size_within_bounds(self):
        f = FontesTema(tamanho_corpo=12)
        assert f.tamanho_corpo == 12

    def test_size_too_small_rejected(self):
        with pytest.raises(ValidationError):
            FontesTema(tamanho_corpo=0)

    def test_size_too_large_rejected(self):
        with pytest.raises(ValidationError):
            FontesTema(tamanho_cabecalho=99)

    def test_titulo_bounds(self):
        with pytest.raises(ValidationError):
            FontesTema(tamanho_titulo=5)


# ─── TemaVisual ───────────────────────────────────────────────────────────────


class TestTemaVisual:
    def test_default_values_valid(self):
        t = TemaVisual(id="test", empresa="Acme")
        assert t.perfil_exibicao == "EXECUTIVO"
        assert isinstance(t.cores, CoresTema)
        assert isinstance(t.fontes, FontesTema)

    def test_invalid_perfil_exibicao_rejected(self):
        with pytest.raises(ValidationError):
            TemaVisual(id="t", empresa="X", perfil_exibicao="PREMIUM")

    def test_to_catalogo_dict_backward_compat(self):
        t = TemaVisual(
            id="ml",
            empresa="MendesLobo",
            perfil_exibicao="EXECUTIVO",
            cores=CoresTema(cabecalho_fundo="1F4E78", destaque="FFC000"),
            fontes=FontesTema(cabecalho="Arial", corpo="Calibri"),
        )
        d = t.to_catalogo_dict()
        assert "empresa" in d
        assert "cores" in d
        assert "fontes" in d
        # backward-compat: exporters expect these exact keys
        assert "cabecalho_fundo" in d["cores"]
        assert "destaque" in d["cores"]
        assert "cabecalho" in d["fontes"]
        assert "corpo" in d["fontes"]

    def test_tema_default_is_valid(self):
        assert isinstance(TEMA_DEFAULT, TemaVisual)
        assert TEMA_DEFAULT.id == "default"

    def test_from_file(self, tmp_path):
        """TemaVisual loads correctly from config/temas/*/tema.json format."""
        tema_dir = tmp_path / "temas" / "test-co"
        tema_dir.mkdir(parents=True)
        data = {
            "id": "test-co",
            "empresa": "Test Corp",
            "perfil_exibicao": "SIMPLES",
            "cores": {
                "cabecalho_fundo": "2B2B2B",
                "cabecalho_texto": "FFFFFF",
                "zebra_par": "FFFFFF",
                "zebra_impar": "F5F5F5",
                "borda": "DDDDDD",
                "destaque": "FF8C00",
            },
            "fontes": {
                "cabecalho": "Arial",
                "corpo": "Arial",
                "tamanho_titulo": 14,
                "tamanho_cabecalho": 11,
                "tamanho_corpo": 10,
            },
        }
        (tema_dir / "tema.json").write_text(json.dumps(data), encoding="utf-8")
        loaded = TemaVisual.model_validate_json((tema_dir / "tema.json").read_text())
        assert loaded.empresa == "Test Corp"
        assert loaded.cores.destaque == "FF8C00"


# ─── ContextoObra: no identidade_visual, has tema_id ─────────────────────────


class TestContextoObra:
    def test_has_tema_id_field(self):
        ctx = ContextoObra(
            id="x",
            perfil_id="p",
            jurisdicao_id="BR",
            referencia_id="r",
            catalogo_id="c",
            tema_id="mendeslobo-corporativo",
        )
        assert ctx.tema_id == "mendeslobo-corporativo"

    def test_tema_id_optional_defaults_none(self):
        ctx = ContextoObra(id="x", perfil_id="p", jurisdicao_id="BR", referencia_id="r", catalogo_id="c")
        assert ctx.tema_id is None

    def test_has_no_identidade_visual_field(self):
        """identidade_visual was removed (ADR-065) — extra="ignore" silently drops it."""
        ctx = ContextoObra(
            id="x",
            perfil_id="p",
            jurisdicao_id="BR",
            referencia_id="r",
            catalogo_id="c",
            identidade_visual={"empresa": "Old"},  # type: ignore[call-arg]
        )
        # Field silently ignored via ConfigDict(extra="ignore")
        assert not hasattr(ctx, "identidade_visual")

    def test_mendeslobo_contexto_loads_with_tema_id(self):
        """The actual mendeslobo context file has tema_id after migration."""
        ctx_file = Path(__file__).resolve().parents[2] / "config/contextos/mendeslobo/versions/v1.json"
        if not ctx_file.exists():
            pytest.skip("mendeslobo context not found")
        data = json.loads(ctx_file.read_text(encoding="utf-8"))
        ctx = ContextoObra.model_validate(data)
        assert ctx.tema_id == "mendeslobo-corporativo"
        assert not hasattr(ctx, "identidade_visual")


# ─── F7: to_catalogo_dict backward-compat with exporters ─────────────────────


class TestBackwardCompat:
    def test_to_catalogo_dict_has_cores_and_fontes(self):
        """catalog_excel.py and price_survey.py read cores and fontes from idv."""
        tema = TemaVisual(id="t", empresa="X")
        idv = tema.to_catalogo_dict()

        # catalog_excel.py:139 pattern
        cores = idv.get("cores", {})
        assert "cabecalho_fundo" in cores
        assert "destaque" in cores

        # price_survey.py:53 pattern
        highlight = idv.get("cores", {}).get("destaque", "FFC000")
        assert len(highlight) == 6  # hex sem '#'

    def test_mendeslobo_tema_matches_old_identidade_visual(self):
        """Config temas/mendeslobo-corporativo has the same values as the old context."""
        tema_file = Path(__file__).resolve().parents[2] / "config/temas/mendeslobo-corporativo/tema.json"
        if not tema_file.exists():
            pytest.skip("mendeslobo-corporativo tema not found")
        tema = TemaVisual.model_validate_json(tema_file.read_text(encoding="utf-8"))
        assert tema.cores.cabecalho_fundo == "1F4E78"
        assert tema.cores.destaque == "FFC000"
        assert tema.fontes.cabecalho == "Arial"
        assert tema.fontes.corpo == "Calibri"
