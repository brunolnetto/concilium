"""Testes — extensão do cronograma além de sa.duration_weeks para fechar quantitativo.

Antes desta correção, `_build_activity_distribuicao` (skill 04) iterava um número FIXO
de semanas (`sa.duration_weeks`, duração nominal do RCPSP com produtividade nominal, sem
antecipar clima/calendário/jornada real). Quando η_p real reduzia a produção semanal, a
atividade terminava sub-entregue (Σ q_ij < Q) e isso só gerava um AVISO não-bloqueante
(VAL-CRON-01) — o quantitativo nunca era de fato fechado.

A correção troca o loop por um `while` que continua além de `sa.duration_weeks`, repetindo
o padrão de alocação/clima das últimas semanas (via `_infer_teams_from_resources`, que já
retorna o pico quando `week_offset` excede o `ramp_profile` original), até
`qtd_acumulada >= item.quantitativo` ou até o teto de segurança
`TETO_EXTENSAO_CRONOGRAMA_SEMANAS` (10 anos).

Duas consistências adicionais que a extensão exige (senão ficam stale):
  - `_build_scheduled_activity_for_item` (_assembly.py): `duration_weeks` não pode mais
    confiar cegamente em `duration_lookup` (RCPSP pré-extensão) — precisa ser o máximo
    entre ele e a duração real observada em `distribuicao_semanal`.
  - `_build_cronograma_out` (_assembly.py): `makespan_weeks` não pode vir cego de
    `schedule_selected.makespan` (também pré-extensão) — precisa ser o máximo entre ele
    e o makespan real das `scheduled_activities_out` (usado por custo indireto/canteiro
    e pelo gatilho de replanejamento).

Gate de ramp-down orientado a estado (não a calendário): `ramp_profile` é calculado pelo
RCPSP ANTES de saber se a atividade vai sub-entregar, ancorando o início do ramp-down numa
duração nominal que pode estar errada. Em vez de confiar na posição do array, extraímos a
taxa de desmobilização (`_extract_taxa_desmobilizacao_fracao`) e decidimos toda semana, com
o estado real (Q remanescente), se é seguro reduzir a equipe agora
(`_producao_maxima_com_rampa_down`) — nunca prevendo clima futuro. Resolve dois problemas:
sub-entrega por desmobilizar cedo demais (rampa ancorada no fim errado) e o platô "eterno"
sem nenhum ramp-down durante a extensão (fallback antigo sempre voltava ao pico).

Import strategy: idêntica a test_skill04_cov2.py — carrega o skill via
`concilium.application.skills` para que sys.modules seja populado via importlib,
preservando os imports relativos dos helpers.
"""

from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace

import pytest

from concilium.application.skills import run_cronograma  # noqa: F401 — trigger module loading

_MOD_NAME = "_concilium_skillpkg_04_cronograma.skill"
_MOD = sys.modules[_MOD_NAME]

_mod_scheduling = _MOD._mod_scheduling
_mod_assembly = _MOD._mod_assembly
_mod_custos = _MOD._mod_custos
_mod_validacao = _MOD._mod_validacao
_build_activity_distribuicao = _mod_scheduling._build_activity_distribuicao
_warn_if_activity_underdelivers = _mod_scheduling._warn_if_activity_underdelivers
_build_scheduled_activity_for_item = _mod_assembly._build_scheduled_activity_for_item
_build_cronograma_out = _MOD._build_cronograma_out
_extract_taxa_desmobilizacao_fracao = _mod_validacao._extract_taxa_desmobilizacao_fracao
_producao_maxima_com_rampa_down = _mod_validacao._producao_maxima_com_rampa_down

_DATA_INICIO = date(2026, 1, 5)  # segunda-feira, semana ISO 2026-W02


def _canonical(data_inicio: date = _DATA_INICIO) -> SimpleNamespace:
    return SimpleNamespace(projeto=SimpleNamespace(data_inicio=data_inicio))


def _sa(start_week: int, duration_weeks: int, num_eq: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        start_week=start_week,
        duration_weeks=duration_weeks,
        assigned_resources={"eq1": num_eq},
    )


