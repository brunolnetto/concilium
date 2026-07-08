"""ADR-079 — Ativação Econômica de Compartilhamento.

TDD: todos os testes escritos ANTES da implementação.

Cobertura:
  A. TestCustoIdleStandby       — custo_idle_semanal_unit no lugar de custo_unit_semanal
  B. TestDesmobilizacaoAntecipada — trailing standby + economia por instância
  C. TestGrViavel                — gap_max pruning no chain builder
  D. TestMatchingEconomico       — leitura de resource_costs em _build_contratos_recurso
  E. TestLambdaInicializacao     — initial_lambdas no LnsScheduler + selector
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parent.parent.parent

_HELPERS_A = (
    _ROOT / "src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers_a/__init__.py"
)
_SELECTOR = _ROOT / "src/concilium/application/scheduling/selector.py"
_LNS = _ROOT / "src/concilium/application/scheduling/lns_scheduler.py"

sys.path.insert(0, str(_ROOT / "src"))


def _load_helpers_a() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_skill_helpers_a", _HELPERS_A)
    assert spec and spec.loader, f"Não encontrou {_HELPERS_A}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_skill_helpers_a"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ──────────────────────────────────────────────────────────────────────────────
# Helpers de stub de schedule
# ──────────────────────────────────────────────────────────────────────────────


def _make_sched_activity(item_id: str, weeks: list[str], num_equipes: int = 1):
    class _Dist:
        def __init__(self, ne):
            self.num_equipes = ne

    class _Sched:
        def __init__(self, aid, weeks, ne):
            self.activity_id = aid
            self.distribuicao_semanal = {w: _Dist(ne) for w in weeks}

    return _Sched(item_id, weeks, num_equipes)


def _weeks(start: int, end: int) -> list[str]:
    return [f"2026-W{w:02d}" for w in range(start, end + 1)]


# ──────────────────────────────────────────────────────────────────────────────
# A. custo_standby_idle
# ──────────────────────────────────────────────────────────────────────────────


class TestCustoIdleStandby:
    """Quando custo_idle_semanal_unit > 0, standby deve usar c_idle, não custo_unit_semanal."""

    def _run(self, custo_unit: float, custo_idle: float):
        """
        Cenário: 1 tipo, pool=2, atividade apenas nas semanas 1-4 do contrato 1-8.
        → instâncias 1-2 têm 4 semanas de standby (semanas 5-8).
        """
        from concilium.domain.models.canonical import RecursoContrato

        mod = _load_helpers_a()

        contrato = RecursoContrato(
            contrato_id="contrato-t1",
            tipo_id="T1",
            quantidade_contratada=2,
            semana_inicio="2026-W01",
            semana_fim="2026-W08",
            semanas_contrato=8,
            custo_unit_semanal=custo_unit,
            custo_total_contrato=2 * custo_unit * 8,
            items_cobertos=["act-a"],
            custo_idle_semanal_unit=custo_idle,
        )

        rcpsp_spec = {
            "resource_pool": {"T1": 2},
            "activities": [{"item_id": "act-a", "required_resources": {"T1": 2}}],
        }
        sched_lookup = {"act-a": _make_sched_activity("act-a", _weeks(1, 4), num_equipes=2)}

        validacoes = []
        instancias, _, resumos = mod._build_instancias_recurso([contrato], rcpsp_spec, sched_lookup, validacoes)
        return instancias, resumos

    def test_usa_custo_idle_quando_disponivel(self):
        """custo_standby por instância deve ser c_idle × standby_weeks quando c_idle > 0."""
        instancias, _ = self._run(custo_unit=10_000.0, custo_idle=2_000.0)
        # 4 semanas standby × R$ 2.000 = R$ 8.000
        for inst in instancias:
            assert inst.custo_standby == pytest.approx(8_000.0), (
                f"Esperado R$ 8.000 (c_idle × 4w), obtido {inst.custo_standby}"
            )

    def test_resumo_usa_custo_idle(self):
        """custo_standby_total no resumo deve usar c_idle × total_mw_standby."""
        _, resumos = self._run(custo_unit=10_000.0, custo_idle=2_000.0)
        # 2 instâncias × 4 semanas = 8 mw_standby × R$ 2.000 = R$ 16.000
        assert resumos[0].custo_standby_total == pytest.approx(16_000.0)

    def test_fallback_para_custo_unit_quando_idle_zero(self):
        """Quando c_idle = 0, deve usar custo_unit_semanal (comportamento pré-ADR-079)."""
        instancias, _ = self._run(custo_unit=10_000.0, custo_idle=0.0)
        # 4 semanas standby × R$ 10.000 = R$ 40.000
        for inst in instancias:
            assert inst.custo_standby == pytest.approx(40_000.0)

    def test_resumo_fallback_quando_idle_zero(self):
        """custo_standby_total no resumo com fallback para custo_unit_semanal."""
        _, resumos = self._run(custo_unit=10_000.0, custo_idle=0.0)
        # 2 instâncias × 4 semanas = 8 mw × R$ 10.000 = R$ 80.000
        assert resumos[0].custo_standby_total == pytest.approx(80_000.0)

    def test_idle_menor_que_unit_reduz_custo(self):
        """c_idle tipicamente < custo_unit — custo_standby deve ser menor após refinamento."""
        instancias_idle, _ = self._run(custo_unit=10_000.0, custo_idle=2_000.0)
        instancias_unit, _ = self._run(custo_unit=10_000.0, custo_idle=0.0)
        assert instancias_idle[0].custo_standby < instancias_unit[0].custo_standby

    def test_standby_zero_nao_muda_com_idle(self):
        """Instância sem standby tem custo_standby = 0 independente de c_idle."""
        # Cenário: pool=1, atividade cobre todo o contrato → 0 standby
        from concilium.domain.models.canonical import RecursoContrato

        mod = _load_helpers_a()

        contrato = RecursoContrato(
            contrato_id="contrato-t2",
            tipo_id="T2",
            quantidade_contratada=1,
            semana_inicio="2026-W01",
            semana_fim="2026-W04",
            semanas_contrato=4,
            custo_unit_semanal=10_000.0,
            custo_total_contrato=40_000.0,
            items_cobertos=["act-b"],
            custo_idle_semanal_unit=5_000.0,
        )
        rcpsp_spec = {
            "resource_pool": {"T2": 1},
            "activities": [{"item_id": "act-b", "required_resources": {"T2": 1}}],
        }
        sched_lookup = {"act-b": _make_sched_activity("act-b", _weeks(1, 4), num_equipes=1)}
        instancias, _, _ = mod._build_instancias_recurso([contrato], rcpsp_spec, sched_lookup, [])
        assert instancias[0].custo_standby == pytest.approx(0.0)


# ──────────────────────────────────────────────────────────────────────────────
# B. Desmobilização Antecipada
# ──────────────────────────────────────────────────────────────────────────────


class TestDesmobilizacaoAntecipada:
    """Instâncias com trailing standby devem ter economia de desmobilização calculada."""

    def _run_trailing(
        self,
        act_weeks_end: int = 4,
        contract_weeks: int = 8,
        custo_idle: float = 2_000.0,
        custo_demob_unit: float = 5_000.0,
    ):
        """
        pool=1, atividade vai de W1 a act_weeks_end, contrato vai até W{contract_weeks}.
        Trailing standby = contract_weeks - act_weeks_end semanas.
        """
        from concilium.domain.models.canonical import RecursoContrato

        mod = _load_helpers_a()

        contrato = RecursoContrato(
            contrato_id="contrato-t3",
            tipo_id="T3",
            quantidade_contratada=1,
            semana_inicio="2026-W01",
            semana_fim=f"2026-W{contract_weeks:02d}",
            semanas_contrato=contract_weeks,
            custo_unit_semanal=10_000.0,
            custo_total_contrato=contract_weeks * 10_000.0,
            items_cobertos=["act-c"],
            custo_idle_semanal_unit=custo_idle,
            custo_demob_unit=custo_demob_unit,
        )
        rcpsp_spec = {
            "resource_pool": {"T3": 1},
            "activities": [{"item_id": "act-c", "required_resources": {"T3": 1}}],
        }
        sched_lookup = {"act-c": _make_sched_activity("act-c", _weeks(1, act_weeks_end), num_equipes=1)}
        validacoes = []
        instancias, _, _ = mod._build_instancias_recurso([contrato], rcpsp_spec, sched_lookup, validacoes)
        return instancias[0]

    def test_semana_ultima_atividade_e_preenchida(self):
        """semana_ultima_atividade deve ser a última semana com atividade."""
        inst = self._run_trailing(act_weeks_end=4, contract_weeks=8)
        assert inst.semana_ultima_atividade == "2026-W04"

    def test_semanas_antecipacao_calculadas(self):
        """trailing = contract_end - last_active (ex: 8-4=4 semanas)."""
        inst = self._run_trailing(act_weeks_end=4, contract_weeks=8)
        # 4 semanas de trailing (W05-W08)
        assert inst.semanas_antecipacao_possivel == 4

    def test_economia_positiva_quando_vale_a_pena(self):
        """c_idle×trailing - c_demob > 0 → economia_desmob > 0."""
        # 4 × 2.000 = 8.000 > 5.000 (c_demob) → economia = 3.000
        inst = self._run_trailing(act_weeks_end=4, contract_weeks=8, custo_idle=2_000.0, custo_demob_unit=5_000.0)
        assert inst.economia_desmobilizacao_antecipada == pytest.approx(3_000.0)

    def test_economia_zero_quando_nao_vale_a_pena(self):
        """c_idle×trailing < c_demob → economia = 0 (não vale desmobilizar)."""
        # 4 × 1_000 = 4.000 < 10.000 (c_demob) → 0
        inst = self._run_trailing(act_weeks_end=4, contract_weeks=8, custo_idle=1_000.0, custo_demob_unit=10_000.0)
        assert inst.economia_desmobilizacao_antecipada == pytest.approx(0.0)
        assert inst.semanas_antecipacao_possivel == 0

    def test_sem_trailing_nao_ha_antecipacao(self):
        """Atividade que vai até o fim do contrato → trailing=0, economia=0."""
        inst = self._run_trailing(act_weeks_end=8, contract_weeks=8)
        assert inst.semanas_antecipacao_possivel == 0
        assert inst.economia_desmobilizacao_antecipada == pytest.approx(0.0)

    def test_sem_custo_idle_nao_calcula_antecipacao(self):
        """c_idle = 0 → não há economia → antecipação = 0."""
        inst = self._run_trailing(act_weeks_end=4, contract_weeks=8, custo_idle=0.0, custo_demob_unit=5_000.0)
        assert inst.semanas_antecipacao_possivel == 0
        assert inst.economia_desmobilizacao_antecipada == pytest.approx(0.0)

    def test_semana_ultima_atividade_vazia_sem_trailing(self):
        """Quando sem trailing, semana_ultima_atividade é setada mas semanas_antecipacao=0."""
        inst = self._run_trailing(act_weeks_end=6, contract_weeks=6)
        # Sem trailing, mas semana_ultima_atividade é a última semana de atividade
        assert inst.semana_ultima_atividade == "2026-W06"
        assert inst.semanas_antecipacao_possivel == 0

    def test_campos_existem_em_instancia_recurso(self):
        """InstanciaRecurso deve ter os três novos campos."""
        from concilium.domain.models.canonical import InstanciaRecurso

        inst = InstanciaRecurso(
            instancia_id="T3-01",
            contrato_id="c",
            tipo_id="T3",
            numero=1,
            semana_entrada="2026-W01",
            semana_saida="2026-W08",
        )
        assert hasattr(inst, "semana_ultima_atividade")
        assert hasattr(inst, "semanas_antecipacao_possivel")
        assert hasattr(inst, "economia_desmobilizacao_antecipada")
        assert inst.semana_ultima_atividade == ""
        assert inst.semanas_antecipacao_possivel == 0
        assert inst.economia_desmobilizacao_antecipada == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# C. G_r^viável — gap_max no chain builder
# ──────────────────────────────────────────────────────────────────────────────


class TestGrViavel:
    """_build_perpetuation_chains deve aceitar gap_max e quebrar cadeia quando gap > gap_max."""

    def _items(self, starts_ends: list[tuple[int, int]], required: int = 2) -> list[dict]:
        """Gera lista de items com start_idx/end_idx indicados."""
        result = []
        for i, (s, e) in enumerate(starts_ends):
            result.append(
                {
                    "item_id": f"act-{i + 1}",
                    "required": required,
                    "active_weeks": _weeks(s, e),
                    "machine_weeks": (e - s + 1) * required,
                    "start_idx": s,
                    "end_idx": e + 1,  # exclusive
                    "semana_inicio": f"2026-W{s:02d}",
                    "semana_fim": f"2026-W{e:02d}",
                }
            )
        return result

    def _chains(self, items, gap_max=9999, custo_mob=0.0, custo_demob=0.0, delta_max=2):
        mod = _load_helpers_a()
        return mod._build_perpetuation_chains(
            tipo_id="ESC",
            items=items,
            custo_mob_unit=custo_mob,
            custo_demob_unit=custo_demob,
            custo_standby_unit=0.0,
            delta_max=delta_max,
            gap_max=gap_max,
        )

    def test_gap_igual_gap_max_perpetua(self):
        """gap = gap_max → cadeia não deve quebrar."""
        # act-1: W1-W4 (end_idx=5), act-2: W9-W12 (start_idx=9) → gap=4
        items = self._items([(1, 4), (9, 12)])
        chains = self._chains(items, gap_max=4, custo_mob=80_000.0, custo_demob=40_000.0)
        assert len(chains) == 1

    def test_gap_maior_gap_max_quebra_cadeia(self):
        """gap = gap_max + 1 → deve criar 2 cadeias."""
        # gap=5 > gap_max=4
        items = self._items([(1, 4), (10, 13)])
        chains = self._chains(items, gap_max=4, custo_mob=80_000.0, custo_demob=40_000.0)
        assert len(chains) == 2

    def test_gap_max_zero_toda_gap_quebra(self):
        """gap_max=0 → qualquer gap quebra a cadeia."""
        items = self._items([(1, 4), (6, 9)])  # gap=1
        chains = self._chains(items, gap_max=0, custo_mob=80_000.0, custo_demob=40_000.0)
        assert len(chains) == 2

    def test_gap_max_nao_afeta_sobreposicao(self):
        """Sobreposição (gap < 0) nunca quebra a cadeia, mesmo com gap_max=0."""
        # act-1: W1-W6, act-2: W5-W10 → gap = 5-7 = -2 (overlap)
        items = self._items([(1, 6), (5, 10)])
        chains = self._chains(items, gap_max=0, custo_mob=80_000.0, custo_demob=40_000.0)
        assert len(chains) == 1

    def test_gap_max_default_preserva_comportamento(self):
        """Sem gap_max explícito (default 9999), comportamento pré-ADR-079 inalterado."""
        # custo-based: gap=10 < gap_max=9 (seria quebra por ADR-078),
        # mas sem gap_max explícito, threshold é custo
        # gap=10, c_idle=0 → standby_cost=0 < c_mob+c_demob → perpetua
        items = self._items([(1, 4), (15, 18)])  # gap=10
        chains_sem = self._chains(items, custo_mob=80_000.0, custo_demob=40_000.0)
        assert len(chains_sem) == 1  # custo-based perpetua

    def test_tres_itens_dois_gaps_diferentes(self):
        """Três itens: primeiro gap ≤ gap_max, segundo gap > gap_max → 2 cadeias."""
        items = self._items([(1, 4), (7, 10), (20, 23)])  # gap1=2, gap2=9
        chains = self._chains(items, gap_max=5, custo_mob=80_000.0, custo_demob=40_000.0)
        # Gap1=2 ≤ 5 → perpetua; Gap2=9 > 5 → quebra
        assert len(chains) == 2

    def test_sem_custos_usa_delta_max_com_gap_max(self):
        """Sem custos (cost-based desativado), gap_max ainda atua sobre delta_max."""
        # gap=3 > delta_max=2 E gap=3 ≤ gap_max=5 → perpetua? Não: cost-based=False, time-based:
        # gap=3 > delta_max=2 → sem cost-based, usa time: gap>delta_max → quebra
        items = self._items([(1, 4), (8, 11)])  # gap=3
        chains = self._chains(items, gap_max=5, custo_mob=0.0, custo_demob=0.0, delta_max=2)
        assert len(chains) == 2


# ──────────────────────────────────────────────────────────────────────────────
# D. Matching Econômico
# ──────────────────────────────────────────────────────────────────────────────


class TestMatchingEconomico:
    """_build_contratos_recurso deve ler resource_costs e passar ao chain builder."""

    def _make_equipe(self, item_id, custo_total=100_000.0):
        class _Eq:
            def __init__(self, iid, c):
                self.item_id = iid
                self.custo_total = c

        return _Eq(item_id, custo_total)

    def test_custo_mob_desmob_contrato_calculado(self):
        """Com resource_costs, custo_mob_desmob_contrato deve refletir n_cadeias × (c_mob+c_demob) × pool."""
        mod = _load_helpers_a()

        equipes = [
            self._make_equipe("act-1", 100_000.0),
            self._make_equipe("act-2", 100_000.0),
        ]
        # act-1: W01-W04, act-2: W06-W09 → gap=1 ≤ delta_max=2 mas gap>gap_max=0?
        # Sem resource_costs: time-based, gap=1 ≤ delta_max=2 → 1 cadeia
        # Com resource_costs: cost-based (custo_mob+custo_demob=120k) → custo_standby=0 < 120k → perpetua
        rcpsp_spec = {
            "resource_pool": {"T4": 2},
            "delta_perpetuacao_semanas": 2,
            "activities": [
                {"item_id": "act-1", "required_resources": {"T4": 2}},
                {"item_id": "act-2", "required_resources": {"T4": 2}},
            ],
            "resource_costs": {
                "T4": {
                    "custo_mob_unit": 80_000.0,
                    "custo_demob_unit": 40_000.0,
                    "custo_idle_semanal_unit": 12_000.0,
                    "unidade_faturamento": "dia_cal",
                }
            },
        }
        sched_lookup = {
            "act-1": _make_sched_activity("act-1", _weeks(1, 4), num_equipes=2),
            "act-2": _make_sched_activity("act-2", _weeks(6, 9), num_equipes=2),
        }
        contratos, _, cadeias = mod._build_contratos_recurso(equipes, rcpsp_spec, sched_lookup, [])
        assert len(contratos) == 1
        c = contratos[0]
        # 1 cadeia → 1 mob + 1 demob × pool=2 → (80k+40k) × 2 = 240k
        assert c.custo_mob_desmob_contrato == pytest.approx(240_000.0)

    def test_sem_resource_costs_mob_desmob_zero(self):
        """Sem resource_costs, custo_mob_desmob_contrato permanece 0.0 (retrocompat)."""
        mod = _load_helpers_a()

        equipes = [self._make_equipe("act-3", 100_000.0)]
        rcpsp_spec = {
            "resource_pool": {"T5": 1},
            "activities": [{"item_id": "act-3", "required_resources": {"T5": 1}}],
        }
        sched_lookup = {"act-3": _make_sched_activity("act-3", _weeks(1, 8), num_equipes=1)}
        contratos, _, _ = mod._build_contratos_recurso(equipes, rcpsp_spec, sched_lookup, [])
        assert contratos[0].custo_mob_desmob_contrato == pytest.approx(0.0)

    def test_custo_idle_propagado_para_chains(self):
        """Custo idle de resource_costs deve ser usado como custo_standby no chain builder."""
        mod = _load_helpers_a()

        equipes = [
            self._make_equipe("act-x", 50_000.0),
            self._make_equipe("act-y", 50_000.0),
        ]
        rcpsp_spec = {
            "resource_pool": {"T6": 1},
            "delta_perpetuacao_semanas": 0,  # sem time-based
            "activities": [
                {"item_id": "act-x", "required_resources": {"T6": 1}},
                {"item_id": "act-y", "required_resources": {"T6": 1}},
            ],
            "resource_costs": {
                "T6": {
                    "custo_mob_unit": 100_000.0,
                    "custo_demob_unit": 50_000.0,
                    "custo_idle_semanal_unit": 10_000.0,
                    "unidade_faturamento": "dia_cal",
                }
            },
        }
        # gap=1: standby_cost = 1×10k×1=10k < mob+demob=150k → perpetua
        sched_lookup = {
            "act-x": _make_sched_activity("act-x", _weeks(1, 4), num_equipes=1),
            "act-y": _make_sched_activity("act-y", _weeks(6, 9), num_equipes=1),
        }
        _, _, cadeias = mod._build_contratos_recurso(equipes, rcpsp_spec, sched_lookup, [])
        # 1 cadeia (perpetua por custo)
        assert len(cadeias) == 1

    def test_custo_idle_alto_quebra_cadeia(self):
        """Custo idle alto (standby > mob+demob) → não perpetua → 2 cadeias."""
        mod = _load_helpers_a()

        equipes = [
            self._make_equipe("act-p", 50_000.0),
            self._make_equipe("act-q", 50_000.0),
        ]
        rcpsp_spec = {
            "resource_pool": {"T7": 1},
            "activities": [
                {"item_id": "act-p", "required_resources": {"T7": 1}},
                {"item_id": "act-q", "required_resources": {"T7": 1}},
            ],
            "resource_costs": {
                "T7": {
                    "custo_mob_unit": 5_000.0,
                    "custo_demob_unit": 3_000.0,
                    "custo_idle_semanal_unit": 10_000.0,  # 10k/w × 5w gap = 50k > 8k
                    "unidade_faturamento": "dia_cal",
                }
            },
        }
        # gap=5: standby_cost = 5×10k×1=50k > mob+demob=8k → quebra
        sched_lookup = {
            "act-p": _make_sched_activity("act-p", _weeks(1, 4), num_equipes=1),
            "act-q": _make_sched_activity("act-q", _weeks(10, 13), num_equipes=1),
        }
        _, _, cadeias = mod._build_contratos_recurso(equipes, rcpsp_spec, sched_lookup, [])
        assert len(cadeias) == 2

    def test_gap_max_aplicado_via_resource_costs(self):
        """gap_max calculado a partir de resource_costs é passado ao chain builder."""
        mod = _load_helpers_a()

        equipes = [
            self._make_equipe("act-r", 50_000.0),
            self._make_equipe("act-s", 50_000.0),
        ]
        # gap_max = ceil((80k+40k)/12k) - 1 = ceil(10) - 1 = 9
        # gap=10 > gap_max=9 → quebra (mesmo que custo-based diria perpetuar)
        rcpsp_spec = {
            "resource_pool": {"T8": 1},
            "activities": [
                {"item_id": "act-r", "required_resources": {"T8": 1}},
                {"item_id": "act-s", "required_resources": {"T8": 1}},
            ],
            "resource_costs": {
                "T8": {
                    "custo_mob_unit": 80_000.0,
                    "custo_demob_unit": 40_000.0,
                    "custo_idle_semanal_unit": 12_000.0,
                    "unidade_faturamento": "dia_cal",
                }
            },
        }
        # gap=10 > gap_max=9 → deve quebrar
        sched_lookup = {
            "act-r": _make_sched_activity("act-r", _weeks(1, 4), num_equipes=1),
            "act-s": _make_sched_activity("act-s", _weeks(15, 18), num_equipes=1),
        }
        _, _, cadeias = mod._build_contratos_recurso(equipes, rcpsp_spec, sched_lookup, [])
        assert len(cadeias) == 2


class TestBuildContratosRecursoEarlyReturns:
    """Covers early-return / skip branches in _build_contratos_recurso and
    _setup_contratos_context that TestMatchingEconomico doesn't exercise."""

    def _make_equipe(self, item_id, custo_total=100_000.0):
        class _Eq:
            def __init__(self, iid, c):
                self.item_id = iid
                self.custo_total = c

        return _Eq(item_id, custo_total)

    def test_empty_pool_and_activities_returns_empty(self):
        """`if not pool or not activities:` → ([], {}, [])."""
        mod = _load_helpers_a()
        contratos, atribuicao, cadeias = mod._build_contratos_recurso([], {}, {}, [])
        assert contratos == []
        assert atribuicao == {}
        assert cadeias == []

    def test_pool_empty_but_activities_present_infers_pool(self):
        """_setup_contratos_context: pool vazio + activities não vazio → chama
        inferir_pool_minimo_from_spec para derivar o pool automaticamente."""
        mod = _load_helpers_a()

        equipes = [self._make_equipe("act-infer", 10_000.0)]
        rcpsp_spec = {
            "activities": [{"item_id": "act-infer", "required_resources": {"T9": 1}}],
        }
        sched_lookup = {"act-infer": _make_sched_activity("act-infer", _weeks(1, 4), num_equipes=1)}

        contratos, _, _ = mod._build_contratos_recurso(equipes, rcpsp_spec, sched_lookup, [])

        # Pool foi inferido e escrito de volta no próprio rcpsp_spec.
        assert rcpsp_spec.get("resource_pool")
        assert isinstance(contratos, list)

    def test_resource_costs_non_dict_falls_back_to_empty(self):
        """resource_costs presente mas não é dict → tratado como {} (retrocompat)."""
        mod = _load_helpers_a()

        equipes = [self._make_equipe("act-badcosts", 50_000.0)]
        rcpsp_spec = {
            "resource_pool": {"T10": 1},
            "activities": [{"item_id": "act-badcosts", "required_resources": {"T10": 1}}],
            "resource_costs": "not-a-dict",
        }
        sched_lookup = {"act-badcosts": _make_sched_activity("act-badcosts", _weeks(1, 4), num_equipes=1)}

        contratos, _, _ = mod._build_contratos_recurso(equipes, rcpsp_spec, sched_lookup, [])
        assert len(contratos) == 1
        assert contratos[0].custo_mob_desmob_contrato == pytest.approx(0.0)

    def test_tipo_with_no_active_schedule_produces_no_contract(self):
        """Quando o item referenciado no pool não tem equipe/schedule casados,
        tipo_items fica vazio para aquele tipo → nenhum contrato é gerado."""
        mod = _load_helpers_a()

        rcpsp_spec = {
            "resource_pool": {"T11": 1},
            "activities": [{"item_id": "act-missing", "required_resources": {"T11": 1}}],
        }
        # Nem equipe nem schedule contêm "act-missing" → _process_item_tipo_map
        # emite VAL-POOL-CONTRATO-01 e retorna cedo, sem popular tipo_items.
        contratos, atribuicao, cadeias = mod._build_contratos_recurso([], rcpsp_spec, {}, [])
        assert contratos == []
        assert atribuicao == {}
        assert cadeias == []


