"""Coverage batch 36 — 01-escopo-e-eap, 02-produtividade-climatica, 07-diagnostico-criticidade."""
from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Module loaders
# ---------------------------------------------------------------------------


def _load_skill(rel_path: str, name: str):
    p = Path(rel_path).resolve()
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MOD_01 = _load_skill(
    "src/concilium/application/skills/manifests/01-escopo-e-eap/skill.py", "skill01_b36"
)
MOD_02 = _load_skill(
    "src/concilium/application/skills/manifests/02-produtividade-climatica/skill.py", "skill02_b36"
)
MOD_07 = _load_skill(
    "src/concilium/application/skills/manifests/07-diagnostico-criticidade/skill.py", "skill07_b36"
)


# ---------------------------------------------------------------------------
# 07-diagnostico-criticidade lines 29-30: _periodo_to_ordinal with week key
# ---------------------------------------------------------------------------


class TestPeriodoToOrdinal:
    def test_week_period_returns_year_x53_plus_week(self):
        """Lines 29-30: '2024-W01' path → int(y)*53 + int(w)."""
        result = MOD_07._periodo_to_ordinal("2024-W01")
        assert result == 2024 * 53 + 1

    def test_week_period_w23(self):
        result = MOD_07._periodo_to_ordinal("2024-W23")
        assert result == 2024 * 53 + 23

    def test_month_period(self):
        """Line 32: '2024-06' → int(y)*12 + int(m) (no W in key)."""
        result = MOD_07._periodo_to_ordinal("2024-06")
        assert result == 2024 * 12 + 6


# ---------------------------------------------------------------------------
# 07-diagnostico-criticidade line 36: _percentil_rank with empty list
# ---------------------------------------------------------------------------


class TestPercentilRank:
    def test_empty_list_returns_empty(self):
        """Line 36: n == 0 → return []."""
        result = MOD_07._percentil_rank([])
        assert result == []

    def test_single_value_returns_list(self):
        result = MOD_07._percentil_rank([42])
        assert isinstance(result, list)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# 07-diagnostico-criticidade line 251:
# Graceful degradation when equipes exist but custo_total == 0
# ---------------------------------------------------------------------------


class TestRunDiagnosticoCriticidadeGracefulDegradation:
    def _make_canonical(self):
        from concilium.domain.models.canonical import (
            CanonicalModel,
            Coordenadas,
            Cronograma,
            EquipeDireta,
            Meta,
            Projeto,
            RegimeTrabalho,
        )

        meta = Meta(gerado_em=datetime.now(UTC), contexto_id="ctx-test")
        proj = Projeto(
            id="proj-test",
            nome="Test",
            tipo_obra="pavimentacao",
            localizacao="CE",
            coordenadas=Coordenadas(lat=-3.7, lng=-38.5),
            data_inicio=date(2026, 1, 1),
            data_termino=date(2026, 6, 30),
            regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
            snapshot_catalogo_id="snap",
            snapshot_perfil_id="perf",
        )
        # custo_total=0.0 by default → triggers graceful degradation
        equipe = EquipeDireta(equipe_id="EQ-001", item_id="ITEM-A", cpu_id="CPU-A", custo_total=0.0)
        cronograma = Cronograma()  # minimal, no scheduled_activities

        return CanonicalModel(
            meta=meta,
            projeto=proj,
            equipes_diretas=[equipe],
            cronograma=cronograma,
        )

    def test_graceful_degradation_returns_empty_report(self):
        """Line 251: equipes exist but custo_total=0 → else branch → empty CostCriticalityResult."""
        canonical = self._make_canonical()
        result = MOD_07.run_diagnostico_criticidade(canonical, inputs={})

        assert result is not None
        # VAL-CC-01 warning should be present (custo_total == 0)
        codes = [v.codigo for v in result.validacoes]
        assert "VAL-CC-01" in codes


# ---------------------------------------------------------------------------
# 02-produtividade-climatica lines 112, 119:
# run_produtividade_climatica when canonical_in.projeto is None
# ---------------------------------------------------------------------------


class TestRunProdutividadeClimaticaNoProject:
    def test_projeto_none_returns_error_validacao(self):
        """Lines 112, 119: canonical_in.projeto is None → VAL-PRAT-PRECONDICAO appended."""
        # Call via the directly-loaded module to avoid import aliasing issues
        canonical_ns = SimpleNamespace(projeto=None)

        result = MOD_02.run_produtividade_climatica(canonical_ns, inputs={}, perfil={})
        codes = [v.codigo for v in result.validacoes]
        assert "VAL-PRAT-PRECONDICAO" in codes


# ---------------------------------------------------------------------------
# 02-produtividade-climatica line 145: VAL-PRAT-01 when percentual out of range
# ---------------------------------------------------------------------------


