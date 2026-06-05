"""ADR-078 — Testes unitários para pré-processamento estrutural de compartilhamento.

TDD: todos os testes são escritos ANTES da implementação.
Cobertura:
  - _gap_max_economico
  - _eta_perpetuacao
  - _sobreposicao_bundle
  - _delta_c_pot
  - _build_pre_processamento_compartilhamento (integração)
  - Markdown section _md_relatorio_oportunidades
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from types import ModuleType

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Helpers de carregamento (mesmo padrão de test_adr077)
# ──────────────────────────────────────────────────────────────────────────────

_HELPERS_B = (
    Path(__file__).parent.parent.parent
    / "src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers_pre.py"
)

# ADR-078: a renderização da seção de oportunidades migrou de runtime.py
# (refatorado em pacote) para o módulo de seções de relatório.
def _render_oportunidades(relatorio):
    from concilium.application.runtime.deliverables.reports.report_markdown_sections import (
        render_oportunidades,
    )

    return render_oportunidades(relatorio)


def _load_helpers_b() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_skill_helpers_pre", _HELPERS_B)
    assert spec and spec.loader, f"Não encontrou {_HELPERS_B}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_skill_helpers_pre"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures de domínio reutilizáveis
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def helpers():
    return _load_helpers_b()


# Custo base: mob=80k, demob=40k, idle=12k → gap_max = ceil(120k/12k)−1 = 9
C_MOB = 80_000.0
C_DEMOB = 40_000.0
C_IDLE = 12_000.0
BUDGET = C_MOB + C_DEMOB  # 120_000


# ──────────────────────────────────────────────────────────────────────────────
# 1. TestGapMaxEconomico
# ──────────────────────────────────────────────────────────────────────────────


class TestGapMaxEconomico:
    """_gap_max_economico(c_mob, c_demob, c_idle, unidade) → int"""

    def test_hora_prod_retorna_sentinela_infinito(self, helpers):
        """hora_prod não gera idle cost → gap_max = 9999."""
        result = helpers._gap_max_economico(C_MOB, C_DEMOB, C_IDLE, "hora_prod")
        assert result == 9999

    def test_c_idle_zero_retorna_sentinela_infinito(self, helpers):
        """c_idle == 0 → nunca há custo de ociosidade → gap_max = 9999."""
        result = helpers._gap_max_economico(C_MOB, C_DEMOB, 0.0, "dia_cal")
        assert result == 9999

    def test_divisao_exata(self, helpers):
        """budget = 10 000, c_idle = 2 500 → ceil(4.0)−1 = 3.
        Gap 3: 3×2500 = 7500 < 10000 ✓
        Gap 4: 4×2500 = 10000 ≮ 10000 ✗
        """
        result = helpers._gap_max_economico(8_000.0, 2_000.0, 2_500.0, "dia_cal")
        assert result == 3

    def test_divisao_com_fracao(self, helpers):
        """budget = 10 000, c_idle = 3 000 → ceil(3.33)−1 = 3.
        Gap 3: 9000 < 10000 ✓
        Gap 4: 12000 > 10000 ✗
        """
        result = helpers._gap_max_economico(8_000.0, 2_000.0, 3_000.0, "dia_cal")
        assert result == 3

    def test_gap_max_standard_esccат(self, helpers):
        """ESC-3CAT: mob=80k, demob=40k, idle=12k → ceil(120k/12k)−1 = 9."""
        result = helpers._gap_max_economico(C_MOB, C_DEMOB, C_IDLE, "dia_cal")
        assert result == 9

    def test_gap_max_unidade_mes(self, helpers):
        """unidade 'mes' com c_idle > 0 deve usar o mesmo cálculo."""
        # budget=30k, c_idle=10k → ceil(3.0)−1 = 2
        result = helpers._gap_max_economico(20_000.0, 10_000.0, 10_000.0, "mes")
        assert result == 2

    def test_gap_max_zero_quando_idle_muito_alto(self, helpers):
        """c_idle > budget → gap_max = 0 (nem 1 semana de standby é viável)."""
        result = helpers._gap_max_economico(5_000.0, 5_000.0, 15_000.0, "dia_cal")
        assert result == 0


# ──────────────────────────────────────────────────────────────────────────────
# 2. TestEtaPerpetuacao
# ──────────────────────────────────────────────────────────────────────────────


class TestEtaPerpetuacao:
    """_eta_perpetuacao(gap, c_mob, c_demob, c_idle, unidade) → float"""

    def test_gap_zero_retorna_um(self, helpers):
        """Sem gap → não há idle → η = 1.0."""
        eta = helpers._eta_perpetuacao(0, C_MOB, C_DEMOB, C_IDLE, "dia_cal")
        assert eta == pytest.approx(1.0)

    def test_hora_prod_retorna_um_independente_do_gap(self, helpers):
        """hora_prod → c_idle=0 → η sempre 1.0."""
        eta = helpers._eta_perpetuacao(50, C_MOB, C_DEMOB, C_IDLE, "hora_prod")
        assert eta == pytest.approx(1.0)

    def test_c_idle_zero_retorna_um(self, helpers):
        eta = helpers._eta_perpetuacao(10, C_MOB, C_DEMOB, 0.0, "dia_cal")
        assert eta == pytest.approx(1.0)

    def test_valor_known(self, helpers):
        """mob=80k, demob=40k, idle=12k, gap=5 → η = 1 − 60k/120k = 0.5."""
        eta = helpers._eta_perpetuacao(5, C_MOB, C_DEMOB, C_IDLE, "dia_cal")
        assert eta == pytest.approx(0.5)

    def test_decrescente_com_gap(self, helpers):
        """η deve diminuir à medida que o gap aumenta."""
        etas = [
            helpers._eta_perpetuacao(g, C_MOB, C_DEMOB, C_IDLE, "dia_cal")
            for g in range(0, 10)
        ]
        for a, b in zip(etas, etas[1:]):
            assert a >= b

    def test_clamped_a_zero_quando_gap_supera_gap_max(self, helpers):
        """Gap além do gap_max → custo_idle > budget → η ≤ 0, clamped a 0.0."""
        eta = helpers._eta_perpetuacao(15, C_MOB, C_DEMOB, C_IDLE, "dia_cal")
        assert eta == pytest.approx(0.0)

    def test_gap_exatamente_em_gap_max_eh_positivo(self, helpers):
        """gap = gap_max (9 para ESC-3CAT) → η > 0 (ainda viável)."""
        gap_max = 9
        eta = helpers._eta_perpetuacao(gap_max, C_MOB, C_DEMOB, C_IDLE, "dia_cal")
        assert eta > 0.0

    def test_gap_alem_de_gap_max_inviavel(self, helpers):
        """gap = gap_max + 1 → η <= 0."""
        eta = helpers._eta_perpetuacao(10, C_MOB, C_DEMOB, C_IDLE, "dia_cal")
        assert eta <= 0.0


# ──────────────────────────────────────────────────────────────────────────────
# 3. TestSobreposicaoBundle
# ──────────────────────────────────────────────────────────────────────────────


class TestSobreposicaoBundle:
    """_sobreposicao_bundle(equipe_i, equipe_j, mob_demob_costs) → (ov, omega)"""

    def test_bundles_identicos_omega_um(self, helpers):
        """Quando equipe_i == equipe_j, Ω = 1.0."""
        e = {"ESC-3CAT": 4}
        costs = {"ESC-3CAT": BUDGET}
        ov, omega = helpers._sobreposicao_bundle(e, e, costs)
        assert omega == pytest.approx(1.0)
        assert ov == {"ESC-3CAT": 4}

    def test_sem_sobreposicao_omega_zero(self, helpers):
        """Recursos distintos → Ω = 0."""
        ei = {"ESC-3CAT": 4}
        ej = {"ATERRO": 3}
        costs = {"ESC-3CAT": BUDGET, "ATERRO": BUDGET}
        ov, omega = helpers._sobreposicao_bundle(ei, ej, costs)
        assert omega == pytest.approx(0.0)
        assert ov.get("ESC-3CAT", 0) == 0
        assert ov.get("ATERRO", 0) == 0

    def test_sobreposicao_parcial_quantidade(self, helpers):
        """eap-1_5 (q=4) vs eap-1_9 (q=2) → ov=2, Ω=2/4=0.5."""
        ei = {"ESC-3CAT": 4}
        ej = {"ESC-3CAT": 2}
        costs = {"ESC-3CAT": BUDGET}
        ov, omega = helpers._sobreposicao_bundle(ei, ej, costs)
        assert ov == {"ESC-3CAT": 2}
        assert omega == pytest.approx(0.5)

    def test_multi_recurso_ponderado_por_custo(self, helpers):
        """Multi-recurso: ESC-3CAT (caro) + ATERRO (barato).
        ei = {ESC-3CAT:4, ATERRO:2}, ej = {ESC-3CAT:2, ATERRO:2}
        ov = {ESC-3CAT:2, ATERRO:2}
        Ω = (2×120k + 2×75k) / (4×120k + 2×75k) = (240k+150k)/(480k+150k) = 390k/630k
        """
        ei = {"ESC-3CAT": 4, "ATERRO": 2}
        ej = {"ESC-3CAT": 2, "ATERRO": 2}
        costs = {"ESC-3CAT": 120_000.0, "ATERRO": 75_000.0}
        ov, omega = helpers._sobreposicao_bundle(ei, ej, costs)
        assert ov == {"ESC-3CAT": 2, "ATERRO": 2}
        expected_omega = (2 * 120_000 + 2 * 75_000) / (4 * 120_000 + 2 * 75_000)
        assert omega == pytest.approx(expected_omega)

    def test_recurso_sem_custo_nao_afeta_omega(self, helpers):
        """Recurso sem custo mob/demob não deve contribuir para Ω."""
        ei = {"ESC-3CAT": 4, "COMBUSTIVEL": 100}
        ej = {"ESC-3CAT": 4, "COMBUSTIVEL": 100}
        costs = {"ESC-3CAT": BUDGET, "COMBUSTIVEL": 0.0}
        _, omega = helpers._sobreposicao_bundle(ei, ej, costs)
        assert omega == pytest.approx(1.0)


# ──────────────────────────────────────────────────────────────────────────────
# 4. TestDeltaCPot
# ──────────────────────────────────────────────────────────────────────────────


class TestDeltaCPot:
    """_delta_c_pot(q_i, q_j, ov_vector, eta, mob_demob_costs) → float"""

    def test_gap_zero_maximo_economia(self, helpers):
        """η=1.0 (gap=0) → ΔC = ov × (c_mob + c_demob).
        ov=2 → ΔC = 2 × 120k = 240k
        """
        ov = {"ESC-3CAT": 2}
        costs = {"ESC-3CAT": BUDGET}
        delta = helpers._delta_c_pot(4, 2, ov, 1.0, costs)
        assert delta == pytest.approx(2 * BUDGET)

    def test_com_gap_desconta_por_eta(self, helpers):
        """η=0.5 (gap=5) → ΔC = 2 × 120k × 0.5 = 120k."""
        ov = {"ESC-3CAT": 2}
        costs = {"ESC-3CAT": BUDGET}
        delta = helpers._delta_c_pot(4, 2, ov, 0.5, costs)
        assert delta == pytest.approx(2 * BUDGET * 0.5)

    def test_eta_zero_retorna_zero(self, helpers):
        """Perpetuação inviável (η=0) → ΔC=0."""
        ov = {"ESC-3CAT": 2}
        costs = {"ESC-3CAT": BUDGET}
        delta = helpers._delta_c_pot(4, 2, ov, 0.0, costs)
        assert delta == pytest.approx(0.0)

    def test_sem_sobreposicao_retorna_zero(self, helpers):
        """ov_vector zerado → nada a compartilhar."""
        ov = {"ESC-3CAT": 0}
        costs = {"ESC-3CAT": BUDGET}
        delta = helpers._delta_c_pot(4, 2, ov, 1.0, costs)
        assert delta == pytest.approx(0.0)

    def test_ov_limitado_por_menor_quantia(self, helpers):
        """ov = min(q_i, q_j) = 2, não q_i=6."""
        ov = {"ESC-3CAT": 2}
        costs = {"ESC-3CAT": BUDGET}
        delta_correto = helpers._delta_c_pot(6, 2, ov, 1.0, costs)
        ov_errado = {"ESC-3CAT": 6}
        delta_errado = helpers._delta_c_pot(6, 2, ov_errado, 1.0, costs)
        assert delta_correto < delta_errado


# ──────────────────────────────────────────────────────────────────────────────
# 5. Fixture AGIS-like para testes de integração
# ──────────────────────────────────────────────────────────────────────────────


def _make_rcpsp_spec_com_resource_costs():
    """Spec mínimo: 3 atividades usando ESC-3CAT, com resource_costs."""
    return {
        "activities": [
            {"item_id": "A", "duration_weeks": 10,
             "required_resources": {"ESC-3CAT": 4}},
            {"item_id": "B", "duration_weeks": 10,
             "required_resources": {"ESC-3CAT": 2}},
            {"item_id": "C", "duration_weeks": 10,
             "required_resources": {"ATERRO": 3}},
        ],
        "resource_pool": {"ESC-3CAT": 6, "ATERRO": 3},
        "resource_costs": {
            "ESC-3CAT": {
                "custo_mob_unit": C_MOB,
                "custo_demob_unit": C_DEMOB,
                "custo_idle_semanal_unit": C_IDLE,
                "unidade_faturamento": "dia_cal",
            },
        },
    }


def _make_cron_lookup(schedule: dict[str, tuple[int, int]]):
    """schedule = {item_id: (start_idx, end_idx)}.
    Retorna objetos com atributos semana_inicio/fim e week index helpers.
    """
    from types import SimpleNamespace

    def _fmt(idx: int) -> str:
        return f"S{idx:03d}"

    result = {}
    for iid, (s, e) in schedule.items():
        result[iid] = SimpleNamespace(
            activity_id=iid,
            semana_inicio=_fmt(s),
            semana_fim=_fmt(e),
        )
    return result


def _make_contratos(tipos: list[str]):
    """Contratos mínimos para os tipos informados."""
    from types import SimpleNamespace

    contratos = []
    for t in tipos:
        contratos.append(
            SimpleNamespace(
                contrato_id=f"C-{t}",
                tipo_id=t,
                quantidade_contratada=6,
                semanas_contrato=48,
                semana_inicio="S001",
                semana_fim="S048",
                custo_unit_semanal=20_000.0,
                custo_total_contrato=6 * 48 * 20_000.0,
                custo_mob_unit=0.0,
                custo_demob_unit=0.0,
                custo_idle_semanal_unit=0.0,
                unidade_faturamento="hora_prod",
                gap_max_economico=9999,
            )
        )
    return contratos


# ──────────────────────────────────────────────────────────────────────────────
# 6. TestBuildPreProcessamento (integração)
# ──────────────────────────────────────────────────────────────────────────────


class TestBuildPreProcessamento:
    """_build_pre_processamento_compartilhamento(...) → RelatorioOportunidades | None"""

    def test_sem_resource_costs_retorna_none(self, helpers):
        """Sem resource_costs no spec → retorna None sem erro."""
        spec = {
            "activities": [{"item_id": "A", "required_resources": {"ESC-3CAT": 4}}],
            "resource_pool": {"ESC-3CAT": 4},
        }
        contratos = _make_contratos(["ESC-3CAT"])
        cron = _make_cron_lookup({"A": (1, 10)})
        validacoes: list = []
        result = helpers._build_pre_processamento_compartilhamento(
            contratos, spec, cron, validacoes
        )
        assert result is None

    def test_sem_resource_costs_emite_val_skip(self, helpers):
        """Sem resource_costs → VAL-PRE-PROCESSAMENTO-SKIP."""
        spec = {"activities": [], "resource_pool": {}}
        validacoes: list = []
        helpers._build_pre_processamento_compartilhamento(
            [], spec, {}, validacoes
        )
        codigos = [v.codigo for v in validacoes]
        assert "VAL-PRE-PROCESSAMENTO-SKIP" in codigos

    def test_atividades_sequenciais_gera_oportunidade(self, helpers):
        """A (W1-10) → B (W15-25) com gap=4 < gap_max=9 → 1 oportunidade viável."""
        spec = _make_rcpsp_spec_com_resource_costs()
        contratos = _make_contratos(["ESC-3CAT"])
        cron = _make_cron_lookup({"A": (1, 10), "B": (15, 25), "C": (1, 25)})
        validacoes: list = []
        relatorio = helpers._build_pre_processamento_compartilhamento(
            contratos, spec, cron, validacoes
        )
        assert relatorio is not None
        viaveis = [o for o in relatorio.oportunidades if o.economicamente_viavel]
        assert len(viaveis) == 1

    def test_gap_maior_que_gap_max_eh_inviavel(self, helpers):
        """A (W1-10) → B (W25-35) com gap=14 > gap_max=9 → inviável."""
        spec = _make_rcpsp_spec_com_resource_costs()
        contratos = _make_contratos(["ESC-3CAT"])
        cron = _make_cron_lookup({"A": (1, 10), "B": (25, 35), "C": (1, 25)})
        validacoes: list = []
        relatorio = helpers._build_pre_processamento_compartilhamento(
            contratos, spec, cron, validacoes
        )
        assert relatorio is not None
        inviavel = next(
            (o for o in relatorio.oportunidades if not o.economicamente_viavel), None
        )
        assert inviavel is not None

    def test_atividades_sobrepostas_nao_geram_oportunidade(self, helpers):
        """Atividades simultâneas (gap < 0) → nenhuma oportunidade."""
        spec = _make_rcpsp_spec_com_resource_costs()
        contratos = _make_contratos(["ESC-3CAT"])
        # A e B se sobrepõem (B começa antes de A terminar)
        cron = _make_cron_lookup({"A": (1, 20), "B": (10, 30), "C": (1, 10)})
        validacoes: list = []
        relatorio = helpers._build_pre_processamento_compartilhamento(
            contratos, spec, cron, validacoes
        )
        # Atividades A e B se sobrepõem para ESC-3CAT → nenhuma oportunidade ESC-3CAT
        if relatorio:
            assert all(o.gap_semanas >= 0 for o in relatorio.oportunidades)

    def test_oportunidades_ordenadas_por_delta_desc(self, helpers):
        """Oportunidades devem estar ordenadas por delta_c_pot decrescente."""
        spec = {
            "activities": [
                {"item_id": "A", "duration_weeks": 10,
                 "required_resources": {"ESC-3CAT": 4}},
                {"item_id": "B", "duration_weeks": 10,
                 "required_resources": {"ESC-3CAT": 4}},
                {"item_id": "D", "duration_weeks": 10,
                 "required_resources": {"ESC-3CAT": 2}},
            ],
            "resource_pool": {"ESC-3CAT": 6},
            "resource_costs": {
                "ESC-3CAT": {
                    "custo_mob_unit": C_MOB,
                    "custo_demob_unit": C_DEMOB,
                    "custo_idle_semanal_unit": C_IDLE,
                    "unidade_faturamento": "dia_cal",
                },
            },
        }
        contratos = _make_contratos(["ESC-3CAT"])
        # A→B gap=2, A→D gap=5, B→D gap=3
        cron = _make_cron_lookup({"A": (1, 10), "B": (13, 23), "D": (17, 27)})
        validacoes: list = []
        relatorio = helpers._build_pre_processamento_compartilhamento(
            contratos, spec, cron, validacoes
        )
        if relatorio and len(relatorio.oportunidades) > 1:
            deltas = [o.delta_c_pot for o in relatorio.oportunidades]
            assert all(a >= b for a, b in zip(deltas, deltas[1:]))

    def test_total_economia_pot_soma_viaveis(self, helpers):
        """total_economia_pot = Σ delta_c_pot (apenas viáveis)."""
        spec = _make_rcpsp_spec_com_resource_costs()
        contratos = _make_contratos(["ESC-3CAT"])
        cron = _make_cron_lookup({"A": (1, 10), "B": (12, 22), "C": (1, 20)})
        validacoes: list = []
        relatorio = helpers._build_pre_processamento_compartilhamento(
            contratos, spec, cron, validacoes
        )
        if relatorio:
            esperado = sum(
                o.delta_c_pot for o in relatorio.oportunidades if o.economicamente_viavel
            )
            assert relatorio.total_economia_pot == pytest.approx(esperado)

    def test_gap_max_por_tipo_inclui_tipo_com_costs(self, helpers):
        """gap_max_por_tipo deve conter ESC-3CAT com valor correto (9)."""
        spec = _make_rcpsp_spec_com_resource_costs()
        contratos = _make_contratos(["ESC-3CAT"])
        cron = _make_cron_lookup({"A": (1, 10), "B": (12, 22), "C": (1, 20)})
        validacoes: list = []
        relatorio = helpers._build_pre_processamento_compartilhamento(
            contratos, spec, cron, validacoes
        )
        if relatorio:
            assert "ESC-3CAT" in relatorio.gap_max_por_tipo
            assert relatorio.gap_max_por_tipo["ESC-3CAT"] == 9

    def test_lambda0_igual_delta_vezes_omega(self, helpers):
        """λ_0 = ΔC_pot × Ω para cada oportunidade."""
        spec = _make_rcpsp_spec_com_resource_costs()
        contratos = _make_contratos(["ESC-3CAT"])
        cron = _make_cron_lookup({"A": (1, 10), "B": (12, 22), "C": (1, 20)})
        validacoes: list = []
        relatorio = helpers._build_pre_processamento_compartilhamento(
            contratos, spec, cron, validacoes
        )
        if relatorio:
            for o in relatorio.oportunidades:
                assert o.lambda0 == pytest.approx(o.delta_c_pot * o.omega_bundle)

    def test_emite_val_ok_quando_ha_oportunidades(self, helpers):
        """Com resource_costs e oportunidades geradas → VAL-PRE-PROCESSAMENTO-OK."""
        spec = _make_rcpsp_spec_com_resource_costs()
        contratos = _make_contratos(["ESC-3CAT"])
        cron = _make_cron_lookup({"A": (1, 10), "B": (12, 22), "C": (1, 20)})
        validacoes: list = []
        helpers._build_pre_processamento_compartilhamento(
            contratos, spec, cron, validacoes
        )
        codigos = [v.codigo for v in validacoes]
        assert "VAL-PRE-PROCESSAMENTO-OK" in codigos

    def test_emite_val_inviavel_quando_ha_aresta_podada(self, helpers):
        """Gap > gap_max → VAL-OPT-INVIAVEL emitido."""
        spec = _make_rcpsp_spec_com_resource_costs()
        contratos = _make_contratos(["ESC-3CAT"])
        # gap = 20 > gap_max = 9
        cron = _make_cron_lookup({"A": (1, 10), "B": (31, 41), "C": (1, 20)})
        validacoes: list = []
        helpers._build_pre_processamento_compartilhamento(
            contratos, spec, cron, validacoes
        )
        codigos = [v.codigo for v in validacoes]
        assert "VAL-OPT-INVIAVEL" in codigos

    def test_recursos_compartilhaveis_correto(self, helpers):
        """recursos_compartilhaveis deve conter ov_vector: min(q_i, q_j)."""
        spec = _make_rcpsp_spec_com_resource_costs()
        contratos = _make_contratos(["ESC-3CAT"])
        cron = _make_cron_lookup({"A": (1, 10), "B": (12, 22), "C": (1, 20)})
        validacoes: list = []
        relatorio = helpers._build_pre_processamento_compartilhamento(
            contratos, spec, cron, validacoes
        )
        if relatorio:
            opp = next(
                (o for o in relatorio.oportunidades
                 if o.atividade_i in ("A", "B") and o.atividade_j in ("A", "B")),
                None,
            )
            if opp:
                # A=4, B=2 → ov=2
                assert opp.recursos_compartilhaveis.get("ESC-3CAT") == 2

    def test_tipo_sem_resource_costs_ignorado(self, helpers):
        """ATERRO não tem resource_costs → nenhuma oportunidade para ATERRO."""
        spec = _make_rcpsp_spec_com_resource_costs()
        contratos = _make_contratos(["ESC-3CAT", "ATERRO"])
        cron = _make_cron_lookup({"A": (1, 10), "B": (12, 22), "C": (35, 45)})
        validacoes: list = []
        relatorio = helpers._build_pre_processamento_compartilhamento(
            contratos, spec, cron, validacoes
        )
        if relatorio:
            aterro_opps = [o for o in relatorio.oportunidades if o.tipo_id == "ATERRO"]
            assert len(aterro_opps) == 0

    def test_contratos_atualizados_com_gap_max(self, helpers):
        """Após execução, contratos ESC-3CAT devem ter gap_max_economico=9."""
        spec = _make_rcpsp_spec_com_resource_costs()
        contratos = _make_contratos(["ESC-3CAT"])
        cron = _make_cron_lookup({"A": (1, 10), "B": (12, 22), "C": (1, 20)})
        validacoes: list = []
        helpers._build_pre_processamento_compartilhamento(
            contratos, spec, cron, validacoes
        )
        esc = next(c for c in contratos if c.tipo_id == "ESC-3CAT")
        assert esc.gap_max_economico == 9
        assert esc.custo_mob_unit == C_MOB
        assert esc.custo_demob_unit == C_DEMOB


# ──────────────────────────────────────────────────────────────────────────────
# 7. TestMarkdownRelatorioOportunidades
# ──────────────────────────────────────────────────────────────────────────────


class TestMarkdownRelatorioOportunidades:
    """_md_relatorio_oportunidades(relatorio) → list[str]"""

    def _make_relatorio_simples(self):
        """Cria RelatorioOportunidades com 2 oportunidades para teste de MD."""
        from concilium.domain.models.canonical import (
            OportunidadeCompartilhamento,
            RelatorioOportunidades,
        )

        opps = [
            OportunidadeCompartilhamento(
                atividade_i="eap-1_6",
                atividade_j="eap-1_9",
                tipo_id="ESC-3CAT",
                gap_semanas=2,
                gap_max_semanas=9,
                eta=0.833,
                omega_bundle=0.5,
                delta_c_pot=200_000.0,
                lambda0=100_000.0,
                recursos_compartilhaveis={"ESC-3CAT": 2},
                economicamente_viavel=True,
            ),
            OportunidadeCompartilhamento(
                atividade_i="eap-1_5",
                atividade_j="eap-1_9",
                tipo_id="ESC-3CAT",
                gap_semanas=11,
                gap_max_semanas=9,
                eta=0.0,
                omega_bundle=0.5,
                delta_c_pot=0.0,
                lambda0=0.0,
                recursos_compartilhaveis={"ESC-3CAT": 2},
                economicamente_viavel=False,
            ),
        ]
        return RelatorioOportunidades(
            total_oportunidades=2,
            total_economia_pot=200_000.0,
            oportunidades_podadas=1,
            lambda0_total=100_000.0,
            oportunidades=opps,
            gap_max_por_tipo={"ESC-3CAT": 9},
        )

    def test_retorna_lista_de_strings(self):
        relatorio = self._make_relatorio_simples()
        lines = _render_oportunidades(relatorio)
        assert isinstance(lines, list)
        assert all(isinstance(s, str) for s in lines)

    def test_contem_header(self):
        relatorio = self._make_relatorio_simples()
        md = "\n".join(_render_oportunidades(relatorio))
        assert "Oportunidade" in md or "Compartilhamento" in md

    def test_contem_atividades(self):
        relatorio = self._make_relatorio_simples()
        md = "\n".join(_render_oportunidades(relatorio))
        assert "eap-1_6" in md
        assert "eap-1_9" in md

    def test_contem_delta_c_pot(self):
        relatorio = self._make_relatorio_simples()
        md = "\n".join(_render_oportunidades(relatorio))
        assert "200" in md  # R$ 200.000 aparece em algum formato

    def test_viavel_marcado_diferente_de_inviavel(self):
        relatorio = self._make_relatorio_simples()
        md = "\n".join(_render_oportunidades(relatorio))
        # Deve diferenciar viável (✅) de inviável (❌ ou ⚠️)
        assert "✅" in md or "❌" in md or "⚠" in md

    def test_relatorio_none_retorna_lista_vazia(self):
        lines = _render_oportunidades(None)
        assert lines == []
