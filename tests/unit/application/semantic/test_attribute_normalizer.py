"""Testes — AttributeNormalizer e CatalogNormalizer."""

import pytest

from concilium.application.semantic.normalizer import AttributeNormalizer, CatalogNormalizer

# ── AttributeNormalizer ───────────────────────────────────────────────────────


class TestAttributeNormalizer:
    def setup_method(self):
        self.norm = AttributeNormalizer()

    def test_normaliza_mm_para_cm(self):
        """Espessura em mm deve ser convertida para cm."""
        canonical, value = self.norm.normalize("espessura", 150.0, "mm")
        assert canonical == "thickness"
        assert value == pytest.approx(15.0)

    def test_alias_resolution_espessura(self):
        """Alias 'espessura' deve mapear para canonical 'thickness'."""
        canonical, _ = self.norm.normalize("espessura", 20.0, "cm")
        assert canonical == "thickness"

    def test_passthrough_nome_desconhecido(self):
        """Nome não no registry deve passar sem transformação."""
        canonical, value = self.norm.normalize("atributo_nao_existe", 42.0)
        assert canonical == "atributo_nao_existe"
        assert value == 42.0

    def test_normaliza_dmt(self):
        """dmt_max_metros é alias para canonical 'dmt'."""
        canonical, value = self.norm.normalize("dmt_max_metros", 2000.0)
        assert canonical == "dmt"
        assert value == pytest.approx(2000.0)

    def test_normaliza_soil_class_uppercase(self):
        """soil_class deve ser convertida para uppercase."""
        canonical, value = self.norm.normalize("categoria_material", "1a")
        assert canonical == "soil_class"
        assert value == "1A"

    def test_normaliza_pipe_diameter_dn(self):
        """'dn' é alias para pipe_diameter."""
        canonical, _ = self.norm.normalize("dn", 300.0)
        assert canonical == "pipe_diameter"


# ── CatalogNormalizer ─────────────────────────────────────────────────────────


class TestCatalogNormalizer:
    def setup_method(self):
        self.norm = CatalogNormalizer()

    def _make_cpu(self, **kwargs) -> dict:
        """Cria dict mínimo de CPU para testes."""
        base = {
            "codigo": "TEST-CPU",
            "descricao": "CPU de teste",
            "unidade": "m3",
            "categoria": "TERRAPLENAGEM",
            "producao_horaria": 100.0,
        }
        base.update(kwargs)
        return base

    def test_normaliza_cpu_terraplenagem_corte(self):
        """CPU de escavação 1a cat DMT2000 deve normalizar corretamente."""
        cpu = self._make_cpu(
            codigo="ESCO-CARGA-1CAT-DMT2000",
            categoria="TERRAPLENAGEM",
            unidade="m3",
            producao_horaria=233.5,
            atributos_categoria={"dmt_min_metros": 0, "dmt_max_metros": 2000},
        )
        canonical = self.norm.normalize_cpu(cpu)
        assert canonical.cpu_id == "ESCO-CARGA-1CAT-DMT2000"
        assert canonical.domain == "earthwork"
        assert canonical.activity_type == "cut_fill"
        assert canonical.unit == "m3"
        assert canonical.attributes.get("dmt") == pytest.approx(2000.0)
        assert canonical.attributes.get("soil_class") == "1A"

    def test_normaliza_cpu_pavimentacao(self):
        """CPU de base BGTC deve ter domain pavement."""
        cpu = self._make_cpu(
            codigo="PAV-BASE-BGTC",
            categoria="PAVIMENTACAO",
            unidade="m3",
        )
        canonical = self.norm.normalize_cpu(cpu)
        assert canonical.domain == "pavement"
        assert canonical.activity_type == "base_course"

    def test_normaliza_cpu_drenagem_coletor(self):
        """CPU DN300 deve ter pipe_diameter inferido do código."""
        cpu = self._make_cpu(
            codigo="DREN-MAN-DN300",
            categoria="SANEAMENTO",
            unidade="m",
        )
        canonical = self.norm.normalize_cpu(cpu)
        assert canonical.domain == "drainage"
        assert canonical.activity_type == "pipe_collector"
        assert canonical.attributes.get("pipe_diameter") == pytest.approx(300.0)
        assert "pipe_diameter" in canonical.required_attributes

    def test_normaliza_compactacao_aterro(self):
        """CPU de compactação deve ter compaction_rate=100 e domain earthwork."""
        cpu = self._make_cpu(
            codigo="COMPACT-ATERRO-100PN",
            categoria="TERRAPLENAGEM",
            unidade="m3",
        )
        canonical = self.norm.normalize_cpu(cpu)
        assert canonical.domain == "earthwork"
        assert canonical.activity_type == "embankment_compaction"
        assert canonical.attributes.get("compaction_rate") == pytest.approx(100.0)

    def test_normaliza_regularizacao_subleito(self):
        """Regularização de subleito deve ter unidade m2."""
        cpu = self._make_cpu(
            codigo="REGULARIZACAO-SUBLEITO",
            categoria="TERRAPLENAGEM",
            unidade="m2",
        )
        canonical = self.norm.normalize_cpu(cpu)
        assert canonical.unit == "m2"
        assert canonical.activity_type == "subgrade_regularization"