class TestRunProdutividadeClimaticaFoiFaixa:
    def test_out_of_range_percentual_triggers_val_prat_01(self):
        """Line 145: percentual semanal > 1 → VAL-PRAT-01 appended."""
        from concilium.domain.models.canonical import (
            CanonicalModel,
            Coordenadas,
            Meta,
            Projeto,
            RegimeTrabalho,
        )
        from concilium.infrastructure.clients.openmeteo import DadosClimaticosMensais

        meta = Meta(gerado_em=datetime.now(UTC), contexto_id="test")
        proj = Projeto(
            id="p1",
            nome="proj",
            tipo_obra="terraplenagem",
            localizacao="CE",
            coordenadas=Coordenadas(lat=-4.36, lng=-38.77),
            regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
            snapshot_catalogo_id="s",
            snapshot_perfil_id="s",
        )
        canonical = CanonicalModel(meta=meta, projeto=proj)

        # Mock client that returns a DadosClimaticosMensais with one week
        dados = DadosClimaticosMensais(
            fonte="test",
            ano_referencia=2024,
            latitude=-4.36,
            longitude=-38.77,
            dias_precipitacao_mensal={str(m).zfill(2): {"5mm": 2, "10mm": 1, "20mm": 0} for m in range(1, 13)},
            dias_precipitacao_semanal={"2024-W01": {"5mm": 0, "10mm": 0, "20mm": 0}},
        )
        mock_client = SimpleNamespace(fetch_dados_anuais=lambda *a, **kw: dados)

        # Patch _calcular_percentual_produtivo_semanal inside the loaded module to return > 1
        with patch.object(MOD_02, "_calcular_percentual_produtivo_semanal", return_value={"2024-W01": 1.5}):
            result = MOD_02.run_produtividade_climatica(canonical, inputs={}, perfil={}, client=mock_client)

        codes = [v.codigo for v in result.validacoes]
        assert "VAL-PRAT-01" in codes


# ---------------------------------------------------------------------------
# 01-escopo-e-eap line 115: _build_atividades_for_item with invalid frac
# ---------------------------------------------------------------------------


class TestBuildAtividadesForItem:
    def test_valid_frac_builds_atividade(self):
        """Happy path: valid frac builds Atividade without error."""
        from concilium.domain.models.canonical import EapItem

        eap_item = EapItem(
            item_id="EAP-001",
            ordem=1,
            cpu_id="CPU-A",
            descricao="Test",
            unidade="m3",
            quantitativo=100.0,
        )
        raw_ativs = [{"fracao_quantitativo": 1.0, "atividade_id": "EAP-001-atv-1"}]
        validacoes = []

        result = MOD_01._build_atividades_for_item(eap_item, raw_ativs, validacoes)
        assert len(result) == 1
        assert result[0].atividade_id == "EAP-001-atv-1"


# ---------------------------------------------------------------------------
# 01-escopo-e-eap line 191: _build_dag_from_precedencias with missing pred
# ---------------------------------------------------------------------------


class TestBuildDagFromPrecedencias:
    def test_missing_predecessor_triggers_val_dag_01(self):
        """Line 191: pred_item_id not in item_to_first_activity → VAL-DAG-01."""
        from concilium.domain.models.canonical import EapItem

        # Item B references item "GHOST" as predecessor, but GHOST has no activity
        eap_b = EapItem(
            item_id="B",
            ordem=2,
            cpu_id="CPU-B",
            descricao="B",
            unidade="m3",
            quantitativo=100.0,
            predecessores=["GHOST"],  # GHOST not in activity ids
        )
        eap_a = EapItem(
            item_id="A",
            ordem=1,
            cpu_id="CPU-A",
            descricao="A",
            unidade="m3",
            quantitativo=100.0,
        )

        nos = ["A-atv-1", "B-atv-1"]  # GHOST-atv-1 not here
        nos_set = set(nos)
        validacoes = []

        result = MOD_01._build_dag_from_precedencias(
            nos, nos_set, precedencias_raw=[], eap=[eap_a, eap_b], validacoes=validacoes
        )

        codes = [v.codigo for v in validacoes]
        assert "VAL-DAG-01" in codes


# ---------------------------------------------------------------------------
# 01-escopo-e-eap line 247: _compute_longest_paths with FF type edge
# ---------------------------------------------------------------------------


