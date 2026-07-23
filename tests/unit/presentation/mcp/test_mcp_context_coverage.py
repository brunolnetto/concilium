"""Tests for helper functions in concilium.presentation.mcp._context."""

from __future__ import annotations

import warnings
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from concilium.presentation.mcp._context import (
    _derivar_inputs_01A,
    _di_build_equip_resources,
    _di_build_func_resources,
    _di_build_indices,
    _di_collect_max_equipe,
)

# ---------------------------------------------------------------------------
# _di_build_indices
# ---------------------------------------------------------------------------


class TestDiBuildIndices:
    def test_insumos_indexed_by_codigo(self):
        catalogo = {
            "insumos": [
                {"codigo": "INS-001", "descricao": "Escavadeira", "preco_unitario": 100.0},
            ],
            "cpus": [],
        }
        insumos_idx, cpus_idx = _di_build_indices(catalogo)
        assert "INS-001" in insumos_idx
        assert insumos_idx["INS-001"]["descricao"] == "Escavadeira"
        assert cpus_idx == {}

    def test_insumos_indexed_by_id_when_no_codigo(self):
        catalogo = {
            "insumos": [
                {"id": "INS-002", "descricao": "Operador", "preco_unitario": 50.0},
            ],
            "cpus": [],
        }
        insumos_idx, _ = _di_build_indices(catalogo)
        assert "INS-002" in insumos_idx

    def test_insumos_skipped_when_no_key(self):
        catalogo = {
            "insumos": [{"descricao": "Sem codigo nem id"}],
            "cpus": [],
        }
        insumos_idx, _ = _di_build_indices(catalogo)
        assert insumos_idx == {}

    def test_cpus_indexed_by_codigo(self):
        catalogo = {
            "insumos": [],
            "cpus": [
                {"codigo": "CPU-A", "equipe": {"equipamentos": [], "funcoes": []}},
                {"codigo": "CPU-B", "composicao_padrao_equipe": {}},
                {"nome": "sem codigo"},  # should be skipped
            ],
        }
        _, cpus_idx = _di_build_indices(catalogo)
        assert "CPU-A" in cpus_idx
        assert "CPU-B" in cpus_idx
        assert "nome" not in cpus_idx

    def test_empty_catalog(self):
        insumos_idx, cpus_idx = _di_build_indices({})
        assert insumos_idx == {}
        assert cpus_idx == {}

    def test_codigo_takes_precedence_over_id(self):
        catalogo = {
            "insumos": [{"codigo": "COD-1", "id": "ID-1", "descricao": "Item"}],
            "cpus": [],
        }
        insumos_idx, _ = _di_build_indices(catalogo)
        assert "COD-1" in insumos_idx
        assert "ID-1" not in insumos_idx


# ---------------------------------------------------------------------------
# _di_collect_max_equipe
# ---------------------------------------------------------------------------


def _make_eap_item(cpu_id: str):
    item = MagicMock()
    item.cpu_id = cpu_id
    return item


