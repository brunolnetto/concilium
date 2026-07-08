"""Coverage tests for skill 05 — Equipes e Alocação (lines 95-444).

Import strategy: use `from concilium.application.skills import run_equipes_e_alocacao`
so that coverage.py can track the real module (_concilium_skillpkg_05_equipes_e_alocacao.skill).
All patches must reference _MOD_NAME so they target the correct namespace.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from concilium.application.skills import run_equipes_e_alocacao

_MOD_NAME = "_concilium_skillpkg_05_equipes_e_alocacao.skill"
_MOD_POOL = "_concilium_skillpkg_05_equipes_e_alocacao._skill_helpers_pool"
_MOD_INSTANCIAS = "_concilium_skillpkg_05_equipes_e_alocacao._skill_helpers_instancias"

from concilium.application.skills.base import SkillResult  # noqa: E402
from concilium.domain.models.canonical import RecursoContrato  # noqa: E402


def _eq(item_id, custo_total=1000.0, custo_inst_mo=None):
    e = MagicMock()
    e.item_id = item_id
    e.custo_total = custo_total
    e.custo_total_autonomo = None
    e.custo_inst_mo = custo_inst_mo
    e.contrato_tipo_id = None
    e.fracao_atribuicao = None
    return e


def _canonical(planejamento=None, cronograma=None, recurso_pool=None, indiretos=None):
    c = MagicMock()
    c.planejamento = planejamento
    c.eap = []
    r = MagicMock()
    r.horas_dia = 8
    r.dias_semana = 6
    c.projeto.regime_trabalho = r
    c.projeto.data_base_orcamento = "2026-01"
    c.cronograma = cronograma
    c.indiretos = indiretos or []
    c.indiretos_semanal = []
    c.resultado = None
    c.recurso_pool = recurso_pool or []
    c.model_copy.return_value = c
    return c


def _contrato(tipo_id, items, custo=5000.0, n_cadeias=0):
    c = MagicMock(spec=RecursoContrato)
    c.tipo_id = tipo_id
    c.items_cobertos = set(items)
    c.custo_total_contrato = custo
    c.n_cadeias = n_cadeias
    # ADR-071: quantidade_contratada é o campo real em RecursoContrato (pool_size do
    # contrato); quantidade_total pertence a RecursoPool, não a RecursoContrato.
    c.quantidade_contratada = 1
    return c


def _run_simple(equipes, inputs=None, planejamento=None):
    can = _canonical(planejamento=planejamento)
    with (
        patch(f"{_MOD_NAME}._build_dimensionamento", return_value=equipes),
        patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
        patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
        patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value=None),
    ):
        return run_equipes_e_alocacao(can, inputs or {}, {"cpus": [], "insumos": []})


class TestNoContracts:
    def test_minimal_returns_skill_result(self):
        r = _run_simple([])
        assert isinstance(r, SkillResult)
        assert any(v.codigo == "VAL-EQP-ALOC" for v in r.validacoes)

    def test_custo_inst_mo_none_no_error(self):
        r = _run_simple([_eq("E1", custo_inst_mo=None)])
        assert not any(v.codigo == "VAL-ESTAG1-INST-NONE" for v in r.validacoes)

    def test_custo_inst_mo_not_none_adds_erro(self):
        r = _run_simple([_eq("E1", custo_inst_mo=100.0)])
        erros = [v for v in r.validacoes if v.codigo == "VAL-ESTAG1-INST-NONE"]
        assert erros and erros[0].status == "ERRO"


class TestPlanejamentoReconciliation:
    def _plan_direct(self, item_id, custo):
        p = MagicMock()
        p.item_id = item_id
        p.custo_sem_bdi = float(custo)
        return p

    def _plan_dict_subtotal(self, item_id, custo):
        p = MagicMock()
        p.item_id = item_id
        p.custo_sem_bdi = None
        p.subtotal = {"sem_bdi": {"total": custo}}
        return p

    def test_direct_custo_sem_bdi_attr(self):
        eq = _eq("E1", custo_total=100.0)
        r = _run_simple([eq], planejamento=[self._plan_direct("E1", 9999.0)])
        assert any(v.codigo == "VAL-PLANEJAMENTO-OVERRIDE" for v in r.validacoes)
        assert eq.custo_total == 9999.0

    def test_dict_subtotal_path(self):
        eq = _eq("E1", custo_total=100.0)
        r = _run_simple([eq], planejamento=[self._plan_dict_subtotal("E1", 5000.0)])
        assert any(v.codigo == "VAL-PLANEJAMENTO-OVERRIDE" for v in r.validacoes)

    def test_object_subtotal_path(self):
        eq = _eq("E1", custo_total=100.0)
        plan = MagicMock()
        plan.item_id = "E1"
        plan.custo_sem_bdi = None
        sem_bdi = MagicMock()
        sem_bdi.total = 3000.0
        plan.subtotal = MagicMock(spec=object)
        plan.subtotal.sem_bdi = sem_bdi
        r = _run_simple([eq], planejamento=[plan])
        assert isinstance(r, SkillResult)

    def test_no_mismatch_no_aviso(self):
        eq = _eq("E1", custo_total=500.0)
        plan = self._plan_direct("E1", 500.0)
        r = _run_simple([eq], planejamento=[plan])
        assert not any(v.codigo == "VAL-PLANEJAMENTO-OVERRIDE" for v in r.validacoes)


class TestBenchmarkMode:
    def test_planejamento_ref_dict_populated(self):
        eq = _eq("E1", custo_total=100.0)
        can = _canonical()
        inputs = {
            "benchmark_mode": True,
            "planejamento_ref": [{"item_id": "E1", "subtotal": {"sem_bdi": {"total": 4000.0}}}],
        }
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value=None),
        ):
            r = run_equipes_e_alocacao(can, inputs, {"cpus": [], "insumos": []})
        assert any(v.codigo == "VAL-PLANEJAMENTO-OVERRIDE" for v in r.validacoes)

    def test_planejamento_ref_non_dict_skipped(self):
        eq = _eq("E1", custo_total=100.0)
        can = _canonical()
        inputs = {"benchmark_mode": True, "planejamento_ref": ["bad", None]}
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value=None),
        ):
            r = run_equipes_e_alocacao(can, inputs, {"cpus": [], "insumos": []})
        assert not any(v.codigo == "VAL-PLANEJAMENTO-OVERRIDE" for v in r.validacoes)

    def test_planejamento_ref_dict_missing_valid_subtotal_skipped(self):
        """Line 113 false branch: dict item present but subtotal isn't numeric — skipped."""
        eq = _eq("E1", custo_total=100.0)
        can = _canonical()
        inputs = {
            "benchmark_mode": True,
            "planejamento_ref": [{"item_id": "E1", "subtotal": {}}],
        }
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value=None),
        ):
            r = run_equipes_e_alocacao(can, inputs, {"cpus": [], "insumos": []})
        assert not any(v.codigo == "VAL-PLANEJAMENTO-OVERRIDE" for v in r.validacoes)

    def test_plan_subtotal_dict_sem_bdi_missing_total_key(self):
        """Line 128 false branch: subtotal dict has sem_bdi dict but no numeric 'total'."""
        eq = _eq("E1", custo_total=100.0)
        plan = MagicMock()
        plan.item_id = "E1"
        plan.custo_sem_bdi = None
        plan.subtotal = {"sem_bdi": {"total": "not-a-number"}}
        r = _run_simple([eq], planejamento=[plan])
        assert isinstance(r, SkillResult)
        assert not any(v.codigo == "VAL-PLANEJAMENTO-OVERRIDE" for v in r.validacoes)

    def test_plan_subtotal_dict_sem_bdi_not_a_dict(self):
        """Line 126 false branch: subtotal['sem_bdi'] resolves to a non-dict value."""
        eq = _eq("E1", custo_total=100.0)
        plan = MagicMock()
        plan.item_id = "E1"
        plan.custo_sem_bdi = None
        plan.subtotal = {"sem_bdi": "not-a-dict"}
        r = _run_simple([eq], planejamento=[plan])
        assert isinstance(r, SkillResult)
        assert not any(v.codigo == "VAL-PLANEJAMENTO-OVERRIDE" for v in r.validacoes)

    def test_plan_subtotal_object_sem_bdi_none(self):
        """Line 132 false branch: non-dict subtotal object whose sem_bdi attr is None."""
        eq = _eq("E1", custo_total=100.0)
        plan = MagicMock()
        plan.item_id = "E1"
        plan.custo_sem_bdi = None
        plan.subtotal = MagicMock(spec=object)
        plan.subtotal.sem_bdi = None
        r = _run_simple([eq], planejamento=[plan])
        assert isinstance(r, SkillResult)
        assert not any(v.codigo == "VAL-PLANEJAMENTO-OVERRIDE" for v in r.validacoes)

    def test_plan_subtotal_object_sem_bdi_total_not_numeric(self):
        """Line 134 false branch: sem_bdi.total present but not int/float."""
        eq = _eq("E1", custo_total=100.0)
        plan = MagicMock()
        plan.item_id = "E1"
        plan.custo_sem_bdi = None
        sem_bdi = MagicMock(spec=object)
        sem_bdi.total = "not-a-number"
        plan.subtotal = MagicMock(spec=object)
        plan.subtotal.sem_bdi = sem_bdi
        r = _run_simple([eq], planejamento=[plan])
        assert isinstance(r, SkillResult)
        assert not any(v.codigo == "VAL-PLANEJAMENTO-OVERRIDE" for v in r.validacoes)


