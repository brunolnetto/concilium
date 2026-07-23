"""Coverage batch 36 — 01-escopo-e-eap, 02-produtividade-climatica, 07-diagnostico-criticidade."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_skill(rel_path: str, name: str):
    p = Path(rel_path).resolve()
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

MOD_01 = _load_skill("src/concilium/application/skills/manifests/01-escopo-e-eap/skill.py", "skill01_b36")

MOD_02 = _load_skill("src/concilium/application/skills/manifests/02-produtividade-climatica/skill.py", "skill02_b36")

MOD_07 = _load_skill("src/concilium/application/skills/manifests/07-diagnostico-criticidade/skill.py", "skill07_b36")


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

    def test_invalid_frac_raises_val_atv_03(self):
        """fracao_quantitativo fora de (0, 1] dispara VAL-ATV-03 mas ainda constrói a atividade."""
        from concilium.domain.models.canonical import EapItem

        eap_item = EapItem(
            item_id="EAP-002",
            ordem=1,
            cpu_id="CPU-A",
            descricao="Test",
            unidade="m3",
            quantitativo=100.0,
        )
        raw_ativs = [{"fracao_quantitativo": 1.5, "atividade_id": "EAP-002-atv-1"}]
        validacoes = []

        result = MOD_01._build_atividades_for_item(eap_item, raw_ativs, validacoes)
        assert len(result) == 1
        # frac=1.5 dispara VAL-ATV-03 (fração inválida) e, como soma_fracoes usa o
        # valor bruto (1.5 != 1.0), também VAL-ATV-02 (soma de frações).
        codigos = {v.codigo for v in validacoes}
        assert codigos == {"VAL-ATV-03", "VAL-ATV-02"}
        assert all(v.status == "ERRO" for v in validacoes)
        # Regressão: Atividade.fracao_quantitativo exige (0, 1] — sem o clamp para
        # 1.0, a construção do modelo levantaria pydantic.ValidationError aqui.
        assert result[0].fracao_quantitativo == 1.0

    def test_zero_frac_raises_val_atv_03(self):
        from concilium.domain.models.canonical import EapItem

        eap_item = EapItem(
            item_id="EAP-003",
            ordem=1,
            cpu_id="CPU-A",
            descricao="Test",
            unidade="m3",
            quantitativo=100.0,
        )
        raw_ativs = [{"fracao_quantitativo": 0.0, "atividade_id": "EAP-003-atv-1"}]
        validacoes = []

        result = MOD_01._build_atividades_for_item(eap_item, raw_ativs, validacoes)
        codigos = {v.codigo for v in validacoes}
        assert "VAL-ATV-03" in codigos
        assert result[0].fracao_quantitativo == 1.0


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

        MOD_01._build_dag_from_precedencias(
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

        MOD_01._build_dag_from_precedencias(nos, nos_set, precedencias_raw=[], eap=eap, validacoes=validacoes)
        # Function emits VAL-DAG-01 with status="OK" when no errors — exactly one such entry
        dag_01 = [v for v in validacoes if v.codigo == "VAL-DAG-01"]
        assert all(v.status == "OK" for v in dag_01)

    def test_raw_edge_already_in_arestas_is_deduplicated(self):
        """Branch 207→203: raw edge already in typed arestas → any() True → skip."""
        from concilium.domain.models.canonical import EapItem

        eap_a = EapItem(item_id="A", ordem=1, cpu_id="CPU-A", descricao="A", unidade="m3", quantitativo=10.0)
        eap_b = EapItem(
            item_id="B",
            ordem=2,
            cpu_id="CPU-B",
            descricao="B",
            unidade="m3",
            quantitativo=10.0,
            predecessores=["A"],  # typed: A→B
        )
        nos = ["A-atv-1", "B-atv-1"]
        nos_set = set(nos)
        # Also pass same edge via precedencias_raw (legacy) → should be deduplicated
        precedencias_raw = [{"predecessora": "A-atv-1", "sucessora": "B-atv-1"}]
        validacoes = []

        MOD_01._build_dag_from_precedencias(nos, nos_set, precedencias_raw, eap=[eap_a, eap_b], validacoes=validacoes)
        # No ERRO VAL-DAG-01 (only OK); duplicate raw edge was skipped
        error_dag01 = [v for v in validacoes if v.codigo == "VAL-DAG-01" and v.status == "ERRO"]
        assert len(error_dag01) == 0



from datetime import UTC, datetime  # noqa: E402

from concilium.application.skills import run_escopo_e_eap  # noqa: E402
from concilium.domain.models.canonical import (  # noqa: E402
    CanonicalModel,
    Coordenadas,
    EapItem,
    Meta,
    Projeto,
    RegimeTrabalho,
)


# Shims: skills atividades/sequenciamento foram fundidas em 01-escopo-e-eap.
def _canonical_to_inputs(canonical, extra_inputs):
    """Converte um canonical existente + extra_inputs em inputs para run_escopo_e_eap."""
    proj = canonical.projeto if canonical else None
    base = {
        "contexto_id": canonical.meta.contexto_id if canonical else "test",
        "snapshot_catalogo_id": proj.snapshot_catalogo_id if proj else "s",
        "snapshot_perfil_id": proj.snapshot_perfil_id if proj else "s",
        "nome": proj.nome if proj else "test",
        "tipo_obra": proj.tipo_obra if proj else "terraplenagem",
        "localizacao": proj.localizacao if proj else "x",
        "coordenadas": {"lat": proj.coordenadas.lat if proj else 0.0, "lng": proj.coordenadas.lng if proj else 0.0},
        "regime_trabalho": {
            "dias_semana": proj.regime_trabalho.dias_semana if proj else 5,
            "horas_dia": proj.regime_trabalho.horas_dia if proj else 8,
        },
        "data_inicio": str(proj.data_inicio) if proj else "2026-01-01",
        "data_termino": str(proj.data_termino) if proj else "2026-12-31",
        "eap": [i.model_dump() for i in canonical.eap] if canonical and canonical.eap else [],
    }
    base.update(extra_inputs or {})
    return base


def run_atividades(canonical, inputs):
    return run_escopo_e_eap(None, _canonical_to_inputs(canonical, inputs))


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")


def _make_proj():
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=0.0, lng=0.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio="2026-01-01",
        data_termino="2026-12-31",
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )


def _minimal_canonical(eap=None, atividades=None):
    return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), eap=eap or [], atividades=atividades or [])


# ══ 01-escopo-e-eap ═══════════════════════════════════════════════════════════


class TestAtividades:
    def test_precondition_eap_vazia(self):
        """EAP vazia deve retornar aviso de EAP vazia."""
        can = _minimal_canonical()
        res = run_atividades(can, {})
        codigos = {v.codigo: v.status for v in res.validacoes}
        assert "VAL-EAP-03" in codigos  # EAP vazia emite VAL-EAP-03

    def test_soma_fracoes_invalida_emite_val_atv02(self):
        """Frações que não somam 1.0 devem emitir VAL-ATV-02 ERRO."""
        eap = [EapItem(item_id="i1", ordem=1, cpu_id="CPU-X", descricao="T", unidade="m3", quantitativo=100)]
        can = _minimal_canonical(eap=eap)
        decomposicao = [
            {
                "eap_item_id": "i1",
                "atividades": [
                    {"atividade_id": "atv-1", "fracao_quantitativo": 0.4, "descricao": "A"},
                    {"atividade_id": "atv-2", "fracao_quantitativo": 0.3, "descricao": "B"},
                ],
            }
        ]
        res = run_atividades(can, {"decomposicao": decomposicao})
        codigos = [v.codigo for v in res.validacoes]
        assert "VAL-ATV-02" in codigos



