"""Coverage batch 4 — small missing-line targets across many files."""

from __future__ import annotations

import json
import sys
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# mob_scheduling.py line 27: _parse_date with date object → return date_str
# mob_scheduling.py line 146: fase not in mob_windows → continue
# ---------------------------------------------------------------------------


class TestMobSchedulingMissingLines:
    def test_parse_date_with_date_object_returns_it(self):
        """Line 27: isinstance(date_str, date) → return date_str."""
        from concilium.application.scheduling.mob_scheduling import _parse_date

        d = date(2024, 6, 15)
        assert _parse_date(d) is d

    def test_calcular_mob_fase_not_in_windows_skipped(self):
        """Line 146: indireto MOB with fase not in mob_windows → skipped."""
        from concilium.application.scheduling.mob_scheduling import calcular_custo_indireto_mob

        mob_windows = {
            "mobilizacao": {"inicio": date(2024, 1, 1), "fim": date(2024, 1, 31)},
        }
        indiretos = [
            {"tipo": "MOB", "fase": "UNKNOWN_FASE", "driver": "projeto", "custo_fixo_total": 5000.0},
        ]
        result = calcular_custo_indireto_mob(indiretos, mob_windows)
        assert result["mob"] == {}
        assert result["custo_mob_total"] == 0.0


# ---------------------------------------------------------------------------
# producao.py line 33: obter_ou_erro with missing file → FileNotFoundError
# ---------------------------------------------------------------------------


class TestProducaoObterOuErro:
    def test_raises_file_not_found(self, tmp_path):
        """Line 33: producao not found → FileNotFoundError."""
        from concilium.infrastructure.repositories.producao import RepositorioProducao

        repo = RepositorioProducao(tmp_path)
        with pytest.raises(FileNotFoundError, match="nao_existe"):
            repo.obter_ou_erro("nao_existe")


# ---------------------------------------------------------------------------
# service_support.py line 25: build_summary with resultado=None → short dict
# ---------------------------------------------------------------------------


class TestBuildSummaryResultadoNone:
    def test_resultado_none_returns_short_dict(self):
        """Line 25: result is None → return pe_deficit/alerta only."""
        from concilium.application.services.service_support import build_summary

        pe1 = SimpleNamespace(status_validacao="ERRO")
        pe2 = SimpleNamespace(status_validacao="AVISO")
        canonical = SimpleNamespace(resultado=None, ponto_equilibrio=[pe1, pe2])
        result = build_summary(canonical)
        assert result == {"pe_deficit_items": 1, "pe_alerta_items": 1}
        assert "preco_venda_total" not in result


# ---------------------------------------------------------------------------
# tributacao.py line 82: fallback return when no INSS bracket matches
# ---------------------------------------------------------------------------


class TestCalculateInssLastBracketFallback:
    def test_fallback_when_no_bracket_matches(self):
        """Line 82: for loop exhausted → fallback return."""
        from concilium.domain.services.financial import tributacao

        fake_brackets = [(1_000.0, 0.07, 0.0)]
        with patch.object(tributacao, "INSS_BRACKETS_2026", fake_brackets):
            result = tributacao.calculate_inss_employee(50_000.0)
        assert result == round(8_475.55 * 0.07 - 0.0, 2)


# ---------------------------------------------------------------------------
# confidence.py line 137: _detect_embedding_failure_modes → low_discriminative_power
# ---------------------------------------------------------------------------