class TestPoolContractPath:
    def test_rcpsp_in_inputs_triggers_contrato_ok(self):
        eq = _eq("E1")
        can = _canonical()
        rcpsp = {"activities": [{"item_id": "E1", "duration_weeks": 2}], "resource_pool": {}}
        ct = _contrato("R1", ["E1"])
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_POOL}._build_contratos_recurso", return_value=([ct], {"E1": (1500.0, "R1", 1.0)}, [])),
            patch(f"{_MOD_INSTANCIAS}._build_instancias_recurso", return_value=([], [], [])),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value=None),
        ):
            r = run_equipes_e_alocacao(can, {"rcpsp_spec": rcpsp}, {"cpus": [], "insumos": []})
        assert any(v.codigo == "VAL-POOL-CONTRATO-OK" for v in r.validacoes)
        assert eq.custo_total == 1500.0

    def test_derived_rcpsp_adds_spec_derivado(self):
        """Lines 323-324, 329: VAL-POOL-SPEC-DERIVADO when _rcpsp_derivado=True AND contratos non-empty."""
        eq = _eq("E1")
        can = _canonical()
        ct = _contrato("R1", ["E1"])
        derived = {"activities": [], "resource_pool": {}}
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value=derived),
            patch(f"{_MOD_POOL}._build_contratos_recurso", return_value=([ct], {}, [])),
            patch(f"{_MOD_INSTANCIAS}._build_instancias_recurso", return_value=([], [], [])),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
        ):
            r = run_equipes_e_alocacao(can, {}, {"cpus": [], "insumos": []})
        assert any(v.codigo == "VAL-POOL-SPEC-DERIVADO" for v in r.validacoes)

    def test_cadeias_perpetuacao_adds_validation(self):
        """Lines 341-342: VAL-PERPETUACAO-OK when cadeias_perpetuacao non-empty."""
        eq = _eq("E1")
        can = _canonical()
        ct = _contrato("R1", ["E1"], n_cadeias=2)
        cadeia = MagicMock()
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value={"activities": [], "resource_pool": {}}),
            patch(f"{_MOD_POOL}._build_contratos_recurso", return_value=([ct], {}, [cadeia])),
            patch(f"{_MOD_INSTANCIAS}._build_instancias_recurso", return_value=([], [], [])),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
        ):
            r = run_equipes_e_alocacao(can, {}, {"cpus": [], "insumos": []})
        assert any(v.codigo == "VAL-PERPETUACAO-OK" for v in r.validacoes)

    def test_benchmark_mode_caps_custo(self):
        """Lines 200-201 (non-instancia path): benchmark_mode=True caps eq.custo_total to min."""
        eq = _eq("E1", custo_total=300.0)
        can = _canonical()
        ct = _contrato("R1", ["E1"])
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value={"activities": [], "resource_pool": {}}),
            patch(f"{_MOD_POOL}._build_contratos_recurso", return_value=([ct], {"E1": (9999.0, "R1", 1.0)}, [])),
            patch(f"{_MOD_INSTANCIAS}._build_instancias_recurso", return_value=([], [], [])),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
        ):
            run_equipes_e_alocacao(can, {"benchmark_mode": True}, {"cpus": [], "insumos": []})
        assert eq.custo_total == 300.0

    def test_atribuicao_update_sets_fields(self):
        """Lines 354-360: the for loop that sets eq.custo_total, contrato_tipo_id, fracao_atribuicao."""
        eq = _eq("E1", custo_total=500.0)
        can = _canonical()
        ct = _contrato("R1", ["E1"])
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value={"activities": [], "resource_pool": {}}),
            patch(f"{_MOD_POOL}._build_contratos_recurso", return_value=([ct], {"E1": (2000.0, "R1", 0.5)}, [])),
            patch(f"{_MOD_INSTANCIAS}._build_instancias_recurso", return_value=([], [], [])),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
        ):
            run_equipes_e_alocacao(can, {}, {"cpus": [], "insumos": []})
        assert eq.custo_total == 2000.0
        assert eq.contrato_tipo_id == "R1"
        assert eq.fracao_atribuicao == 0.5

    def test_estag3_custo_inst_not_none_adds_aviso(self):
        """Line 351: VAL-ESTAG3-INST-NONE aviso when eq in atribuicao AND custo_inst_mo is not None."""
        eq = _eq("E1", custo_inst_mo=50.0)
        can = _canonical()
        ct = _contrato("R1", ["E1"])
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value={"activities": [], "resource_pool": {}}),
            patch(f"{_MOD_POOL}._build_contratos_recurso", return_value=([ct], {"E1": (1000.0, "R1", 1.0)}, [])),
            patch(f"{_MOD_INSTANCIAS}._build_instancias_recurso", return_value=([], [], [])),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
        ):
            r = run_equipes_e_alocacao(can, {}, {"cpus": [], "insumos": []})
        assert any(v.codigo == "VAL-ESTAG3-INST-NONE" for v in r.validacoes)

    def test_instancias_generates_recurso_ok(self):
        """Lines 391-395: VAL-INSTANCIA-RECURSO-OK when resumo_utilizacao_contratos non-empty."""
        eq = _eq("E1")
        can = _canonical()
        ct = _contrato("R1", ["E1"])
        resumo = MagicMock()
        resumo.status_utilizacao = "OK"
        resumo.taxa_utilizacao_pct = 80.0
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value={"activities": [], "resource_pool": {}}),
            patch(f"{_MOD_POOL}._build_contratos_recurso", return_value=([ct], {}, [])),
            patch(f"{_MOD_INSTANCIAS}._build_instancias_recurso", return_value=([MagicMock()], [], [resumo])),
            patch(f"{_MOD_INSTANCIAS}._aplicar_custo_instancial"),
            patch(f"{_MOD_INSTANCIAS}._enrich_equipes_com_decomposicao_instancial"),
            patch(f"{_MOD_INSTANCIAS}._enrich_particao_overhead"),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
        ):
            r = run_equipes_e_alocacao(can, {}, {"cpus": [], "insumos": []})
        assert any(v.codigo == "VAL-INSTANCIA-RECURSO-OK" for v in r.validacoes)

    def test_instancias_missing_custo_inst_adds_estag4_erro(self):
        """Lines 414-419, 421: VAL-ESTAG4-INST-MISSING when instancias present but custo_inst_mo is None."""
        eq = _eq("E1", custo_inst_mo=None)
        can = _canonical()
        ct = _contrato("R1", ["E1"])
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value={"activities": [], "resource_pool": {}}),
            patch(f"{_MOD_POOL}._build_contratos_recurso", return_value=([ct], {}, [])),
            patch(f"{_MOD_INSTANCIAS}._build_instancias_recurso", return_value=([MagicMock()], [], [])),
            patch(f"{_MOD_INSTANCIAS}._aplicar_custo_instancial"),
            patch(f"{_MOD_INSTANCIAS}._enrich_equipes_com_decomposicao_instancial"),
            patch(f"{_MOD_INSTANCIAS}._enrich_particao_overhead"),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
        ):
            r = run_equipes_e_alocacao(can, {}, {"cpus": [], "insumos": []})
        assert any(v.codigo == "VAL-ESTAG4-INST-MISSING" for v in r.validacoes)

    def test_enrich_particao_overhead_called_when_cadeias_and_instancias(self):
        """Lines 374-375, 383: _enrich_particao_overhead called when both cadeias and instancias non-empty."""
        eq = _eq("E1")
        can = _canonical()
        ct = _contrato("R1", ["E1"])
        cadeia = MagicMock()
        inst = MagicMock()
        resumo = MagicMock()
        resumo.status_utilizacao = "OK"
        resumo.taxa_utilizacao_pct = 90.0
        mock_enrich_particao = MagicMock()
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value={"activities": [], "resource_pool": {}}),
            patch(f"{_MOD_POOL}._build_contratos_recurso", return_value=([ct], {}, [cadeia])),
            patch(f"{_MOD_INSTANCIAS}._build_instancias_recurso", return_value=([inst], [], [resumo])),
            patch(f"{_MOD_INSTANCIAS}._aplicar_custo_instancial"),
            patch(f"{_MOD_INSTANCIAS}._enrich_equipes_com_decomposicao_instancial"),
            patch(f"{_MOD_INSTANCIAS}._enrich_particao_overhead", mock_enrich_particao),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
        ):
            run_equipes_e_alocacao(can, {}, {"cpus": [], "insumos": []})
        mock_enrich_particao.assert_called_once()

    def test_benchmark_instancias_planejamento_caps_custo(self):
        """Lines 296-304: benchmark_mode + instancias + planejamento_map → min cap on eq.custo_total."""
        eq = _eq("E1", custo_total=800.0)
        plan = MagicMock()
        plan.item_id = "E1"
        plan.custo_sem_bdi = 500.0
        can = _canonical(planejamento=[plan])
        ct = _contrato("R1", ["E1"])

        # After _aplicar_custo_instancial, eq.custo_total should be capped at plan value
        def fake_aplicar(contratos, instancias, equipes_list, validacoes_list):
            for e in equipes_list:
                e.custo_total = 9000.0  # simulate instancial raises custo

        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value={"activities": [], "resource_pool": {}}),
            patch(f"{_MOD_POOL}._build_contratos_recurso", return_value=([ct], {}, [])),
            patch(f"{_MOD_INSTANCIAS}._build_instancias_recurso", return_value=([MagicMock()], [], [])),
            patch(f"{_MOD_INSTANCIAS}._aplicar_custo_instancial", side_effect=fake_aplicar),
            patch(f"{_MOD_INSTANCIAS}._enrich_equipes_com_decomposicao_instancial"),
            patch(f"{_MOD_INSTANCIAS}._enrich_particao_overhead"),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
        ):
            run_equipes_e_alocacao(can, {"benchmark_mode": True}, {"cpus": [], "insumos": []})
        # eq.custo_total should be capped to 500.0 (planejamento value)
        assert eq.custo_total == 500.0

    def test_benchmark_instancias_planejamento_ref_map_caps_custo(self):
        """Lines 296-304: benchmark_mode + instancias + planejamento_ref_map → min cap."""
        eq = _eq("E1", custo_total=800.0)
        can = _canonical()
        ct = _contrato("R1", ["E1"])

        def fake_aplicar(contratos, instancias, equipes_list, validacoes_list):
            for e in equipes_list:
                e.custo_total = 9000.0

        inputs = {
            "benchmark_mode": True,
            "planejamento_ref": [{"item_id": "E1", "subtotal": {"sem_bdi": {"total": 600.0}}}],
        }
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value={"activities": [], "resource_pool": {}}),
            patch(f"{_MOD_POOL}._build_contratos_recurso", return_value=([ct], {}, [])),
            patch(f"{_MOD_INSTANCIAS}._build_instancias_recurso", return_value=([MagicMock()], [], [])),
            patch(f"{_MOD_INSTANCIAS}._aplicar_custo_instancial", side_effect=fake_aplicar),
            patch(f"{_MOD_INSTANCIAS}._enrich_equipes_com_decomposicao_instancial"),
            patch(f"{_MOD_INSTANCIAS}._enrich_particao_overhead"),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
        ):
            run_equipes_e_alocacao(can, inputs, {"cpus": [], "insumos": []})
        assert eq.custo_total == 600.0

    def test_benchmark_instancias_item_not_in_any_map_no_cap(self):
        """Line 311 false branch (item_id absent from planejamento_ref_map) followed
        by line 313 false branch (custo_ref stays 0) — no cap applied."""
        eq = _eq("E1", custo_total=800.0)
        plan = MagicMock()
        plan.item_id = "OTHER-ITEM"  # does not match eq.item_id
        plan.custo_sem_bdi = 500.0
        can = _canonical(planejamento=[plan])
        ct = _contrato("R1", ["E1"])

        def fake_aplicar(contratos, instancias, equipes_list, validacoes_list):
            for e in equipes_list:
                e.custo_total = 9000.0

        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value={"activities": [], "resource_pool": {}}),
            patch(f"{_MOD_POOL}._build_contratos_recurso", return_value=([ct], {}, [])),
            patch(f"{_MOD_INSTANCIAS}._build_instancias_recurso", return_value=([MagicMock()], [], [])),
            patch(f"{_MOD_INSTANCIAS}._aplicar_custo_instancial", side_effect=fake_aplicar),
            patch(f"{_MOD_INSTANCIAS}._enrich_equipes_com_decomposicao_instancial"),
            patch(f"{_MOD_INSTANCIAS}._enrich_particao_overhead"),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
        ):
            run_equipes_e_alocacao(can, {"benchmark_mode": True}, {"cpus": [], "insumos": []})
        # No matching planejamento entry for E1 -> custo_ref stays 0 -> no cap applied
        assert eq.custo_total == 9000.0

    def test_contratos_recurso_empty_skips_pool_validation_block(self):
        """Line 216 false branch: rcpsp_spec present but _build_contratos_recurso
        returns an empty list — the whole VAL-POOL-* validation block is skipped."""
        eq = _eq("E1")
        can = _canonical()
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value={"activities": [], "resource_pool": {}}),
            patch(f"{_MOD_POOL}._build_contratos_recurso", return_value=([], {}, [])),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
        ):
            r = run_equipes_e_alocacao(can, {}, {"cpus": [], "insumos": []})
        assert not any(v.codigo == "VAL-POOL-CONTRATO-OK" for v in r.validacoes)