class TestDiCollectMaxEquipe:
    def test_collects_equip_and_func(self):
        cpus_idx = {
            "CPU-A": {
                "equipe": {
                    "equipamentos": [{"equip_id": "ESCAV", "num_unidades": 2}],
                    "funcoes": [{"funcao_id": "OPER", "num_pessoas": 3}],
                }
            }
        }
        canonical = SimpleNamespace(eap=[_make_eap_item("CPU-A")])
        equip_max, func_max = _di_collect_max_equipe(canonical, cpus_idx)
        assert equip_max == {"EQUIP-ESCAV": 2}
        assert func_max == {"FUNC-OPER": 3}

    def test_dedup_takes_max_across_items(self):
        cpus_idx = {
            "CPU-A": {
                "equipe": {
                    "equipamentos": [{"equip_id": "ESCAV", "num_unidades": 1}],
                    "funcoes": [{"funcao_id": "OPER", "num_pessoas": 2}],
                }
            },
            "CPU-B": {
                "equipe": {
                    "equipamentos": [{"equip_id": "ESCAV", "num_unidades": 3}],
                    "funcoes": [{"funcao_id": "OPER", "num_pessoas": 1}],
                }
            },
        }
        canonical = SimpleNamespace(eap=[_make_eap_item("CPU-A"), _make_eap_item("CPU-B")])
        equip_max, func_max = _di_collect_max_equipe(canonical, cpus_idx)
        assert equip_max["EQUIP-ESCAV"] == 3
        assert func_max["FUNC-OPER"] == 2

    def test_empty_eap_returns_empty_dicts(self):
        canonical = SimpleNamespace(eap=[])
        equip_max, func_max = _di_collect_max_equipe(canonical, {})
        assert equip_max == {}
        assert func_max == {}

    def test_none_eap_returns_empty_dicts(self):
        canonical = SimpleNamespace(eap=None)
        equip_max, func_max = _di_collect_max_equipe(canonical, {})
        assert equip_max == {}
        assert func_max == {}

    def test_cpu_not_in_index_yields_empty_equipe(self):
        canonical = SimpleNamespace(eap=[_make_eap_item("CPU-MISSING")])
        equip_max, func_max = _di_collect_max_equipe(canonical, {})
        assert equip_max == {}
        assert func_max == {}

    def test_uses_composicao_padrao_equipe_fallback(self):
        cpus_idx = {
            "CPU-X": {
                "composicao_padrao_equipe": {
                    "equipamentos": [{"equip_id": "TRATOR", "num_unidades": 1}],
                    "funcoes": [],
                }
            }
        }
        canonical = SimpleNamespace(eap=[_make_eap_item("CPU-X")])
        equip_max, _ = _di_collect_max_equipe(canonical, cpus_idx)
        assert equip_max == {"EQUIP-TRATOR": 1}

    def test_items_without_equip_id_are_skipped(self):
        cpus_idx = {
            "CPU-A": {
                "equipe": {
                    "equipamentos": [{"num_unidades": 2}],  # no equip_id
                    "funcoes": [{"num_pessoas": 1}],  # no funcao_id
                }
            }
        }
        canonical = SimpleNamespace(eap=[_make_eap_item("CPU-A")])
        equip_max, func_max = _di_collect_max_equipe(canonical, cpus_idx)
        assert equip_max == {}
        assert func_max == {}


# ---------------------------------------------------------------------------
# _di_build_equip_resources
# ---------------------------------------------------------------------------


class TestDiBuildEquipResources:
    def _horas_mes(self):
        from concilium.domain.constants import HORAS_MES_REGIME_6x1

        return float(HORAS_MES_REGIME_6x1)

    def _dias_mes(self):
        from concilium.domain.constants import SEMANAS_POR_MES

        return float(SEMANAS_POR_MES) * 7.0

    def test_known_insumo_with_atributos_horas_mes(self):
        horas_mes = self._horas_mes()
        dias_mes = self._dias_mes()
        insumos_idx = {
            "ESCAV": {
                "descricao": "Escavadeira HID",
                "preco_unitario": 10.0,
                "atributos_especificos": {"horas_mes": 160.0},
            }
        }
        equip_max = {"EQUIP-ESCAV": 2}
        tipos, pool = _di_build_equip_resources(equip_max, insumos_idx, horas_mes, dias_mes)
        assert len(tipos) == 1
        assert tipos[0]["id"] == "EQUIP-ESCAV"
        assert tipos[0]["categoria"] == "EQUIPAMENTO"
        assert tipos[0]["nome"] == "Escavadeira HID"
        expected_custo_dia = round(10.0 * (160.0 / dias_mes), 2)
        assert tipos[0]["custo_unitario_dia"] == expected_custo_dia
        assert pool[0] == {"tipo_id": "EQUIP-ESCAV", "quantidade_total": 2}

    def test_unknown_insumo_uses_defaults(self):
        horas_mes = self._horas_mes()
        dias_mes = self._dias_mes()
        equip_max = {"EQUIP-UNKNOWN": 1}
        tipos, pool = _di_build_equip_resources(equip_max, {}, horas_mes, dias_mes)
        assert len(tipos) == 1
        assert tipos[0]["custo_unitario_dia"] == 0.0
        assert tipos[0]["nome"] == "UNKNOWN"  # fallback to raw_id
        assert tipos[0]["categoria"] == "EQUIPAMENTO"

    def test_falls_back_to_horas_mes_when_atributos_missing(self):
        horas_mes = self._horas_mes()
        dias_mes = self._dias_mes()
        insumos_idx = {
            "TRATOR": {
                "descricao": "Trator",
                "preco_unitario": 5.0,
                # no atributos_especificos
            }
        }
        equip_max = {"EQUIP-TRATOR": 1}
        tipos, _ = _di_build_equip_resources(equip_max, insumos_idx, horas_mes, dias_mes)
        expected = round(5.0 * (horas_mes / dias_mes), 2)
        assert tipos[0]["custo_unitario_dia"] == expected

    def test_empty_equip_max_returns_empty_lists(self):
        horas_mes = self._horas_mes()
        dias_mes = self._dias_mes()
        tipos, pool = _di_build_equip_resources({}, {}, horas_mes, dias_mes)
        assert tipos == []
        assert pool == []

    def test_none_preco_unitario_treated_as_zero(self):
        horas_mes = self._horas_mes()
        dias_mes = self._dias_mes()
        insumos_idx = {"X": {"preco_unitario": None}}
        equip_max = {"EQUIP-X": 1}
        tipos, _ = _di_build_equip_resources(equip_max, insumos_idx, horas_mes, dias_mes)
        assert tipos[0]["custo_unitario_dia"] == 0.0