class TestConfidenceEmbeddingFailures:
    def _make_cand(self, score, sem_sim=0.5, attr_match=0.8):
        from concilium.application.resolution.models import ScoredCandidate

        explanations = [
            {"feature": "semantic_similarity", "value": sem_sim, "weight": 1.0, "contribution": sem_sim},
            {"feature": "attribute_match", "value": attr_match, "weight": 1.0, "contribution": attr_match},
        ]
        return ScoredCandidate(cpu_id=f"CPU-{score}", score=score, explanations=explanations)

    def test_low_discriminative_power_appended(self):
        """Line 137: 3+ close-scored candidates → low_discriminative_power in failures."""
        from concilium.application.resolution.confidence import ConfidenceAssigner

        estimator = ConfidenceAssigner()
        cand = self._make_cand(0.90, sem_sim=0.5, attr_match=0.9)
        all_candidates = [
            self._make_cand(0.90),
            self._make_cand(0.87),
            self._make_cand(0.86),
        ]
        failures = estimator._detect_embedding_failure_modes(cand, all_candidates)
        assert "low_discriminative_power" in failures

    def test_false_positive_detected(self):
        """Line 137 path: sem_sim >= 0.8 and attr_match <= 0.3 → failure."""
        from concilium.application.resolution.confidence import ConfidenceAssigner

        estimator = ConfidenceAssigner()
        cand = self._make_cand(0.9, sem_sim=0.9, attr_match=0.1)
        failures = estimator._detect_embedding_failure_modes(cand, [cand])
        assert "high_similarity_low_attribute_match" in failures


# ---------------------------------------------------------------------------
# catalog_governance.py line 55: producao not found → CatalogGovernanceError
# ---------------------------------------------------------------------------


class TestCatalogGovernanceMissingProducao:
    def test_producao_not_found_raises(self, tmp_path):
        """Line 55: producao file missing → CatalogGovernanceError."""
        from concilium.application.orchestrators.catalog_governance import (
            CatalogGovernanceError,
            validate_and_resolve_producao_file,
        )

        (tmp_path / "producoes").mkdir()
        (tmp_path / "produtividades").mkdir()
        with pytest.raises(CatalogGovernanceError, match="nao_existe"):
            validate_and_resolve_producao_file(tmp_path, "nao_existe", 100.0)


# ---------------------------------------------------------------------------
# client_store.py line 50: no secret_hash, no plaintext → return False
# ---------------------------------------------------------------------------


class TestVerifySecretNoCredentials:
    def test_returns_false_when_no_hash_no_plaintext(self):
        """Line 50: entry has neither secret_hash nor secret → False."""
        from concilium.infrastructure.auth.client_store import _verify_secret

        entry = {"secret_hash": "", "secret": ""}
        assert _verify_secret("any_secret", entry) is False


# ---------------------------------------------------------------------------
# granular.py lines 20-22: _load_json with invalid JSON → warning + return {}
# ---------------------------------------------------------------------------


class TestGranularLoadJsonBadJson:
    def test_bad_json_returns_empty_dict(self, tmp_path):
        """Lines 20-22: invalid JSON file → except branch → return {}."""
        from concilium.application.benchmarks.comparison.granular import _load_json

        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not-valid-json", encoding="utf-8")
        result = _load_json(bad_file)
        assert result == {}


# ---------------------------------------------------------------------------
# equipes_detail.py lines 17-18: _load_json with invalid JSON → return {}
# ---------------------------------------------------------------------------


class TestEquipesDetailLoadJsonBadJson:
    def test_bad_json_returns_empty_dict(self, tmp_path):
        """Lines 17-18: invalid JSON → except branch → return {}."""
        from concilium.application.benchmarks.comparison.equipes_detail import _load_json

        bad_file = tmp_path / "cpu_bad.json"
        bad_file.write_text("{{invalid", encoding="utf-8")
        result = _load_json(bad_file)
        assert result == {}


# ---------------------------------------------------------------------------
# healer.py lines 70-71: _remap_equipamentos called with equipes having equipamentos
# ---------------------------------------------------------------------------


class TestHealerRemapEquipamentos:
    def test_remap_equipamentos_runs_on_equipe_with_equipamentos(self, tmp_path):
        """Lines 70-71: _heal_producoes calls _remap_equipamentos on equipe with equipamentos."""
        from concilium.infrastructure.catalog.mapping.healer import heal_catalog

        # Set up minimal catalog structure
        cat_root = tmp_path
        (cat_root / "insumos" / "equipamento").mkdir(parents=True)
        (cat_root / "insumos" / "mao_obra").mkdir(parents=True)
        (cat_root / "insumos" / "material").mkdir(parents=True)
        (cat_root / "producoes").mkdir()
        (cat_root / "cpus").mkdir()
        (cat_root / "produtividades").mkdir()

        # Put an insumo equipamento so id_map gets populated
        eq_file = cat_root / "insumos" / "equipamento" / "EQ-ESCAV01.json"
        eq_file.write_text('{"equip_id": "EQ-ESCAV01"}', encoding="utf-8")

        # Create a producao with an equipe that has equipamentos
        producao_data = {
            "composicao_padrao_equipe": {
                "funcoes": [],
                "equipamentos": [{"equip_id": "ESCAV01"}],
            }
        }
        (cat_root / "producoes" / "prod1.json").write_text(json.dumps(producao_data), encoding="utf-8")

        result = heal_catalog(cat_root)
        assert "Cura concluída" in result


