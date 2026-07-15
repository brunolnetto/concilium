"""NEP-041 F3 → NEP-049 — mecanismo de skills dormentes e aposentadoria de 08/09.

Histórico: a NEP-041 F3 deixou `08-avaliacao-intervencoes` e `09-registro-decisoes`
dormentes (fora do pipeline automático, invocáveis). A NEP-049 (2026-07-14) as
aposentou de vez: input obrigatório sem produtor real (08), output sem consumidor
(ambas) e casos de uso superados por skill 11 + `simular_cenario_replan` (08) e
`aprovar_versao` + AuditService (09).

Este teste é o contrato do estado pós-NEP-049: as duas não existem mais em lugar
nenhum, o registry tem 9 skills todas ativas, e o MECANISMO de dormência
(status="dormante" no skill.toml) permanece funcional para uso futuro.
"""

from __future__ import annotations

from concilium.application.skills import SKILLS
from concilium.application.skills.phase_classifier import (
    _DORMANTES,
    CANONICAL_SKILL_ORDER,
    MANIFEST_META,
    PHASE_MAP,
)

_APOSENTADAS = {"08-avaliacao-intervencoes", "09-registro-decisoes"}


class TestAposentadoriaNep049:
    def test_aposentadas_fora_de_skills(self):
        assert not _APOSENTADAS & set(SKILLS)

    def test_aposentadas_fora_do_canonical_order_e_do_phase_map(self):
        assert not _APOSENTADAS & set(CANONICAL_SKILL_ORDER)
        todas_em_fases = {s for skills in PHASE_MAP.values() for s in skills}
        assert not _APOSENTADAS & todas_em_fases

    def test_registry_tem_9_skills_todas_ativas(self):
        assert len(MANIFEST_META) == 9
        assert _DORMANTES == set()
        assert set(CANONICAL_SKILL_ORDER) == set(MANIFEST_META)


class TestMecanismoDormenciaPreservado:
    def test_canonical_order_deriva_de_phase_map_menos_dormentes(self):
        """O mecanismo NEP-041 F3 continua: dormentes saem do auto-avanço."""
        dormantes = {sid for sid, m in MANIFEST_META.items() if m.get("status") == "dormante"}
        expected = [s for phase in PHASE_MAP.values() for s in phase if s not in dormantes]
        assert CANONICAL_SKILL_ORDER == expected

    def test_skills_ativas_continuam_no_canonical_order(self):
        for sid in (
            "01-escopo-e-eap",
            "06-resultado-financeiro",
            "09-relatorio-e-artefatos",
            "08-replanejamento-e-cenarios",
        ):
            assert sid in CANONICAL_SKILL_ORDER
