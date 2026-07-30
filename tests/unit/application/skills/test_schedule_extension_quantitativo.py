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

    def test_extends_beyond_duration_weeks_to_complete_quantitativo(self):
        """η_p real (clima=0.5) reduz a capacidade semanal — loop estende até fechar Q."""
        sa = _sa(start_week=0, duration_weeks=3, num_eq=1)
        item = SimpleNamespace(quantitativo=30.0)
        semanas_obra = ["2026-W02", "2026-W03", "2026-W04"]
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

        # capacidade semanal = 10 * 1 * 0.5 = 5/sem; para fechar 30, precisa de 6 semanas
        # (as 3 nominais + 3 extras, além de sa.duration_weeks, sem novo AVISO de teto).
        assert len(distribuicao) == 6
        assert qtd_acumulada == 30.0
        # As semanas extras (offset 3..5) excedem semanas_obra (len=3) — exercitam o
        # fallback de _iso_week_key(data_inicio + timedelta(weeks=week_num)).
        extra_keys = set(distribuicao) - set(semanas_obra)
        assert len(extra_keys) == 3

    def test_extension_stops_at_safety_cap_and_warns(self, monkeypatch):
        """Praticabilidade zero: mesmo estendendo, nunca fecha Q — teto de segurança para o loop."""
        monkeypatch.setattr(_mod_scheduling, "TETO_EXTENSAO_CRONOGRAMA_SEMANAS", 5)
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

        assert len(distribuicao) == 5  # parou no teto (monkeypatched para 5), não indefinidamente
        assert qtd_acumulada == 0.0

        validacoes = []
        _warn_if_activity_underdelivers(item, "eap-01", sa, qtd_acumulada, validacoes)
        assert len(validacoes) == 1
        assert validacoes[0].codigo == "VAL-CRON-01"
        assert validacoes[0].status == "AVISO"
        assert "teto de segurança" in validacoes[0].mensagem
        assert "0.0%" in validacoes[0].mensagem

    def test_no_warning_when_quantitativo_is_fully_delivered(self):
        """Com a extensão, o caso comum (sub-entrega na janela nominal) não gera mais AVISO."""
        sa = _sa(start_week=0, duration_weeks=3, num_eq=1)
        item = SimpleNamespace(quantitativo=30.0)
        semanas_obra = ["2026-W02", "2026-W03", "2026-W04"]
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

    def test_vetoes_premature_rampdown_when_much_work_remains(self):
        """Muito trabalho restante: gate mantém o pico em vez de seguir o ramp_profile
        estático (que, na posição do calendário, já estaria descendo)."""
        sa = _sa(start_week=0, duration_weeks=3, num_eq=4)
        item = SimpleNamespace(quantitativo=1000.0)
        semanas_obra = ["2026-W02", "2026-W03", "2026-W04"]

        distribuicao, qtd_acumulada = _build_activity_distribuicao(
            sa,
            item,
            cpu={},
            ramp=self._RAMP,
            n_max=4,
            producao_semanal_base=100.0,
            semanas_obra=semanas_obra,
            canonical_in=_canonical(),
            prat_semanal={},
            prat_mensal={},
            fator_calendario_semanal={},
        )

        equipes = [c.num_equipes for _, c in sorted(distribuicao.items())]
        assert equipes == [4, 4, 3]  # só reduz na semana em que passa a ser seguro
        assert qtd_acumulada == 1000.0

    def test_allows_immediate_descent_when_little_work_remains(self):
        """Pouco trabalho: seguro descer já na primeira semana no pico (regime
        'triângulo' emergente, sem precisar resolver a equação fechada)."""
        sa = _sa(start_week=0, duration_weeks=1, num_eq=4)
        item = SimpleNamespace(quantitativo=200.0)
        semanas_obra = ["2026-W02"]

        distribuicao, qtd_acumulada = _build_activity_distribuicao(
            sa,
            item,
            cpu={},
            ramp=self._RAMP,
            n_max=4,
            producao_semanal_base=100.0,
            semanas_obra=semanas_obra,
            canonical_in=_canonical(),
            prat_semanal={},
            prat_mensal={},
            fator_calendario_semanal={},
        )

        cell = distribuicao["2026-W02"]
        assert cell.num_equipes == 3  # já desmobiliza 1 equipe na própria 1ª semana
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

    def test_self_corrects_by_pausing_descent_after_a_bad_week(self):
        """Já em ramp-down, uma semana de clima ruim atrasa o progresso — o gate
        PAUSA a redução (mantém o nível atual) em vez de continuar descendo às
        cegas até esvaziar a equipe com trabalho ainda pendente. Retoma a descida
        assim que o clima volta e o teste de suficiência passa a valer de novo."""
        sa = _sa(start_week=0, duration_weeks=5, num_eq=4)
        item = SimpleNamespace(quantitativo=1250.0)
        semanas_obra = ["2026-W02", "2026-W03", "2026-W04", "2026-W05", "2026-W06"]
        prat_semanal = {"2026-W05": 0.0}  # clima ruim só na semana em que já reduziu 1x

        distribuicao, qtd_acumulada = _build_activity_distribuicao(
            sa,
            item,
            cpu={},
            ramp=self._RAMP,
            n_max=4,
            producao_semanal_base=100.0,
            semanas_obra=semanas_obra,
            canonical_in=_canonical(),
            prat_semanal=prat_semanal,
            prat_mensal={},
            fator_calendario_semanal={},
        )

        equipes = [distribuicao[s].num_equipes for s in semanas_obra]
        # semanas 0-1: veto (falta muito); semana 2: reduz p/ 3 (seguro); semana 3
        # (clima=0): PAUSA em 3 em vez de continuar p/ 2; semana 4: clima normaliza,
        # retoma a descida p/ 2 e fecha exatamente Q.
        assert equipes == [4, 4, 3, 3, 2]
        assert qtd_acumulada == 1250.0
