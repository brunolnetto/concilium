"""ADR-082-cons / NEP-035: consistência da base de cálculo (produtividade × custo).

Cobre:
  - _build_dist_cell: η_s (alocação), η_p (praticabilidade), η_w (gestão), q_max, perda_fisica
  - fator_total = η_s · η_p · η_w  (identidade verificável)
  - VAL-PROD-VS-PU: divergência de produtividade engine ↔ catálogo isolada do clima
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

_ROOT = Path(__file__).parent.parent.parent.parent.parent / "src/concilium/application/skills/manifests"


def _load(mod_name: str, rel_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(mod_name, _ROOT / rel_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


from concilium.application.skills import run_cronograma as _run_cronograma  # noqa: E402

assert _run_cronograma
_cron = sys.modules["_concilium_skillpkg_04_cronograma.skill"]
_cons = _load("_cons_helpers_082", "06-resultado-financeiro/_consolidacao/_skill_helpers/__init__.py")


# ── _build_dist_cell: eficiencia = utilização; fator_total = p_j × m_ij ──────


class TestBuildDistCell:
    def test_semana_pico_todos_os_eta_1(self):
        # n_j = n_max, clima=1, calend=1, sem fechamento → η_s=η_p=η_w=1
        cell = _cron._build_dist_cell(
            producao_semanal_base=100.0,
            num_eq=2,
            n_max=2,
            fator_clima=1.0,
            fator_calendario=1.0,
            quantitativo=10_000.0,
            qtd_acumulada=0.0,
        )
        assert cell.eta_s == 1.0
        assert cell.eta_p == 1.0
        assert cell.eta_w == 1.0
        assert abs(cell.fator_total - 1.0) < 1e-6
        assert cell.qtd_executada == 200.0  # 100 × 1 × 2
        assert cell.q_max_celula == 200.0
        assert cell.perda_fisica == 0.0

    def test_subalocacao_captura_eta_s(self):
        # n_j=1, n_max=2 → η_s=0.5; clima=1, calend=1
        cell = _cron._build_dist_cell(
            producao_semanal_base=100.0,
            num_eq=1,
            n_max=2,
            fator_clima=1.0,
            fator_calendario=1.0,
            quantitativo=10_000.0,
            qtd_acumulada=0.0,
        )
        assert abs(cell.eta_s - 0.5) < 1e-6
        assert cell.eta_p == 1.0
        assert cell.eta_w == 1.0
        assert abs(cell.fator_total - 0.5) < 1e-6
        assert cell.qtd_executada == 100.0  # 100 × 0.5
        assert cell.q_max_celula == 200.0  # referência = pico n_max=2
        assert abs(cell.perda_fisica - 100.0) < 1e-4  # q_max(200) - q_executada(100)

    def test_praticabilidade_captura_eta_p(self):
        # n_j=2, n_max=2, clima=0.8, calend=0.9 → η_p=0.72
        cell = _cron._build_dist_cell(
            producao_semanal_base=100.0,
            num_eq=2,
            n_max=2,
            fator_clima=0.8,
            fator_calendario=0.9,
            quantitativo=10_000.0,
            qtd_acumulada=0.0,
        )
        assert abs(cell.eta_s - 1.0) < 1e-6
        assert abs(cell.eta_p - 0.72) < 1e-6
        assert cell.eta_w == 1.0
        assert abs(cell.fator_total - 0.72) < 1e-6
        assert abs(cell.qtd_executada - 144.0) < 1e-4

    def test_fechamento_parcial_captura_eta_w(self):
        # n_j=2, n_max=2, clima=0.9, calend=0.8 → capacidade=144; remanescente=50 → η_w<1
        cell = _cron._build_dist_cell(
            producao_semanal_base=100.0,
            num_eq=2,
            n_max=2,
            fator_clima=0.9,
            fator_calendario=0.8,
            quantitativo=10_000.0,
            qtd_acumulada=9_950.0,
        )
        assert cell.qtd_executada == 50.0
        assert cell.eta_s == 1.0
        assert abs(cell.eta_p - 0.72) < 1e-6
        assert 0.0 < cell.eta_w < 1.0  # fechamento parcial
        # identidade: fator_total = η_s × η_p × η_w
        assert abs(cell.fator_total - cell.eta_s * cell.eta_p * cell.eta_w) < 1e-4

    def test_identidade_fator_total_eta_produto(self):
        # fator_total deve ser sempre η_s × η_p × η_w (identidade fundamental)
        for n_eq, n_max, clima, calend in [
            (1, 2, 0.8, 0.9),
            (2, 2, 1.0, 1.0),
            (1, 3, 0.6, 0.7),
        ]:
            cell = _cron._build_dist_cell(
                100.0,
                n_eq,
                n_max,
                clima,
                calend,
                10_000.0,
                0.0,
            )
            assert abs(cell.fator_total - cell.eta_s * cell.eta_p * cell.eta_w) < 1e-4, (
                f"identidade falhou para n_eq={n_eq}, n_max={n_max}, clima={clima}, calend={calend}"
            )

    def test_eficiencia_e_eta_w(self):
        # eficiencia (m_ij) deve ser igual a eta_w
        cell = _cron._build_dist_cell(100.0, 1, 2, 0.9, 0.8, 10_000.0, 0.0)
        assert abs(cell.eficiencia - cell.eta_w) < 1e-6

    def test_q_max_referencia_n_max(self):
        # q_max_celula = base × n_max (independente de n_j)
        cell = _cron._build_dist_cell(100.0, 1, 4, 0.8, 0.8, 10_000.0, 0.0)
        assert abs(cell.q_max_celula - 400.0) < 1e-4  # 100 × 4

    def test_eficiencia_nao_e_clima(self):
        # garante que eficiencia (utilização) != clima×calendário (conflação corrigida)
        cell = _cron._build_dist_cell(100.0, 2, 2, 0.5, 0.5, 10_000.0, 0.0)
        assert cell.eficiencia == 1.0  # η_w = 1 (sem fechamento parcial)
        assert abs(cell.fator_total - 0.25) < 1e-6  # = η_s(1) × η_p(0.25) × η_w(1)


# ── VAL-PROD-VS-PU: resíduo = fe_nec × fator_clima_medio ─────────────────────


def _pe(item_id: str, fe_nec: float, clima: float):
    from concilium.domain.models.canonical import PontoEquilibrio

    return PontoEquilibrio(
        item_id=item_id,
        custo_fixo_equipe=1000.0,
        custo_venda_cpu=1000.0,
        delta=0.0,
        delta_pct=0.0,
        status_validacao="OK",
        frentes_equivalentes_necessarias=fe_nec,
        fator_clima_medio=clima,
        pu_catalogo_unitario=10.0,
        pu_calibrado_unitario=10.0 * fe_nec,
    )


class TestValProdVsPU:
    def test_flag_quando_residuo_acima_de_1(self):
        # fe_nec=1.29, clima=1.00 → resíduo 1.29 (puro mismatch de P, sem clima)
        val = []
        _cons._validate_prod_vs_pu(_pe("eap-1_5", 1.29, 1.00), val)
        assert len(val) == 1
        assert val[0].codigo == "VAL-PROD-VS-PU"
        assert "P_engine > P_catálogo" in val[0].mensagem

    def test_flag_quando_residuo_abaixo_de_1(self):
        # fe_nec=0.84, clima=0.87 → resíduo 0.73 (engine mais barato)
        val = []
        _cons._validate_prod_vs_pu(_pe("eap-1_8", 0.84, 0.87), val)
        assert len(val) == 1
        assert "P_engine < P_catálogo" in val[0].mensagem

    def test_silencioso_quando_gap_e_puro_clima(self):
        # fe_nec ≈ 1/clima → resíduo ≈ 1 → consistente, sem flag
        val = []
        _cons._validate_prod_vs_pu(_pe("eap-x", 1.05, 0.95), val)  # 1.05×0.95 = 0.9975
        assert val == []


# ── VAL-PROD-PU-FALLBACK-DESYNC (issue #132): correlação dos DOIS fallbacks ──


def _sched(fallback: bool):
    return SimpleNamespace(produtividade_fallback_aplicada=fallback)


def _plan(fallback: bool):
    return SimpleNamespace(precificacao_via_fallback_composicao=fallback)


class TestValProdPuFallbackDesync:
    def test_dispara_quando_ambos_os_lados_tem_fallback(self):
        sched_por_item = {"eap-1": _sched(True)}
        plan_por_item = {"eap-1": _plan(True)}
        val = []
        _cons._validate_prod_pu_fallback_desync("eap-1", sched_por_item, plan_por_item, val)
        assert len(val) == 1
        assert val[0].codigo == "VAL-PROD-PU-FALLBACK-DESYNC"
        assert val[0].status == "AVISO"
        assert "eap-1" in val[0].mensagem

    def test_nao_dispara_quando_so_schedule_tem_fallback(self):
        # fallback isolado do lado do cronograma já é sinalizado por VAL-PROD-04;
        # esta validação é especificamente sobre a correlação dos dois lados.
        sched_por_item = {"eap-2": _sched(True)}
        plan_por_item = {"eap-2": _plan(False)}
        val = []
        _cons._validate_prod_pu_fallback_desync("eap-2", sched_por_item, plan_por_item, val)
        assert val == []

    def test_nao_dispara_quando_so_precificacao_tem_fallback(self):
        sched_por_item = {"eap-3": _sched(False)}
        plan_por_item = {"eap-3": _plan(True)}
        val = []
        _cons._validate_prod_pu_fallback_desync("eap-3", sched_por_item, plan_por_item, val)
        assert val == []

    def test_nao_dispara_quando_nenhum_lado_tem_fallback(self):
        sched_por_item = {"eap-4": _sched(False)}
        plan_por_item = {"eap-4": _plan(False)}
        val = []
        _cons._validate_prod_pu_fallback_desync("eap-4", sched_por_item, plan_por_item, val)
        assert val == []

    def test_item_ausente_em_sched_ou_plan_nao_dispara(self):
        val = []
        _cons._validate_prod_pu_fallback_desync("eap-ausente", {}, {"eap-ausente": _plan(True)}, val)
        _cons._validate_prod_pu_fallback_desync("eap-ausente", {"eap-ausente": _sched(True)}, {}, val)
        assert val == []


# ── ADR-128/139 F5: estoque de consumíveis — edge cases de _validacao.py ────


class TestParseLogisticaConsumiveisOverrides:
    def test_entrada_nao_dict_e_ignorada(self):
        # ADR-128 F5: valor não-dict para um insumo (dado malformado de projeto)
        # deve ser pulado (`continue`), sem interromper o parse dos demais.
        result = _cron._mod_validacao._parse_logistica_consumiveis_overrides(
            {"INSUMO-X": "nao-e-dict", "INSUMO-Y": {"estoque_inicial": 10.0}}
        )
        assert result is not None
        assert "INSUMO-X" not in result
        assert result["INSUMO-Y"].estoque_inicial == 10.0

    def test_deficit_provisionado_externamente_e_aceito(self):
        # ADR-151: o override de projeto (Escopo.logistica_consumiveis) é o lugar
        # onde o engenheiro declara o provisionamento externo conhecido.
        result = _cron._mod_validacao._parse_logistica_consumiveis_overrides(
            {"MA-SOLO-ESCAVADO-3CAT": {"deficit_provisionado_externamente": 24721.17}}
        )
        assert result is not None
        assert result["MA-SOLO-ESCAVADO-3CAT"].deficit_provisionado_externamente == 24721.17


class TestBuildReplenishableResourcesIfAnyErro:
    def test_value_error_do_builder_vira_val_estoque_build_01(self):
        # materiais_gerados referenciando insumo inexistente -> build_replenishable_resources
        # levanta ValueError (VAL-PROD-GERACAO-01) -> _build_replenishable_resources_if_any
        # deve capturar e converter em ValidacaoItem ERRO, retornando None (sem propagar).
        validacoes: list = []
        producoes_por_atividade = {
            "A1": {
                "id": "PROD-X",
                "materiais_gerados": [{"insumo_id": "MAT-INEXISTENTE", "geracao_por_hora": 1.0}],
            }
        }
        result = _cron._mod_validacao._build_replenishable_resources_if_any(
            producoes_por_atividade,
            insumos_lookup={},
            logistica_consumiveis=None,
            validacoes=validacoes,
        )
        assert result is None
        assert any(v.codigo == "VAL-ESTOQUE-BUILD-01" and v.status == "ERRO" for v in validacoes)


class TestBuildReplenishableResourcesIfAnyProvisionamento:
    def test_deficit_provisionado_emite_aviso(self):
        """ADR-151: engenheiro declara, via logistica_consumiveis, que MA-ROCHA
        (geração interna) tem déficit estrutural conhecido — VAL-ESTOQUE-
        PROVISIONAMENTO-01 (AVISO) torna isso visível no relatório do projeto."""
        validacoes: list = []
        producoes_por_atividade = {
            "A1": {
                "id": "PROD-X",
                "materiais_gerados": [{"insumo_id": "MA-ROCHA", "geracao_por_hora": 10.0}],
            }
        }
        insumos_lookup = {"MA-ROCHA": {"origem_material": "GERACAO_INTERNA"}}
        result = _cron._mod_validacao._build_replenishable_resources_if_any(
            producoes_por_atividade,
            insumos_lookup=insumos_lookup,
            logistica_consumiveis={"MA-ROCHA": {"deficit_provisionado_externamente": 500.0}},
            validacoes=validacoes,
        )
        assert result is not None
        avisos = [v for v in validacoes if v.codigo == "VAL-ESTOQUE-PROVISIONAMENTO-01"]
        assert len(avisos) == 1
        assert avisos[0].status == "AVISO"
        assert "MA-ROCHA" in avisos[0].mensagem
        assert "500" in avisos[0].mensagem

    def test_sem_deficit_nao_emite_aviso(self):
        """Regressão zero: recurso sem deficit_provisionado_externamente (default
        0.0) não deve gerar nenhum aviso de provisionamento."""
        validacoes: list = []
        producoes_por_atividade = {
            "A1": {
                "id": "PROD-X",
                "materiais_gerados": [{"insumo_id": "MA-ROCHA", "geracao_por_hora": 10.0}],
            }
        }
        insumos_lookup = {"MA-ROCHA": {"origem_material": "GERACAO_INTERNA"}}
        result = _cron._mod_validacao._build_replenishable_resources_if_any(
            producoes_por_atividade,
            insumos_lookup=insumos_lookup,
            logistica_consumiveis=None,
            validacoes=validacoes,
        )
        assert result is not None
        assert not any(v.codigo == "VAL-ESTOQUE-PROVISIONAMENTO-01" for v in validacoes)


class TestRasfcRunHeuristicsEstoque:
    def _activity_dag_pool(self):
        from concilium.application.scheduling.models import Activity, ActivityDAG, ResourcePool

        activities = [Activity(activity_id="A1", description="A1", duration_weeks=2, required_resources={})]
        dag = ActivityDAG(activities=activities, precedence=[])
        pool = ResourcePool(resources={})
        return activities, dag, pool

    def test_algoritmo_nao_cpsat_gera_val_estoque_algo_01(self, monkeypatch):
        # ADR-128 F5: replenishable_resources construído mas algoritmo selecionado
        # (forçado aqui para não-CP-SAT) não suporta a restrição -> VAL-ESTOQUE-ALGO-01
        # (AVISO) e a restrição é descartada (replenishable_resources vira None/[]).
        from concilium.application.scheduling.models import ReplenishableResource
        from concilium.domain.models.catalog.disponibilidade_consumivel import DisponibilidadeConsumivel

        resource = ReplenishableResource(
            resource_id="MAT-X",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=1000.0),
            consumo_por_semana={"A1": 5.0},
        )
        monkeypatch.setattr(
            _cron._mod_validacao,
            "_build_replenishable_resources_if_any",
            lambda *a, **k: [resource],
        )

        activities, dag, pool = self._activity_dag_pool()
        validacoes: list = []
        candidates, relaxed, repl = _cron._rasfc_run_heuristics(
            activities,
            dag,
            pool,
            deadline_weeks=4,
            inputs={"algorithm": "SerialScheduler"},
            validacoes=validacoes,
            producoes_por_atividade={"A1": {}},
            insumos_lookup={"MAT-X": {}},
        )

        assert any(v.codigo == "VAL-ESTOQUE-ALGO-01" and v.status == "AVISO" for v in validacoes)
        assert repl == []
        assert candidates  # SerialScheduler ainda produz um schedule, só sem a restrição

    def test_violation_estoque_acima_capacidade_reportada(self, monkeypatch):
        # ADR-139/128: capacidade_armazenamento baixa + taxa_reabastecimento_max alta
        # gera excedente projetado toda semana ativa (sem estoque negativo) ->
        # violation_estoque_acima_capacidade retorna VAL-ESTOQUE-CAP-01 (AVISO).
        from concilium.application.scheduling.models import ReplenishableResource
        from concilium.domain.models.catalog.disponibilidade_consumivel import DisponibilidadeConsumivel

        resource = ReplenishableResource(
            resource_id="MAT-Y",
            disponibilidade=DisponibilidadeConsumivel(
                estoque_inicial=0.0, taxa_reabastecimento_max=1000.0, capacidade_armazenamento=10.0
            ),
            consumo_por_semana={"A1": 5.0},
        )
        monkeypatch.setattr(
            _cron._mod_validacao,
            "_build_replenishable_resources_if_any",
            lambda *a, **k: [resource],
        )

        activities, dag, pool = self._activity_dag_pool()
        validacoes: list = []
        # Sem 'algorithm' explícito -> select_scheduling_algorithm escolhe CP-SAT
        # (n_activities <= 200), único path que de fato aplica ReplenishableResource.
        candidates, relaxed, repl = _cron._rasfc_run_heuristics(
            activities,
            dag,
            pool,
            deadline_weeks=4,
            inputs={},
            validacoes=validacoes,
            producoes_por_atividade={"A1": {}},
            insumos_lookup={"MAT-Y": {}},
        )

        assert repl == [resource]
        assert any(v.codigo == "VAL-ESTOQUE-CAP-01" and v.status == "AVISO" for v in validacoes)
        assert candidates


class TestMergePoolDeficits:
    def test_segundo_resultado_sem_melhora_nao_atualiza_merge(self):
        # ADR-128 F7 (issue #117): quando mais de um resultado explorado reporta
        # déficit para o MESMO recurso, o merge deve tomar o pico máximo — o
        # segundo valor, menor ou igual ao já mesclado, não deve sobrescrever.
        r1 = SimpleNamespace(schedule=SimpleNamespace(pool_deficit={"E": 5}))
        r2 = SimpleNamespace(schedule=SimpleNamespace(pool_deficit={"E": 3}))
        result = _cron._mod_validacao._merge_pool_deficits([r1, r2])
        assert result == {"E": 5}

    def test_segundo_resultado_com_pico_maior_atualiza_merge(self):
        # Complementa o caso acima: quando o segundo valor É maior, o merge
        # atualiza normalmente (branch TRUE do mesmo `if`).
        r1 = SimpleNamespace(schedule=SimpleNamespace(pool_deficit={"E": 3}))
        r2 = SimpleNamespace(schedule=SimpleNamespace(pool_deficit={"E": 5}))
        result = _cron._mod_validacao._merge_pool_deficits([r1, r2])
        assert result == {"E": 5}