# ---------------------------------------------------------------------------
# cubo_combustivel_builder.py line 36: equip with custo_mensal <= 0 → skip
# ---------------------------------------------------------------------------


class TestCuboCombustivelSkipsZeroCusto:
    def test_equip_with_zero_custo_skipped(self):
        """Line 36: custo_combustivel_mensal=0 → continue (equip not added to celulas)."""
        from concilium.domain.services.analytics.cubo_combustivel_builder import build_cubo_combustivel_face

        equip = SimpleNamespace(
            equip_id="EQ-CAM01",
            custo_combustivel_mensal=0.0,
            tipo_combustivel="DIESEL",
        )
        equipe = SimpleNamespace(
            item_id="CPU-01",
            permanencia_meses=3.0,
            equipamentos=[equip],
        )
        canonical = SimpleNamespace(
            projeto=SimpleNamespace(nome="TestProj"),
            equipes_diretas=[equipe],
        )
        face = build_cubo_combustivel_face(canonical)
        assert len(face.celulas) == 0


# ---------------------------------------------------------------------------
# tool_invocations/repository.py lines 100-101: _max_size with non-int env var
# ---------------------------------------------------------------------------


class TestMaxSizeInvalidEnvVar:
    def test_invalid_env_returns_10000(self, monkeypatch):
        """Lines 100-101: env var is not a valid int → except ValueError → 10_000."""
        monkeypatch.setenv("CONCILIUM__TOOL_INVOCATIONS_MAX_SIZE", "not_an_int")
        from concilium.application.tool_invocations.repository import _max_size

        result = _max_size()
        assert result == 10_000


# ---------------------------------------------------------------------------
# heatmap_top_n.py lines 34-35: matplotlib ImportError → return None
# ---------------------------------------------------------------------------


class TestHeatmapTopNMatplotlibImportError:
    def test_importerror_returns_none(self):
        """Lines 34-35: matplotlib not available → return None."""
        from concilium.application.runtime.deliverables.visualizations.eficiencia.heatmap_top_n import (
            plot_heatmap_top_n,
        )

        campo = MagicMock()
        with patch.dict(sys.modules, {"matplotlib.colors": None, "matplotlib.pyplot": None}):
            result = plot_heatmap_top_n(campo)
        assert result is None


# ---------------------------------------------------------------------------
# waterfall_causal.py lines 30-31: matplotlib ImportError → return None
# ---------------------------------------------------------------------------


class TestWaterfallCausalMatplotlibImportError:
    def test_importerror_returns_none(self):
        """Lines 30-31: matplotlib not available → return None."""
        from concilium.application.runtime.deliverables.visualizations.eficiencia.waterfall_causal import (
            plot_waterfall_causal,
        )

        campo = MagicMock()
        with patch.dict(sys.modules, {"matplotlib.pyplot": None}):
            result = plot_waterfall_causal(campo)
        assert result is None


# ---------------------------------------------------------------------------
# bar_tempo_natureza.py lines 25-26: init_mpl ImportError → return None
# ---------------------------------------------------------------------------


class TestBarTempoNaturezaImportError:
    def test_init_mpl_importerror_returns_none(self):
        """Lines 25-26: init_mpl raises ImportError → return None."""
        import concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_natureza as mod

        canonical = MagicMock()
        cubo = MagicMock()

        with patch.object(mod, "build_payload", return_value={"rows": [{"a": 1}], "columns": ["a"]}):
            with patch.object(mod, "init_mpl", side_effect=ImportError("no matplotlib")):
                result = mod.build(canonical, cubo)
        assert result is None
