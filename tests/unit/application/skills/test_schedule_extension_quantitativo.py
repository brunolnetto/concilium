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

Import strategy: idêntica a test_skill04_cov2.py — carrega o skill via
`concilium.application.skills` para que sys.modules seja populado via importlib,
preservando os imports relativos dos helpers.
"""

from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace

from concilium.application.skills import run_cronograma  # noqa: F401 — trigger module loading

_MOD_NAME = "_concilium_skillpkg_04_cronograma.skill"
_MOD = sys.modules[_MOD_NAME]

_mod_scheduling = _MOD._mod_scheduling
_mod_assembly = _MOD._mod_assembly
_mod_custos = _MOD._mod_custos
_build_activity_distribuicao = _mod_scheduling._build_activity_distribuicao
_warn_if_activity_underdelivers = _mod_scheduling._warn_if_activity_underdelivers
_build_scheduled_activity_for_item = _mod_assembly._build_scheduled_activity_for_item
_build_cronograma_out = _MOD._build_cronograma_out

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