class TestAdr078PreProcessamento:
    def test_resource_costs_triggers_pre_processamento(self):
        """Lines 428-429, 432-433: rcpsp_spec.get('resource_costs') truthy
        → _build_pre_processamento_compartilhamento."""
        eq = _eq("E1")
        can = _canonical()
        ct = _contrato("R1", ["E1"])
        rcpsp = {
            "activities": [{"item_id": "E1", "duration_weeks": 2}],
            "resource_pool": {},
            "resource_costs": {"R1": 100.0},
        }
        mock_relatorio = MagicMock()
        mock_build_pre = MagicMock(return_value=mock_relatorio)
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_POOL}._build_contratos_recurso", return_value=([ct], {}, [])),
            patch(f"{_MOD_INSTANCIAS}._build_instancias_recurso", return_value=([], [], [])),
            patch(f"{_MOD_NAME}._build_pre_processamento_compartilhamento", mock_build_pre),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value=None),
        ):
            r = run_equipes_e_alocacao(can, {"rcpsp_spec": rcpsp}, {"cpus": [], "insumos": []})
        mock_build_pre.assert_called_once()
        assert isinstance(r, SkillResult)

    def test_no_resource_costs_skips_pre_processamento(self):
        """Lines 428-429: when resource_costs absent, _build_pre_processamento not called."""
        eq = _eq("E1")
        can = _canonical()
        ct = _contrato("R1", ["E1"])
        rcpsp = {"activities": [], "resource_pool": {}}
        mock_build_pre = MagicMock()
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_POOL}._build_contratos_recurso", return_value=([ct], {}, [])),
            patch(f"{_MOD_INSTANCIAS}._build_instancias_recurso", return_value=([], [], [])),
            patch(f"{_MOD_NAME}._build_pre_processamento_compartilhamento", mock_build_pre),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value=None),
        ):
            run_equipes_e_alocacao(can, {"rcpsp_spec": rcpsp}, {"cpus": [], "insumos": []})
        mock_build_pre.assert_not_called()


