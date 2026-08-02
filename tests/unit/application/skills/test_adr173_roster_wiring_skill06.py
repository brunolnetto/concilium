"""ADR-173 F7 — Wiring real do roster de MO em skill-06 (custo indireto).

Prova que `run_custos_indiretos` de fato lê `inputs["roster_mo"]`, parseia e
propaga até `_composicao_qsms_bottom_up` — hoje (pré-ADR-173) o headcount de
QSMS/MOB vinha sempre de `equipes_diretas` agregado, nunca de indivíduos reais.
"""

from __future__ import annotations

from concilium.application.skills import load_skill_stage
from concilium.domain.models.canonical import (
    CanonicalModel,
    EquipeDireta,
    FuncaoEquipeDireta,
)

run_custos_indiretos = load_skill_stage("06-resultado-financeiro", "_indiretos", "run_custos_indiretos")


def _make_canonical(equipes_diretas: list[EquipeDireta]) -> CanonicalModel:
    can = CanonicalModel.model_validate(
        {
            "meta": {"gerado_em": "2026-01-01T00:00:00Z", "contexto_id": "ctx-test"},
            "projeto": {
                "id": "proj-test",
                "nome": "Test Project",
                "tipo_obra": "terraplenagem",
                "localizacao": "SP",
                "coordenadas": {"lat": -23.5, "lng": -46.6},
                "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
                "data_inicio": "2026-01-01",
                "data_termino": "2026-03-31",
                "snapshot_catalogo_id": "cat-v1",
                "snapshot_perfil_id": "perf-v1",
            },
        }
    )
    return can.model_copy(update={"equipes_diretas": equipes_diretas})


def _insumo(codigo, tipo, preco, vida_util_dias=None, funcoes_aplicaveis=None):
    return {
        "codigo": codigo,
        "tipo": tipo,
        "descricao": codigo,
        "unidade": "unid",
        "preco_unitario": preco,
        "fonte_preco": "catalogo_proprio",
        "status": "ativo",
        "atributos_especificos": {
            "vida_util_dias": vida_util_dias,
            "funcoes_aplicaveis": funcoes_aplicaveis,
        },
    }


def _perfil_com_qsms() -> dict:
    return {"categorias_indireto": [{"codigo": "QSMS", "descricao": "QSMS"}]}


class TestWiringSkill06RosterMo:
    def test_sem_roster_mo_usa_headcount_agregado(self):
        equipes = [
            EquipeDireta(
                item_id="eap-1", custo_total=0.0, funcoes=[FuncaoEquipeDireta(funcao_id="MO-ARMADOR", num_pessoas=1)]
            )
        ]
        can = _make_canonical(equipes)
        catalogo = {"insumos": [_insumo("EPI-CAPACETE-3M", "MATERIAL", 360.0, 360)]}
        result = run_custos_indiretos(can, {}, catalogo, _perfil_com_qsms())
        qsms = next(i for i in result.canonical.indiretos if i.categoria == "QSMS")
        assert qsms.funcoes == [] or all(f.quantidade == 1 for f in qsms.funcoes)

    def test_com_roster_mo_cobrindo_funcao_usa_contagem_real(self):
        equipes = [
            EquipeDireta(
                item_id="eap-1", custo_total=0.0, funcoes=[FuncaoEquipeDireta(funcao_id="MO-ARMADOR", num_pessoas=1)]
            )
        ]
        can = _make_canonical(equipes)
        catalogo = {"insumos": [_insumo("EPI-CAPACETE-3M", "MATERIAL", 360.0, 360)]}
        roster_mo = [
            {
                "individuo_id": "mo-001",
                "funcao_id": "MO-ARMADOR",
                "salario_base_mensal": 3000.0,
                "data_admissao": "2026-01-01",
            },
            {
                "individuo_id": "mo-002",
                "funcao_id": "MO-ARMADOR",
                "salario_base_mensal": 3000.0,
                "data_admissao": "2026-01-01",
            },
        ]
        sem_roster = run_custos_indiretos(can, {}, catalogo, _perfil_com_qsms())
        com_roster = run_custos_indiretos(can, {"roster_mo": roster_mo}, catalogo, _perfil_com_qsms())

        qsms_sem = next(i for i in sem_roster.canonical.indiretos if i.categoria == "QSMS")
        qsms_com = next(i for i in com_roster.canonical.indiretos if i.categoria == "QSMS")
        # Roster tem 2 indivíduos reais vs. 1 no headcount agregado -> custo QSMS dobra
        assert qsms_com.custo_total == qsms_sem.custo_total * 2