class TestBuildActivityDistribuicaoExtensao:
    def test_no_extension_when_nominal_duration_suffices(self):
        """Sem perda de clima, a janela nominal já fecha 100% — loop não estende."""
        sa = _sa(start_week=0, duration_weeks=3, num_eq=1)
        item = SimpleNamespace(quantitativo=30.0)
        semanas_obra = ["2026-W02", "2026-W03", "2026-W04"]

        distribuicao, qtd_acumulada = _build_activity_distribuicao(
            sa,
            item,
            cpu={},
            ramp=None,
            n_max=1,
            producao_semanal_base=10.0,
            semanas_obra=semanas_obra,
            canonical_in=_canonical(),
            prat_semanal={},
            prat_mensal={},
            fator_calendario_semanal={},
        )

        assert len(distribuicao) == 3
        assert qtd_acumulada == 30.0

    def test_searches_longer_duration_within_real_calendar(self):
        """Clima adverso aumenta N_i, mas apenas dentro do calendário disponível."""
        sa = _sa(start_week=0, duration_weeks=3, num_eq=1)
        item = SimpleNamespace(quantitativo=30.0)
        semanas_obra = ["2026-W02", "2026-W03", "2026-W04", "2026-W05", "2026-W06", "2026-W07"]
        prat_semanal = {s: 0.5 for s in semanas_obra}

        distribuicao, qtd_acumulada = _build_activity_distribuicao(
            sa,
            item,
            cpu={},
            ramp=None,
            n_max=1,
            producao_semanal_base=10.0,
            semanas_obra=semanas_obra,
            canonical_in=_canonical(),
            prat_semanal=prat_semanal,
            prat_mensal={},
            fator_calendario_semanal={},
        )

        # capacidade semanal = 10 * 1 * 0.5 = 5/sem; para fechar 30, N_i=6.
        assert len(distribuicao) == 6
        assert qtd_acumulada == 30.0

    def test_reports_infeasibility_when_known_calendar_cannot_close_scope(self):
        """Praticabilidade nula no calendário disponível não cria semanas fictícias."""
        sa = _sa(start_week=0, duration_weeks=3, num_eq=1)
        item = SimpleNamespace(quantitativo=30.0)
        semanas_obra = ["2026-W02", "2026-W03", "2026-W04"]
        prat_semanal = {s: 0.0 for s in semanas_obra}  # clima=0 → capacidade_real=0 sempre

        distribuicao, qtd_acumulada = _build_activity_distribuicao(
            sa,
            item,
            cpu={},
            ramp=None,
            n_max=1,
            producao_semanal_base=10.0,
            semanas_obra=semanas_obra,
            canonical_in=_canonical(),
            prat_semanal=prat_semanal,
            prat_mensal={},
            fator_calendario_semanal={},
        )

        assert distribuicao == {}
        assert qtd_acumulada == 0.0

        validacoes = []
        _warn_if_activity_underdelivers(item, "eap-01", sa, qtd_acumulada, validacoes)
        assert len(validacoes) == 1
        assert validacoes[0].codigo == "VAL-CRON-01"
        assert validacoes[0].status == "ERRO"
        assert "residual=30" in validacoes[0].mensagem
        assert "calendário disponível" in validacoes[0].mensagem
        assert "0.0000%" in validacoes[0].mensagem

    def test_no_warning_when_real_calendar_closes_scope(self):
        """A busca de N_i não alerta quando há semanas reais suficientes para fechar Q."""
        sa = _sa(start_week=0, duration_weeks=3, num_eq=1)
        item = SimpleNamespace(quantitativo=30.0)
        semanas_obra = ["2026-W02", "2026-W03", "2026-W04", "2026-W05", "2026-W06", "2026-W07"]
        prat_semanal = {s: 0.5 for s in semanas_obra}

        _distribuicao, qtd_acumulada = _build_activity_distribuicao(
            sa,
            item,
            cpu={},
            ramp=None,
            n_max=1,
            producao_semanal_base=10.0,
            semanas_obra=semanas_obra,
            canonical_in=_canonical(),
            prat_semanal=prat_semanal,
            prat_mensal={},
            fator_calendario_semanal={},
        )

        validacoes = []
        _warn_if_activity_underdelivers(item, "eap-01", sa, qtd_acumulada, validacoes)
        assert validacoes == []


def test_scope_closure_reports_exact_residual_and_horizon() -> None:
    closure = _mod_scheduling.assess_scope_closure(
        "eap-01", 30.0, 12.5, calendar_horizon_weeks=3,
    )
    assert closure.status == "FAIL"
    assert closure.reason == "CALENDAR_OR_CAPACITY_EXHAUSTED"
    assert closure.required == 30.0
    assert closure.delivered == 12.5
    assert closure.residual == 17.5
    assert closure.absolute_error == 17.5
    assert closure.calendar_horizon_weeks == 3