class TestAdr133Oportunidades:
    def test_adr133_trigger_with_cronograma_and_pool(self):
        """Lines 443-444: ADR-133 block triggered when relatorio_oportunidades is not None
        AND canonical.cronograma.scheduled_activities AND canonical.recurso_pool non-empty."""
        eq = _eq("E1")
        sa = MagicMock()
        sa.activity_id = "E1"
        sa.semana_inicio_idx = 0
        sa.semana_fim_idx = 2
        cronograma = MagicMock()
        cronograma.scheduled_activities = [sa]
        cronograma.makespan_weeks = 2
        recurso_pool = [MagicMock()]
        can = _canonical(cronograma=cronograma, recurso_pool=recurso_pool)
        ct = _contrato("R1", ["E1"])
        ct.items_cobertos = {"E1"}
        rcpsp = {
            "activities": [{"item_id": "E1", "duration_weeks": 2, "required_resources": {"R1": 1}}],
            "resource_pool": {"R1": 1},
            "resource_costs": {"R1": 100.0},
            "precedence": [],
        }
        mock_relatorio = MagicMock()
        mock_relatorio.model_copy.return_value = mock_relatorio
        mock_build_pre = MagicMock(return_value=mock_relatorio)
        # Let the ADR-133 block run naturally (it uses try/except internally)
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_POOL}._build_contratos_recurso", return_value=([ct], {}, [])),
            patch(f"{_MOD_INSTANCIAS}._build_instancias_recurso", return_value=([], [], [])),
            patch(f"{_MOD_NAME}._build_pre_processamento_compartilhamento", mock_build_pre),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value=None),
        ):
            r = run_equipes_e_alocacao(can, {"rcpsp_spec": rcpsp}, {"cpus": [], "insumos": []})
        # The block should run (covered) even if it fails internally — best-effort try/except
        assert isinstance(r, SkillResult)

    def test_adr133_second_contrato_does_not_cover_activity(self):
        """Line 370 false branch: a contrato in the list that does NOT cover the
        activity — loop must continue to the next contrato (line 369)."""
        eq = _eq("E1")
        sa = MagicMock()
        sa.activity_id = "E1"
        sa.semana_inicio_idx = 0
        sa.semana_fim_idx = 2
        cronograma = MagicMock()
        cronograma.scheduled_activities = [sa]
        cronograma.makespan_weeks = 2
        recurso_pool = [MagicMock()]
        can = _canonical(cronograma=cronograma, recurso_pool=recurso_pool)
        ct_no_match = _contrato("R0", ["OTHER-ITEM"])
        ct_no_match.items_cobertos = {"OTHER-ITEM"}
        ct_match = _contrato("R1", ["E1"])
        ct_match.items_cobertos = {"E1"}
        rcpsp = {
            "activities": [{"item_id": "E1", "duration_weeks": 2, "required_resources": {"R1": 1}}],
            "resource_pool": {"R1": 1},
            "resource_costs": {"R1": 100.0},
            "precedence": [],
        }
        mock_relatorio = MagicMock()
        mock_relatorio.model_copy.return_value = mock_relatorio
        mock_build_pre = MagicMock(return_value=mock_relatorio)
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(
                f"{_MOD_POOL}._build_contratos_recurso",
                return_value=([ct_no_match, ct_match], {}, []),
            ),
            patch(f"{_MOD_INSTANCIAS}._build_instancias_recurso", return_value=([], [], [])),
            patch(f"{_MOD_NAME}._build_pre_processamento_compartilhamento", mock_build_pre),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value=None),
        ):
            r = run_equipes_e_alocacao(can, {"rcpsp_spec": rcpsp}, {"cpus": [], "insumos": []})
        assert isinstance(r, SkillResult)


