"""ADR-086: Cubo de Pool Instancial — exploração honesta da decomposição de pool.

Cobre:
  A. Modelo CelulaPoolInstancial / CuboPoolInstancial (slice, group_by, projeções físicas)
  B. Builder + invariantes H1 (soma) / H3 (off zero)
  C. As 7 faces (físicas + causais + estruturais) + narração + separação física/causal (H4)
    D. Honestidade: off não faturado, idle com MO integral, economia com baseline homogênea
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from concilium.application.services.analytics.cubo_pool_projection import (
    cubo_pool_projection_contract,
    resolve_cubo_pool_projection,
)
from concilium.domain.models.analytics.cubo_pool import CelulaPoolInstancial
from concilium.domain.services.analytics.cubo_pool_builder import (
    CuboPoolInstancialBuilder,
    validar_invariantes_cubo_pool,
)

_ROOT = Path(__file__).resolve().parents[2]
_HELPERS_A = (
    _ROOT / "src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers/__init__.py"
)


def _load_helpers_a():
    import sys

    spec = importlib.util.spec_from_file_location("_skill_helpers_a_086", _HELPERS_A)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_skill_helpers_a_086"] = mod
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
    mod._aplicar_custo_instancial(contratos, instancias, equipes, val)
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
    """H1: Σ custo das células (prod/idle/off) == custo_total_contrato − (mob + demob).

    ADR-136 F3: mob/demob são custo de evento (entrada/saída do pool), sem célula
    própria no cubo — cada célula representa uma semana física do ciclo de vida.
    """
    canonical, contratos, instancias = _build_pool([f"S{n:03d}" for n in range(13, 19)])
    cubo = CuboPoolInstancialBuilder().build(canonical)
    soma_contratos = sum(c.custo_total_contrato for c in contratos)
    mob_demob_total = sum(i.custo_mob_instancia + i.custo_demob_instancia for i in instancias)
    assert mob_demob_total > 0  # fixture usa resource_costs com custo_mob_unit/custo_demob_unit
    assert cubo.custo_total == pytest.approx(soma_contratos - mob_demob_total, abs=1.0)
    assert validar_invariantes_cubo_pool(cubo, contratos, instancias) == []


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


def test_economia_pool_cita_baseline_homogenea():
    """H4: economia sempre apresentada contra baseline homogênea explícita."""
    canonical, _, _ = _build_pool([f"S{n:03d}" for n in range(20, 26)])
    canonical.planejamento = [
        SimpleNamespace(item_id="eap-A", subtotal=SimpleNamespace(sem_bdi=SimpleNamespace(total=320.0))),
        SimpleNamespace(item_id="eap-B", subtotal=SimpleNamespace(sem_bdi=SimpleNamespace(total=480.0))),
    ]
    proj = resolve_cubo_pool_projection(canonical, face="economia_pool")
    assert any("baseline homogênea" in n.lower() for n in proj["narrativa"])
    assert "economia_total" in proj["operator_meta"]
    for r in proj["rows"]:
        assert "custo_autonomo" in r and "custo_instancial" in r


def test_economia_pool_fallback_operacional_expande_por_frentes():
    canonical, _, _ = _build_pool([f"S{n:03d}" for n in range(20, 26)])
    canonical.equipes_diretas = [
        SimpleNamespace(item_id="eap-A", custo_total_autonomo=100.0, num_equipes_base=3),
        SimpleNamespace(item_id="eap-B", custo_total_autonomo=200.0, num_equipes_base=2),
    ]
    proj = resolve_cubo_pool_projection(canonical, face="economia_pool")
    rows = {r["atividade_id"]: r for r in proj["rows"]}
    assert rows["eap-A"]["custo_autonomo"] == pytest.approx(300.0)
    assert rows["eap-B"]["custo_autonomo"] == pytest.approx(400.0)


def test_economia_pool_prefere_planejamento_sem_bdi_quando_disponivel():
    canonical, _, _ = _build_pool([f"S{n:03d}" for n in range(20, 26)])
    canonical.planejamento = [
        SimpleNamespace(item_id="eap-A", subtotal=SimpleNamespace(sem_bdi=SimpleNamespace(total=900.0))),
        SimpleNamespace(item_id="eap-B", subtotal=SimpleNamespace(sem_bdi=SimpleNamespace(total=700.0))),
    ]
    canonical.equipes_diretas = [
        SimpleNamespace(item_id="eap-A", custo_total_autonomo=100.0, num_equipes_base=3),
        SimpleNamespace(item_id="eap-B", custo_total_autonomo=200.0, num_equipes_base=2),
    ]
    proj = resolve_cubo_pool_projection(canonical, face="economia_pool")
    rows = {r["atividade_id"]: r for r in proj["rows"]}
    assert rows["eap-A"]["custo_autonomo"] == pytest.approx(900.0)
    assert rows["eap-B"]["custo_autonomo"] == pytest.approx(700.0)
    assert rows["eap-A"]["baseline_source"] == "planejamento_sem_bdi"


def test_utilizacao_temporal_explica_eventos_mob_demob():
    canonical, _, _ = _build_pool([f"S{n:03d}" for n in range(20, 26)])
    proj = resolve_cubo_pool_projection(canonical, face="utilizacao_temporal", granularidade="semana")
    assert any("mob" in r and "demob" in r for r in proj["rows"])
    assert sum(int(r.get("mob", 0) or 0) for r in proj["rows"]) > 0
    assert sum(int(r.get("demob", 0) or 0) for r in proj["rows"]) > 0


def test_atividade_instancia_so_fisica_sem_imputacao():
    """H4: face física não imputa idle/mob a atividades (só semanas produtivas)."""
    canonical, _, _ = _build_pool([f"S{n:03d}" for n in range(13, 19)])
    proj = resolve_cubo_pool_projection(canonical, face="atividade_instancia")
    # machine_weeks somados == semanas produtivas totais do cubo
    cubo = CuboPoolInstancialBuilder().build(canonical)
    prod_w = cubo.semanas_por_estado()["prod"]
    assert sum(r["machine_weeks"] for r in proj["rows"]) == prod_w


# ─── Missing branch coverage ──────────────────────────────────────────────────


def test_unknown_face_falls_back_to_ciclo_vida():
    """Line 183: unknown face name defaults to instancia_ciclo_vida."""
    canonical, _, _ = _build_pool(["W01", "W02"])
    proj = resolve_cubo_pool_projection(canonical, face="face_que_nao_existe")
    assert proj["face"] == "instancia_ciclo_vida"


def test_filter_by_atividade_id():
    """Lines 192-196: atividade_id filter slices the cubo."""
    canonical, _, _ = _build_pool(["W01", "W02", "W03"])
    proj = resolve_cubo_pool_projection(canonical, face="atividade_instancia", atividade_id="eap-A")
    assert all(r["atividade_id"] == "eap-A" for r in proj["rows"])


def test_filter_by_instancia_id():
    """Lines 192-196: instancia_id with dash triggers tipo/num parsing."""
    canonical, _, _ = _build_pool(["W01", "W02"])
    # instancia_id "ESC-1" should parse tipo="ESC", num=1
    proj = resolve_cubo_pool_projection(canonical, face="instancia_ciclo_vida", instancia_id="ESC-1")
    assert proj is not None  # no exception


def test_filter_by_instancia_id_no_dash():
    """Lines 192-196: instancia_id without dash → tipo=None, inst_num=None."""
    canonical, _, _ = _build_pool(["W01", "W02"])
    proj = resolve_cubo_pool_projection(canonical, face="instancia_ciclo_vida", instancia_id="NOHYPHEN")
    assert proj is not None


def test_truncation_when_rows_exceed_top_n():
    """Lines 228-230: operator_meta.truncado = True when rows > top_n."""
    canonical, _, _ = _build_pool([f"W{n:02d}" for n in range(1, 10)])
    # economia_pool has 2 rows (eap-A + eap-B), so top_n=1 triggers truncation
    proj = resolve_cubo_pool_projection(canonical, face="economia_pool", top_n=1)
    assert proj["operator_meta"].get("truncado") is True
    assert len(proj["rows"]) == 1


def test_autonomo_total_zero_when_custo_zero():
    """Line 87: _autonomo_total_por_item returns 0.0 when custo_total_autonomo == 0."""
    from concilium.application.services.analytics.cubo_pool_projection import _autonomo_total_por_item

    eq = SimpleNamespace(custo_total_autonomo=0.0, num_equipes_base=2)
    result = _autonomo_total_por_item(eq)
    assert result == 0.0


def test_baseline_skips_empty_item_id():
    """Line 105: item_id='' in planejamento is skipped (continue)."""
    from concilium.application.services.analytics.cubo_pool_projection import _baseline_homogenea_por_item

    empty_plan = SimpleNamespace(item_id="", subtotal=SimpleNamespace(sem_bdi=SimpleNamespace(total=500.0)))
    canonical = SimpleNamespace(planejamento=[empty_plan], equipes_diretas=[])
    baseline, _ = _baseline_homogenea_por_item(canonical)
    assert "" not in baseline


def test_economia_pool_sem_baseline_triggers_warning():
    """Line 492, 545: atividade without baseline emits warning narrative."""
    from unittest.mock import MagicMock

    from concilium.application.services.analytics.cubo_pool_projection import _face_economia_pool

    # Create a mock cubo and partition with custo_total_autonomo=0 → aut=0
    mock_cubo = MagicMock()
    mock_cubo.custo_total = 5000.0
    mock_cubo.custo_por_estado.return_value = {}
    mock_cubo.custo_por_componente.return_value = {}

    mock_p = MagicMock()
    mock_p.item_id = "A1"
    mock_p.custo_total_autonomo = 0.0
    mock_p.custo_total_particionado = 1000.0
    mock_p.custo_produtivo_exclusivo = 1000.0
    mock_p.custo_produtivo_compartilhado = 0.0
    mock_p.custo_ocioso_imputado = 0.0
    mock_p.custo_mob_imputado = 0.0
    mock_p.custo_demob_imputado = 0.0

    mock_c = MagicMock()
    mock_c.particao_por_item = [mock_p]
    contratos = [mock_c]

    columns, rows, narrativa, _ = _face_economia_pool(
        mock_cubo, contratos, [], baseline_por_item={}, baseline_source_by_item={}
    )
    assert any("sem baseline" in n for n in narrativa)


def test_baseline_skips_planejamento_with_nonpositive_total():
    """Line 124 false branch: planejamento total <= 0.0 is not added to baseline."""
    from concilium.application.services.analytics.cubo_pool_projection import _baseline_homogenea_por_item

    zero_plan = SimpleNamespace(item_id="eap-Z", subtotal=SimpleNamespace(sem_bdi=SimpleNamespace(total=0.0)))
    canonical = SimpleNamespace(planejamento=[zero_plan], equipes_diretas=[])
    baseline, source = _baseline_homogenea_por_item(canonical)
    assert "eap-Z" not in baseline
    assert "eap-Z" not in source


def test_baseline_skips_equipe_fallback_with_zero_custo():
    """Line 133 false branch: operational fallback total <= 0.0 is not added."""
    from concilium.application.services.analytics.cubo_pool_projection import _baseline_homogenea_por_item

    eq = SimpleNamespace(item_id="eap-Y", custo_total_autonomo=0.0, num_equipes_base=1)
    canonical = SimpleNamespace(planejamento=[], equipes_diretas=[eq])
    baseline, source = _baseline_homogenea_por_item(canonical)
    assert "eap-Y" not in baseline
    assert "eap-Y" not in source


def test_count_mob_demob_bucket_empty_week_label():
    """Line 146-147: empty week label bucket resolves to ''."""
    from unittest.mock import MagicMock

    from concilium.application.services.analytics.cubo_pool_projection import _count_mob_demob_por_periodo

    mock_cubo = MagicMock()
    mock_cubo.ciclo_vida_instancias.return_value = {"inst-1": {"semana_mob": "", "semana_demob": ""}}
    counts = _count_mob_demob_por_periodo(mock_cubo, "semana")
    # Neither mob nor demob bucket recorded since both labels are empty.
    assert counts == {}


def test_count_mob_demob_bucket_without_dash_w_returns_raw():
    """Line 148-150: week label without '-W' returns the raw text as bucket."""
    from unittest.mock import MagicMock

    from concilium.application.services.analytics.cubo_pool_projection import _count_mob_demob_por_periodo

    mock_cubo = MagicMock()
    mock_cubo.ciclo_vida_instancias.return_value = {"inst-1": {"semana_mob": "FASE-1", "semana_demob": ""}}
    counts = _count_mob_demob_por_periodo(mock_cubo, "semana")
    assert "FASE-1" in counts
    assert counts["FASE-1"]["mob"] == 1


def test_count_mob_demob_bucket_with_dash_w_calls_bucket_from_week_iso():
    """Line 150: a week label containing '-W' (ISO week format) is bucketed via
    bucket_from_week_iso instead of being returned raw."""
    from unittest.mock import MagicMock

    from concilium.application.services.analytics.cubo_pool_projection import _count_mob_demob_por_periodo

    mock_cubo = MagicMock()
    mock_cubo.ciclo_vida_instancias.return_value = {"inst-1": {"semana_mob": "2026-W23", "semana_demob": ""}}
    counts = _count_mob_demob_por_periodo(mock_cubo, "mes")
    # bucket_from_week_iso("2026-W23", "mes") collapses the ISO week into a month bucket,
    # which differs from the raw "2026-W23" string.
    assert "2026-W23" not in counts
    assert sum(v["mob"] for v in counts.values()) == 1


def test_count_mob_demob_only_demob_present():
    """Line 155->158 false (no semana_mob) then line 158 true (semana_demob present)."""
    from unittest.mock import MagicMock

    from concilium.application.services.analytics.cubo_pool_projection import _count_mob_demob_por_periodo

    mock_cubo = MagicMock()
    mock_cubo.ciclo_vida_instancias.return_value = {"inst-1": {"semana_mob": "", "semana_demob": "FASE-2"}}
    counts = _count_mob_demob_por_periodo(mock_cubo, "semana")
    assert counts["FASE-2"]["demob"] == 1
    assert counts["FASE-2"]["mob"] == 0


def test_utilizacao_temporal_off_weeks_add_honesty_narrative():
    """Line 321-322: sem['off'] truthy adds the 'não representa desmobilização' narrative."""
    canonical, contratos, _ = _build_pool([f"S{n:03d}" for n in range(20, 26)], mo=8000.0, remob=(5000.0, 2500.0))
    proj = resolve_cubo_pool_projection(canonical, face="utilizacao_temporal", granularidade="semana")
    assert any("Desmobilizado (off)" in n for n in proj["narrativa"])