@pytest.mark.parametrize(
    ("required", "delivered"),
    [(30.0, float("nan")), (float("inf"), 30.0), (-5.0, 0.0)],
)
def test_scope_closure_rejects_invalid_quantities(required: float, delivered: float) -> None:
    closure = _mod_scheduling.assess_scope_closure("invalid", required, delivered)
    assert closure.status == "UNKNOWN"
    assert closure.reason == "INVALID_QUANTITY"


def test_overproduction_never_passes_scope_closure() -> None:
    closure = _mod_scheduling.assess_scope_closure("excess", 10.0, 11.0)
    assert closure.status == "FAIL"
    assert closure.reason == "OVERPRODUCTION"
    assert closure.residual == -1.0


def test_scope_closure_tolerance_is_explicit_and_small() -> None:
    closed = _mod_scheduling.assess_scope_closure("closed", 30.0, 30.0 - 1e-10)
    assert closed.status == "PASS"
    missing = _mod_scheduling.assess_scope_closure("missing", 30.0, 29.9)
    assert missing.status == "FAIL"


def test_calendar_infeasibility_emits_error_not_preview_warning() -> None:
    validacoes = []
    _warn_if_activity_underdelivers(
        SimpleNamespace(quantitativo=30.0),
        "eap-01",
        _sa(start_week=0, duration_weeks=3),
        12.5,
        validacoes,
        calendar_horizon_weeks=3,
    )
    assert [v.status for v in validacoes] == ["ERRO"]
    assert "residual=17.5" in validacoes[0].mensagem
    assert "horizonte_semanas=3" in validacoes[0].mensagem


def _dist_semanal(qtd_executada: float) -> object:
    return _mod_custos._build_dist_cell(
        producao_semanal_base=10.0,
        num_eq=1,
        n_max=1,
        fator_clima=1.0,
        fator_calendario=1.0,
        quantitativo=1_000_000.0,  # nunca satura qtd_remanescente neste helper
        qtd_acumulada=0.0,
    ).model_copy(update={"qtd_executada": qtd_executada})


class TestBuildScheduledActivityForItemDurationRecompute:
    def test_duration_weeks_prefers_real_span_when_extension_occurred(self):
        """duration_lookup (RCPSP pré-extensão) fica stale — usar o span real observado."""
        item = SimpleNamespace(item_id="eap-01")
        semanas_obra = ["2026-W02", "2026-W03", "2026-W04", "2026-W05", "2026-W06"]
        distribuicao_semanal = {s: _dist_semanal(5.0) for s in semanas_obra}
        distribuicao_por_item = {"eap-01": distribuicao_semanal}

        sa_out = _build_scheduled_activity_for_item(
            item,
            distribuicao_por_item,
            semanas_obra,
            _canonical(),
            assigned_lookup={},
            duration_lookup={"eap-01": 3},  # nominal pré-extensão, stale
            ramp_lookup={},
        )

        assert sa_out.start_week == 0
        assert sa_out.end_week == 4
        assert sa_out.duration_weeks == 5  # max(3, 5), não o stale 3

    def test_duration_weeks_unaffected_when_no_extension(self):
        """Regressão: sem extensão, duration_lookup e o span real já coincidem."""
        item = SimpleNamespace(item_id="eap-01")
        semanas_obra = ["2026-W02", "2026-W03", "2026-W04"]
        distribuicao_semanal = {s: _dist_semanal(10.0) for s in semanas_obra}
        distribuicao_por_item = {"eap-01": distribuicao_semanal}

        sa_out = _build_scheduled_activity_for_item(
            item,
            distribuicao_por_item,
            semanas_obra,
            _canonical(),
            assigned_lookup={},
            duration_lookup={"eap-01": 3},
            ramp_lookup={},
        )

        assert sa_out.duration_weeks == 3

    def test_persists_effective_ramp_and_final_closure_fraction(self):
        """The canonical artifact retains W_i and φ_i from the real final week."""
        item = SimpleNamespace(item_id="eap-01")
        semanas_obra = ["2026-W02", "2026-W03"]
        first = _mod_custos._build_dist_cell(10.0, 1, 1, 1.0, 1.0, 15.0, 0.0)
        final = _mod_custos._build_dist_cell(10.0, 1, 1, 1.0, 1.0, 15.0, first.qtd_acumulada)

        sa_out = _build_scheduled_activity_for_item(
            item,
            {"eap-01": {semanas_obra[0]: first, semanas_obra[1]: final}},
            semanas_obra,
            _canonical(),
            assigned_lookup={},
            duration_lookup={"eap-01": 2},
            ramp_lookup={"eap-01": [1.0, 1.0]},
            ramp_params_lookup={"eap-01": {"n_inicial": 1, "n_max": 1, "n_final": 1}},
        )

        assert sa_out.ramp_params == {"n_inicial": 1, "n_max": 1, "n_final": 1}
        assert sa_out.ramp_profile == [1.0, 1.0]
        assert sa_out.fracao_fechamento == pytest.approx(0.5)


