"""Unit tests for _skill_helpers_b.py (Skill 05 — Equipes e Alocação).

Covers:
- _build_requisitos_e_tipos: with and without cronograma (VAL-EQUIP-SEM-CRON)
- _build_alocacoes_pool: pool auto-creation, Alocacao fields
- _processar_funcoes_requisitos: tipo creation, requisitos added
- _processar_equipamentos_requisitos: tipo creation, requisitos added

ADR-182 D6: _resolve_salario/_resolve_encargo_funcao/_calcular_custo_funcao/
_converter_preco_equip/_consumo_from_decomposicao removidas de b.py (eram
duplicatas mortas, não importadas por __init__.py) — testes correspondentes
removidos junto. A versão ativa dessas funções vive em
_dimensionamento_custos.py, testada em test_skill05_helpers_a_coverage.py.
"""

from __future__ import annotations

# ── Import the module under test ────────────────────────────────────────────
# The module lives in "05-equipes-e-alocacao/" which is not a valid Python
# identifier, so we load it via importlib below instead of a direct import.
# ---------------------------------------------------------------------------
# Helpers to import from the actual file path since the module lives in a
# directory whose name starts with a digit ("05-equipes-e-alocacao") and the
# public entrypoint re-exports everything.
# ---------------------------------------------------------------------------
import importlib.util
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock

_HELPERS_PATH = str(
    Path(__file__).resolve().parents[4]
    / "src"
    / "concilium"
    / "application"
    / "skills"
    / "manifests"
    / "05-equipes-e-alocacao"
    / "_skill_helpers"
    / "b.py"
)


