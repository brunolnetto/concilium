"""Coverage tests for missing lines in skill 03-catalogo-de-recursos/skill.py.

Missing lines covered:
  36-39  — _resolve_custo_unit_from_repo: repo=None and insumo=None branches
  45-51  — _resolve_custo_unit_from_repo: unit conversion branches (h, mes, other)
  156    — _build_pool_from_specs: fallback to pools_existentes when pool is empty
"""

import importlib.util
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SKILL_PATH = Path("src/concilium/application/skills/manifests/03-catalogo-de-recursos/skill.py")

spec = importlib.util.spec_from_file_location("skill03", _SKILL_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

_resolve_custo_unit_from_repo = mod._resolve_custo_unit_from_repo
_build_pool_from_specs = mod._build_pool_from_specs


# ---------------------------------------------------------------------------
# _resolve_custo_unit_from_repo
# ---------------------------------------------------------------------------


class TestResolveCustoUnitFromRepo:
    def test_repo_none_returns_zero(self):
        """Line 35: repo is falsy — return 0.0 immediately."""
        result = _resolve_custo_unit_from_repo("tipo-a", None, None, None, None)
        assert result == 0.0

    def test_repo_falsy_empty_dict_returns_zero(self):
        """Line 35: repo is an empty dict (falsy) — return 0.0."""
        result = _resolve_custo_unit_from_repo("tipo-a", {}, None, None, None)
        assert result == 0.0

    def test_insumo_none_returns_zero(self):
        """Lines 37-38: repo present but obter_insumo returns None — return 0.0."""
        repo = MagicMock()
        repo.obter_insumo.return_value = None
        result = _resolve_custo_unit_from_repo("tipo-b", repo, None, None, None)
        assert result == 0.0
        repo.obter_insumo.assert_called_once_with("tipo-b")

    def test_insumo_falsy_empty_dict_returns_zero(self):
        """Lines 37-38: obter_insumo returns empty dict (falsy) — return 0.0."""
        repo = MagicMock()
        repo.obter_insumo.return_value = {}
        result = _resolve_custo_unit_from_repo("tipo-c", repo, None, None, None)
        assert result == 0.0

    def test_unit_h_multiplies_by_8(self):
        """Lines 45-48: unidade='h' — preco * 8."""
        repo = MagicMock()
        repo.obter_insumo.return_value = {"preco_unitario": 10.0, "unidade": "h"}
        repo.resolver_preco.return_value = (10.0, "catalogo")
        result = _resolve_custo_unit_from_repo("tipo-d", repo, "BR-SP", None, "2026-01-01")
        assert result == pytest.approx(80.0)

    def test_unit_h_uses_insumo_preco_when_resolver_returns_none(self):
        """Line 45: preco_resolvido is None — falls back to insumo['preco_unitario']."""
        repo = MagicMock()
        repo.obter_insumo.return_value = {"preco_unitario": 5.0, "unidade": "h"}
        repo.resolver_preco.return_value = (None, "fallback")
        result = _resolve_custo_unit_from_repo("tipo-e", repo, None, None, None)
        assert result == pytest.approx(40.0)

    def test_unit_mes_divides_by_30(self):
        """Lines 49-50: unidade='mes' — preco / 30."""
        repo = MagicMock()
        repo.obter_insumo.return_value = {"preco_unitario": 3000.0, "unidade": "mes"}
        repo.resolver_preco.return_value = (3000.0, "catalogo")
        result = _resolve_custo_unit_from_repo("tipo-f", repo, None, None, None)
        assert result == pytest.approx(100.0)

    def test_unit_other_returns_preco_as_is(self):
        """Line 51: unidade is neither 'h' nor 'mes' — return preco unchanged."""
        repo = MagicMock()
        repo.obter_insumo.return_value = {"preco_unitario": 250.0, "unidade": "un"}
        repo.resolver_preco.return_value = (250.0, "catalogo")
        result = _resolve_custo_unit_from_repo("tipo-g", repo, None, None, None)
        assert result == pytest.approx(250.0)

    def test_unit_default_h_when_missing_from_insumo(self):
        """Line 46: insumo has no 'unidade' key — defaults to 'h', so preco*8."""
        repo = MagicMock()
        repo.obter_insumo.return_value = {"preco_unitario": 20.0}
        repo.resolver_preco.return_value = (20.0, "catalogo")
        result = _resolve_custo_unit_from_repo("tipo-h", repo, None, None, None)
        assert result == pytest.approx(160.0)


# ---------------------------------------------------------------------------
# _build_pool_from_specs — line 156
# ---------------------------------------------------------------------------


def _make_pool_entry(tipo_id: str, projeto_id: str):
    """Create a minimal RecursoPool-like object via the domain model."""
    from concilium.domain.models.canonical import RecursoPool

    return RecursoPool(
        id=str(uuid.uuid4()),
        tipo_id=tipo_id,
        projeto_id=projeto_id,
        quantidade_total=3,
        quantidade_disponivel=3,
    )


class TestBuildPoolFromSpecsLine156:
    """Line 156: pool_inicial is empty and pools_existentes is non-empty.

    Expected: pool is populated from pools_existentes.values() instead of
    generating one-per-tipo fallback entries.
    """

    def test_fallback_to_pools_existentes_when_pool_inicial_empty(self):
        projeto_id = str(uuid.uuid4())
        existing1 = _make_pool_entry("EQUIP-A", projeto_id)
        existing2 = _make_pool_entry("EQUIP-B", projeto_id)
        pools_existentes = {existing1.id: existing1, existing2.id: existing2}

        tipos_por_id = {}  # no types known — pool_inicial is empty, not relevant
        validacoes = []

        result = _build_pool_from_specs(
            pool_inicial=[],
            tipos_por_id=tipos_por_id,
            pools_existentes=pools_existentes,
            projeto_id=projeto_id,
            validacoes=validacoes,
        )

        assert len(result) == 2
        result_ids = {p.id for p in result}
        assert existing1.id in result_ids
        assert existing2.id in result_ids
        assert validacoes == []

    def test_fallback_to_pools_existentes_preferred_over_per_tipo_default(self):
        """When pools_existentes is non-empty, line 156 is taken (not 158-167)."""
        projeto_id = str(uuid.uuid4())
        existing = _make_pool_entry("EQUIP-Z", projeto_id)
        pools_existentes = {existing.id: existing}

        from concilium.domain.models.canonical import TipoRecurso

        tipo = TipoRecurso(id="EQUIP-Z", nome="Equipamento Z", categoria="EQUIPAMENTO", custo_unitario_dia=100.0)
        tipos_por_id = {"EQUIP-Z": tipo}
        validacoes = []

        result = _build_pool_from_specs(
            pool_inicial=[],
            tipos_por_id=tipos_por_id,
            pools_existentes=pools_existentes,
            projeto_id=projeto_id,
            validacoes=validacoes,
        )

        # Must return the existing pool (id preserved), not a newly generated one
        assert len(result) == 1
        assert result[0].id == existing.id
        assert result[0].quantidade_total == 3

    def test_per_tipo_fallback_when_pools_existentes_empty(self):
        """Else branch (lines 158-167): pools_existentes is empty — one pool per tipo."""
        projeto_id = str(uuid.uuid4())

        from concilium.domain.models.canonical import TipoRecurso

        tipo_a = TipoRecurso(id="A", nome="A", categoria="EQUIPAMENTO", custo_unitario_dia=10.0)
        tipo_b = TipoRecurso(id="B", nome="B", categoria="MATERIAL", custo_unitario_dia=20.0)
        tipos_por_id = {"A": tipo_a, "B": tipo_b}
        validacoes = []

        result = _build_pool_from_specs(
            pool_inicial=[],
            tipos_por_id=tipos_por_id,
            pools_existentes={},
            projeto_id=projeto_id,
            validacoes=validacoes,
        )

        assert len(result) == 2
        tipo_ids = {p.tipo_id for p in result}
        assert tipo_ids == {"A", "B"}
        for p in result:
            assert p.quantidade_total == 1
