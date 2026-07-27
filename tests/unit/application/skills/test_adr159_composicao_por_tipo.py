"""ADR-159 F1 — Wiring real: enriquecer_composicao_por_tipo: TDD.

Popula composicao_funcoes_mo/composicao_equipamentos_eq (ADR-156/157) em
RecursoContrato reais, reaproveitando _tipo_recurso_fungivel (importada, não
reimplementada) para casamento exato de tipo_id. Puramente descritivo — não
altera nenhum campo de custo.

Escrito antes da implementação (red phase). Segue o mesmo padrão de fixture
(SimpleNamespace + dicts crus, módulo carregado via sys.modules após lazy load)
de test_skill05_helpers_a_coverage.py.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import concilium.application.skills as _skills_pkg
from concilium.domain.models.canonical import RecursoContrato

_ = _skills_pkg.run_equipes_e_alocacao  # trigger lazy load so _skill_helpers lands in sys.modules

_MOD = sys.modules["_concilium_skillpkg_05_equipes_e_alocacao._skill_helpers"]

enriquecer_composicao_por_tipo = _MOD.enriquecer_composicao_por_tipo
_tipo_recurso_fungivel = _MOD._tipo_recurso_fungivel


def _contrato(tipo_id: str) -> RecursoContrato:
    return RecursoContrato(
        contrato_id=f"contrato-{tipo_id.lower()}",
        tipo_id=tipo_id,
        quantidade_contratada=1,
        semana_inicio="2026-W01",
        semana_fim="2026-W04",
        semanas_contrato=4,
        custo_unit_semanal=1000.0,
        custo_total_contrato=4000.0,
    )


def _item(item_id: str, cpu_id: str) -> SimpleNamespace:
    return SimpleNamespace(item_id=item_id, cpu_id=cpu_id)


class TestEnriquecerComposicaoPorTipo:
    def test_popula_funcoes_mo_e_equipamentos_eq(self):
        composicao = {
            "funcoes": [{"funcao_id": "MO-OPER-ESCAV", "num_pessoas": 1}],
            "equipamentos": [{"equip_id": "EQ-E0019", "num_unidades": 1}],
        }
        tipo_id = _tipo_recurso_fungivel("CPU-1", composicao)
        cpu_lookup = {"CPU-1": {"producao_id_ref": "PROD-1"}}
        prod_lookup = {"PROD-1": {"composicao_padrao_equipe": composicao}}
        item = _item("EAP-1", "CPU-1")
        sched_lookup = {"EAP-1": SimpleNamespace()}
        contrato = _contrato(tipo_id)

        enriquecer_composicao_por_tipo([contrato], [item], sched_lookup, cpu_lookup, prod_lookup)

        assert contrato.composicao_funcoes_mo == {"MO-OPER-ESCAV": 1}
        assert contrato.composicao_equipamentos_eq == {"EQ-E0019": 1}

    def test_item_sem_agendamento_e_ignorado(self):
        item = _item("EAP-NAO-AGENDADO", "CPU-1")
        contrato = _contrato("ESC-3CAT")
        enriquecer_composicao_por_tipo([contrato], [item], {}, {"CPU-1": {}}, {})
        assert contrato.composicao_funcoes_mo == {}
        assert contrato.composicao_equipamentos_eq == {}

    def test_contrato_sem_correspondencia_na_eap_mantem_vazio(self):
        contrato = _contrato("TIPO-NUNCA-VISTO")
        item = _item("EAP-1", "CPU-X")
        sched_lookup = {"EAP-1": SimpleNamespace()}
        enriquecer_composicao_por_tipo([contrato], [item], sched_lookup, {"CPU-X": {}}, {})
        assert contrato.composicao_funcoes_mo == {}
        assert contrato.composicao_equipamentos_eq == {}

    def test_multiplos_contratos_enriquecidos_independentemente(self):
        comp_a = {"funcoes": [{"funcao_id": "PEDREIRO", "num_pessoas": 2}], "equipamentos": []}
        comp_b = {"funcoes": [], "equipamentos": [{"equip_id": "EQ-B", "num_unidades": 3}]}
        tipo_a = _tipo_recurso_fungivel("CPU-A", comp_a)
        tipo_b = _tipo_recurso_fungivel("CPU-B", comp_b)
        cpu_lookup = {"CPU-A": {"producao_id_ref": "PROD-A"}, "CPU-B": {"producao_id_ref": "PROD-B"}}
        prod_lookup = {
            "PROD-A": {"composicao_padrao_equipe": comp_a},
            "PROD-B": {"composicao_padrao_equipe": comp_b},
        }
        item_a = _item("EAP-A", "CPU-A")
        item_b = _item("EAP-B", "CPU-B")
        sched_lookup = {"EAP-A": SimpleNamespace(), "EAP-B": SimpleNamespace()}
        contrato_a, contrato_b = _contrato(tipo_a), _contrato(tipo_b)

        enriquecer_composicao_por_tipo(
            [contrato_a, contrato_b], [item_a, item_b], sched_lookup, cpu_lookup, prod_lookup
        )

        assert contrato_a.composicao_funcoes_mo == {"PEDREIRO": 2}
        assert contrato_a.composicao_equipamentos_eq == {}
        assert contrato_b.composicao_funcoes_mo == {}
        assert contrato_b.composicao_equipamentos_eq == {"EQ-B": 3}

    def test_lista_de_contratos_vazia_nao_faz_nada(self):
        enriquecer_composicao_por_tipo([], [], {}, {}, {})  # não deve lançar exceção