def _scheduled_activity(end_week: int) -> object:
    from concilium.domain.models.canonical import ScheduledActivityCanonical

    return ScheduledActivityCanonical(
        activity_id="eap-01-atv-1",
        start_week=0,
        end_week=end_week,
        duration_weeks=end_week + 1,
    )


class TestBuildCronogramaOutMakespanRecompute:
    def test_makespan_weeks_prefers_real_activities_span_when_extension_occurred(self):
        """schedule_selected.makespan (RCPSP pré-extensão) fica stale — usar o real."""
        schedule_selected = SimpleNamespace(
            heuristic="MINSLK",
            quality_score=1.0,
            makespan=3,
            relaxed=False,
            estoque_delays=None,
        )
        scheduled_activities_out = [
            _scheduled_activity(end_week=1),
            _scheduled_activity(end_week=5),  # estendida pela correção
        ]

        cronograma_out = _build_cronograma_out(
            mode="AUTO_SCHEDULE",
            schedule_selected=schedule_selected,
            scheduled_activities_out=scheduled_activities_out,
            semanas_obra=["2026-W02", "2026-W03", "2026-W04"],
            distribuicao_mensal={},
            validacoes=[],
        )

        assert cronograma_out.makespan_weeks == 6  # max(3, end_week=5 + 1)

    def test_makespan_weeks_unaffected_when_no_extension(self):
        """Regressão: makespan nominal já é >= à duração observada — nenhuma mudança."""
        schedule_selected = SimpleNamespace(
            heuristic="MINSLK",
            quality_score=1.0,
            makespan=6,
            relaxed=False,
            estoque_delays=None,
        )
        scheduled_activities_out = [_scheduled_activity(end_week=1), _scheduled_activity(end_week=2)]

        cronograma_out = _build_cronograma_out(
            mode="AUTO_SCHEDULE",
            schedule_selected=schedule_selected,
            scheduled_activities_out=scheduled_activities_out,
            semanas_obra=["2026-W02", "2026-W03", "2026-W04"],
            distribuicao_mensal={},
            validacoes=[],
        )

        assert cronograma_out.makespan_weeks == 6

    def test_makespan_weeks_falls_back_to_semanas_obra_when_no_schedule_selected(self):
        """Modo manual (schedule_selected=None): fallback antigo preservado."""
        scheduled_activities_out = [_scheduled_activity(end_week=1)]

        cronograma_out = _build_cronograma_out(
            mode="MANUAL_ALLOCATION",
            schedule_selected=None,
            scheduled_activities_out=scheduled_activities_out,
            semanas_obra=["2026-W02", "2026-W03", "2026-W04"],
            distribuicao_mensal={},
            validacoes=[],
        )

        assert cronograma_out.makespan_weeks == 3


class TestExtractTaxaDesmobilizacaoFracao:
    def test_extracts_rate_from_trailing_decreasing_segment(self):
        ramp = [1.0, 1.0, 1.0, 0.75, 0.5, 0.25, 0.0]
        assert _extract_taxa_desmobilizacao_fracao(ramp) == pytest.approx(0.25)

    def test_ignores_ramp_up_before_trailing_decrease(self):
        """Só a cauda decrescente conta — sobe, mantém, desce."""
        ramp = [0.2, 0.6, 1.0, 1.0, 0.6, 0.2]
        assert _extract_taxa_desmobilizacao_fracao(ramp) == pytest.approx(0.4)

    def test_none_when_profile_is_none(self):
        assert _extract_taxa_desmobilizacao_fracao(None) is None

    def test_none_when_profile_never_decreases(self):
        """Ramp-up puro ou platô sem ramp-down: nenhuma política declarada."""
        assert _extract_taxa_desmobilizacao_fracao([0.25, 0.5, 0.75, 1.0, 1.0]) is None

    def test_none_when_too_short(self):
        assert _extract_taxa_desmobilizacao_fracao([1.0]) is None
        assert _extract_taxa_desmobilizacao_fracao([]) is None


