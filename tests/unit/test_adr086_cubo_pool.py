"""ADR-086: Cubo de Pool Instancial — exploração honesta da decomposição de pool.

Cobre:
  A. Modelo CelulaPoolInstancial / CuboPoolInstancial (slice, group_by, projeções físicas)
  B. Builder + invariantes H1 (soma) / H3 (off zero)
  C. As 7 faces (físicas + causais + estruturais) + narração + separação física/causal (H4)
  D. Honestidade: off não faturado, idle com MO integral, economia com baseline autônomo
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from concilium.application.services.cubo_pool_projection import (
    cubo_pool_projection_contract,
    resolve_cubo_pool_projection,
)
from concilium.domain.models.cubo_pool import CelulaPoolInstancial
from concilium.domain.services.cubo_pool_builder import (
    CuboPoolInstancialBuilder,
    validar_invariantes_cubo_pool,
)

_ROOT = Path(__file__).resolve().parents[2]
_HELPERS_A = _ROOT / "src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers_a.py"


def _load_helpers_a():
    spec = importlib.util.spec_from_file_location("_skill_helpers_a_086", _HELPERS_A)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mk_sched(item_id, weeks):
    from concilium.domain.models.canonical import DistribuicaoSemanal, ScheduledActivityCanonical

    dist = {
        w: DistribuicaoSemanal(
            num_equipes=1,
            qtd_executada=10.0,
            qtd_acumulada=10.0,
            pct=1.0,
            eficiencia=1.0,
            fator_clima=1.0,
            fator_calendario=1.0,
        )
        for w in weeks
    }
    return ScheduledActivityCanonical(
        activity_id=item_id, start_week=0, end_week=len(weeks), duration_weeks=len(weeks), distribuicao_semanal=dist
    )


def _mk_equipe(item_id, mo, eq, comb, mat, custo_total):
    from concilium.domain.models.canonical import EquipeDireta

    return EquipeDireta(
        equipe_id=f"eq-{item_id}",
        item_id=item_id,
        cpu_id="CPU-X",
        custo_mao_obra_mensal=mo,
        custo_equipamentos_mensal=eq,
        custo_combustivel_total_mensal=comb,
        custo_material_mensal=mat,
        custo_fixo_mensal=mo + eq + mat,
        custo_total=custo_total,
    )


def _build_pool(weeks_b, mo=200.0, remob=(20000.0, 10000.0)):
    """Constrói contratos+instancias para 2 atividades do mesmo tipo (pool=1)."""
    mod = _load_helpers_a()
    weeks_a = [f"S{n:03d}" for n in range(1, 11)]
    base = mo + 3000.0 + 1500.0 + 500.0
    equipes = [
        _mk_equipe("eap-A", mo, 3000.0, 1500.0, 500.0, base * 10),
        _mk_equipe("eap-B", mo, 3000.0, 1500.0, 500.0, base * len(weeks_b)),
    ]
    sched = {"eap-A": _mk_sched("eap-A", weeks_a), "eap-B": _mk_sched("eap-B", weeks_b)}
    rcpsp = {
        "resource_pool": {"ESC": 1},
        "activities": [
            {"item_id": "eap-A", "required_resources": {"ESC": 1}},
            {"item_id": "eap-B", "required_resources": {"ESC": 1}},
        ],
        "resource_costs": {
            "ESC": {
                "custo_mob_unit": remob[0],
                "custo_demob_unit": remob[1],
                "custo_idle_semanal_unit": 2000.0,
                "unidade_faturamento": "dia_cal",
            }
        },
    }
    val = []
    contratos, atrib, cadeias = mod._build_contratos_recurso(equipes, rcpsp, sched, val)
    for eq in equipes:
        if eq.item_id in atrib:
            eq.custo_total_autonomo = eq.custo_total
            eq.custo_total = atrib[eq.item_id][0]
    instancias, _comp, _res = mod._build_instancias_recurso(contratos, rcpsp, sched, val)
    mod._aplicar_custo_instancial_adr085(contratos, instancias, equipes, val)
    canonical = SimpleNamespace(
        projeto=SimpleNamespace(nome="TEST-POOL"),
        contratos_recurso=contratos,
        instancias_recurso=instancias,
        cadeias_perpetuacao=cadeias,
    )
    return canonical, contratos, instancias


# ── A. Modelo ───────────────────────────────────────────────────────────────


def test_celula_custo_total_e_id():
    c = CelulaPoolInstancial(
        contrato_id="c",
        tipo_id="ESC",
        instancia_numero=3,
        semana_iso="S005",
        estado="prod",
        atividade_id="a",
        custo_mo=100,
        custo_eq=40,
        custo_comb=20,
        custo_mat=10,
    )
    assert c.custo_total == 170.0
    assert c.instancia_id == "ESC-03"


def test_cubo_slice_group_by():
    cubo, _, _ = _build_pool([f"S{n:03d}" for n in range(13, 19)])
    cubo_obj = CuboPoolInstancialBuilder().build(cubo)
    prod = cubo_obj.slice(estado="prod")
    assert all(c.estado == "prod" for c in prod.celulas)
    g = cubo_obj.group_by("estado", measure="semanas")
    assert sum(g.values()) == len(cubo_obj.celulas)


# ── B. Builder + invariantes ──────────────────────────────────────────────────


def test_builder_h1_soma_reconcilia():
    """H1: Σ custo das células == Σ custo_total_contrato."""
    canonical, contratos, _ = _build_pool([f"S{n:03d}" for n in range(13, 19)])
    cubo = CuboPoolInstancialBuilder().build(canonical)
    soma_contratos = sum(c.custo_total_contrato for c in contratos)
    assert cubo.custo_total == pytest.approx(soma_contratos, abs=1.0)
    assert validar_invariantes_cubo_pool(cubo, contratos) == []


def test_builder_h3_off_zero():
    """H3: células off têm custo zero; H2: cobertura total do span.

    MO pesada + remob barato → gap longo é liberado (off), não mantido idle.
    """
    canonical, contratos, _ = _build_pool([f"S{n:03d}" for n in range(20, 26)], mo=8000.0, remob=(5000.0, 2500.0))
    cubo = CuboPoolInstancialBuilder().build(canonical)
    off = [c for c in cubo.celulas if c.estado == "off"]
    assert off, "esperava semanas off com gap longo e MO pesada"
    assert all(c.custo_total == 0.0 for c in off)


def test_idle_mantem_mo_zera_comb():
    """Honestidade: idle cobra MO integral + EQ reduzida, comb/mat zero."""
    canonical, _, _ = _build_pool([f"S{n:03d}" for n in range(13, 19)])  # gap curto barato → idle
    cubo = CuboPoolInstancialBuilder().build(canonical)
    idle = [c for c in cubo.celulas if c.estado == "idle"]
    assert idle, "esperava semanas idle com gap curto e MO barata"
    assert all(c.custo_comb == 0.0 and c.custo_mat == 0.0 for c in idle)
    assert any(c.custo_mo > 0.0 for c in idle)


# ── C. Faces ──────────────────────────────────────────────────────────────────


def test_contrato_lista_7_faces():
    contract = cubo_pool_projection_contract()
    assert set(contract["faces"]) == {
        "utilizacao_temporal",
        "custo_estado_componente",
        "instancia_ciclo_vida",
        "atividade_instancia",
        "causa_custo",
        "economia_pool",
        "cadeia_perpetuacao",
    }


@pytest.mark.parametrize(
    "face",
    [
        "utilizacao_temporal",
        "custo_estado_componente",
        "instancia_ciclo_vida",
        "atividade_instancia",
        "causa_custo",
        "economia_pool",
        "cadeia_perpetuacao",
    ],
)
def test_face_retorna_contrato_projecao(face):
    canonical, _, _ = _build_pool([f"S{n:03d}" for n in range(13, 19)])
    proj = resolve_cubo_pool_projection(canonical, face=face, granularidade="mes")
    assert proj["face"] == face
    assert "columns" in proj and "rows" in proj
    assert isinstance(proj["narrativa"], list) and proj["narrativa"], "faces devem narrar"
    assert proj["invariantes_ok"] is True
    assert "natureza" in proj


def test_ciclo_vida_narra_mob_e_custo():
    canonical, _, _ = _build_pool([f"S{n:03d}" for n in range(13, 19)])
    proj = resolve_cubo_pool_projection(canonical, face="instancia_ciclo_vida")
    txt = " ".join(proj["narrativa"]).lower()
    assert "mobilizada" in txt and ("mo " in txt or "integral" in txt)


def test_economia_pool_cita_baseline_autonomo():
    """H4: economia sempre apresentada contra baseline autônomo explícito."""
    canonical, _, _ = _build_pool([f"S{n:03d}" for n in range(20, 26)])
    proj = resolve_cubo_pool_projection(canonical, face="economia_pool")
    assert any("autônomo" in n.lower() or "autonomo" in n.lower() for n in proj["narrativa"])
    assert "economia_total" in proj["operator_meta"]
    for r in proj["rows"]:
        assert "custo_autonomo" in r and "custo_instancial" in r


def test_atividade_instancia_so_fisica_sem_imputacao():
    """H4: face física não imputa idle/mob a atividades (só semanas produtivas)."""
    canonical, _, _ = _build_pool([f"S{n:03d}" for n in range(13, 19)])
    proj = resolve_cubo_pool_projection(canonical, face="atividade_instancia")
    # machine_weeks somados == semanas produtivas totais do cubo
    cubo = CuboPoolInstancialBuilder().build(canonical)
    prod_w = cubo.semanas_por_estado()["prod"]
    assert sum(r["machine_weeks"] for r in proj["rows"]) == prod_w
