"""Tests for campaign_report.py — serialize, Markdown, and PDF generation.

Uses the same _make_cenario helper pattern from test_adr070_campaign.py.
No real pipeline execution — all data is built from domain model constructors.
"""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from concilium.application.services.campaign.campaign_report import (
    render_campaign_report_md,
    render_campaign_report_pdf,
    serialize_campaign_report,
)
from concilium.application.services.campaign.campaign_service import (
    classificar_EF,
    classificar_O,
)
from concilium.domain.models.campaign.campaign import (
    CampaignBundleCube,
    CampaignOutputBundle,
    CenarioAvaliado,
    CenarioRankeado,
    CuboDimensao,
    FaceAnalitica,
    JustificativaCenario,
    PerfilExpectativas,
    ResumoMarginal,
    VetorEspacoEF,
    VetorEspacoO,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers (mirrors test_adr070_campaign.py pattern)
# ---------------------------------------------------------------------------

PERFIL = PerfilExpectativas(meta_margem_pct=0.10, tolerancia_margem=0.03)


def _make_cenario(
    cid: str,
    *,
    viabilidade: str = "APROVADO",
    prazo: int | None = 40,
    fe_nec: float | None = 0.9,
    gap_pool: float | None = 0.0,
    margem: float | None = 0.12,
    custo_ind: float | None = 10_000.0,
    share_mo: float | None = 0.40,
    share_eq: float | None = 0.35,
    paralelismo: float | None = 3.5,
    rank: int | None = None,
    pareto_O: bool = False,
    pareto_EF: bool = False,
    pareto_intersecao: bool = False,
) -> CenarioAvaliado:
    v_O = VetorEspacoO(
        prazo_semanas=prazo,
        folga_semanas=None,
        fe_nec_medio=fe_nec,
        itens_criticos_pct=0.0,
        gap_pool_total=gap_pool,
        paralelismo_medio=paralelismo,
    )
    v_EF = VetorEspacoEF(
        margem_pct=margem,
        custo_indireto=custo_ind,
        ratio_pool_vs_cat=0.95,
        share_mo_pct=share_mo,
        share_eq_pct=share_eq,
    )
    cl_O = classificar_O(v_O, PERFIL)
    cl_EF = classificar_EF(v_EF, PERFIL)
    return CenarioAvaliado(
        cenario_id=cid,
        parametros_variados={"objetivo": cid, "deadline": 52},
        viabilidade=viabilidade,  # type: ignore[arg-type]
        vetor_O=v_O,
        vetor_EF=v_EF,
        classificacao_O=cl_O,
        classificacao_EF=cl_EF,
        rank_final=rank,
        pareto_O=pareto_O,
        pareto_EF=pareto_EF,
        pareto_intersecao=pareto_intersecao,
    )


def _make_ranked(cenario: CenarioAvaliado, rank: int) -> CenarioRankeado:
    return CenarioRankeado(
        rank=rank,
        cenario=cenario,
        justificativa=JustificativaCenario(
            motivo_inclusao="Pareto-O+EF",
            destaques_O=["prazo aceitável"],
            destaques_EF=["margem dentro"],
            alertas=[],
            parametros_chave=cenario.parametros_variados,
        ),
    )


def _make_bundle(cenarios: list[CenarioAvaliado], shortlist: list[CenarioRankeado]) -> CampaignOutputBundle:
    n_vi = sum(1 for c in cenarios if c.viabilidade in {"APROVADO", "APROVADO_COM_RESSALVAS"})
    n_fa = sum(1 for c in cenarios if c.viabilidade == "ERRO")
    return CampaignOutputBundle(
        campaign_id="test-abc123",
        campaign_version="v1",
        gerado_em=datetime(2026, 6, 12, 10, 0, 0),
        n_cenarios_avaliados=len(cenarios),
        n_cenarios_viaveis=n_vi,
        n_falhas=n_fa,
        status="SUCESSO",
        cenarios=cenarios,
        shortlist=shortlist,
    )


def _make_cube(campaign_id: str = "test-abc123") -> CampaignBundleCube:
    dim1 = CuboDimensao(nome="deadline_weeks", campo="inputs_cronograma.rcpsp_spec.deadline_weeks", valores=[48, 52, 56])
    dim2 = CuboDimensao(nome="regime_trabalho", campo="meta.regime_trabalho", valores=["normal", "intensivo"])

    resumos = [
        ResumoMarginal(
            dimensao="deadline_weeks",
            metrica="prazo_semanas",
            valores=[48, 52, 56],
            medias=[46.0, 50.0, 54.0],
            tendencia="crescente",
        ),
        ResumoMarginal(
            dimensao="regime_trabalho",
            metrica="margem_pct",
            valores=["normal", "intensivo"],
            medias=[0.11, 0.14],
            tendencia="crescente",
        ),
    ]

    faces = [
        FaceAnalitica(
            dim_x="deadline_weeks",
            dim_y="regime_trabalho",
            metrica="prazo_semanas",
            valores_x=[48, 52, 56],
            valores_y=["normal", "intensivo"],
            grade=[[46.0, 50.0, 54.0], [44.0, 48.0, 52.0]],
        ),
    ]

    return CampaignBundleCube(
        campaign_id=campaign_id,
        dimensoes=[dim1, dim2],
        celulas=[],
        faces=faces,
        resumos_marginais=resumos,
        n_celulas_total=6,
        n_celulas_avaliadas=6,
        n_celulas_viaveis=5,
        n_celulas_pareto=2,
        cobertura_pct=1.0,
    )


def _make_report():
    c1 = _make_cenario("c1", prazo=38, fe_nec=0.85, margem=0.15, pareto_intersecao=True, rank=1)
    c2 = _make_cenario("c2", prazo=42, fe_nec=0.90, margem=0.12, pareto_O=True, rank=2)
    c3 = _make_cenario("c3", prazo=50, fe_nec=1.10, margem=0.09, rank=None)
    sl = [_make_ranked(c1, 1), _make_ranked(c2, 2)]
    bundle = _make_bundle([c1, c2, c3], sl)
    cube = _make_cube()
    return serialize_campaign_report(bundle, cube)


# ---------------------------------------------------------------------------
# 1. serialize_campaign_report — output is JSON-serializable, has required keys
# ---------------------------------------------------------------------------

class TestSerializeCampaignReport:
    def test_output_is_json_serializable(self):
        report = _make_report()
        # Should not raise
        json_str = json.dumps(report, default=str)
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)

    def test_has_required_top_level_keys(self):
        report = _make_report()
        assert "meta" in report
        assert "shortlist" in report
        assert "cenarios" in report
        assert "cubo" in report

    def test_meta_has_required_fields(self):
        report = _make_report()
        meta = report["meta"]
        for key in ["campaign_id", "campaign_version", "gerado_em", "status",
                    "n_avaliados", "n_viaveis", "n_falhas", "cobertura_pct"]:
            assert key in meta, f"meta missing: {key}"

    def test_meta_values_correct(self):
        report = _make_report()
        meta = report["meta"]
        assert meta["campaign_id"] == "test-abc123"
        assert meta["campaign_version"] == "v1"
        assert meta["status"] == "SUCESSO"
        assert meta["n_avaliados"] == 3
        assert meta["n_viaveis"] == 3
        assert meta["n_falhas"] == 0

    def test_shortlist_structure(self):
        report = _make_report()
        assert len(report["shortlist"]) == 2
        item = report["shortlist"][0]
        for key in ["rank", "cenario_id", "motivo_inclusao", "destaques_O",
                    "destaques_EF", "alertas", "parametros_chave", "vetor_O", "vetor_EF"]:
            assert key in item, f"shortlist item missing: {key}"

    def test_shortlist_rank_order(self):
        report = _make_report()
        ranks = [item["rank"] for item in report["shortlist"]]
        assert ranks == sorted(ranks)

    def test_cenarios_count_and_fields(self):
        report = _make_report()
        assert len(report["cenarios"]) == 3
        c = report["cenarios"][0]
        for key in ["cenario_id", "viabilidade", "classificacao_O", "classificacao_EF",
                    "pareto_O", "pareto_EF", "pareto_intersecao", "rank_final",
                    "vetor_O", "vetor_EF", "parametros_variados"]:
            assert key in c, f"cenario missing: {key}"

    def test_vetor_O_fields(self):
        report = _make_report()
        vO = report["cenarios"][0]["vetor_O"]
        for key in ["prazo_semanas", "folga_semanas", "fe_nec_medio", "itens_criticos_pct",
                    "gap_pool_total", "custo_mob_window_total", "utilizacao_recursos_pct",
                    "paralelismo_medio", "idle_pool_pct"]:
            assert key in vO, f"vetor_O missing: {key}"

    def test_vetor_EF_fields(self):
        report = _make_report()
        vEF = report["cenarios"][0]["vetor_EF"]
        for key in ["margem_pct", "custo_execucao_pool", "custo_indireto", "preco_venda",
                    "ratio_pool_vs_cat", "fidelidade_gates", "share_mo_pct",
                    "share_eq_pct", "share_comb_pct", "concentracao_atividade"]:
            assert key in vEF, f"vetor_EF missing: {key}"

    def test_cubo_structure(self):
        report = _make_report()
        cubo = report["cubo"]
        for key in ["dimensoes", "n_celulas_total", "n_celulas_avaliadas",
                    "cobertura_pct", "resumos_marginais", "faces"]:
            assert key in cubo, f"cubo missing: {key}"

    def test_cubo_dimensoes(self):
        report = _make_report()
        dims = report["cubo"]["dimensoes"]
        assert len(dims) == 2
        d = dims[0]
        assert "nome" in d and "campo" in d and "valores" in d

    def test_cubo_resumos_marginais(self):
        report = _make_report()
        resumos = report["cubo"]["resumos_marginais"]
        assert len(resumos) == 2
        r = resumos[0]
        for key in ["dimensao", "metrica", "valores", "medias", "tendencia"]:
            assert key in r, f"resumo_marginal missing: {key}"

    def test_cubo_faces(self):
        report = _make_report()
        faces = report["cubo"]["faces"]
        assert len(faces) == 1
        f = faces[0]
        for key in ["dim_x", "dim_y", "metrica", "valores_x", "valores_y", "grade"]:
            assert key in f, f"face missing: {key}"

    def test_pareto_intersecao_preserved(self):
        report = _make_report()
        c1 = next(c for c in report["cenarios"] if c["cenario_id"] == "c1")
        assert c1["pareto_intersecao"] is True

    def test_cobertura_100pct(self):
        report = _make_report()
        assert report["cubo"]["cobertura_pct"] == 100.0

    def test_cobertura_meta_pct(self):
        report = _make_report()
        # 3 viáveis / 3 avaliados = 100%
        assert report["meta"]["cobertura_pct"] == 100.0

    def test_empty_shortlist(self):
        c1 = _make_cenario("c1", viabilidade="BLOQUEADO")
        bundle = _make_bundle([c1], [])
        cube = _make_cube()
        report = serialize_campaign_report(bundle, cube)
        assert report["shortlist"] == []
        assert json.dumps(report, default=str)  # still serializable