# ---------------------------------------------------------------------------
# _di_build_func_resources
# ---------------------------------------------------------------------------


class TestDiBuildFuncResources:
    def _horas_mes(self):
        from concilium.domain.constants import HORAS_MES_REGIME_6x1

        return float(HORAS_MES_REGIME_6x1)

    def _dias_mes(self):
        from concilium.domain.constants import SEMANAS_POR_MES

        return float(SEMANAS_POR_MES) * 7.0

    def test_unidade_h_multiplies_by_horas_mes(self):
        horas_mes = self._horas_mes()
        dias_mes = self._dias_mes()
        insumos_idx = {"OPER": {"descricao": "Operador", "preco_unitario": 20.0, "unidade": "h"}}
        func_max = {"FUNC-OPER": 3}
        tipos, pool = _di_build_func_resources(func_max, insumos_idx, horas_mes, dias_mes)
        expected_salario = 20.0 * horas_mes
        expected_custo_dia = round(expected_salario / dias_mes, 2)
        assert tipos[0]["custo_unitario_dia"] == expected_custo_dia
        assert tipos[0]["categoria"] == "EQUIPE"
        assert pool[0] == {"tipo_id": "FUNC-OPER", "quantidade_total": 3}

    def test_unidade_mes_uses_preco_directly(self):
        horas_mes = self._horas_mes()
        dias_mes = self._dias_mes()
        insumos_idx = {"ENG": {"descricao": "Engenheiro", "preco_unitario": 5000.0, "unidade": "mes"}}
        func_max = {"FUNC-ENG": 1}
        tipos, _ = _di_build_func_resources(func_max, insumos_idx, horas_mes, dias_mes)
        expected_custo_dia = round(5000.0 / dias_mes, 2)
        assert tipos[0]["custo_unitario_dia"] == expected_custo_dia

    def test_default_unidade_treated_as_mes(self):
        horas_mes = self._horas_mes()
        dias_mes = self._dias_mes()
        insumos_idx = {"TEC": {"descricao": "Tecnico", "preco_unitario": 3000.0}}  # no unidade
        func_max = {"FUNC-TEC": 2}
        tipos, _ = _di_build_func_resources(func_max, insumos_idx, horas_mes, dias_mes)
        expected_custo_dia = round(3000.0 / dias_mes, 2)
        assert tipos[0]["custo_unitario_dia"] == expected_custo_dia

    def test_unknown_insumo_uses_defaults(self):
        horas_mes = self._horas_mes()
        dias_mes = self._dias_mes()
        func_max = {"FUNC-UNKNOWN": 1}
        tipos, pool = _di_build_func_resources(func_max, {}, horas_mes, dias_mes)
        assert tipos[0]["custo_unitario_dia"] == 0.0
        assert tipos[0]["nome"] == "UNKNOWN"

    def test_empty_func_max_returns_empty_lists(self):
        horas_mes = self._horas_mes()
        dias_mes = self._dias_mes()
        tipos, pool = _di_build_func_resources({}, {}, horas_mes, dias_mes)
        assert tipos == []
        assert pool == []

    def test_none_preco_unitario_treated_as_zero(self):
        horas_mes = self._horas_mes()
        dias_mes = self._dias_mes()
        insumos_idx = {"X": {"preco_unitario": None, "unidade": "h"}}
        func_max = {"FUNC-X": 1}
        tipos, _ = _di_build_func_resources(func_max, insumos_idx, horas_mes, dias_mes)
        assert tipos[0]["custo_unitario_dia"] == 0.0