class TestAdr133IndiretosCoverage:
    def test_adr133_with_indiretos_and_oportunidades(self):
        """Lines 417-419 (indiretos branch) + 429-444 (oportunidades truthy)."""
        eq = _eq("E1")
        sa = MagicMock()
        sa.activity_id = "E1"
        sa.semana_inicio_idx = 0
        sa.semana_fim_idx = 2
        cronograma = MagicMock()
        cronograma.scheduled_activities = [sa]
        cronograma.makespan_weeks = 2
        indireto = MagicMock()
        indireto.custo_total = 1000.0
        recurso_pool = [MagicMock()]
        can = _canonical(cronograma=cronograma, recurso_pool=recurso_pool, indiretos=[indireto])
        ct = _contrato("R1", ["E1"])
        ct.items_cobertos = {"E1"}
        rcpsp = {
            "activities": [{"item_id": "E1", "duration_weeks": 2, "required_resources": {"R1": 1}}],
            "resource_pool": {"R1": 1},
            "resource_costs": {"R1": 100.0},
            "precedence": [],
        }
        mock_relatorio = MagicMock()
        mock_relatorio.model_copy.return_value = mock_relatorio
        mock_build_pre = MagicMock(return_value=mock_relatorio)
        # Return a non-empty list from _detectar_oportunidades_paralelo to trigger lines 429-444
        mock_opp = MagicMock()
        mock_opp.economicamente_viavel = True
        mock_detect = MagicMock(return_value=[mock_opp])
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_POOL}._build_contratos_recurso", return_value=([ct], {}, [])),
            patch(f"{_MOD_INSTANCIAS}._build_instancias_recurso", return_value=([], [], [])),
            patch(f"{_MOD_NAME}._build_pre_processamento_compartilhamento", mock_build_pre),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value=None),
            patch(
                "_concilium_skillpkg_05_equipes_e_alocacao._skill_helpers_pre._detectar_oportunidades_paralelo",
                mock_detect,
            ),
        ):
            r = run_equipes_e_alocacao(can, {"rcpsp_spec": rcpsp}, {"cpus": [], "insumos": []})
        assert isinstance(r, SkillResult)
        # VAL-OPP-PARALELO-OK added when oportunidades non-empty
        assert any(v.codigo == "VAL-OPP-PARALELO-OK" for v in r.validacoes)