# ---------------------------------------------------------------------------
# 2. render_campaign_report_md — contains expected sections
# ---------------------------------------------------------------------------

class TestRenderCampaignReportMd:
    def _md(self):
        return render_campaign_report_md(_make_report())

    def test_returns_string(self):
        assert isinstance(self._md(), str)

    def test_has_title(self):
        md = self._md()
        assert "# Relatório de Campanha GO" in md
        assert "test-abc123" in md

    def test_has_status_and_gerado_em(self):
        md = self._md()
        assert "**Status:**" in md
        assert "SUCESSO" in md
        assert "**Gerado em:**" in md

    def test_has_cenarios_summary(self):
        md = self._md()
        assert "avaliados" in md
        assert "viáveis" in md
        assert "falhas" in md

    def test_has_shortlist_section(self):
        md = self._md()
        assert "## Shortlist" in md
        # Table header
        assert "| Rank |" in md
        assert "| fe_nec |" in md

    def test_shortlist_has_rows(self):
        md = self._md()
        # Cenário c1 with rank=1 should appear
        assert "c1" in md
        assert "c2" in md

    def test_has_todos_cenarios_section(self):
        md = self._md()
        assert "## Todos os Cenários" in md
        assert "| O-class |" in md
        assert "| EF-class |" in md

    def test_todos_cenarios_has_all_rows(self):
        md = self._md()
        assert "c1" in md
        assert "c2" in md
        assert "c3" in md

    def test_pareto_intersecao_star(self):
        md = self._md()
        # c1 has pareto_intersecao=True → marked with ★
        assert "★" in md

    def test_has_cubo_section(self):
        md = self._md()
        assert "## Análise do CampaignBundleCube" in md
        assert "Células:" in md

    def test_has_efeitos_marginais(self):
        md = self._md()
        assert "### Efeitos Marginais" in md
        assert "deadline_weeks" in md
        assert "prazo_semanas" in md
        assert "crescente" in md

    def test_marginal_table_has_medias(self):
        md = self._md()
        # medias [46.0, 50.0, 54.0] → formatted as 46.000, 50.000, 54.000
        assert "46.000" in md
        assert "50.000" in md

    def test_has_faces_2d_section(self):
        md = self._md()
        assert "### Faces 2D" in md
        assert "deadline_weeks × regime_trabalho" in md

    def test_face_table_has_values(self):
        md = self._md()
        # grade values 46.00, 50.00, etc.
        assert "46.00" in md

    def test_has_insights_section(self):
        md = self._md()
        assert "## Insights" in md
        # At least one bullet
        assert "- " in md.split("## Insights")[1]

    def test_insights_contains_lever_prazo(self):
        md = self._md()
        insights_block = md.split("## Insights")[1]
        assert "deadline_weeks" in insights_block

    def test_insights_contains_lever_margem(self):
        md = self._md()
        insights_block = md.split("## Insights")[1]
        assert "regime_trabalho" in insights_block

    def test_no_extra_curly_braces(self):
        md = self._md()
        # Should not have Python format placeholders left over
        assert "{" not in md.replace("\\{", "")

    def test_empty_shortlist_renders_ok(self):
        c1 = _make_cenario("cx", viabilidade="BLOQUEADO")
        bundle = _make_bundle([c1], [])
        cube = _make_cube()
        report = serialize_campaign_report(bundle, cube)
        md = render_campaign_report_md(report)
        assert "## Shortlist" in md
        assert isinstance(md, str)