class TestComputeLongestPaths:
    def test_ff_edge_uses_fs_conservative_bound(self):
        """Line 247: tipo == 'FF' → offsets.append(base + 1 + lag)."""
        nos = ["A", "B"]
        succ_map = {"A": ["B"]}
        # FF edge from A to B with lag=0
        pred_map_typed = {"B": [("A", "FF", 0)]}
        ordem_topologica = ["A", "B"]

        longest_path_to, start_offset_min = MOD_01._compute_longest_paths(
            nos, succ_map, pred_map_typed, ordem_topologica
        )

        # FF uses FS-conservative: base(A)=0 + 1 + lag(0) = 1
        assert start_offset_min["B"] == 1

    def test_ss_edge_uses_start_offset(self):
        """SS edge uses base + lag."""
        nos = ["A", "B"]
        succ_map = {"A": ["B"]}
        pred_map_typed = {"B": [("A", "SS", 2)]}
        ordem_topologica = ["A", "B"]

        _, start_offset_min = MOD_01._compute_longest_paths(nos, succ_map, pred_map_typed, ordem_topologica)
        # SS: base(A)=0 + lag(2) = 2
        assert start_offset_min["B"] == 2

    def test_shorter_candidate_not_longer_branch(self):
        """Branch 236→234: cand NOT longer than existing → skip update."""
        # A→C, B→C; A comes first so C gets [A,C]; then B's cand [B,C] is same length (not longer)
        nos = ["A", "B", "C"]
        succ_map = {"A": ["C"], "B": ["C"], "C": []}
        pred_map_typed = {"C": [("A", "FS", 5), ("B", "FS", 0)]}
        ordem_topologica = ["A", "B", "C"]

        longest_path_to, start_offset_min = MOD_01._compute_longest_paths(
            nos, succ_map, pred_map_typed, ordem_topologica
        )
        # C's start_offset = max(0+1+5, 0+1+0) = 6
        assert start_offset_min["C"] == 6
        # C's longest path goes through A (first update wins in a tie)
        assert "A" in longest_path_to["C"]


# ---------------------------------------------------------------------------
# 01-escopo-e-eap branch arcs: _topo_sort in_degree stays > 0 (51→49)
# ---------------------------------------------------------------------------


class TestTopoSort:
    def test_diamond_graph_triggers_non_zero_in_degree_branch(self):
        """Branch 51→49: diamond (A→C, B→C) — when A processed, C in_degree=1≠0 (False branch)."""
        nos = {"A", "B", "C"}
        succ = {"A": ["C"], "B": ["C"], "C": []}
        result = MOD_01._kahn(sorted(nos), [("A", "C"), ("B", "C")])
        assert set(result) == {"A", "B", "C"}
        assert result.index("C") > result.index("A")
        assert result.index("C") > result.index("B")


# ---------------------------------------------------------------------------
# 01-escopo-e-eap branch arcs: _build_dag_from_precedencias
# branch 175→170 (item already in map) and 207→203 (duplicate raw edge)
# ---------------------------------------------------------------------------


class TestBuildDagBranchArcs:
    def test_two_activities_same_item_second_skips_map_insert(self):
        """Branch 175→170: 2nd activity of same item → already in map → False branch."""
        from concilium.domain.models.canonical import EapItem

        eap = [EapItem(item_id="A", ordem=1, cpu_id="CPU-A", descricao="A", unidade="m3", quantitativo=10.0)]
        # Two activities for item "A" — second triggers the False branch at line 175
        nos = ["A-atv-1", "A-atv-2"]
        nos_set = set(nos)
        validacoes = []

        result = MOD_01._build_dag_from_precedencias(nos, nos_set, precedencias_raw=[], eap=eap, validacoes=validacoes)
        # Function emits VAL-DAG-01 with status="OK" when no errors — exactly one such entry
        dag_01 = [v for v in validacoes if v.codigo == "VAL-DAG-01"]
        assert all(v.status == "OK" for v in dag_01)

    def test_raw_edge_already_in_arestas_is_deduplicated(self):
        """Branch 207→203: raw edge already in typed arestas → any() True → skip."""
        from concilium.domain.models.canonical import EapItem

        eap_a = EapItem(item_id="A", ordem=1, cpu_id="CPU-A", descricao="A", unidade="m3", quantitativo=10.0)
        eap_b = EapItem(
            item_id="B", ordem=2, cpu_id="CPU-B", descricao="B", unidade="m3", quantitativo=10.0,
            predecessores=["A"],  # typed: A→B
        )
        nos = ["A-atv-1", "B-atv-1"]
        nos_set = set(nos)
        # Also pass same edge via precedencias_raw (legacy) → should be deduplicated
        precedencias_raw = [{"predecessora": "A-atv-1", "sucessora": "B-atv-1"}]
        validacoes = []

        result = MOD_01._build_dag_from_precedencias(nos, nos_set, precedencias_raw, eap=[eap_a, eap_b], validacoes=validacoes)
        # No ERRO VAL-DAG-01 (only OK); duplicate raw edge was skipped
        error_dag01 = [v for v in validacoes if v.codigo == "VAL-DAG-01" and v.status == "ERRO"]
        assert len(error_dag01) == 0
