"""ADR-181 F3 — Aviso de qualidade condicional para leadtime_mob_semanas ausente.

`VAL-MOB-LEADTIME-01` dispara só quando o item NÃO tem `leadtime_mob_semanas`
E o custo direto do item já é material (acima de `TETO_MATERIALIDADE_MOB`) —
não vira obrigatoriedade cega (mesmo padrão fail-loud condicional do ADR-138).
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import concilium.application.skills as _skills_pkg
from concilium.application.skills import run_equipes_e_alocacao  # noqa: F401 — trigger lazy load
from concilium.domain.constants import TETO_MATERIALIDADE_MOB

_ = _skills_pkg.run_equipes_e_alocacao
_MOD = sys.modules["_concilium_skillpkg_05_equipes_e_alocacao._skill_helpers"]

_checar_leadtime_mob_ausente = _MOD._checar_leadtime_mob_ausente


def _item(leadtime_mob_semanas=None, item_id="eap-1"):
    return SimpleNamespace(item_id=item_id, leadtime_mob_semanas=leadtime_mob_semanas)


class TestChecarLeadtimeMobAusente:
    def test_avisa_quando_ausente_e_acima_do_teto(self):
        validacoes: list = []
        _checar_leadtime_mob_ausente(_item(), TETO_MATERIALIDADE_MOB + 1, validacoes)
        assert len(validacoes) == 1
        assert validacoes[0].codigo == "VAL-MOB-LEADTIME-01"
        assert validacoes[0].status == "AVISO"
        assert "eap-1" in validacoes[0].mensagem

    def test_nao_avisa_quando_leadtime_presente(self):
        """Mesmo acima do teto, presença explícita (inclusive 0) não dispara aviso."""
        validacoes: list = []
        _checar_leadtime_mob_ausente(_item(leadtime_mob_semanas=0), TETO_MATERIALIDADE_MOB + 1, validacoes)
        assert validacoes == []

    def test_nao_avisa_quando_abaixo_do_teto(self):
        validacoes: list = []
        _checar_leadtime_mob_ausente(_item(), TETO_MATERIALIDADE_MOB - 1, validacoes)
        assert validacoes == []

    def test_nao_avisa_no_teto_exato(self):
        """Limite é exclusivo (> teto, não >=) — custo igual ao teto não é material o suficiente."""
        validacoes: list = []
        _checar_leadtime_mob_ausente(_item(), TETO_MATERIALIDADE_MOB, validacoes)
        assert validacoes == []