# ---------------------------------------------------------------------------
# 3. render_campaign_report_pdf — returns bytes or None
# ---------------------------------------------------------------------------

class TestRenderCampaignReportPdf:
    def _pdf(self):
        report = _make_report()
        md = render_campaign_report_md(report)
        return render_campaign_report_pdf(report, md)

    def test_returns_bytes_or_none(self):
        result = self._pdf()
        assert result is None or isinstance(result, bytes)

    def test_if_bytes_starts_with_pdf_magic(self):
        result = self._pdf()
        if result is not None:
            assert result[:4] == b"%PDF", "PDF output must start with %PDF magic bytes"

    def test_if_bytes_non_empty(self):
        result = self._pdf()
        if result is not None:
            assert len(result) > 1000, "PDF should be more than 1kB"

    def test_empty_shortlist_renders_without_crash(self):
        c1 = _make_cenario("cx", viabilidade="BLOQUEADO")
        bundle = _make_bundle([c1], [])
        cube = _make_cube()
        report = serialize_campaign_report(bundle, cube)
        md = render_campaign_report_md(report)
        result = render_campaign_report_pdf(report, md)
        assert result is None or isinstance(result, bytes)

    def test_multiple_cenarios_render_without_crash(self):
        """Stress test with more scenarios to exercise page-break logic."""
        cenarios = [
            _make_cenario(f"c{i}", prazo=30 + i, margem=0.10 + i * 0.01)
            for i in range(10)
        ]
        sl = [_make_ranked(cenarios[0], 1), _make_ranked(cenarios[1], 2)]
        bundle = _make_bundle(cenarios, sl)
        cube = _make_cube()
        report = serialize_campaign_report(bundle, cube)
        md = render_campaign_report_md(report)
        result = render_campaign_report_pdf(report, md)
        assert result is None or isinstance(result, bytes)

    def test_pareto_intersecao_highlight_does_not_crash(self):
        """Ensure green row highlight for pareto_intersecao doesn't break PDF."""
        c1 = _make_cenario("c1", pareto_intersecao=True, rank=1)
        sl = [_make_ranked(c1, 1)]
        bundle = _make_bundle([c1], sl)
        cube = _make_cube()
        report = serialize_campaign_report(bundle, cube)
        md = render_campaign_report_md(report)
        result = render_campaign_report_pdf(report, md)
        assert result is None or isinstance(result, bytes)
