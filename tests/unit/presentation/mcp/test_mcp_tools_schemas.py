"""Tier 1 coverage — scheduling/pool_validator, mcp/tools/schemas, mcp/tools/prompts."""

from __future__ import annotations

from concilium.presentation.mcp.tools.schemas import (
    CatalogDraftSchema,
    ReplanSimResult,
    ResumoProjetoSchema,
    TaxProfileSchema,
)

# ── MCP Schemas ───────────────────────────────────────────────────────────────


class TestTaxProfileSchema:
    def test_instanciacao(self):
        s = TaxProfileSchema(
            jurisdicao_id="BR",
            iss_aliquota=0.03,
            regime_default="lucro_presumido",
            cofins=0.03,
            pis=0.0065,
            cssl=0.0199,
            ir=0.0274,
            encargos_horistas=1.777,
            encargos_mensalistas=1.060,
            fonte="rfi_catalog.xlsm",
        )
        assert s.municipio is None
        assert s.jurisdicao_id == "BR"

    def test_com_municipio(self):
        s = TaxProfileSchema(
            jurisdicao_id="BR",
            municipio="Goiânia",
            iss_aliquota=0.02,
            regime_default="simples_nacional",
            cofins=0.0,
            pis=0.0,
            cssl=0.0,
            ir=0.0,
            encargos_horistas=1.0,
            encargos_mensalistas=1.0,
            fonte="x",
        )
        assert s.municipio == "Goiânia"


class TestCatalogDraftSchema:
    def test_instanciacao(self):
        s = CatalogDraftSchema(
            draft_id="draft-001",
            status="pending",
            entity_type="cpu",
            catalog_name="mendeslobo",
            diff_preview="+ATI-019-M2: R$1,50/m²",
            proximos_passos="Aprovar via catalog approve",
        )
        assert s.draft_id == "draft-001"


class TestReplanSimResult:
    def test_persisted_default_false(self):
        s = ReplanSimResult(
            project_id="p1",
            tipo="extend_deadline",
            parametros_aplicados={"weeks": 2},
            baseline={"custo": 1_000_000},
            simulado={"custo": 1_050_000},
            delta={"custo": "+5%"},
            nota="Simulação de extensão de prazo",
        )
        assert s.persisted is False

    def test_persisted_true(self):
        s = ReplanSimResult(
            project_id="p1",
            tipo="extend_deadline",
            parametros_aplicados={},
            persisted=True,
            baseline={},
            simulado={},
            delta={},
            nota="",
        )
        assert s.persisted is True


class TestResumoProjetoSchema:
    def test_instanciacao(self):
        s = ResumoProjetoSchema(
            project_id="p1",
            venda_total_com_bdi=10_000_000.0,
            custo_total=8_500_000.0,
            resultado_financeiro=1_500_000.0,
            margem_pct=0.15,
            status_margem="VIAVEL",
            breakdown_escopos=[],
            avisos=[],
        )
        assert s.margem_pct == 0.15