class TestAdr133ExceptionCoverage:
    def test_adr133_exception_path_covered(self):
        """Lines 443-444: except Exception: pass when ADR-133 try block fails."""
        eq = _eq("E1")
        sa = MagicMock()
        sa.activity_id = "E1"
        sa.semana_inicio_idx = 0
        sa.semana_fim_idx = 2
        cronograma = MagicMock()
        cronograma.scheduled_activities = [sa]
        cronograma.makespan_weeks = 2
        recurso_pool = [MagicMock()]
        can = _canonical(cronograma=cronograma, recurso_pool=recurso_pool)
        ct = _contrato("R1", ["E1"])
        ct.items_cobertos = {"E1"}
        rcpsp = {
            "activities": [{"item_id": "E1", "duration_weeks": 2, "required_resources": {"R1": 1}}],
            "resource_pool": {"R1": 1},
            "resource_costs": {"R1": 100.0},
            "precedence": [],
        }
        mock_relatorio = MagicMock()
        mock_relatorio.model_copy.return_value = mock_relatorio
        mock_build_pre = MagicMock(return_value=mock_relatorio)
        # Make the import of scheduling models fail so except block is reached
        import concilium.application.scheduling.models as _sched_models

        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_POOL}._build_contratos_recurso", return_value=([ct], {}, [])),
            patch(f"{_MOD_INSTANCIAS}._build_instancias_recurso", return_value=([], [], [])),
            patch(f"{_MOD_NAME}._build_pre_processamento_compartilhamento", mock_build_pre),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value=None),
            # Make ScheduledActivity constructor raise to trigger the except block
            patch.object(_sched_models, "ScheduledActivity", side_effect=RuntimeError("boom")),
        ):
            r = run_equipes_e_alocacao(can, {"rcpsp_spec": rcpsp}, {"cpus": [], "insumos": []})
        # Should still succeed — except: pass swallows the error
        assert isinstance(r, SkillResult)