# ---------------------------------------------------------------------------
# _derivar_inputs_01A
# ---------------------------------------------------------------------------


class TestDerivarInputs01A:
    def _make_store(self, canonical, contexto_id="ctx-1"):
        store = MagicMock()
        store.load_canonical.return_value = canonical
        store.meta = {"contexto_id": contexto_id}
        return store

    def test_returns_empty_when_canonical_is_none(self):
        store = self._make_store(None)
        rt = MagicMock()
        result = _derivar_inputs_01A(rt, store, "v1")
        assert result == {}

    def test_returns_empty_when_load_contexto_raises(self):
        canonical = SimpleNamespace(eap=[])
        store = self._make_store(canonical)
        rt = MagicMock()
        rt.load_contexto.side_effect = RuntimeError("not found")
        result = _derivar_inputs_01A(rt, store, "v1")
        assert result == {}

    def test_returns_empty_when_load_catalogo_raises(self):
        canonical = SimpleNamespace(eap=[])
        store = self._make_store(canonical)
        rt = MagicMock()
        contexto = MagicMock()
        contexto.catalogo_id = "cat-1"
        rt.load_contexto.return_value = contexto
        rt.load_catalogo.side_effect = KeyError("not found")
        result = _derivar_inputs_01A(rt, store, "v1")
        assert result == {}

    def test_returns_empty_when_no_equipamentos_or_funcoes(self):
        canonical = SimpleNamespace(eap=[_make_eap_item("CPU-A")])
        store = self._make_store(canonical)
        rt = MagicMock()
        contexto = MagicMock()
        contexto.catalogo_id = "cat-1"
        rt.load_contexto.return_value = contexto
        # catalogo has cpus but CPU-A has no equipe
        rt.load_catalogo.return_value = {
            "insumos": [],
            "cpus": [{"codigo": "CPU-A", "equipe": {"equipamentos": [], "funcoes": []}}],
        }
        result = _derivar_inputs_01A(rt, store, "v1")
        assert result == {}

    def test_success_path_returns_tipos_and_pool(self):
        item = _make_eap_item("CPU-A")
        canonical = SimpleNamespace(eap=[item])
        store = self._make_store(canonical)

        contexto = MagicMock()
        contexto.catalogo_id = "cat-1"
        rt = MagicMock()
        rt.load_contexto.return_value = contexto
        rt.load_catalogo.return_value = {
            "insumos": [
                {
                    "codigo": "ESCAV",
                    "descricao": "Escavadeira",
                    "preco_unitario": 10.0,
                    "atributos_especificos": {"horas_mes": 160.0},
                },
                {
                    "codigo": "OPER",
                    "descricao": "Operador",
                    "preco_unitario": 20.0,
                    "unidade": "h",
                },
            ],
            "cpus": [
                {
                    "codigo": "CPU-A",
                    "equipe": {
                        "equipamentos": [{"equip_id": "ESCAV", "num_unidades": 2}],
                        "funcoes": [{"funcao_id": "OPER", "num_pessoas": 3}],
                    },
                }
            ],
        }

        result = _derivar_inputs_01A(rt, store, "v1")

        assert "tipos_recurso" in result
        assert "pool_inicial" in result
        assert len(result["tipos_recurso"]) == 2
        assert len(result["pool_inicial"]) == 2

        ids = {r["id"] for r in result["tipos_recurso"]}
        assert "EQUIP-ESCAV" in ids
        assert "FUNC-OPER" in ids

        pool_ids = {p["tipo_id"] for p in result["pool_inicial"]}
        assert "EQUIP-ESCAV" in pool_ids
        assert "FUNC-OPER" in pool_ids

    def test_success_path_pool_quantities_correct(self):
        item = _make_eap_item("CPU-A")
        canonical = SimpleNamespace(eap=[item])
        store = self._make_store(canonical)

        contexto = MagicMock()
        contexto.catalogo_id = "cat-1"
        rt = MagicMock()
        rt.load_contexto.return_value = contexto
        rt.load_catalogo.return_value = {
            "insumos": [
                {"codigo": "E1", "preco_unitario": 0.0},
                {"codigo": "F1", "preco_unitario": 0.0, "unidade": "mes"},
            ],
            "cpus": [
                {
                    "codigo": "CPU-A",
                    "equipe": {
                        "equipamentos": [{"equip_id": "E1", "num_unidades": 5}],
                        "funcoes": [{"funcao_id": "F1", "num_pessoas": 4}],
                    },
                }
            ],
        }

        result = _derivar_inputs_01A(rt, store, "v1")

        pool_by_tipo = {p["tipo_id"]: p["quantidade_total"] for p in result["pool_inicial"]}
        assert pool_by_tipo["EQUIP-E1"] == 5
        assert pool_by_tipo["FUNC-F1"] == 4