class TestProducaoMaximaComRampaDown:
    def test_triangle_area_formula(self):
        # capacidade_pico=400, frac=0.75, taxa=0.25 -> 400 * 0.75^2 / (2*0.25) = 450
        assert _producao_maxima_com_rampa_down(0.75, 0.25, 400.0) == pytest.approx(450.0)

    def test_zero_when_frac_is_zero(self):
        assert _producao_maxima_com_rampa_down(0.0, 0.25, 400.0) == 0.0

    def test_infinite_when_taxa_is_zero(self):
        assert _producao_maxima_com_rampa_down(1.0, 0.0, 400.0) == float("inf")


class TestRampDownGateOrientadoAEstado:
    """`_build_activity_distribuicao` só reduz a equipe quando o estado real (Q
    remanescente) confirma que é seguro — nunca por posição no calendário."""

    _RAMP = [1.0, 1.0, 1.0, 0.75, 0.5, 0.25, 0.0]  # taxa extraída = 0.25/semana

    def test_rebuilds_the_formal_profile_for_the_converged_duration(self):
        """O perfil final é a aplicação literal das três retas para N_i=3."""
        sa = _sa(start_week=0, duration_weeks=3, num_eq=4)
        sa.ramp_params = {"n_inicial": 4, "n_max": 4, "n_final": 1, "taxa_mobilizacao": 1.0, "taxa_desmobilizacao": 1.0}
        item = SimpleNamespace(quantitativo=550.0)
        semanas_obra = ["2026-W02", "2026-W03", "2026-W04"]

        distribuicao, qtd_acumulada = _build_activity_distribuicao(
            sa,
            item,
            cpu={},
            ramp=None,
            n_max=4,
            producao_semanal_base=100.0,
            semanas_obra=semanas_obra,
            canonical_in=_canonical(),
            prat_semanal={},
            prat_mensal={},
            fator_calendario_semanal={},
        )

        equipes = [c.num_equipes for _, c in sorted(distribuicao.items())]
        assert equipes == [3, 2, 1]
        assert qtd_acumulada == 550.0

    def test_final_week_uses_nominal_terminal_floor_with_partial_quantity(self):
        """A última semana mantém m_i(N_i-1), embora execute apenas o residual."""
        sa = _sa(start_week=0, duration_weeks=1, num_eq=4)
        sa.ramp_params = {"n_inicial": 4, "n_max": 4, "n_final": 1, "taxa_mobilizacao": 1.0, "taxa_desmobilizacao": 1.0}
        item = SimpleNamespace(quantitativo=200.0)
        semanas_obra = ["2026-W02", "2026-W03"]

        distribuicao, qtd_acumulada = _build_activity_distribuicao(
            sa,
            item,
            cpu={},
            ramp=None,
            n_max=4,
            producao_semanal_base=100.0,
            semanas_obra=semanas_obra,
            canonical_in=_canonical(),
            prat_semanal={},
            prat_mensal={},
            fator_calendario_semanal={},
        )

        cell = distribuicao["2026-W02"]
        assert cell.num_equipes == 2
        assert qtd_acumulada == 200.0

    def test_no_gating_without_a_declared_demobilization_rate(self):
        """Sem trecho decrescente no ramp_profile (ou ramp=None), comportamento
        idêntico ao anterior — nunca inventa uma política de desmobilização."""
        sa = _sa(start_week=0, duration_weeks=3, num_eq=4)
        item = SimpleNamespace(quantitativo=100_000.0)  # nunca fecha na janela nominal
        semanas_obra = ["2026-W02", "2026-W03", "2026-W04"]

        distribuicao, _qtd_acumulada = _build_activity_distribuicao(
            sa,
            item,
            cpu={},
            ramp=[1.0, 1.0, 1.0],  # platô puro, sem cauda decrescente
            n_max=4,
            producao_semanal_base=100.0,
            semanas_obra=semanas_obra,
            canonical_in=_canonical(),
            prat_semanal={},
            prat_mensal={},
            fator_calendario_semanal={},
        )

        # todas as semanas (nominais + extensão) seguem no pico — igual ao fallback antigo
        assert all(c.num_equipes == 4 for c in distribuicao.values())

    def test_adverse_calendar_is_included_in_the_formal_duration_search(self):
        """Uma semana nula leva a N_i=6 e mantém o perfil formal sem gate de estado."""
        sa = _sa(start_week=0, duration_weeks=5, num_eq=4)
        sa.ramp_params = {"n_inicial": 4, "n_max": 4, "n_final": 1, "taxa_mobilizacao": 1.0, "taxa_desmobilizacao": 1.0}
        item = SimpleNamespace(quantitativo=1250.0)
        semanas_obra = ["2026-W02", "2026-W03", "2026-W04", "2026-W05", "2026-W06", "2026-W07"]
        prat_semanal = {"2026-W05": 0.0}  # clima ruim só na semana em que já reduziu 1x

        distribuicao, qtd_acumulada = _build_activity_distribuicao(
            sa,
            item,
            cpu={},
            ramp=None,
            n_max=4,
            producao_semanal_base=100.0,
            semanas_obra=semanas_obra,
            canonical_in=_canonical(),
            prat_semanal=prat_semanal,
            prat_mensal={},
            fator_calendario_semanal={},
        )

        equipes = [distribuicao[s].num_equipes for s in semanas_obra]
        assert equipes == [4, 4, 4, 3, 2, 1]
        assert qtd_acumulada == 1250.0