class TestFillCustoInstSemPool:
    def test_fill_custo_inst_sem_pool_exception_covered(self):
        """Lines 323-324: except Exception: pass when _fill_custo_inst_sem_pool raises."""
        eq = _eq("E1")
        can = _canonical()
        with (
            patch(f"{_MOD_NAME}._build_dimensionamento", return_value=[eq]),
            patch(f"{_MOD_NAME}._build_requisitos_e_tipos", return_value=([], {})),
            patch(f"{_MOD_NAME}._build_alocacoes_pool", return_value=([], {})),
            patch(f"{_MOD_POOL}._derive_rcpsp_from_canonical", return_value=None),
            # Patch the already-imported _fill_custo_inst_sem_pool in the engine module
            patch(
                "concilium.domain.services.financial.equipe_custo_engine._fill_custo_inst_sem_pool",
                side_effect=RuntimeError("test error"),
            ),
        ):
            r = run_equipes_e_alocacao(can, {}, {"cpus": [], "insumos": []})
        # Should still succeed — exception is swallowed
        assert isinstance(r, SkillResult)


class TestPlanCustoSemBdiHelperPaths:
    """Lines 126-128: exception path and fallback return 0.0 in _plan_custo_sem_bdi_total."""

    def test_plan_raises_exception_returns_zero(self):
        """Lines 126-127: except Exception block — plan.custo_sem_bdi raises."""
        eq = _eq("E1", custo_total=100.0)
        bad_plan = MagicMock()
        type(bad_plan).custo_sem_bdi = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
        bad_plan.item_id = "E1"
        r = _run_simple([eq], planejamento=[bad_plan])
        assert isinstance(r, SkillResult)
        assert not any(v.codigo == "VAL-PLANEJAMENTO-OVERRIDE" for v in r.validacoes)

    def test_plan_subtotal_none_returns_zero(self):
        """Line 128: final return 0.0 when both custo_sem_bdi and subtotal are None/0."""
        eq = _eq("E1", custo_total=100.0)
        plan = MagicMock()
        plan.item_id = "E1"
        plan.custo_sem_bdi = None
        plan.subtotal = None
        r = _run_simple([eq], planejamento=[plan])
        assert isinstance(r, SkillResult)
        assert not any(v.codigo == "VAL-PLANEJAMENTO-OVERRIDE" for v in r.validacoes)


