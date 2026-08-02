"""ADR-173 F6 — Wiring real do roster de MO em skill-05.

Cobre:
  - `aplicar_roster_a_contratos` (função pura de wiring, `_roster_wiring.py`):
    parsing de `inputs["roster_mo"]` (dicts crus) + substituição integral via
    `aplicar_roster_custo_real_mo` (ADR-156), degradação segura sem roster.
  - `run_equipes_e_alocacao` de fato chama `aplicar_roster_a_contratos` com o
    roster de `inputs["roster_mo"]` quando há `contratos_recurso` — hoje nunca
    invocado em produção (ADR-154→160 eram código dormente).

Segue o mesmo padrão de fixture (SimpleNamespace + dicts crus, módulo carregado
via sys.modules após lazy load) de test_adr159_composicao_por_tipo.py.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import concilium.application.skills as _skills_pkg
from concilium.domain.models.canonical import RecursoContrato

_ = _skills_pkg.run_equipes_e_alocacao  # trigger lazy load so os módulos landam em sys.modules

_HELPERS_MOD = sys.modules["_concilium_skillpkg_05_equipes_e_alocacao._skill_helpers"]
_SKILL_MOD = sys.modules["_concilium_skillpkg_05_equipes_e_alocacao.skill"]

aplicar_roster_a_contratos = _HELPERS_MOD.aplicar_roster_a_contratos


def _contrato(tipo_id: str = "TIPO-1", **overrides) -> RecursoContrato:
    defaults = dict(
        contrato_id=f"contrato-{tipo_id.lower()}",
        tipo_id=tipo_id,
        quantidade_contratada=1,
        semana_inicio="2026-W01",
        semana_fim="2026-W04",
        semanas_contrato=4,
        custo_unit_semanal=1000.0,
        custo_unit_semanal_mo=800.0,
        custo_unit_semanal_eq=100.0,
        custo_unit_semanal_comb=50.0,
        custo_unit_semanal_mat=50.0,
        custo_total_contrato=4000.0,
        composicao_funcoes_mo={"MO-ARMADOR": 1},
    )
    defaults.update(overrides)
    return RecursoContrato(**defaults)


class TestAplicarRosterAContratos:
    def test_sem_roster_mo_raw_retorna_mesma_lista(self):
        contrato = _contrato()
        out = aplicar_roster_a_contratos([contrato], None)
        assert out == [contrato]
        assert out[0].custo_unit_semanal_mo == 800.0

    def test_roster_vazio_retorna_mesma_lista(self):
        contrato = _contrato()
        out = aplicar_roster_a_contratos([contrato], [])
        assert out[0].custo_unit_semanal_mo == 800.0

    def test_roster_cobre_composicao_substitui_custo_direto(self):
        contrato = _contrato()
        roster_raw = [
            {
                "individuo_id": "mo-001",
                "funcao_id": "MO-ARMADOR",
                "salario_base_mensal": 3000.0,
                "data_admissao": "2026-01-01",
            }
        ]
        out = aplicar_roster_a_contratos([contrato], roster_raw)
        assert out[0].custo_unit_semanal_mo != 800.0

    def test_roster_nao_cobre_mantem_custo_calibrado(self):
        contrato = _contrato(composicao_funcoes_mo={"MO-ARMADOR": 2})  # precisa de 2, só há 1 no roster
        roster_raw = [
            {
                "individuo_id": "mo-001",
                "funcao_id": "MO-ARMADOR",
                "salario_base_mensal": 3000.0,
                "data_admissao": "2026-01-01",
            }
        ]
        out = aplicar_roster_a_contratos([contrato], roster_raw)
        assert out[0].custo_unit_semanal_mo == 800.0


class TestWiringSkill05:
    def test_run_equipes_e_alocacao_aplica_roster_quando_ha_contratos(self):
        """Confirma que skill.py de fato chama aplicar_roster_a_contratos com
        inputs['roster_mo'] — hoje (pré-ADR-173) essa chamada não existia."""
        contrato = _contrato()

        with (
            patch.object(_SKILL_MOD, "_build_dimensionamento", return_value=[]),
            patch.object(_SKILL_MOD, "_resolve_planejamento_maps", return_value=({}, {})),
            patch.object(_SKILL_MOD, "_aplicar_reconciliacao_planejamento", return_value=None),
            patch.object(_SKILL_MOD, "_validar_estagio1_inst_none", return_value=None),
            patch.object(_SKILL_MOD, "_build_pool_setup", return_value=({}, {}, {})),
            patch.object(_SKILL_MOD, "_resolve_rcpsp_spec", return_value=({"algo": "cp_sat"}, False)),
            patch.object(_SKILL_MOD, "_processar_pool_contratos", return_value=([contrato], [])),
            patch.object(_SKILL_MOD, "enriquecer_composicao_por_tipo", return_value=None),
            patch.object(
                _SKILL_MOD,
                "_processar_instancias_recurso",
                return_value=([], [], None),
            ),
            patch.object(_SKILL_MOD, "_preencher_custo_inst_estagio_f3", return_value=None),
            patch.object(_SKILL_MOD, "_deve_processar_compartilhamento", return_value=False),
            patch.object(_SKILL_MOD, "_processar_oportunidades_paralelo", return_value=None),
            patch.object(_SKILL_MOD, "_build_requisitos_e_tipos", return_value=([], {})),
            patch.object(_SKILL_MOD, "_build_alocacoes_pool", return_value=([], {})),
            patch.object(
                _SKILL_MOD, "aplicar_roster_a_contratos", wraps=_SKILL_MOD.aplicar_roster_a_contratos
            ) as spy,
        ):
            canonical_in = type(
                "CanonicalStub",
                (),
                {
                    "projeto": type("P", (), {"data_base_orcamento": None})(),
                    "eap": [],
                    "model_copy": lambda self, update=None: update,
                },
            )()

            roster_raw = [
                {
                    "individuo_id": "mo-001",
                    "funcao_id": "MO-ARMADOR",
                    "salario_base_mensal": 3000.0,
                    "data_admissao": "2026-01-01",
                }
            ]
            resultado = _SKILL_MOD.run_equipes_e_alocacao(
                canonical_in, {"roster_mo": roster_raw}, {"insumos": []}
            )

        spy.assert_called_once()
        args, _ = spy.call_args
        assert args[0] == [contrato]
        assert args[1] == roster_raw
        assert resultado.canonical["contratos_recurso"][0].custo_unit_semanal_mo != 800.0