def test_partial_final_week_closes_exact_scope_without_counting_unused_capacity() -> None:
    sa = _sa(start_week=0, duration_weeks=3, num_eq=1)
    item = SimpleNamespace(quantitativo=25.0)
    weeks = ["2026-W02", "2026-W03", "2026-W04"]

    distribution, delivered = _build_activity_distribuicao(
        sa,
        item,
        cpu={},
        ramp=None,
        n_max=1,
        producao_semanal_base=10.0,
        semanas_obra=weeks,
        canonical_in=_canonical(),
        prat_semanal={},
        prat_mensal={},
        fator_calendario_semanal={},
    )

    quantities = [cell.qtd_executada for cell in distribution.values()]
    assert quantities == [10.0, 10.0, 5.0]
    assert sum(quantities) == 25.0
    assert delivered == 25.0
    assert distribution[weeks[-1]].fracao_fechamento == pytest.approx(0.5)
    assert _mod_scheduling.assess_scope_closure("eap-01", 25.0, sum(quantities)).status == "PASS"


def test_exhausted_calendar_reports_maximum_real_delivery_and_exact_residual() -> None:
    sa = _sa(start_week=0, duration_weeks=5, num_eq=1)
    item = SimpleNamespace(quantitativo=50.0)
    weeks = ["2026-W02", "2026-W03", "2026-W04"]

    distribution, delivered = _build_activity_distribuicao(
        sa,
        item,
        cpu={},
        ramp=None,
        n_max=1,
        producao_semanal_base=10.0,
        semanas_obra=weeks,
        canonical_in=_canonical(),
        prat_semanal={},
        prat_mensal={},
        fator_calendario_semanal={},
    )

    assert list(distribution) == weeks
    assert [cell.qtd_executada for cell in distribution.values()] == [10.0, 10.0, 10.0]
    assert delivered == 30.0

    validacoes = []
    _warn_if_activity_underdelivers(
        item, "eap-01", sa, delivered, validacoes, calendar_horizon_weeks=len(weeks)
    )
    assert len(validacoes) == 1
    assert validacoes[0].status == "ERRO"
    assert "Q=50" in validacoes[0].mensagem
    assert "Σq=30" in validacoes[0].mensagem
    assert "residual=20" in validacoes[0].mensagem
    assert "horizonte_semanas=3" in validacoes[0].mensagem


def test_zero_productivity_preserves_zero_delivery_and_exact_scope_residual() -> None:
    sa = _sa(start_week=0, duration_weeks=3, num_eq=1)
    item = SimpleNamespace(quantitativo=50.0)
    weeks = ["2026-W02", "2026-W03", "2026-W04"]

    distribution, delivered = _build_activity_distribuicao(
        sa,
        item,
        cpu={},
        ramp=None,
        n_max=1,
        producao_semanal_base=0.0,
        semanas_obra=weeks,
        canonical_in=_canonical(),
        prat_semanal={},
        prat_mensal={},
        fator_calendario_semanal={},
    )

    assert list(distribution) == weeks
    assert [cell.qtd_executada for cell in distribution.values()] == [0.0, 0.0, 0.0]
    assert delivered == 0.0
    validacoes = []
    _warn_if_activity_underdelivers(
        item, "eap-zero", sa, delivered, validacoes, calendar_horizon_weeks=len(weeks)
    )
    assert len(validacoes) == 1
    assert validacoes[0].status == "ERRO"
    assert "Q=50" in validacoes[0].mensagem
    assert "Σq=0" in validacoes[0].mensagem
    assert "residual=50" in validacoes[0].mensagem
