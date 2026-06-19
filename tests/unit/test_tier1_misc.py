"""Tier 1 coverage — scheduling/pool_validator, mcp/tools/schemas, mcp/tools/prompts."""

from __future__ import annotations

from concilium.application.scheduling.pool_validator import (
    ResourcePoolValidator,
    _collect_schedule_weeks,
    _compute_week_demand,
)
from concilium.presentation.mcp.tools import prompts
from concilium.presentation.mcp.tools.schemas import (
    CatalogDraftSchema,
    ReplanSimResult,
    ResumoProjetoSchema,
    TaxProfileSchema,
)

# ── _collect_schedule_weeks ───────────────────────────────────────────────────


class TestCollectScheduleWeeks:
    def test_semanas_de_uma_atividade(self):
        schedule = {"A1": {"start_week": 1, "end_week": 3}}
        assert _collect_schedule_weeks(schedule) == {1, 2, 3}

    def test_semanas_de_multiplas_atividades(self):
        schedule = {
            "A1": {"start_week": 1, "end_week": 2},
            "A2": {"start_week": 3, "end_week": 4},
        }
        assert _collect_schedule_weeks(schedule) == {1, 2, 3, 4}

    def test_vazio(self):
        assert _collect_schedule_weeks({}) == set()

    def test_atividade_sem_start_end(self):
        # defaults para 0, gera range(0, 1) = {0}
        weeks = _collect_schedule_weeks({"A1": {}})
        assert 0 in weeks


# ── _compute_week_demand ──────────────────────────────────────────────────────


class TestComputeWeekDemand:
    def test_demanda_na_semana_ativa(self):
        schedule = {"A1": {"start_week": 1, "end_week": 3}}
        team_alloc = {"A1": {"OPERADOR": 2, "MOTORISTA": 1}}
        demand = _compute_week_demand(2, schedule, team_alloc)
        assert demand["OPERADOR"] == 2
        assert demand["MOTORISTA"] == 1

    def test_sem_demanda_fora_do_intervalo(self):
        schedule = {"A1": {"start_week": 5, "end_week": 8}}
        team_alloc = {"A1": {"OPERADOR": 2}}
        demand = _compute_week_demand(2, schedule, team_alloc)
        assert demand.get("OPERADOR", 0) == 0

    def test_duas_atividades_acumulam(self):
        schedule = {
            "A1": {"start_week": 1, "end_week": 2},
            "A2": {"start_week": 1, "end_week": 2},
        }
        team_alloc = {"A1": {"OPERADOR": 1}, "A2": {"OPERADOR": 2}}
        demand = _compute_week_demand(1, schedule, team_alloc)
        assert demand["OPERADOR"] == 3


# ── ResourcePoolValidator.validate_schedule ───────────────────────────────────


class TestResourcePoolValidatorValidateSchedule:
    def setup_method(self):
        self.validator = ResourcePoolValidator()

    def test_sem_pool_retorna_vazio(self):
        result = self.validator.validate_schedule(
            {"A1": {"start_week": 1, "end_week": 3}},
            {"A1": {"OPERADOR": 2}},
            pool_capacity={},
        )
        assert result == []

    def test_dentro_da_capacidade_sem_violacao(self):
        schedule = {"A1": {"start_week": 1, "end_week": 2}}
        team_alloc = {"A1": {"OPERADOR": 2}}
        pool = {"OPERADOR": 5}
        result = self.validator.validate_schedule(schedule, team_alloc, pool)
        assert result == []

    def test_excede_capacidade_gera_violacao(self):
        schedule = {"A1": {"start_week": 1, "end_week": 1}}
        team_alloc = {"A1": {"OPERADOR": 10}}
        pool = {"OPERADOR": 3}
        violations = self.validator.validate_schedule(schedule, team_alloc, pool)
        assert len(violations) > 0
        v = violations[0]
        assert v.code == "VAL-POOL-TEAM-01"
        assert v.status == "ERRO"
        assert v.magnitude == 7.0  # 10 - 3

    def test_role_sem_capacidade_definida_ignorado(self):
        schedule = {"A1": {"start_week": 1, "end_week": 1}}
        team_alloc = {"A1": {"ROLE_DESCONHECIDO": 99}}
        pool = {"OPERADOR": 5}
        result = self.validator.validate_schedule(schedule, team_alloc, pool)
        assert result == []

    def test_violacao_em_semana_especifica(self):
        schedule = {"A1": {"start_week": 1, "end_week": 3}}
        # só semana 2 excede
        team_alloc = {"A1": {"OPERADOR": 4}}
        pool = {"OPERADOR": 3}
        violations = self.validator.validate_schedule(schedule, team_alloc, pool)
        # deve ter violação em todas as 3 semanas (alocação constante)
        affected = [v.affected_items[0] for v in violations]
        assert any("week_1" in a for a in affected)
        assert any("week_2" in a for a in affected)
        assert any("week_3" in a for a in affected)

    def test_remediation_hint_contem_role(self):
        schedule = {"A1": {"start_week": 1, "end_week": 1}}
        team_alloc = {"A1": {"MOTORISTA": 5}}
        pool = {"MOTORISTA": 2}
        violations = self.validator.validate_schedule(schedule, team_alloc, pool)
        assert "MOTORISTA" in violations[0].remediation_hint


# ── ResourcePoolValidator.validate_week_allocations ──────────────────────────


class TestResourcePoolValidatorValidateWeekAllocations:
    def setup_method(self):
        self.validator = ResourcePoolValidator()

    def test_dentro_capacidade(self):
        result = self.validator.validate_week_allocations(
            week=1,
            week_allocations={"OPERADOR": 3},
            pool_capacity={"OPERADOR": 5},
        )
        assert result == []

    def test_excede_capacidade(self):
        violations = self.validator.validate_week_allocations(
            week=3,
            week_allocations={"MOTORISTA": 8},
            pool_capacity={"MOTORISTA": 4},
        )
        assert len(violations) == 1
        v = violations[0]
        assert v.magnitude == 4.0
        assert "week_3_MOTORISTA" in v.affected_items[0]
        assert "MOTORISTA" in v.remediation_hint

    def test_role_sem_capacidade_ignorado(self):
        result = self.validator.validate_week_allocations(
            week=1,
            week_allocations={"ROLE_X": 99},
            pool_capacity={"OPERADOR": 5},
        )
        assert result == []


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


# ── MCP Prompts ───────────────────────────────────────────────────────────────


class TestMcpPrompts:
    def test_nota_eap_sugerida_nao_vazia(self):
        assert len(prompts.NOTA_EAP_SUGERIDA) > 0

    def test_dica_busca_cpu_nao_vazia(self):
        assert len(prompts.DICA_BUSCA_CPU) > 0

    def test_notas_viabilidade_tem_viavel_e_inviavel(self):
        assert "VIAVEL" in prompts.NOTAS_VIABILIDADE
        assert "INVIAVEL" in prompts.NOTAS_VIABILIDADE

    def test_notas_viabilidade_inviavel_tem_placeholder(self):
        assert "{semanas}" in prompts.NOTAS_VIABILIDADE["INVIAVEL"]

    def test_proximos_passos_replan_e_lista(self):
        assert isinstance(prompts.PROXIMOS_PASSOS_REPLAN, list)
        assert len(prompts.PROXIMOS_PASSOS_REPLAN) >= 1

    def test_err_no_active_version_nao_vazio(self):
        assert len(prompts.ERR_NO_ACTIVE_VERSION) > 0

    def test_err_canonical_not_found_nao_vazio(self):
        assert len(prompts.ERR_CANONICAL_NOT_FOUND) > 0
