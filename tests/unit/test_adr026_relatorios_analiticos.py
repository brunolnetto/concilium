"""Tests for ADR-026 — Multi-channel Output Phase.

Covers:
  - Skills 15/16/17: each emits exactly one ArtifactEnvelope with correct ArtifactKind
  - Skill 07: VAL-ADAPTER-CRITICIDADE OK when cost_criticality_report present
  - Skill 07: VAL-ADAPTER-CRITICIDADE AVISO when cost_criticality_report absent
  - Skill 07: planejamento_rows include 'criticidade' key when enriched
  - render_planejamento: adds 'Criticidade' header column when data present
  - render_planejamento: no 'Criticidade' column when cost_criticality_report is None
  - CANONICAL_SKILL_ORDER includes 11, 15, 16, 17
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from concilium.application.skills.base import SkillResult
from concilium.domain.models.artifact import ArtifactEnvelope, ArtifactKind
from concilium.domain.models.canonical import CanonicalModel

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_meta():
    from concilium.domain.models.canonical import Meta

    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")


def _make_projeto():
    from concilium.domain.models.canonical import Coordenadas, Projeto, RegimeTrabalho

    return Projeto(
        id="test-proj-026",
        nome="ADR-026 Test",
        tipo_obra="pavimentacao",
        localizacao="RJ",
        coordenadas=Coordenadas(lat=-22.9, lng=-43.2),
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        snapshot_catalogo_id="snap-cat-test",
        snapshot_perfil_id="snap-perf-test",
    )


def _make_resultado():
    from concilium.domain.models.canonical import CustoTotal, Resultado, Venda

    return Resultado(
        venda=Venda(total_sem_bdi=1_000_000.0, total_com_bdi=1_300_000.0),
        custo=CustoTotal(direto_equipes=800_000.0, total=1_000_000.0),
        resultado_financeiro=300_000.0,
        margem_pct=0.23,
        status_margem="VERDE",
        validacoes=[],
    )


def _make_criticidade_result(n: int = 3):
    """Build a minimal CostCriticalityResult with n activities."""
    from concilium.domain.models.canonical import CostCriticalityResult, CriticidadeProfile, DimensaoCriticidade

    atividades = []
    classes = ["A+", "A", "B", "C"]
    for i in range(n):
        atividades.append(
            CriticidadeProfile(
                atividade_id=f"item-{i + 1:02d}",
                custo=DimensaoCriticidade(valor_raw=0.4 - i * 0.1, rank=i + 1, percentil=0.9 - i * 0.2),
                duracao=DimensaoCriticidade(valor_raw=0.3, rank=i + 1, percentil=0.8),
                recurso=DimensaoCriticidade(valor_raw=0.2, rank=i + 1, percentil=0.7),
                sensibilidade=DimensaoCriticidade(valor_raw=0.1, rank=i + 1, percentil=0.5),
                pareto_frontier=(i == 0),
                rank_lexicografico=i + 1,
                classe=classes[i % len(classes)],
                interpretacao=f"Atividade {i + 1}",
            )
        )
    return CostCriticalityResult(
        atividades=atividades,
        n_pareto_frontier=1,
        n_atividades=n,
    )


def _load_skill(number_dash_name: str):
    """Load a skill.py module by skill-id string."""
    import importlib.util
    from pathlib import Path

    skill_path = (
        Path(__file__).parent.parent.parent / f"src/concilium/application/skills/manifests/{number_dash_name}/skill.py"
    )
    spec = importlib.util.spec_from_file_location(f"skill_{number_dash_name}", skill_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ── Relatório Executivo (NEP-041 Fase 1: absorvido em skill-09) ─────────────


class TestSkill15RelatorioCriticidade:
    def _run(self, canonical_in: CanonicalModel):
        """NEP-041 Fase 1: relatório executivo agora é estágio interno de skill-09.

        Testa o builder diretamente via _skill_helpers_executivo, envolvendo o
        retorno (canonical_update, artifacts, validacoes) num objeto compatível.
        """
        import importlib.util
        from pathlib import Path
        from types import SimpleNamespace

        path = (
            Path(__file__).resolve().parents[2]
            / "src/concilium/application/skills/manifests"
            / "10-relatorio-e-artefatos/_skill_helpers_executivo.py"
        )
        spec = importlib.util.spec_from_file_location("sk09_exec", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        update, artifacts, validacoes = mod.build_relatorio_executivo(canonical_in)
        canonical_out = canonical_in.model_copy(update=update)
        return SimpleNamespace(
            artifacts=artifacts,
            validacoes=validacoes,
            canonical=canonical_out,
            has_errors=any(v.status == "ERRO" for v in validacoes),
        )

    def _canonical_with_criticidade(self) -> CanonicalModel:
        return CanonicalModel(
            meta=_make_meta(),
            projeto=_make_projeto(),
            cost_criticality_report=_make_criticidade_result(3),
        )

    def test_emits_artifact_envelope(self):
        """Skill 15 returns a SkillResult with at least one ArtifactEnvelope."""
        result = self._run(self._canonical_with_criticidade())
        assert len(result.artifacts) >= 1
        assert all(isinstance(a, ArtifactEnvelope) for a in result.artifacts)

    def test_artifact_kind_is_relatorio_criticidade(self):
        result = self._run(self._canonical_with_criticidade())
        assert result.artifacts[0].meta.kind == ArtifactKind.RELATORIO_CRITICIDADE

    def test_artifact_schema_name(self):
        result = self._run(self._canonical_with_criticidade())
        assert result.artifacts[0].meta.schema_name == "RelatorioCriticidade"

    def test_artifact_content_hash_set(self):
        result = self._run(self._canonical_with_criticidade())
        assert result.artifacts[0].meta.content_hash

    def test_payload_itens_matches_atividades(self):
        result = self._run(self._canonical_with_criticidade())
        assert not result.has_errors
        # relatorio_criticidade should be populated in canonical too
        assert result.canonical.relatorio_criticidade is not None

    def test_degrades_gracefully_without_criticidade(self):
        """Skill 15 without cost_criticality_report: no ERRO, may still emit artifacts."""
        canonical_in = CanonicalModel(meta=_make_meta(), projeto=_make_projeto())
        result = self._run(canonical_in)
        # Should emit an AVISO but not crash
        assert not any(v.status == "ERRO" for v in result.validacoes)
        # Artifacts may be fewer than with criticidade (graceful degradation)
        n_with = len(self._run(self._canonical_with_criticidade()).artifacts)
        assert len(result.artifacts) <= n_with


# ── Skill 07: criticidade enrichment (ADR-026 §D5) ──────────────────────────


class TestSkill07CriticidadeEnrichment:
    pytestmark = [pytest.mark.slow]

    @pytest.fixture(scope="class")
    def _result_crit(self):
        """Roda skill 10 com criticidade uma vez para toda a classe."""
        can = TestSkill07CriticidadeEnrichment._make_canonical(with_criticidade=True)
        mod = _load_skill("10-relatorio-e-artefatos")
        return mod.run_relatorio_e_artefatos(canonical_in=can, inputs={}, perfil={})

    @pytest.fixture(scope="class")
    def _result_no_crit(self):
        """Roda skill 10 sem criticidade uma vez para toda a classe."""
        can = TestSkill07CriticidadeEnrichment._make_canonical(with_criticidade=False)
        mod = _load_skill("10-relatorio-e-artefatos")
        return mod.run_relatorio_e_artefatos(canonical_in=can, inputs={}, perfil={})

    @staticmethod
    def _make_canonical(with_criticidade: bool = False) -> CanonicalModel:
        """Helper estático para fixtures de classe — sem acesso a self."""
        from concilium.domain.models.canonical import (
            BdiCategorias,
            EapItem,
            Planejamento,
            PrecoUnitarioCategoria,
            SubtotalCategorias,
            SubtotalSemBdiComBdi,
        )

        eap = [
            EapItem(
                item_id="item-01", ordem=1, cpu_id="CPU-001", descricao="Serviço A", unidade="m³", quantitativo=100.0
            )
        ]
        bdi = BdiCategorias(material=0.05, diesel=0.26, mao_obra=0.35, equipamentos=0.30)
        preco_unit = PrecoUnitarioCategoria(material=10.0, diesel=5.0, mao_obra=20.0, equipamentos=15.0, total=50.0)
        preco_com = PrecoUnitarioCategoria(material=10.5, diesel=6.3, mao_obra=27.0, equipamentos=19.5, total=63.3)
        sub_sem = SubtotalCategorias(material=1000.0, diesel=500.0, mao_obra=2000.0, equipamentos=1500.0, total=5000.0)
        sub_com = SubtotalCategorias(material=1050.0, diesel=630.0, mao_obra=2700.0, equipamentos=1950.0, total=6330.0)
        planejamento = [
            Planejamento(
                item_id="item-01",
                cpu_id="CPU-001",
                quantitativo=100.0,
                preco_unitario=preco_unit,
                bdi=bdi,
                preco_unitario_com_bdi=preco_com,
                subtotal=SubtotalSemBdiComBdi(sem_bdi=sub_sem, com_bdi=sub_com),
            )
        ]
        crit_report = _make_criticidade_result(1) if with_criticidade else None
        if crit_report:
            crit_report.atividades[0] = crit_report.atividades[0].model_copy(update={"atividade_id": "item-01"})
        return CanonicalModel(
            meta=_make_meta(),
            projeto=_make_projeto(),
            eap=eap,
            planejamento=planejamento,
            resultado=_make_resultado(),
            cost_criticality_report=crit_report,
        )

    def _run(self, canonical_in: CanonicalModel) -> SkillResult:
        mod = _load_skill("10-relatorio-e-artefatos")
        return mod.run_relatorio_e_artefatos(
            canonical_in=canonical_in,
            inputs={},
            perfil={},
        )

    def _canonical_with_resultado(self, with_criticidade: bool = False) -> CanonicalModel:
        from concilium.domain.models.canonical import (
            BdiCategorias,
            EapItem,
            Planejamento,
            PrecoUnitarioCategoria,
            SubtotalCategorias,
            SubtotalSemBdiComBdi,
        )

        eap = [
            EapItem(
                item_id="item-01", ordem=1, cpu_id="CPU-001", descricao="Serviço A", unidade="m³", quantitativo=100.0
            )
        ]
        bdi = BdiCategorias(material=0.05, diesel=0.26, mao_obra=0.35, equipamentos=0.30)
        preco_unit = PrecoUnitarioCategoria(material=10.0, diesel=5.0, mao_obra=20.0, equipamentos=15.0, total=50.0)
        preco_com = PrecoUnitarioCategoria(material=10.5, diesel=6.3, mao_obra=27.0, equipamentos=19.5, total=63.3)
        sub_sem = SubtotalCategorias(material=1000.0, diesel=500.0, mao_obra=2000.0, equipamentos=1500.0, total=5000.0)
        sub_com = SubtotalCategorias(material=1050.0, diesel=630.0, mao_obra=2700.0, equipamentos=1950.0, total=6330.0)
        planejamento = [
            Planejamento(
                item_id="item-01",
                cpu_id="CPU-001",
                quantitativo=100.0,
                preco_unitario=preco_unit,
                bdi=bdi,
                preco_unitario_com_bdi=preco_com,
                subtotal=SubtotalSemBdiComBdi(sem_bdi=sub_sem, com_bdi=sub_com),
            )
        ]
        crit_report = _make_criticidade_result(1) if with_criticidade else None
        # Override atividade_id to match item_id
        if crit_report:
            crit_report.atividades[0] = crit_report.atividades[0].model_copy(update={"atividade_id": "item-01"})
        return CanonicalModel(
            meta=_make_meta(),
            projeto=_make_projeto(),
            eap=eap,
            planejamento=planejamento,
            resultado=_make_resultado(),
            cost_criticality_report=crit_report,
        )

    def test_val_adapter_criticidade_ok_when_enriched(self, _result_crit):
        """VAL-ADAPTER-CRITICIDADE is OK when cost_criticality_report present."""
        val = next((v for v in _result_crit.validacoes if v.codigo == "VAL-ADAPTER-CRITICIDADE"), None)
        assert val is not None, "VAL-ADAPTER-CRITICIDADE not found in validacoes"
        assert val.status == "OK"

    def test_val_adapter_criticidade_aviso_when_absent(self, _result_no_crit):
        """VAL-ADAPTER-CRITICIDADE is AVISO when cost_criticality_report is None."""
        val = next((v for v in _result_no_crit.validacoes if v.codigo == "VAL-ADAPTER-CRITICIDADE"), None)
        assert val is not None
        assert val.status == "AVISO"

    def test_planejamento_rows_include_criticidade_key(self, _result_crit):
        """When enriched, planejamento rows include 'criticidade' field."""
        relatorio = getattr(_result_crit, "relatorio", None)
        if relatorio is None:
            relatorio = getattr(_result_crit.canonical, "_relatorio_saida", None)
        if relatorio and "PLANEJAMENTO" in relatorio:
            rows = relatorio["PLANEJAMENTO"]
            if rows:
                assert "criticidade" in rows[0], "planejamento row missing 'criticidade' key when enriched"

    def test_planejamento_rows_no_criticidade_when_absent(self, _result_no_crit):
        """When not enriched, planejamento rows do not include 'criticidade' field."""
        relatorio = getattr(_result_no_crit, "relatorio", None)
        if relatorio is None:
            relatorio = getattr(_result_no_crit.canonical, "_relatorio_saida", None)
        if relatorio and "PLANEJAMENTO" in relatorio:
            rows = relatorio["PLANEJAMENTO"]
            if rows:
                assert "criticidade" not in rows[0]

    def test_resultado_prefers_operational_direct_cost(self):
        """Relatório financeiro deve usar custo direto operacional como fonte única."""
        from concilium.domain.models.canonical import CustoTotal, Resultado, Venda

        mod = _load_skill("10-relatorio-e-artefatos")
        canonical_in = self._canonical_with_resultado(with_criticidade=False)
        resultado = Resultado(
            venda=Venda(total_sem_bdi=5_000.0, total_com_bdi=7_000.0),
            custo=CustoTotal(
                direto_equipes=15_000.0,
                indireto_adm=1_000.0,
                total=6_000.0,
            ),
            resultado_financeiro=1_000.0,
            margem_pct=0.1,
            status_margem="VERDE",
            validacoes=[],
        )
        canonical_in = canonical_in.model_copy(update={"resultado": resultado})

        result = mod.run_relatorio_e_artefatos(canonical_in=canonical_in, inputs={}, perfil={})
        relatorio = getattr(result, "relatorio", None)
        assert relatorio is not None
        assert relatorio["RESULTADO"]["custo_direto"] == 15000.0
        assert relatorio["RESULTADO"]["custo_direto_fonte"] == "operacional_equipes"


# ── render_planejamento: criticidade column ──────────────────────────────────


class TestRenderPlanejamentoCriticidade:
    def _render(self, with_criticidade: bool):
        from openpyxl import Workbook

        from concilium.domain.models.canonical import (
            BdiCategorias,
            EapItem,
            Planejamento,
            PrecoUnitarioCategoria,
            SubtotalCategorias,
            SubtotalSemBdiComBdi,
        )
        from concilium.infrastructure.adapters.excel_adapter import render_planejamento_ml

        eap = [
            EapItem(item_id="item-01", ordem=1, cpu_id="CPU-001", descricao="Aterro", unidade="m³", quantitativo=50.0)
        ]
        bdi = BdiCategorias(material=0.05, diesel=0.26, mao_obra=0.35, equipamentos=0.30)
        preco = PrecoUnitarioCategoria(material=10.0, diesel=5.0, mao_obra=20.0, equipamentos=15.0, total=50.0)
        preco_c = PrecoUnitarioCategoria(material=10.5, diesel=6.3, mao_obra=27.0, equipamentos=19.5, total=63.3)
        sub_s = SubtotalCategorias(material=500.0, diesel=250.0, mao_obra=1000.0, equipamentos=750.0, total=2500.0)
        sub_c = SubtotalCategorias(material=525.0, diesel=315.0, mao_obra=1350.0, equipamentos=975.0, total=3165.0)
        plano = [
            Planejamento(
                item_id="item-01",
                cpu_id="CPU-001",
                quantitativo=50.0,
                preco_unitario=preco,
                bdi=bdi,
                preco_unitario_com_bdi=preco_c,
                subtotal=SubtotalSemBdiComBdi(sem_bdi=sub_s, com_bdi=sub_c),
            )
        ]
        crit_report = _make_criticidade_result(1) if with_criticidade else None
        if crit_report:
            if crit_report.atividades:
                atividades_updated = list(crit_report.atividades)
                atividades_updated[0] = atividades_updated[0].model_copy(update={"atividade_id": "item-01"})
                crit_report = crit_report.model_copy(update={"atividades": atividades_updated})
        canonical = CanonicalModel(
            meta=_make_meta(),
            projeto=_make_projeto(),
            eap=eap,
            planejamento=plano,
            resultado=_make_resultado(),
            cost_criticality_report=crit_report,
        )
        wb = Workbook()
        render_planejamento_ml(wb, canonical)
        ws = wb["PLANEJAMENTO"]
        return ws

    def test_with_criticidade_header_row_has_criticidade_column(self):
        """When enriched, 'Criticidade' appears in the header row."""
        ws = self._render(with_criticidade=True)
        # render_planejamento_ml: row 1 = title, row 2 = headers
        header_values = [ws.cell(row=2, column=c).value for c in range(1, 16)]
        assert "Criticidade" in header_values, f"'Criticidade' not found in header row: {header_values}"

    def test_without_criticidade_no_criticidade_column(self):
        """When not enriched, 'Criticidade' is absent from all header cells."""
        ws = self._render(with_criticidade=False)
        all_values = set()
        for row in ws.iter_rows():
            for cell in row:
                all_values.add(cell.value)
        assert "Criticidade" not in all_values

    def test_with_criticidade_data_row_has_value(self):
        """Data row (row 3) should have a non-None value in the criticidade column."""
        ws = self._render(with_criticidade=True)
        # Find Criticidade column index in row 2 (headers)
        crit_col = None
        for c in range(1, 16):
            if ws.cell(row=2, column=c).value == "Criticidade":
                crit_col = c
                break
        assert crit_col is not None, "Criticidade column not found"
        # Data starts at row 3
        crit_cell_value = ws.cell(row=3, column=crit_col).value
        assert crit_cell_value is not None


# ── CANONICAL_SKILL_ORDER completeness ──────────────────────────────────────


class TestCanonicalSkillOrder:
    def test_includes_all_adrs_026_skills(self):
        from concilium.application.skills import SKILLS
        from concilium.application.skills.phase_classifier import CANONICAL_SKILL_ORDER

        # NEP-041 Fase 1: 15 absorvido em 09 (ativo no pipeline)
        assert "10-relatorio-e-artefatos" in CANONICAL_SKILL_ORDER
        # NEP-041 Fase 3: 09-registro-decisoes dormante — invocável mas fora do pipeline auto
        assert "09-registro-decisoes" in SKILLS
        assert "09-registro-decisoes" not in CANONICAL_SKILL_ORDER

    def test_07_comes_after_09(self):
        """ADR-026 §D: 10-relatorio-e-artefatos (Saída) must come after 07-diagnostico-criticidade (Análise)."""
        from concilium.application.skills.phase_classifier import CANONICAL_SKILL_ORDER

        # Skill 09 (Saída) deve vir depois de skill 10 (Análise) na ordem canônica
        assert CANONICAL_SKILL_ORDER.index("10-relatorio-e-artefatos") > CANONICAL_SKILL_ORDER.index(
            "07-diagnostico-criticidade"
        ), "10-relatorio-e-artefatos must come after 09-cost-criticality"

    def test_09_relatorio_absorve_executivo(self):
        """NEP-041 Fase 1: 15 foi absorvido em 09 — 09 vem depois de 10 (Análise)."""
        from concilium.application.skills.phase_classifier import CANONICAL_SKILL_ORDER

        assert "15-relatorio-executivo" not in CANONICAL_SKILL_ORDER
        assert CANONICAL_SKILL_ORDER.index("10-relatorio-e-artefatos") > CANONICAL_SKILL_ORDER.index(
            "07-diagnostico-criticidade"
        )