# ──────────────────────────────────────────────────────────────────────────────
# E. Inicialização λ₀
# ──────────────────────────────────────────────────────────────────────────────


class TestLambdaInicializacao:
    """LnsScheduler.initial_lambdas pré-aquece o dicionário de penalidades."""

    def test_lns_aceita_initial_lambdas(self):
        """LnsScheduler deve aceitar campo initial_lambdas sem erro."""
        pytest.importorskip("ortools", reason="ortools não disponível neste ambiente")
        from concilium.application.scheduling.lns_scheduler import LnsScheduler
        from concilium.domain.services.planning.matching_oracle import MatchingOracle

        oracle = MatchingOracle(mob_costs={})
        lambdas = {("act-1", "act-2", "ESC-3CAT"): 480_000.0}
        lns = LnsScheduler(oracle=oracle, initial_lambdas=lambdas)
        assert lns.initial_lambdas == lambdas

    def test_lns_sem_initial_lambdas_compativel(self):
        """LnsScheduler sem initial_lambdas funciona como antes."""
        pytest.importorskip("ortools", reason="ortools não disponível neste ambiente")
        from concilium.application.scheduling.lns_scheduler import LnsScheduler
        from concilium.domain.services.planning.matching_oracle import MatchingOracle

        oracle = MatchingOracle(mob_costs={})
        lns = LnsScheduler(oracle=oracle)
        assert lns.initial_lambdas is None

    def test_initial_lambdas_none_inicia_vazio(self):
        """initial_lambdas=None → schedule() inicia com lambdas={}."""
        pytest.importorskip("ortools", reason="ortools não disponível neste ambiente")
        from concilium.application.scheduling.lns_scheduler import LnsScheduler
        from concilium.application.scheduling.models import ActivityDAG, ResourcePool
        from concilium.domain.services.planning.matching_oracle import MatchingOracle

        oracle = MatchingOracle(mob_costs={})
        lns = LnsScheduler(oracle=oracle, initial_lambdas=None)
        # Schedular dag vazio retorna empty
        dag = ActivityDAG(activities=[], precedence=[])
        pool = ResourcePool(resources={})
        out = lns.schedule(dag=dag, pool=pool)
        assert out is not None  # não deve explodir

    def test_explore_schedules_aceita_initial_lambdas(self):
        """explore_schedules deve aceitar parâmetro initial_lambdas."""
        import inspect

        from concilium.application.scheduling.selector import explore_schedules

        sig = inspect.signature(explore_schedules)
        assert "initial_lambdas" in sig.parameters

    def test_explore_schedules_initial_lambdas_default_none(self):
        """initial_lambdas deve ter default=None em explore_schedules."""
        import inspect

        from concilium.application.scheduling.selector import explore_schedules

        sig = inspect.signature(explore_schedules)
        param = sig.parameters["initial_lambdas"]
        assert param.default is None

    def test_initial_lambdas_preservado_entre_iteracoes(self):
        """O dicionário passado como initial_lambdas não deve ser mutado pelo schedule()."""
        pytest.importorskip("ortools", reason="ortools não disponível neste ambiente")
        from concilium.application.scheduling.lns_scheduler import LnsScheduler
        from concilium.application.scheduling.models import ActivityDAG, ResourcePool
        from concilium.domain.services.planning.matching_oracle import MatchingOracle

        oracle = MatchingOracle(mob_costs={})
        original_lambdas = {("a", "b", "T"): 100.0}
        lns = LnsScheduler(oracle=oracle, initial_lambdas=dict(original_lambdas))

        dag = ActivityDAG(activities=[], precedence=[])
        pool = ResourcePool(resources={})
        lns.schedule(dag=dag, pool=pool)

        # initial_lambdas não deve ter sido mutado
        assert lns.initial_lambdas == {("a", "b", "T"): 100.0}
