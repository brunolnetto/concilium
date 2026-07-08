"""ADR-084: Custo Particionado de Pool com Predecessão Parcial em DAG — Fase 3.

DoD Fase 3:
  - test_euler_interval_tres_atividades: regiões exclusivas e compartilhadas corretas
  - test_euler_interval_gap_imputado: gap entre atividades imputado ao sucessor crítico
  - test_dag_predecessor_critico: predecessor_critico_id da atividade mais longa
  - test_iter_intervals_polimorfismo: _iter_intervals aceita Interval, IntervalSet e vazio
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

# ---------------------------------------------------------------------------
# Carregamento dinâmico do módulo de helpers (diretório com hifens)
# ---------------------------------------------------------------------------

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_HELPERS_PATH = (
    _ROOT / "src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers_a/__init__.py"
)

sys.path.insert(0, str(_ROOT / "src"))

_spec = importlib.util.spec_from_file_location("_skill_helpers_a", _HELPERS_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["_skill_helpers_a"] = _mod
_spec.loader.exec_module(_mod)

particionar_contrato = _mod.particionar_contrato
_iter_intervals = _mod._iter_intervals
_EULE_AVAILABLE = _mod._EULE_AVAILABLE

pytestmark = pytest.mark.skipif(
    not _EULE_AVAILABLE,
    reason="eule[interval] não instalado — Fase 3 indisponível",
)


# ---------------------------------------------------------------------------
# Helpers de teste
# ---------------------------------------------------------------------------


def _run(items_raw, c_mob=0.0, c_demob=0.0, c_unit=1.0, qty=1, T0=None, T1=None):
    """Atalho: cria atribuicao={id: (0.0,...)} e cadeias=[] automaticamente."""
    atrib = {it["item_id"]: (0.0, "produtivo", it["T_end"] - it["T_start"]) for it in items_raw}
    t0 = T0 if T0 is not None else min(it["T_start"] for it in items_raw)
    t1 = T1 if T1 is not None else max(it["T_end"] for it in items_raw)
    return particionar_contrato(
        items_com_janela=items_raw,
        c_mob=c_mob,
        c_demob=c_demob,
        c_unit_semana=c_unit,
        quantidade_contratada=qty,
        T_contrato_start=t0,
        T_contrato_end=t1,
        atribuicao=atrib,
        cadeias=[],
    )


def _by_id(items):
    return {it.item_id: it for it in items}


# ---------------------------------------------------------------------------
# ADR-084 DoD Fase 3
# ---------------------------------------------------------------------------


class TestEulerIntervalTresAtividades:
    """Três atividades com sobreposicoes parciais — regiões exclusivas e compartilhadas."""

    def test_regioes_exclusivas_e_compartilhadas(self):
        """a1=[0,3.5), a2=[2.1,6.0), a3=[5.0,9.3) — sobreposicao a1∩a2 e a2∩a3.

        Shapley igualitário: custo_compartilhado = duracao_overlap / n_participantes.
        Para sobreposicao 2-way: cada participante recebe metade do custo da região.
        """
        items = [
            {"item_id": "a1", "T_start": 0.0, "T_end": 3.5},
            {"item_id": "a2", "T_start": 2.1, "T_end": 6.0},
            {"item_id": "a3", "T_start": 5.0, "T_end": 9.3},
        ]
        r = _by_id(_run(items, c_unit=1.0))

        # a1: exclusivo [0, 2.1) = 2.1w; compartilhado a1∩a2 [2.1, 3.5) = 1.4w / 2 = 0.7
        assert abs(r["a1"].custo_produtivo_exclusivo - 2.1) < 0.01
        assert abs(r["a1"].custo_produtivo_compartilhado - 0.7) < 0.01
        assert abs(r["a1"].overlap_semanas - 1.4) < 0.01  # duração do overlap, não custo

        # a3: exclusivo (6.0, 9.3] = 3.3w; compartilhado a2∩a3 [5.0, 6.0) = 1.0w / 2 = 0.5
        assert abs(r["a3"].custo_produtivo_exclusivo - 3.3) < 0.01
        assert abs(r["a3"].custo_produtivo_compartilhado - 0.5) < 0.01
        assert abs(r["a3"].overlap_semanas - 1.0) < 0.01

    def test_sem_regiao_exclusiva_totalmente_subconjunto(self):
        """Atividade que é subconjunto de outra tem custo_produtivo_exclusivo = 0.

        Shapley igualitário: sobreposicao [2,5) = 3w, 2-way split → cada recebe 1.5.
        """
        items = [
            {"item_id": "grande", "T_start": 0.0, "T_end": 10.0},
            {"item_id": "pequena", "T_start": 2.0, "T_end": 5.0},
        ]
        r = _by_id(_run(items, c_unit=1.0))

        # pequena está totalmente dentro de grande: sem região exclusiva
        assert r["pequena"].custo_produtivo_exclusivo == 0.0
        # sobreposicao [2,5) = 3w, split 2-way → 1.5 cada
        assert abs(r["pequena"].custo_produtivo_compartilhado - 1.5) < 0.01
        assert abs(r["pequena"].overlap_semanas - 3.0) < 0.01
        # grande tem exclusivo [0,2) + (5,10] = 7w
        assert abs(r["grande"].custo_produtivo_exclusivo - 7.0) < 0.01
        assert abs(r["grande"].custo_produtivo_compartilhado - 1.5) < 0.01


class TestEulerIntervalGapImputado:
    """Gap entre atividades deve ser imputado ao sucessor crítico."""

    def test_gap_imputado_ao_sucessor(self):
        """a1=[0,3], gap=[3,5], a2=[5,9] — gap imputado a a2 (sucessor)."""
        items = [
            {"item_id": "a1", "T_start": 0.0, "T_end": 3.0},
            {"item_id": "a2", "T_start": 5.0, "T_end": 9.0},
        ]
        # Contrato cobre toda a janela [0, 9]
        r = _by_id(_run(items, c_unit=2.0, T0=0.0, T1=9.0))

        # Gap [3,5] = 2w a custo 2.0/w = 4.0 → imputado a a2
        assert abs(r["a2"].custo_ocioso_imputado - 4.0) < 0.01
        # a1 não recebe custo de gap
        assert r["a1"].custo_ocioso_imputado == 0.0

    def test_sem_gap_sem_ocioso(self):
        """Atividades sem gap → custo_ocioso_imputado = 0 para todos."""
        items = [
            {"item_id": "a1", "T_start": 0.0, "T_end": 5.0},
            {"item_id": "a2", "T_start": 5.0, "T_end": 9.0},
        ]
        r = _by_id(_run(items, c_unit=1.0))

        # O ponto de toque Point(5.0) tem medida 0 → sem custo ocioso
        assert r["a1"].custo_ocioso_imputado == 0.0
        assert r["a2"].custo_ocioso_imputado == 0.0

    def test_gap_no_inicio_imputado_ao_primeiro(self):
        """Quando há gap antes da primeira atividade, imputar ao primeiro sucessor."""
        items = [
            {"item_id": "a1", "T_start": 3.0, "T_end": 7.0},
        ]
        # Contrato começa em 0, atividade só começa em 3 → gap [0,3]
        r = _by_id(_run(items, c_unit=1.0, T0=0.0, T1=7.0))

        # Gap [0,3) = 3w imputado a a1 (primeiro sucessor)
        assert abs(r["a1"].custo_ocioso_imputado - 3.0) < 0.01


class TestDagPredecessorCritico:
    """predecessor_critico_id via cadeias de perpetuação."""

    def test_predecessor_critico_da_cadeia(self):
        """Em cadeia a1→a2→a3, predecessor de a2 é a1 e de a3 é a2."""
        from concilium.domain.models.canonical import CadeiaPerpetuacao

        items = [
            {"item_id": "a1", "T_start": 0.0, "T_end": 3.0},
            {"item_id": "a2", "T_start": 3.0, "T_end": 6.0},
            {"item_id": "a3", "T_start": 6.0, "T_end": 9.0},
        ]
        cadeia = CadeiaPerpetuacao(
            cadeia_id="c1",
            item_ids=["a1", "a2", "a3"],
            tipo_id="ESCAVADEIRA",
            semana_inicio="W01",
            semana_fim="W09",
        )
        atrib = {it["item_id"]: (0.0, "produtivo", 3.0) for it in items}
        result = particionar_contrato(
            items_com_janela=items,
            c_mob=0.0,
            c_demob=0.0,
            c_unit_semana=1.0,
            quantidade_contratada=1,
            T_contrato_start=0.0,
            T_contrato_end=9.0,
            atribuicao=atrib,
            cadeias=[cadeia],
        )
        r = _by_id(result)

        assert r["a1"].predecessor_critico_id is None
        assert r["a2"].predecessor_critico_id == "a1"
        assert r["a3"].predecessor_critico_id == "a2"

    def test_sem_cadeia_predecessor_nulo(self):
        """Sem cadeia, predecessor_critico_id deve ser None."""
        items = [{"item_id": "solo", "T_start": 0.0, "T_end": 5.0}]
        r = _by_id(_run(items))
        assert r["solo"].predecessor_critico_id is None


class TestIterIntervalsPolimorfismo:
    """_iter_intervals deve aceitar Interval, IntervalSet não-vazio e IntervalSet vazio."""

    def test_single_interval(self):
        from interval_sets import Interval

        ivs = _iter_intervals(Interval(0.0, 3.0))
        assert len(ivs) == 1

    def test_non_empty_interval_set(self):
        from interval_sets import Interval, IntervalSet

        ivs = _iter_intervals(IntervalSet([Interval(0.0, 1.0), Interval(2.0, 3.0)]))
        assert len(ivs) == 2

    def test_empty_interval_set(self):
        from interval_sets import IntervalSet

        ivs = _iter_intervals(IntervalSet([]))
        assert ivs == []

    def test_non_interval_returns_empty(self):
        """Objeto arbitrário sem .is_empty() → lista vazia."""
        ivs = _iter_intervals(42)
        assert ivs == []

    def test_eule_unavailable_returns_empty(self, monkeypatch):
        """Quando _EULE_AVAILABLE é False (dependência opcional ausente em
        produção), _iter_intervals deve retornar [] sem tentar usar Interval."""
        monkeypatch.setattr(_mod._causal_cost_partition, "_EULE_AVAILABLE", False)
        from interval_sets import Interval

        ivs = _iter_intervals(Interval(0.0, 3.0))
        assert ivs == []


class TestParticionarContratoEdgeCases:
    """Ramos de fallback de particionar_contrato: lista vazia, eule indisponível
    e nenhum item com janela válida (T_end > T_start)."""

    def test_empty_items_returns_empty_list(self):
        """Linha 1871: items_com_janela vazio → [] imediatamente."""
        result = particionar_contrato(
            items_com_janela=[],
            c_mob=0.0,
            c_demob=0.0,
            c_unit_semana=1.0,
            quantidade_contratada=1,
            T_contrato_start=0.0,
            T_contrato_end=1.0,
            atribuicao={},
            cadeias=[],
        )
        assert result == []

    def test_eule_unavailable_delegates_to_fase2(self, monkeypatch):
        """Linha 1878: sem eule[interval], delega para _compute_particao_por_tipo
        (caminho Fase 2) em vez de construir IntervalSet."""
        monkeypatch.setattr(_mod, "_EULE_AVAILABLE", False)
        items = [{"item_id": "a1", "T_start": 0.0, "T_end": 5.0, "machine_weeks": 5, "required": 1}]
        result = _run(items)
        assert len(result) == 1
        assert result[0].item_id == "a1"

    def test_all_items_zero_width_falls_back_to_fase2(self):
        """Linha 1895: todos os itens têm T_end == T_start (janela degenerada) —
        `sets` fica vazio mesmo com eule disponível, delega para Fase 2."""
        items = [{"item_id": "a1", "T_start": 3.0, "T_end": 3.0, "machine_weeks": 0, "required": 1}]
        result = _run(items, T0=3.0, T1=3.0)
        assert len(result) == 1
        assert result[0].item_id == "a1"