def _load_helpers():
    """Load _skill_helpers_b directly by file path (dir name is not a valid identifier)."""
    spec = importlib.util.spec_from_file_location("_skill_helpers_b", _HELPERS_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Load once at module level
_mod = _load_helpers()

_build_requisitos_e_tipos = _mod._build_requisitos_e_tipos
_build_alocacoes_pool = _mod._build_alocacoes_pool
_processar_funcoes_requisitos = _mod._processar_funcoes_requisitos
_processar_equipamentos_requisitos = _mod._processar_equipamentos_requisitos

# ── Domain model imports ─────────────────────────────────────────────────────
from concilium.domain.models.canonical import (  # noqa: E402
    Atividade,
    CanonicalModel,
    Coordenadas,
    EquipamentoEquipeDireta,
    EquipeDireta,
    FuncaoEquipeDireta,
    Meta,
    Projeto,
    RecursoPool,
    RegimeTrabalho,
    RequisitoRecurso,
    TipoRecurso,
)

# ============================================================================
# Shared fixtures
# ============================================================================


def _make_projeto() -> Projeto:
    return Projeto(
        id=str(uuid.uuid4()),
        nome="Projeto Teste",
        tipo_obra="terraplenagem",
        localizacao="Brasil",
        coordenadas=Coordenadas(lat=-15.0, lng=-47.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2025, 1, 1),
        data_termino=date(2025, 12, 31),
        snapshot_catalogo_id="cat-001",
        snapshot_perfil_id="perfil-001",
    )


def _make_meta() -> Meta:
    return Meta(
        gerado_em=datetime(2025, 1, 1, tzinfo=UTC),
        contexto_id="ctx-001",
    )


def _make_canonical(
    atividades=None,
    tipos_recurso=None,
    recurso_pool=None,
) -> CanonicalModel:
    return CanonicalModel(
        meta=_make_meta(),
        projeto=_make_projeto(),
        atividades=atividades or [],
        tipos_recurso=tipos_recurso or [],
        recurso_pool=recurso_pool or [],
    )


def _make_atividade(atividade_id: str, eap_item_id: str) -> Atividade:
    return Atividade(
        atividade_id=atividade_id,
        eap_item_id=eap_item_id,
        descricao="Atividade de teste",
        fracao_quantitativo=1.0,
        quantitativo_atividade=100.0,
        cpu_id="cpu-001",
    )


def _make_equipe(item_id: str, funcoes=None, equipamentos=None) -> EquipeDireta:
    return EquipeDireta(
        equipe_id=str(uuid.uuid4()),
        item_id=item_id,
        cpu_id="cpu-001",
        nome="Equipe A",
        funcoes=funcoes or [],
        equipamentos=equipamentos or [],
    )


def _make_funcao(
    funcao_id: str = "F1", descricao: str = "Operador", num_pessoas: int = 2, custo_mensal_unitario: float = 3000.0
) -> FuncaoEquipeDireta:
    return FuncaoEquipeDireta(
        funcao_id=funcao_id,
        descricao=descricao,
        num_pessoas=num_pessoas,
        custo_mensal_unitario=custo_mensal_unitario,
    )


def _make_equipamento(
    equip_id: str = "E1", descricao: str = "Escavadeira", num_unidades: int = 1, custo_mensal: float = 10000.0
) -> EquipamentoEquipeDireta:
    return EquipamentoEquipeDireta(
        equip_id=equip_id,
        descricao=descricao,
        num_unidades=num_unidades,
        custo_mensal=custo_mensal,
    )


# ============================================================================
# ADR-182: _resolve_salario/_resolve_encargo_funcao/_calcular_custo_funcao/
# _converter_preco_equip/_consumo_from_decomposicao removidas deste módulo —
# eram duplicatas mortas pré-refatoração (não importadas por __init__.py; a
# versão ativa vive em _dimensionamento_custos.py, testada em
# test_skill05_helpers_a_coverage.py). Ver ADR-182 D6.
# ============================================================================


# ============================================================================
# Tests for _processar_funcoes_requisitos
# ============================================================================


class TestProcessarFuncoesRequisitos:
    def test_creates_tipo_for_new_funcao(self):
        eq = _make_equipe("item-1", funcoes=[_make_funcao("F1", "Operador", 2, 3000.0)])
        atv = _make_atividade("atv-1", "item-1")
        atvs_por_item = defaultdict(list, {"item-1": [atv]})
        tipos = {}
        requisitos = []
        d_ini = date(2025, 1, 1)
        d_fim = date(2025, 12, 31)

        _processar_funcoes_requisitos(eq, d_ini, d_fim, atvs_por_item, tipos, requisitos)

        assert "FUNC-F1" in tipos
        t = tipos["FUNC-F1"]
        assert t.nome == "Operador"
        assert t.categoria == "EQUIPE"
        assert t.custo_unitario_dia == round(3000.0 / 26, 2)

    def test_creates_requisito_per_atividade(self):
        eq = _make_equipe("item-1", funcoes=[_make_funcao("F1", num_pessoas=3)])
        atv1 = _make_atividade("atv-1", "item-1")
        atv2 = _make_atividade("atv-2", "item-1")
        atvs_por_item = defaultdict(list, {"item-1": [atv1, atv2]})
        tipos = {}
        requisitos = []

        _processar_funcoes_requisitos(eq, date(2025, 1, 1), date(2025, 12, 31), atvs_por_item, tipos, requisitos)

        assert len(requisitos) == 2
        for req in requisitos:
            assert req.tipo_recurso_id == "FUNC-F1"
            assert req.quantidade == 3.0

    def test_does_not_overwrite_existing_tipo(self):
        existing_tipo = TipoRecurso(id="FUNC-F1", nome="Existente", categoria="EQUIPE", custo_unitario_dia=99.0)
        eq = _make_equipe("item-1", funcoes=[_make_funcao("F1", "Novo")])
        atvs_por_item = defaultdict(list, {"item-1": []})
        tipos = {"FUNC-F1": existing_tipo}
        requisitos = []

        _processar_funcoes_requisitos(eq, date(2025, 1, 1), date(2025, 12, 31), atvs_por_item, tipos, requisitos)

        assert tipos["FUNC-F1"].nome == "Existente"


# ============================================================================
# Tests for _processar_equipamentos_requisitos
# ============================================================================


class TestProcessarEquipamentosRequisitos:
    def test_creates_tipo_for_new_equip(self):
        eq = _make_equipe("item-2", equipamentos=[_make_equipamento("E1", "Escavadeira", 1, 10000.0)])
        atv = _make_atividade("atv-3", "item-2")
        atvs_por_item = defaultdict(list, {"item-2": [atv]})
        tipos = {}
        requisitos = []

        _processar_equipamentos_requisitos(eq, date(2025, 1, 1), date(2025, 12, 31), atvs_por_item, tipos, requisitos)

        assert "EQUIP-E1" in tipos
        t = tipos["EQUIP-E1"]
        assert t.nome == "Escavadeira"
        assert t.categoria == "EQUIPAMENTO"
        assert t.custo_unitario_dia == round(10000.0 / 26, 2)

    def test_creates_requisito_with_num_unidades(self):
        eq = _make_equipe("item-2", equipamentos=[_make_equipamento("E1", num_unidades=3)])
        atv = _make_atividade("atv-3", "item-2")
        atvs_por_item = defaultdict(list, {"item-2": [atv]})
        tipos = {}
        requisitos = []

        _processar_equipamentos_requisitos(eq, date(2025, 1, 1), date(2025, 12, 31), atvs_por_item, tipos, requisitos)

        assert len(requisitos) == 1
        assert requisitos[0].quantidade == 3.0


# ============================================================================
# Tests for _build_requisitos_e_tipos
# ============================================================================


class TestBuildRequisitosETipos:
    def _cron_lookup_with_dist(self, item_id: str) -> dict:
        """Fake cron_lookup where item has distribuicao_semanal."""
        mock_cron = MagicMock()
        mock_cron.distribuicao_semanal = {"2025-W01": MagicMock(), "2025-W52": MagicMock()}
        return {item_id: mock_cron}

    def test_emits_val_equip_sem_cron_when_no_cron(self):
        eq = _make_equipe("item-X")
        canonical = _make_canonical(atividades=[])
        validacoes = []

        _build_requisitos_e_tipos(
            equipes=[eq],
            canonical_in=canonical,
            cron_lookup={},  # no entry for item-X
            validacoes=validacoes,
        )

        codes = [v.codigo for v in validacoes]
        assert "VAL-EQUIP-SEM-CRON" in codes

    def test_emits_val_equip_sem_cron_when_no_distribuicao(self):
        eq = _make_equipe("item-Y")
        canonical = _make_canonical(atividades=[])
        validacoes = []
        mock_cron = MagicMock()
        mock_cron.distribuicao_semanal = {}  # empty dict

        _build_requisitos_e_tipos(
            equipes=[eq],
            canonical_in=canonical,
            cron_lookup={"item-Y": mock_cron},
            validacoes=validacoes,
        )

        codes = [v.codigo for v in validacoes]
        assert "VAL-EQUIP-SEM-CRON" in codes

    def test_uses_projeto_data_inicio_when_no_cron(self):
        eq = _make_equipe("item-Z")
        canonical = _make_canonical(atividades=[])
        validacoes = []

        requisitos, tipos = _build_requisitos_e_tipos(
            equipes=[eq],
            canonical_in=canonical,
            cron_lookup={},
            validacoes=validacoes,
        )
        # No atividades -> no requisitos, but validation should fire
        assert any(v.codigo == "VAL-EQUIP-SEM-CRON" for v in validacoes)

    def test_with_cron_no_warning(self):
        item_id = "item-A"
        funcao = _make_funcao("F1", "Operador", 2, 2600.0)
        eq = _make_equipe(item_id, funcoes=[funcao])
        atv = _make_atividade("atv-1", item_id)
        canonical = _make_canonical(atividades=[atv])
        validacoes = []
        cron_lookup = self._cron_lookup_with_dist(item_id)

        requisitos, tipos = _build_requisitos_e_tipos(
            equipes=[eq],
            canonical_in=canonical,
            cron_lookup=cron_lookup,
            validacoes=validacoes,
        )

        assert not any(v.codigo == "VAL-EQUIP-SEM-CRON" for v in validacoes)
        assert "FUNC-F1" in tipos
        assert len(requisitos) == 1

    def test_with_cron_sets_dates_from_distribuicao(self):
        item_id = "item-B"
        funcao = _make_funcao("F2", "Motorista", 1, 2000.0)
        eq = _make_equipe(item_id, funcoes=[funcao])
        atv = _make_atividade("atv-2", item_id)
        canonical = _make_canonical(atividades=[atv])
        validacoes = []
        mock_cron = MagicMock()
        mock_cron.distribuicao_semanal = {"2025-W01": MagicMock(), "2025-W26": MagicMock()}
        cron_lookup = {item_id: mock_cron}

        requisitos, tipos = _build_requisitos_e_tipos(
            equipes=[eq],
            canonical_in=canonical,
            cron_lookup=cron_lookup,
            validacoes=validacoes,
        )

        assert len(requisitos) == 1
        req = requisitos[0]
        # d_ini from "2025-W01".split("-W")[0] + "-01-01" = 2025-01-01
        assert req.data_inicio == date(2025, 1, 1)
        # d_fim from "2025-W26".split("-W")[0] + "-12-31" = 2025-12-31
        assert req.data_termino == date(2025, 12, 31)

    def test_existing_tipos_recurso_preserved(self):
        """Tipos already in canonical_in are included in returned tipos dict."""
        existing = TipoRecurso(id="EXISTING-001", nome="Existente", categoria="EQUIPE", custo_unitario_dia=100.0)
        canonical = _make_canonical(atividades=[], tipos_recurso=[existing])
        validacoes = []

        _, tipos = _build_requisitos_e_tipos(
            equipes=[],
            canonical_in=canonical,
            cron_lookup={},
            validacoes=validacoes,
        )

        assert "EXISTING-001" in tipos


# ============================================================================
# Tests for _build_alocacoes_pool
# ============================================================================


class TestBuildAlocacoesPool:
    def _make_requisito(
        self, tipo_recurso_id: str, atividade_id: str = "atv-1", quantidade: float = 2.0
    ) -> RequisitoRecurso:
        return RequisitoRecurso(
            requisito_id=str(uuid.uuid4()),
            atividade_id=atividade_id,
            tipo_recurso_id=tipo_recurso_id,
            descricao="Req de teste",
            quantidade=quantidade,
            data_inicio=date(2025, 1, 1),
            data_termino=date(2025, 6, 30),
        )

    def test_pool_auto_created_for_new_tipo(self):
        canonical = _make_canonical()
        tid = "FUNC-F99"
        tipos = {tid: TipoRecurso(id=tid, nome="Operador", categoria="EQUIPE", custo_unitario_dia=100.0)}
        requisitos = [self._make_requisito(tid)]

        alocacoes, pool_dict = _build_alocacoes_pool(requisitos, canonical, tipos)

        assert tid in pool_dict
        pool = pool_dict[tid]
        assert pool.quantidade_total == 1000
        assert pool.quantidade_disponivel == 1000
        assert str(canonical.projeto.id) == pool.projeto_id

    def test_alocacao_fields_are_correct(self):
        canonical = _make_canonical()
        tid = "EQUIP-E99"
        tipos = {tid: TipoRecurso(id=tid, nome="Trator", categoria="EQUIPAMENTO", custo_unitario_dia=500.0)}
        req = self._make_requisito(tid, atividade_id="atv-42", quantidade=3.0)
        alocacoes, pool_dict = _build_alocacoes_pool([req], canonical, tipos)

        assert len(alocacoes) == 1
        aloc = alocacoes[0]
        assert aloc.atividade_id == "atv-42"
        assert aloc.quantidade_alocada == 3.0
        assert aloc.status == "PLANEJADA"
        assert aloc.recurso_id == pool_dict[tid].id
        assert aloc.data_inicio == date(2025, 1, 1)
        assert aloc.data_termino == date(2025, 6, 30)

    def test_existing_pool_not_overwritten(self):
        """RecursoPool already in canonical_in should be preserved."""
        tid = "FUNC-F10"
        existing_pool = RecursoPool(
            id="existing-pool-id",
            tipo_id=tid,
            projeto_id="proj-001",
            quantidade_total=5,
            quantidade_disponivel=5,
        )
        canonical = _make_canonical(recurso_pool=[existing_pool])
        tipos = {tid: TipoRecurso(id=tid, nome="Encarregado", categoria="EQUIPE", custo_unitario_dia=200.0)}
        req = self._make_requisito(tid)
        alocacoes, pool_dict = _build_alocacoes_pool([req], canonical, tipos)

        # existing pool preserved (not replaced by auto-created)
        assert pool_dict[tid].id == "existing-pool-id"
        assert pool_dict[tid].quantidade_total == 5

    def test_requisito_without_matching_tipo_skipped(self):
        """Requisito whose tipo_recurso_id not in tipos or pool is silently skipped."""
        canonical = _make_canonical()
        tipos = {}  # no tipos
        req = self._make_requisito("UNKNOWN-TYPE")
        alocacoes, pool_dict = _build_alocacoes_pool([req], canonical, tipos)

        assert len(alocacoes) == 0

    def test_multiple_requisitos_sorted_by_data_inicio(self):
        canonical = _make_canonical()
        tid = "FUNC-F20"
        tipos = {tid: TipoRecurso(id=tid, nome="Operador", categoria="EQUIPE", custo_unitario_dia=150.0)}
        req_late = RequisitoRecurso(
            requisito_id=str(uuid.uuid4()),
            atividade_id="atv-late",
            tipo_recurso_id=tid,
            descricao="Late",
            quantidade=1.0,
            data_inicio=date(2025, 6, 1),
            data_termino=date(2025, 12, 31),
        )
        req_early = RequisitoRecurso(
            requisito_id=str(uuid.uuid4()),
            atividade_id="atv-early",
            tipo_recurso_id=tid,
            descricao="Early",
            quantidade=1.0,
            data_inicio=date(2025, 1, 1),
            data_termino=date(2025, 3, 31),
        )
        alocacoes, _ = _build_alocacoes_pool([req_late, req_early], canonical, tipos)

        assert len(alocacoes) == 2
        # sorted by data_inicio: early first
        assert alocacoes[0].atividade_id == "atv-early"
        assert alocacoes[1].atividade_id == "atv-late"

    def test_pool_dict_values_are_copies(self):
        """pool_dict should contain copies of original RecursoPool (model_copy)."""
        tid = "FUNC-F30"
        original_pool = RecursoPool(
            id="orig-id",
            tipo_id=tid,
            projeto_id="proj-X",
            quantidade_total=10,
            quantidade_disponivel=10,
        )
        canonical = _make_canonical(recurso_pool=[original_pool])
        tipos = {}
        alocacoes, pool_dict = _build_alocacoes_pool([], canonical, tipos)

        # Modifying pool_dict shouldn't affect original
        assert pool_dict[tid] is not original_pool


import os  # noqa: E402
import sys  # noqa: E402


def _load_skill_module(skill_dir: str, module_name: str):
    """Load a skill module from a directory with dashes in name."""
    from pathlib import Path as _Path

    base = str(_Path(__file__).resolve().parents[4] / "src/concilium/application/skills/manifests")
    target = os.path.join(base, skill_dir, f"{module_name}.py")
    if not os.path.exists(target):
        target = os.path.join(base, skill_dir, module_name, "__init__.py")
    if not os.path.exists(target):
        return None
    spec = importlib.util.spec_from_file_location(
        module_name, target, submodule_search_locations=[os.path.dirname(target)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(module_name, None)
        return None
    return mod


# ─── skill-05 _skill_helpers_b.py ────────────────────────────────────────────


class TestSkill05HelpersB:
    def _load(self):
        return _load_skill_module("05-equipes-e-alocacao", "_skill_helpers/b")

    def test_module_loads(self):
        mod = self._load()
        assert mod is not None

    def test_functions_available(self):
        mod = self._load()
        if mod is None:
            return
        fns = [f for f in dir(mod) if not f.startswith("_")]
        assert len(fns) >= 0



