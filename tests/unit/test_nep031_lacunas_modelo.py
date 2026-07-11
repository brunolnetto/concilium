"""Testes de validação para as lacunas identificadas na NEP-031.

Cobre:
    L1 — rental_unit no cadastro de equipamentos
    L2 — custo de equipamento ocioso dentro da janela de mobilização
    L3 — custo de mob/desmob por evento de transição
    L4 — relações de precedência SS/FF com lag no DAG
    L5 — validação VAL-PLAN-ENCARGOS-DUPLA
    L6 — equivalência da fórmula de ramp-up (teste de sanidade)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── loaders de helpers (manifests têm dashes no nome de diretório) ────────────
_MANIFESTS = Path(__file__).resolve().parents[2] / "src" / "concilium" / "application" / "skills" / "manifests"


def _load_mod(skill_dir: str, mod_name: str):
    """Carrega módulo de helper de um manifest por caminho de arquivo."""
    key = f"_nep031_test_{skill_dir}_{mod_name}"
    if key in sys.modules:
        return sys.modules[key]
    path = _MANIFESTS / skill_dir / f"{mod_name}.py"
    if not path.exists():
        path = _MANIFESTS / skill_dir / mod_name / "__init__.py"
    spec = importlib.util.spec_from_file_location(key, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


def _h05():
    return _load_mod("05-equipes-e-alocacao", "_skill_helpers")


def _h06():
    # NEP-041 F4: precificação agora vive no sub-pacote da skill unificada
    return _load_mod("06-resultado-financeiro/_precificacao", "_skill_helpers")


def _s01():
    return _load_mod("01-escopo-e-eap", "skill")


# ── helpers de teste ──────────────────────────────────────────────────────────


def _make_cron(seq: list[int]):
    """Cria objeto de cronograma mock com distribuicao_semanal."""
    periodos = {}
    for i, n in enumerate(seq):
        d = MagicMock()
        d.num_equipes = n
        d.eficiencia = 1.0
        periodos[f"2026-W{i + 1:02d}"] = d
    cron = MagicMock()
    cron.distribuicao_semanal = periodos
    return cron


# ── L1: rental_unit ───────────────────────────────────────────────────────────


def test_l1_rental_unit_hora_produtiva():
    """Equipamento com rental_unit=hora_produtiva: preco × horas_mes."""
    h = _h05()
    insumo = {
        "codigo": "EQ-HORA",
        "preco_unitario": 100.0,
        "unidade": "h",
        "atributos_especificos": {"rental_unit": "hora_produtiva"},
    }
    result = h._converter_preco_equip(insumo, 8.0, 26.0)
    assert result == pytest.approx(100.0 * 8.0 * 26.0, rel=1e-3)


def test_l1_rental_unit_dia_calendario():
    """Equipamento com rental_unit=dia_calendario: preco × dias_uteis."""
    h = _h05()
    insumo = {
        "codigo": "EQ-DIA",
        "preco_unitario": 500.0,
        "unidade": "dia",
        "atributos_especificos": {"rental_unit": "dia_calendario"},
    }
    result = h._converter_preco_equip(insumo, 8.0, 26.0)
    assert result == pytest.approx(500.0 * 26.0, rel=1e-3)


def test_l1_rental_unit_mes():
    """Equipamento com rental_unit=mes: preco já é mensal."""
    h = _h05()
    insumo = {
        "codigo": "EQ-MES",
        "preco_unitario": 8000.0,
        "unidade": "mes",
        "atributos_especificos": {"rental_unit": "mes"},
    }
    result = h._converter_preco_equip(insumo, 8.0, 26.0)
    assert result == pytest.approx(8000.0, rel=1e-3)


def test_l1_dia_maior_que_hora():
    """dia_calendario com mesmo valor absoluto deve custar menos por hora que hora_produtiva."""
    h = _h05()
    base_price = 100.0
    horas_dia, dias_uteis = 8.0, 26.0

    eq_hora = {
        "codigo": "H",
        "preco_unitario": base_price,
        "unidade": "h",
        "atributos_especificos": {"rental_unit": "hora_produtiva"},
    }
    eq_dia = {
        "codigo": "D",
        "preco_unitario": base_price,
        "unidade": "dia",
        "atributos_especificos": {"rental_unit": "dia_calendario"},
    }
    eq_mes = {
        "codigo": "M",
        "preco_unitario": base_price,
        "unidade": "mes",
        "atributos_especificos": {"rental_unit": "mes"},
    }

    custo_hora = h._converter_preco_equip(eq_hora, horas_dia, dias_uteis)
    custo_dia = h._converter_preco_equip(eq_dia, horas_dia, dias_uteis)
    custo_mes = h._converter_preco_equip(eq_mes, horas_dia, dias_uteis)

    # hora_produtiva × 208 > dia × 26 > mes × 1 (para mesmo valor base)
    assert custo_hora > custo_dia > custo_mes


def test_l1_rental_unit_propagado_para_modelo():
    """rental_unit do insumo é propagado para EquipamentoEquipeDireta.rental_unit."""
    h = _h05()
    insumo = {
        "codigo": "EQ-MENSAL",
        "descricao": "Guindaste mensal",
        "preco_unitario": 15000.0,
        "unidade": "mes",
        "atributos_especificos": {"rental_unit": "mes"},
    }
    eq_obj, _ = h._calcular_custo_equipamento(
        insumo=insumo, num_unidades=1, horas_dia=8.0, dias_uteis=26.0, preco_diesel=6.0
    )
    assert eq_obj.rental_unit == "mes"
    assert eq_obj.custo_mensal == pytest.approx(15000.0, rel=1e-3)


# ── L2: equipamento ocioso ───────────────────────────────────────────────────


def test_l2_sem_ociosidade():
    """Sem semanas ociosas dentro da janela → custo_ocioso = 0."""
    h = _h05()
    cron = _make_cron([2, 2, 2, 2])
    *_, custo_ocioso = h._calc_custo_cron(cron, 5000.0, 2000.0, 500.0)
    assert custo_ocioso == 0.0


def test_l2_gap_interno_gera_custo_ocioso():
    """Semana ociosa dentro da janela [primeiro_ativo, último_ativo] gera custo."""
    from concilium.domain.constants import SEMANAS_POR_MES

    h = _h05()
    cron = _make_cron([2, 0, 2])  # gap na semana do meio
    custo_eq = 3000.0
    *_, custo_ocioso = h._calc_custo_cron(cron, 5000.0, custo_eq, 500.0)
    assert custo_ocioso == pytest.approx(custo_eq / SEMANAS_POR_MES, rel=1e-3)


def test_l2_semanas_apos_ultimo_ativo_nao_custam():
    """Semanas inteiramente APÓS o último ativo não geram custo de ociosidade."""
    h = _h05()
    cron = _make_cron([3, 2, 1, 0, 0])  # ramp-down + 2 semanas sem atividade
    *_, custo_ocioso = h._calc_custo_cron(cron, 5000.0, 2000.0, 500.0)
    assert custo_ocioso == 0.0


def test_l2_multiplos_gaps_acumulam():
    """Dois gaps internos geram duas unidades de custo ocioso."""
    from concilium.domain.constants import SEMANAS_POR_MES

    h = _h05()
    cron = _make_cron([1, 0, 1, 0, 1])  # dois gaps internos
    custo_eq = 4000.0
    *_, custo_ocioso = h._calc_custo_cron(cron, 5000.0, custo_eq, 500.0)
    assert custo_ocioso == pytest.approx(2 * custo_eq / SEMANAS_POR_MES, rel=1e-3)


# ── L3: mob/desmob por evento ────────────────────────────────────────────────


def test_l3_sem_custo_definido_retorna_zero():
    """Sem custo_mobilizacao definido na composição → custo = 0."""
    h = _h05()
    comp = {"funcoes": [{"funcao_id": "P0001", "num_pessoas": 2}], "equipamentos": []}
    cron = _make_cron([0, 1, 1, 0])
    assert h._calc_custo_mob_desmob(comp, cron) == 0.0


def test_l3_um_ciclo_mob_desmob():
    """Um ciclo: 1 mobilização + 1 desmobilização ao final."""
    h = _h05()
    comp = {
        "funcoes": [
            {"funcao_id": "P0001", "num_pessoas": 1, "custo_mobilizacao": 1000.0, "custo_desmobilizacao": 500.0}
        ],
        "equipamentos": [],
    }
    custo = h._calc_custo_mob_desmob(comp, _make_cron([0, 1, 1]))
    assert custo == pytest.approx(1500.0, rel=1e-4)  # 1×1000 + 1×500


def test_l3_dois_ciclos_custam_mais():
    """Atividade com gap: 2 ciclos custam mais que 1 ciclo contínuo."""
    h = _h05()
    comp = {
        "funcoes": [],
        "equipamentos": [
            {"equip_id": "EQ-01", "num_unidades": 1, "custo_mobilizacao": 2000.0, "custo_desmobilizacao": 2000.0}
        ],
    }
    custo_com_gap = h._calc_custo_mob_desmob(comp, _make_cron([1, 0, 1]))
    custo_sem_gap = h._calc_custo_mob_desmob(comp, _make_cron([1, 1, 1]))
    assert custo_com_gap == pytest.approx(8000.0, rel=1e-4)  # 2×mob + 2×desmob
    assert custo_sem_gap == pytest.approx(4000.0, rel=1e-4)  # 1×mob + 1×desmob
    assert custo_com_gap > custo_sem_gap


def test_l3_proporcional_num_pessoas():
    """Custo de mobilização escala com num_pessoas."""
    h = _h05()
    comp = {
        "funcoes": [
            {"funcao_id": "P0032", "num_pessoas": 7, "custo_mobilizacao": 300.0, "custo_desmobilizacao": 150.0}
        ],
        "equipamentos": [],
    }
    custo = h._calc_custo_mob_desmob(comp, _make_cron([0, 7, 7]))
    assert custo == pytest.approx(300.0 * 7 + 150.0 * 7, rel=1e-4)  # 3150


# ── L3-bis (ADR-106 F2-bis): split mob vs. demob para diretos sem pool ────────


def test_l3bis_split_um_ciclo():
    """Um ciclo: mob e demob retornados separadamente, somando ao agregado."""
    h = _h05()
    comp = {
        "funcoes": [
            {"funcao_id": "P0001", "num_pessoas": 1, "custo_mobilizacao": 1000.0, "custo_desmobilizacao": 500.0}
        ],
        "equipamentos": [],
    }
    cron = _make_cron([0, 1, 1])
    custo_mob, custo_demob = h._calc_custo_mob_desmob_split(comp, cron)
    assert custo_mob == pytest.approx(1000.0, rel=1e-4)
    assert custo_demob == pytest.approx(500.0, rel=1e-4)
    assert custo_mob + custo_demob == pytest.approx(h._calc_custo_mob_desmob(comp, cron), rel=1e-4)


def test_l3bis_dois_ciclos_dobra_ambos():
    """Dois ciclos (gap interno): mob e demob dobram igualmente."""
    h = _h05()
    comp = {
        "funcoes": [],
        "equipamentos": [
            {"equip_id": "EQ-01", "num_unidades": 1, "custo_mobilizacao": 2000.0, "custo_desmobilizacao": 2000.0}
        ],
    }
    custo_mob, custo_demob = h._calc_custo_mob_desmob_split(comp, _make_cron([1, 0, 1]))
    assert custo_mob == pytest.approx(4000.0, rel=1e-4)  # 2× mob
    assert custo_demob == pytest.approx(4000.0, rel=1e-4)  # 2× demob


def test_l3bis_sem_custo_retorna_zero_zero():
    h = _h05()
    comp = {"funcoes": [{"funcao_id": "P0001", "num_pessoas": 2}], "equipamentos": []}
    assert h._calc_custo_mob_desmob_split(comp, _make_cron([0, 1, 1, 0])) == (0.0, 0.0)


def test_l3bis_cron_none_retorna_zero_zero():
    h = _h05()
    assert h._calc_custo_mob_desmob_split({}, None) == (0.0, 0.0)


# ── L4: precedências SS/FF ───────────────────────────────────────────────────


def test_l4_precedencia_item_defaults():
    """PrecedenciaItem sem tipo/lag assume FS lag=0."""
    from concilium.domain.models.canonical import PrecedenciaItem

    p = PrecedenciaItem(item_id="eap-1")
    assert p.tipo == "FS"
    assert p.lag == 0


def test_l4_str_legado_normalizado_para_fs():
    """predecessores=[str] é convertido para PrecedenciaItem FS lag=0."""
    from concilium.domain.models.canonical import EapItem

    item = EapItem(
        item_id="B", ordem=2, cpu_id="CPU-X", descricao="B", unidade="m3", quantitativo=100.0, predecessores=["A"]
    )
    tipados = item.predecessores_tipados()
    assert len(tipados) == 1
    assert tipados[0].item_id == "A"
    assert tipados[0].tipo == "FS"
    assert tipados[0].lag == 0


def test_l4_ss_lag_2_start_offset():
    """SS lag=2: start(B) >= start(A) + 2 (sem a unidade de duração do FS)."""
    from concilium.domain.models.canonical import EapItem, PrecedenciaItem

    s01 = _s01()

    item_a = EapItem(item_id="A", ordem=1, cpu_id="C", descricao="A", unidade="m3", quantitativo=1.0)
    item_b = EapItem(
        item_id="B",
        ordem=2,
        cpu_id="C",
        descricao="B",
        unidade="m3",
        quantitativo=1.0,
        predecessores=[PrecedenciaItem(item_id="A", tipo="SS", lag=2)],
    )

    arestas = s01._build_dag_from_precedencias(["A", "B"], {"A", "B"}, [], [item_a, item_b], [])
    dag = s01._build_activity_dag(["A", "B"], arestas, ["A", "B"])

    assert dag.start_offset_min["B"] == 2


def test_l4_fs_lag_3_start_offset():
    """FS lag=3: start(B) >= start(A) + 1 + 3 = 4."""
    from concilium.domain.models.canonical import EapItem, PrecedenciaItem

    s01 = _s01()

    item_a = EapItem(item_id="A", ordem=1, cpu_id="C", descricao="A", unidade="m3", quantitativo=1.0)
    item_b = EapItem(
        item_id="B",
        ordem=2,
        cpu_id="C",
        descricao="B",
        unidade="m3",
        quantitativo=1.0,
        predecessores=[PrecedenciaItem(item_id="A", tipo="FS", lag=3)],
    )

    arestas = s01._build_dag_from_precedencias(["A", "B"], {"A", "B"}, [], [item_a, item_b], [])
    dag = s01._build_activity_dag(["A", "B"], arestas, ["A", "B"])
    assert dag.start_offset_min["B"] == 4


def test_l4_ss_lag_zero_inicio_simultâneo():
    """SS lag=0: B pode iniciar no mesmo instante que A."""
    from concilium.domain.models.canonical import EapItem, PrecedenciaItem

    s01 = _s01()

    item_a = EapItem(item_id="A", ordem=1, cpu_id="C", descricao="A", unidade="m3", quantitativo=1.0)
    item_b = EapItem(
        item_id="B",
        ordem=2,
        cpu_id="C",
        descricao="B",
        unidade="m3",
        quantitativo=1.0,
        predecessores=[PrecedenciaItem(item_id="A", tipo="SS", lag=0)],
    )

    arestas = s01._build_dag_from_precedencias(["A", "B"], {"A", "B"}, [], [item_a, item_b], [])
    dag = s01._build_activity_dag(["A", "B"], arestas, ["A", "B"])
    assert dag.start_offset_min["B"] == 0


def test_l4_aresta_tem_tipo_e_lag():
    """ArestaActivityDag preserva tipo e lag da precedência."""
    from concilium.domain.models.canonical import EapItem, PrecedenciaItem

    s01 = _s01()

    item_a = EapItem(item_id="A", ordem=1, cpu_id="C", descricao="A", unidade="m3", quantitativo=1.0)
    item_b = EapItem(
        item_id="B",
        ordem=2,
        cpu_id="C",
        descricao="B",
        unidade="m3",
        quantitativo=1.0,
        predecessores=[PrecedenciaItem(item_id="A", tipo="SS", lag=2)],
    )

    arestas = s01._build_dag_from_precedencias(["A", "B"], {"A", "B"}, [], [item_a, item_b], [])
    dag = s01._build_activity_dag(["A", "B"], arestas, ["A", "B"])

    aresta = next((a for a in dag.arestas if a.de == "A" and a.para == "B"), None)
    assert aresta is not None
    assert aresta.tipo == "SS"
    assert aresta.lag == 2


# ── L5: VAL-PLAN-ENCARGOS-DUPLA ──────────────────────────────────────────────


def test_l5_preco_alto_mo_dispara_aviso():
    """Insumo MAO_OBRA com preco > R$100/h dispara VAL-PLAN-ENCARGOS-DUPLA."""
    h = _h06()
    cpu = {
        "codigo": "CPU-TEST",
        "composicao_itens": [{"insumo_id": "MO-CARO", "categoria_custo": "MAO_OBRA", "coeficiente": 1.0}],
    }
    insumo_lookup = {"MO-CARO": {"codigo": "MO-CARO", "preco_unitario": 150.0, "unidade": "h"}}
    validacoes = []
    h._validate_encargos_separacao("CPU-TEST", cpu, insumo_lookup, validacoes)
    assert any(v.codigo == "VAL-PLAN-ENCARGOS-DUPLA" for v in validacoes)


def test_l5_preco_normal_nao_dispara():
    """Insumo MAO_OBRA com preco normal não dispara o aviso."""
    h = _h06()
    cpu = {
        "codigo": "CPU-NORMAL",
        "composicao_itens": [{"insumo_id": "MO-OK", "categoria_custo": "MAO_OBRA", "coeficiente": 1.0}],
    }
    insumo_lookup = {"MO-OK": {"codigo": "MO-OK", "preco_unitario": 20.0, "unidade": "h"}}
    validacoes = []
    h._validate_encargos_separacao("CPU-NORMAL", cpu, insumo_lookup, validacoes)
    assert not any(v.codigo == "VAL-PLAN-ENCARGOS-DUPLA" for v in validacoes)


def test_l5_diesel_e_material_nao_disparam():
    """Categorias diferentes de MAO_OBRA não disparam o aviso mesmo com preco alto."""
    h = _h06()
    cpu = {
        "codigo": "CPU-DIESEL",
        "composicao_itens": [
            {"insumo_id": "DIESEL", "categoria_custo": "DIESEL", "coeficiente": 1.0},
            {"insumo_id": "MAT", "categoria_custo": "MATERIAL", "coeficiente": 1.0},
        ],
    }
    insumo_lookup = {
        "DIESEL": {"preco_unitario": 999.0, "unidade": "h"},
        "MAT": {"preco_unitario": 999.0, "unidade": "h"},
    }
    validacoes = []
    h._validate_encargos_separacao("CPU-DIESEL", cpu, insumo_lookup, validacoes)
    assert not any(v.codigo == "VAL-PLAN-ENCARGOS-DUPLA" for v in validacoes)


# ── L6: fórmula de ramp-up ───────────────────────────────────────────────────


def test_l6_ramp_up_atinge_plateau():
    """A curva de ramp-up deve atingir n_maximo e mantê-lo no plateau."""
    from concilium.domain.models.planning.mobilizacao import MobilizacaoPolicy
    from concilium.domain.services.planning.mobilizacao_simulator import WorkforcePolicySimulator

    policy = MobilizacaoPolicy(
        n_inicial=1,
        n_maximo=4,
        taxa_mobilizacao=1.0,
        semanas_plateau=None,
    )
    sim = WorkforcePolicySimulator()
    curve = sim.simulate(
        policy=policy,
        atividade_id="test",
        quantitativo=50_000.0,  # grande o suficiente para ramp-up completo
        producao_horaria=10.0,
        dias_semana=6,
        horas_dia=8,
    )
    equipes = [s.num_equipes for s in curve.semanas]
    assert 4 in equipes  # atinge plateau
    assert max(equipes) == 4  # nunca ultrapassa m_max


def test_l6_ramp_up_monotone_crescente():
    """Durante o ramp-up, n(t) é monotonamente não-decrescente."""
    from concilium.domain.models.planning.mobilizacao import MobilizacaoPolicy
    from concilium.domain.services.planning.mobilizacao_simulator import WorkforcePolicySimulator

    policy = MobilizacaoPolicy(
        n_inicial=1,
        n_maximo=6,
        taxa_mobilizacao=1.5,
        semanas_plateau=None,
    )
    sim = WorkforcePolicySimulator()
    curve = sim.simulate(
        policy=policy,
        atividade_id="test",
        quantitativo=500.0,
        producao_horaria=8.0,
        dias_semana=6,
        horas_dia=8,
    )
    equipes = [s.num_equipes for s in curve.semanas]
    # Enquanto n < m_max, deve ser crescente
    for i in range(1, len(equipes)):
        if equipes[i - 1] < policy.n_maximo:
            assert equipes[i] >= equipes[i - 1], (
                f"Ramp-up não monotônico: equipes[{i - 1}]={equipes[i - 1]} > equipes[{i}]={equipes[i]}"
            )


def test_l6_parametrizacao_equivalente_ao_enunciado():
    """Parametrização com taxa=m_max/r reproduz curva similar à fórmula do enunciado.

    Enunciado: m_j = round(m_max × j/r) para j = 1…r
    Implementação: floor(n_inicial + t × taxa_mobilizacao) com taxa = m_max/r, n_inicial=1

    Os valores diferem em ±1 por semana, mas o total de semanas de ramp-up é o mesmo.
    """

    from concilium.domain.models.planning.mobilizacao import MobilizacaoPolicy
    from concilium.domain.services.planning.mobilizacao_simulator import WorkforcePolicySimulator

    m_max, r = 5, 5
    policy = MobilizacaoPolicy(
        n_inicial=1,
        n_maximo=m_max,
        taxa_mobilizacao=m_max / r,
        semanas_plateau=None,
    )
    sim = WorkforcePolicySimulator()

    # Valores reais gerados pela implementação
    ns_impl = [sim._compute_n(policy, t) for t in range(r + 2)]
    # Valores esperados pelo enunciado (j=1…r, mas indexado a partir de t=0 → t+1)
    ns_enun = [min(round(m_max * (t + 1) / r), m_max) for t in range(r + 2)]

    # Implementação não deve ultrapassar m_max
    assert all(n <= m_max for n in ns_impl)
    # Deve atingir m_max até t=r
    assert ns_impl[r] == m_max
    # Diferença máxima de 1 por semana (arredondamento floor vs round)
    for t in range(r):
        assert abs(ns_impl[t] - ns_enun[t]) <= 1, f"t={t}: impl={ns_impl[t]}, enun={ns_enun[t]} — diferença > 1"