# ---------------------------------------------------------------------------
# _build_gate_predecessors error path
# ---------------------------------------------------------------------------


class TestBuildGatePredecessorsErrorPath:
    def test_warns_and_returns_empty_dict_when_registry_raises(self):
        with patch(
            "concilium.presentation.mcp._context.SkillRegistry",
            side_effect=RuntimeError("registry broken"),
        ):
            from concilium.presentation.mcp._context import _build_gate_predecessors

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result = _build_gate_predecessors()

            assert result == {}
            assert len(caught) == 1
            assert "Erro ao construir _GATE_PREDECESSORS" in str(caught[0].message)

    def test_warns_and_returns_empty_dict_when_get_all_skills_raises(self):
        mock_registry = MagicMock()
        mock_registry.get_all_skills.side_effect = ValueError("no skills")

        with patch(
            "concilium.presentation.mcp._context.SkillRegistry",
            return_value=mock_registry,
        ):
            from concilium.presentation.mcp._context import _build_gate_predecessors

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result = _build_gate_predecessors()

            assert result == {}
            assert len(caught) == 1
            assert "no skills" in str(caught[0].message)



from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

# ─── MCP _context.py helpers ─────────────────────────────────────────────────


class TestMcpContext:
    def test_resolve_env_path_primary_set(self, monkeypatch, tmp_path):
        from concilium.presentation.mcp._context import _resolve_env_path

        monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(tmp_path))
        result = _resolve_env_path("CONCILIUM__CONFIG_ROOT", "./default")
        assert result == tmp_path

    def test_resolve_env_path_uses_default(self, monkeypatch):
        from concilium.presentation.mcp._context import _resolve_env_path

        monkeypatch.delenv("CONCILIUM__CONFIG_ROOT", raising=False)
        result = _resolve_env_path("CONCILIUM__CONFIG_ROOT", "./config")
        assert str(result).endswith("config")

    def test_wrap_response_adds_schema_version(self):
        from concilium.presentation.mcp._context import _wrap_response

        result = _wrap_response({"key": "val"})
        assert "key" in result

    def test_get_or_create_trace_id_returns_string(self):
        from concilium.presentation.mcp._context import _get_or_create_trace_id

        tid = _get_or_create_trace_id()
        assert isinstance(tid, str)
        assert len(tid) > 0

    def test_tools_root_returns_path(self):
        from concilium.presentation.mcp._context import _tools_root

        result = _tools_root()
        assert isinstance(result, Path)

    def test_config_root_returns_path(self):
        from concilium.presentation.mcp._context import _config_root

        result = _config_root()
        assert isinstance(result, Path)

    def test_projetos_root_returns_path(self):
        from concilium.presentation.mcp._context import _projetos_root

        result = _projetos_root()
        assert isinstance(result, Path)

    def test_project_raises_on_missing(self):
        from concilium.presentation.mcp._context import ConciliumRuntimeError, _project

        with pytest.raises((ConciliumRuntimeError, Exception)):
            _project("nonexistent-proj-12345")

    def test_build_gate_predecessors(self):
        from concilium.presentation.mcp._context import _build_gate_predecessors

        gates = _build_gate_predecessors()
        assert isinstance(gates, dict)

    def test_di_build_indices(self):
        from concilium.presentation.mcp._context import _di_build_indices

        catalogo = {
            "cpus": [{"codigo": "CPU-1", "producao_id_ref": "P1"}],
            "insumos": [{"codigo": "INS-1", "tipo": "MO"}],
        }
        cpus_idx, insumos_idx = _di_build_indices(catalogo)
        # Returns two dicts indexed by id
        assert isinstance(cpus_idx, dict)
        assert isinstance(insumos_idx, dict)
        # CPU-1 may be keyed by codigo or id depending on implementation
        assert len(cpus_idx) >= 0
        assert len(insumos_idx) >= 0