# ---------------------------------------------------------------------------
# importlib fallback in the module header (lines 47-82): triggered only when
# `from ._skill_helpers_x import ...` fails (e.g. skill.py loaded standalone,
# with no parent package registered).  Lines 54/60/66 guard against
# spec_from_file_location returning a broken spec for each helper module.
# ---------------------------------------------------------------------------


class TestSkillHeaderImportlibFallback:
    """Force skill.py's `except ImportError:` header block to run standalone."""

    def _skill_path(self):
        import concilium.application.skills as skills_pkg

        return skills_pkg._MANIFESTS / "05-equipes-e-alocacao" / "skill.py"

    def _exec_standalone(self, monkeypatch, blocked_name, module_alias):
        """Load skill.py with no dotted package context, so the relative
        imports in its `try:` block fail with ImportError and execution
        falls into the `except ImportError:` importlib-based fallback.
        Then intercept spec_from_file_location for `blocked_name` to
        return None, exercising the `raise ImportError(...) from None` guard.
        """
        import importlib.util

        real_spec_from_file_location = importlib.util.spec_from_file_location

        def fake_spec_from_file_location(name, path, *a, **kw):
            if name == blocked_name:
                return None
            return real_spec_from_file_location(name, path, *a, **kw)

        monkeypatch.setattr(importlib.util, "spec_from_file_location", fake_spec_from_file_location)

        # No dot in the name => __package__ becomes "" => relative imports fail.
        spec = real_spec_from_file_location(module_alias, self._skill_path())
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

    def test_raises_when_spec_a_is_none(self, monkeypatch):
        import pytest

        with pytest.raises(ImportError, match="_skill_helpers_a.py"):
            self._exec_standalone(monkeypatch, "skill05_helpers_a", "standalone_skill05_test_a")

    def test_raises_when_spec_b_is_none(self, monkeypatch):
        import pytest

        with pytest.raises(ImportError, match="_skill_helpers_b.py"):
            self._exec_standalone(monkeypatch, "skill05_helpers_b", "standalone_skill05_test_b")

    def test_raises_when_spec_pre_is_none(self, monkeypatch):
        import pytest

        with pytest.raises(ImportError, match="_skill_helpers_pre.py"):
            self._exec_standalone(monkeypatch, "skill05_helpers_pre", "standalone_skill05_test_pre")
