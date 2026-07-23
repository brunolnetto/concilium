"""Unit tests for concilium.presentation.mcp.tools.spec.

Covers _schema_path, _validate_spec, _resolve_tributario, and the
criar_projeto_spec tool registered via register().
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

import concilium.presentation.mcp.rate_limit as _rate_limit_mod
from concilium.presentation.mcp.tools.formulario import register as register_formulario
from concilium.presentation.mcp.tools.spec import (
    _resolve_tributario,
    _schema_path,
    _validate_spec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_server() -> FastMCP:
    """Return a fresh FastMCP instance for tool registration."""
    return FastMCP("test-spec")


def _get_tools(server: FastMCP) -> dict[str, Any]:
    """Extract {name: callable} from a server's tool manager."""
    return {name: tool.fn for name, tool in server._tool_manager._tools.items()}


@pytest.fixture(autouse=True)
def reset_rate_limit_counters():
    """Clear the in-memory rate-limit counters before every test."""
    _rate_limit_mod._counters.clear()
    yield
    _rate_limit_mod._counters.clear()


# Minimal valid spec used in multiple tests
_VALID_SPEC = {
    "meta": {
        "nome": "Projeto Teste",
        "contexto_id": "ctx-test",
        "tipo_obra": "terraplenagem",
        "localizacao": "Fortaleza, CE",
        "coordenadas": {"lat": -3.71, "lng": -38.54},
        "data_inicio": "2026-01-01",
        "data_termino": "2026-06-30",
    },
    "escopos": [
        {
            "escopo_id": "esc-01",
            "nome": "Escopo Principal",
            "eap": [
                {
                    "item_id": "it-01",
                    "cpu_id": "CPU-ESCAV-001",
                    "descricao": "Escavacao",
                    "unidade": "m3",
                    "quantitativo": 100.0,
                    "ordem": 1,
                    "predecessores": [],
                }
            ],
        }
    ],
}


# ===========================================================================
# _schema_path
# ===========================================================================


class TestSchemaPath:
    """Tests for _schema_path()."""

    def test_returns_path_object(self):
        p = _schema_path()
        assert isinstance(p, Path)

    def test_ends_with_expected_suffix(self):
        p = _schema_path()
        assert p.name == "projeto_spec.schema.json"
        assert "config" in p.parts
        assert "schemas" in p.parts


# ===========================================================================
# _validate_spec
# ===========================================================================


class TestValidateSpec:
    """Tests for _validate_spec(spec)."""

    def test_returns_empty_list_when_no_errors(self):
        """When jsonschema validator reports no errors, returns []."""
        mock_validator_instance = MagicMock()
        mock_validator_instance.iter_errors.return_value = iter([])

        mock_validator_class = MagicMock(return_value=mock_validator_instance)

        mock_jsonschema = MagicMock()
        mock_jsonschema.Draft202012Validator = mock_validator_class

        schema_text = '{"type": "object"}'

        with (
            patch.dict("sys.modules", {"jsonschema": mock_jsonschema}),
            patch("concilium.presentation.mcp.tools.spec._schema_path") as mock_sp,
        ):
            mock_sp.return_value.read_text.return_value = schema_text
            result = _validate_spec({"any": "data"})

        assert result == []

    def test_returns_messages_when_errors_present(self):
        """When jsonschema validator yields errors, returns list of messages."""
        err1 = MagicMock()
        err1.message = "campo 'nome' obrigatorio"
        err2 = MagicMock()
        err2.message = "tipo inválido"

        mock_validator_instance = MagicMock()
        mock_validator_instance.iter_errors.return_value = iter([err1, err2])

        mock_validator_class = MagicMock(return_value=mock_validator_instance)

        mock_jsonschema = MagicMock()
        mock_jsonschema.Draft202012Validator = mock_validator_class

        with (
            patch.dict("sys.modules", {"jsonschema": mock_jsonschema}),
            patch("concilium.presentation.mcp.tools.spec._schema_path") as mock_sp,
        ):
            mock_sp.return_value.read_text.return_value = '{"type": "object"}'
            result = _validate_spec({})

        assert "campo 'nome' obrigatorio" in result
        assert "tipo inválido" in result

    def test_importerror_returns_empty_list(self):
        """When jsonschema is not installed (ImportError), returns [] silently."""
        import builtins

        real_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "jsonschema":
                raise ImportError("No module named 'jsonschema'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_mock_import):
            result = _validate_spec({"any": "data"})

        assert result == []


# ===========================================================================
# _resolve_tributario
# ===========================================================================


class TestResolveTributario:
    """Tests for _resolve_tributario(meta, rt)."""

    def _mock_rt(self, jurisdicao_data: dict | None = None, raise_exc: bool = False):
        rt = MagicMock()
        if raise_exc:
            rt.load_jurisdicao.side_effect = ValueError("jurisdicao not found")
        else:
            rt.load_jurisdicao.return_value = jurisdicao_data or {}
        return rt

    def test_all_fields_present_no_lookup(self):
        """When all 4 fields are already in regime_tributario, no lookup is made."""
        meta = {
            "regime_tributario": {
                "iss": 0.03,
                "pis": 0.005,
                "cofins": 0.02,
                "cprb": 0.04,
            }
        }
        rt = self._mock_rt()
        result = _resolve_tributario(meta, rt)

        assert result["iss"] == 0.03
        assert result["pis"] == 0.005
        assert result["cofins"] == 0.02
        assert result["cprb"] == 0.04
        rt.load_jurisdicao.assert_not_called()

    def test_missing_fields_uses_br_defaults(self):
        """When regime_tributario is empty, BR defaults are applied."""
        meta = {"regime_tributario": {}}
        rt = self._mock_rt(jurisdicao_data={})
        result = _resolve_tributario(meta, rt)

        assert result["iss"] == 0.05
        assert result["pis"] == 0.0065
        assert result["cofins"] == 0.03
        assert result["cprb"] == 0.045

    def test_no_regime_tributario_key_uses_defaults(self):
        """When meta has no regime_tributario key, BR defaults are applied."""
        meta: dict = {}
        rt = self._mock_rt()
        result = _resolve_tributario(meta, rt)

        assert result["iss"] == 0.05
        assert result["pis"] == 0.0065
        assert result["cofins"] == 0.03
        assert result["cprb"] == 0.045

    def test_jurisdicao_id_triggers_lookup_and_uses_aliquotas(self):
        """When jurisdicao_id is present, loads jurisdiction and uses its aliquotas."""
        jur_data = {
            "motor_tributario_bdi": {
                "aliquotas": {
                    "ISS": 0.02,
                    "PIS": 0.001,
                    "COFINS": 0.01,
                    "CPRB": 0.02,
                }
            }
        }
        meta = {"regime_tributario": {"jurisdicao_id": "BR-CE"}}
        rt = self._mock_rt(jurisdicao_data=jur_data)

        result = _resolve_tributario(meta, rt)

        rt.load_jurisdicao.assert_called_once_with("BR-CE")
        assert result["iss"] == 0.02
        assert result["pis"] == 0.001
        assert result["cofins"] == 0.01
        assert result["cprb"] == 0.02
        # jurisdicao_id should be popped from result
        assert "jurisdicao_id" not in result

    def test_jurisdicao_load_raises_falls_to_defaults(self):
        """When rt.load_jurisdicao raises, silently falls back to BR defaults."""
        meta = {"regime_tributario": {"jurisdicao_id": "BR-INVALID"}}
        rt = self._mock_rt(raise_exc=True)

        result = _resolve_tributario(meta, rt)

        assert result["iss"] == 0.05
        assert result["cofins"] == 0.03
        assert "jurisdicao_id" not in result

    def test_partial_fields_in_spec_respected(self):
        """When only some fields set in spec, missing ones are filled from jurisdiction."""
        jur_data = {"motor_tributario_bdi": {"aliquotas": {"ISS": 0.02, "PIS": 0.001, "COFINS": 0.01, "CPRB": 0.02}}}
        meta = {
            "regime_tributario": {
                "jurisdicao_id": "BR-CE",
                "iss": 0.035,  # explicitly set
            }
        }
        rt = self._mock_rt(jurisdicao_data=jur_data)

        result = _resolve_tributario(meta, rt)

        # Explicitly set value preserved
        assert result["iss"] == 0.035
        # Others filled from jurisdiction
        assert result["pis"] == 0.001
        assert result["cofins"] == 0.01
        assert result["cprb"] == 0.02


# ===========================================================================
# criar_projeto_spec (registered tool)
# ===========================================================================


@pytest.fixture()
def _base_mocks(tmp_path):
    """Return a dict of common mock objects used across tool tests."""
    mock_ps = MagicMock()
    mock_ps.plano_id = "plan-001"

    mock_es = MagicMock()
    mock_es.create_plan.return_value = mock_ps

    mock_root = MagicMock()
    mock_root.name = "proj-spec-001"

    mock_store = MagicMock()
    mock_store.root = mock_root
    mock_store.create_escopo.return_value = mock_es

    mock_r = MagicMock()
    mock_r.has_errors = False
    mock_r.validacoes = []

    mock_coord = MagicMock()
    mock_coord.avancar_plano.return_value = mock_r

    mock_contexto = MagicMock()
    mock_contexto.referencia_id = "ref-123"

    mock_rt = MagicMock()
    mock_rt.load_contexto.return_value = mock_contexto

    return {
        "tmp_path": tmp_path,
        "mock_ps": mock_ps,
        "mock_es": mock_es,
        "mock_root": mock_root,
        "mock_store": mock_store,
        "mock_r": mock_r,
        "mock_coord": mock_coord,
        "mock_contexto": mock_contexto,
        "mock_rt": mock_rt,
    }


def _make_tool_with_patches(tmp_path, mock_rt, mock_coord, mock_store, extra_patches=None):
    """Register spec tool on a fresh server with all infra patched; return callable."""
    server = _make_server()
    register_formulario(server)
    tool = _get_tools(server)["criar_projeto"]

    patches = {
        "concilium.presentation.mcp.tools.formulario._runtime": mock_rt,
        "concilium.presentation.mcp.tools.formulario._projetos_root": MagicMock(return_value=tmp_path),
        "concilium.presentation.mcp.tools.formulario._lifecycle_coordinator": MagicMock(return_value=mock_coord),
        "concilium.presentation.mcp.tools.formulario._wrap_response": MagicMock(side_effect=lambda d: d),
        "concilium.infrastructure.storage.project.ProjectStore.init": MagicMock(return_value=mock_store),
    }
    if extra_patches:
        patches.update(extra_patches)
    return tool, patches


class TestCriarProjetoSpec:
    """Tests for the criar_projeto_spec MCP tool."""

    # -----------------------------------------------------------------------
    # _validate_spec errors → early return
    # -----------------------------------------------------------------------

    def test_invalid_spec_returns_erro(self, _base_mocks):
        """When _validate_spec returns errors, tool returns erro without touching infra."""
        server = _make_server()
        register_formulario(server)
        tool = _get_tools(server)["criar_projeto"]

        with (
            patch(
                "concilium.presentation.mcp.tools.spec._validate_spec",
                return_value=["campo obrigatorio faltando"],
            ),
            patch("concilium.presentation.mcp.tools.formulario._runtime") as mock_rt_fn,
            patch(
                "concilium.presentation.mcp.tools.formulario._wrap_response",
                side_effect=lambda d: d,
            ),
        ):
            result = tool(spec={"meta": {}, "escopos": []})

        assert "erro" in result
        assert "Spec inválido" in result["erro"]
        assert "campo obrigatorio faltando" in result["detalhes"]
        mock_rt_fn.assert_not_called()

    def test_invalid_spec_truncates_to_10_errors(self, _base_mocks):
        """detalhes is capped at 10 entries even with many errors."""
        server = _make_server()
        register_formulario(server)
        tool = _get_tools(server)["criar_projeto"]

        erros = [f"erro {i}" for i in range(20)]

        with (
            patch(
                "concilium.presentation.mcp.tools.spec._validate_spec",
                return_value=erros,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._wrap_response",
                side_effect=lambda d: d,
            ),
        ):
            result = tool(spec={})

        assert len(result["detalhes"]) == 10

    # -----------------------------------------------------------------------
    # Invalid contexto_id
    # -----------------------------------------------------------------------

    def test_invalid_contexto_id_returns_erro(self, _base_mocks):
        """When rt.load_contexto raises, returns erro with contexto_id message."""
        server = _make_server()
        register_formulario(server)
        tool = _get_tools(server)["criar_projeto"]

        mock_rt = MagicMock()
        mock_rt.load_contexto.side_effect = ValueError("contexto not found")

        with (
            patch(
                "concilium.presentation.mcp.tools.spec._validate_spec",
                return_value=[],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._runtime",
                return_value=mock_rt,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._wrap_response",
                side_effect=lambda d: d,
            ),
        ):
            result = tool(spec=_VALID_SPEC)

        assert "erro" in result
        assert "contexto_id" in result["erro"]

    # -----------------------------------------------------------------------
    # Successful single escopo, no cronograma_spec
    # -----------------------------------------------------------------------

    def test_success_single_escopo_no_cronograma(self, _base_mocks, tmp_path):
        """Single escopo with no cronograma_spec succeeds; proxima_skill_sugerida set."""
        mocks = _base_mocks
        tool, patches = _make_tool_with_patches(
            tmp_path,
            mock_rt=MagicMock(return_value=mocks["mock_rt"]),
            mock_coord=mocks["mock_coord"],
            mock_store=mocks["mock_store"],
        )

        with (
            patch(
                "concilium.presentation.mcp.tools.spec._validate_spec",
                return_value=[],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._runtime",
                return_value=mocks["mock_rt"],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._projetos_root",
                return_value=tmp_path,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._lifecycle_coordinator",
                return_value=mocks["mock_coord"],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._wrap_response",
                side_effect=lambda d: d,
            ),
            patch(
                "concilium.infrastructure.storage.project.ProjectStore.init",
                return_value=mocks["mock_store"],
            ),
        ):
            result = tool(spec=_VALID_SPEC)

        assert "project_id" in result
        assert len(result["escopos"]) == 1
        assert result["escopos"][0]["status_skill_01"] == "OK"
        assert result["proxima_skill_sugerida"] == "02-produtividade-climatica"
        assert "tributario_efetivo" in result

    # -----------------------------------------------------------------------
    # Successful escopo with cronograma_spec
    # -----------------------------------------------------------------------

    def test_success_escopo_with_cronograma_spec(self, _base_mocks, tmp_path):
        """Escopo with cronograma_spec injects _cronograma_spec into inputs_01."""
        mocks = _base_mocks

        spec_with_cron = {
            "meta": _VALID_SPEC["meta"],
            "escopos": [
                {
                    **_VALID_SPEC["escopos"][0],
                    "cronograma": [{"item_id": "it-01", "n_equipes": 2, "producao_diaria": 50.0}],
                }
            ],
        }

        with (
            patch(
                "concilium.presentation.mcp.tools.spec._validate_spec",
                return_value=[],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._runtime",
                return_value=mocks["mock_rt"],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._projetos_root",
                return_value=tmp_path,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._lifecycle_coordinator",
                return_value=mocks["mock_coord"],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._wrap_response",
                side_effect=lambda d: d,
            ),
            patch(
                "concilium.infrastructure.storage.project.ProjectStore.init",
                return_value=mocks["mock_store"],
            ),
        ):
            server = _make_server()
            register_formulario(server)
            tool = _get_tools(server)["criar_projeto"]
            result = tool(spec=spec_with_cron)

        assert result["escopos"][0]["status_skill_01"] == "OK"
        # cronograma_spec should have been added to inputs
        call_kwargs = mocks["mock_coord"].avancar_plano.call_args
        inputs_passed = call_kwargs[1]["inputs"] if call_kwargs[1] else call_kwargs[0][3]
        assert "_cronograma_spec" in inputs_passed

    # -----------------------------------------------------------------------
    # Escopo creation failure
    # -----------------------------------------------------------------------

    def test_escopo_creation_failure_returns_erro(self, _base_mocks, tmp_path):
        """When store.create_escopo raises, tool returns erro immediately."""
        mocks = _base_mocks
        mocks["mock_store"].create_escopo.side_effect = RuntimeError("disk error")

        with (
            patch(
                "concilium.presentation.mcp.tools.spec._validate_spec",
                return_value=[],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._runtime",
                return_value=mocks["mock_rt"],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._projetos_root",
                return_value=tmp_path,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._lifecycle_coordinator",
                return_value=mocks["mock_coord"],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._wrap_response",
                side_effect=lambda d: d,
            ),
            patch(
                "concilium.infrastructure.storage.project.ProjectStore.init",
                return_value=mocks["mock_store"],
            ),
        ):
            server = _make_server()
            register_formulario(server)
            tool = _get_tools(server)["criar_projeto"]
            result = tool(spec=_VALID_SPEC)

        assert "erro" in result
        assert "esc-01" in result["erro"]

    # -----------------------------------------------------------------------
    # Coordinator raises exception
    # -----------------------------------------------------------------------

    def test_coordinator_raises_exception(self, _base_mocks, tmp_path):
        """When coord.avancar_plano raises, status_skill_01=ERRO with EXCECAO code."""
        mocks = _base_mocks
        mocks["mock_coord"].avancar_plano.side_effect = ValueError("pipeline error!")

        with (
            patch(
                "concilium.presentation.mcp.tools.spec._validate_spec",
                return_value=[],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._runtime",
                return_value=mocks["mock_rt"],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._projetos_root",
                return_value=tmp_path,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._lifecycle_coordinator",
                return_value=mocks["mock_coord"],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._wrap_response",
                side_effect=lambda d: d,
            ),
            patch(
                "concilium.infrastructure.storage.project.ProjectStore.init",
                return_value=mocks["mock_store"],
            ),
        ):
            server = _make_server()
            register_formulario(server)
            tool = _get_tools(server)["criar_projeto"]
            result = tool(spec=_VALID_SPEC)

        assert result["escopos"][0]["status_skill_01"] == "ERRO"
        erros = result["escopos"][0]["erros"]
        assert any(e["codigo"] == "EXCECAO" for e in erros)
        assert any("pipeline error!" in e["mensagem"] for e in erros)
        # proxima_skill_sugerida should be None since not all succeeded
        assert result["proxima_skill_sugerida"] is None

    # -----------------------------------------------------------------------
    # Coordinator returns has_errors=True
    # -----------------------------------------------------------------------

    def test_coordinator_has_errors_true(self, _base_mocks, tmp_path):
        """When r.has_errors is True, status_skill_01=ERRO with validation errors."""
        mocks = _base_mocks

        val1 = MagicMock()
        val1.codigo = "VAL-001"
        val1.mensagem = "cpu_id invalido"
        val1.status = "ERRO"

        mocks["mock_r"].has_errors = True
        mocks["mock_r"].validacoes = [val1]

        with (
            patch(
                "concilium.presentation.mcp.tools.spec._validate_spec",
                return_value=[],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._runtime",
                return_value=mocks["mock_rt"],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._projetos_root",
                return_value=tmp_path,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._lifecycle_coordinator",
                return_value=mocks["mock_coord"],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._wrap_response",
                side_effect=lambda d: d,
            ),
            patch(
                "concilium.infrastructure.storage.project.ProjectStore.init",
                return_value=mocks["mock_store"],
            ),
        ):
            server = _make_server()
            register_formulario(server)
            tool = _get_tools(server)["criar_projeto"]
            result = tool(spec=_VALID_SPEC)

        assert result["escopos"][0]["status_skill_01"] == "ERRO"
        erros = result["escopos"][0]["erros"]
        assert any(e["codigo"] == "VAL-001" for e in erros)
        assert result["proxima_skill_sugerida"] is None

    # -----------------------------------------------------------------------
    # Multiple escopos — partial failure
    # -----------------------------------------------------------------------

    def test_partial_failure_across_multiple_escopos(self, _base_mocks, tmp_path):
        """If one escopo fails and another succeeds, proxima_skill_sugerida is None."""
        mocks = _base_mocks

        spec_two_escopos = {
            "meta": _VALID_SPEC["meta"],
            "escopos": [
                {
                    "escopo_id": "esc-01",
                    "nome": "Escopo Um",
                    "eap": _VALID_SPEC["escopos"][0]["eap"],
                },
                {
                    "escopo_id": "esc-02",
                    "nome": "Escopo Dois",
                    "eap": _VALID_SPEC["escopos"][0]["eap"],
                },
            ],
        }

        call_count = {"n": 0}

        def coord_side_effect(skill_id, store, ps, inputs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First escopo: success
                r = MagicMock()
                r.has_errors = False
                r.validacoes = []
                return r
            else:
                # Second escopo: raises
                raise RuntimeError("second escopo failed")

        mocks["mock_coord"].avancar_plano.side_effect = coord_side_effect

        # Need two plan objects
        mock_ps2 = MagicMock()
        mock_ps2.plano_id = "plan-002"
        mock_es2 = MagicMock()
        mock_es2.create_plan.return_value = mock_ps2

        escopo_call_count = {"n": 0}

        def create_escopo_side_effect(**kwargs):
            escopo_call_count["n"] += 1
            if escopo_call_count["n"] == 1:
                return mocks["mock_es"]
            return mock_es2

        mocks["mock_store"].create_escopo.side_effect = create_escopo_side_effect

        with (
            patch(
                "concilium.presentation.mcp.tools.spec._validate_spec",
                return_value=[],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._runtime",
                return_value=mocks["mock_rt"],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._projetos_root",
                return_value=tmp_path,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._lifecycle_coordinator",
                return_value=mocks["mock_coord"],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._wrap_response",
                side_effect=lambda d: d,
            ),
            patch(
                "concilium.infrastructure.storage.project.ProjectStore.init",
                return_value=mocks["mock_store"],
            ),
        ):
            server = _make_server()
            register_formulario(server)
            tool = _get_tools(server)["criar_projeto"]
            result = tool(spec=spec_two_escopos)

        assert len(result["escopos"]) == 2
        assert result["escopos"][0]["status_skill_01"] == "OK"
        assert result["escopos"][1]["status_skill_01"] == "ERRO"
        # Not all succeed → proxima_skill_sugerida must be None
        assert result["proxima_skill_sugerida"] is None

    # -----------------------------------------------------------------------
    # proxima_skill_sugerida only when ALL escopos succeed
    # -----------------------------------------------------------------------

    def test_proxima_skill_sugerida_only_when_all_succeed(self, _base_mocks, tmp_path):
        """proxima_skill_sugerida is set iff all escopos have status_skill_01=OK."""
        mocks = _base_mocks

        spec_two = {
            "meta": _VALID_SPEC["meta"],
            "escopos": [
                {
                    "escopo_id": "esc-A",
                    "nome": "Escopo A",
                    "eap": _VALID_SPEC["escopos"][0]["eap"],
                },
                {
                    "escopo_id": "esc-B",
                    "nome": "Escopo B",
                    "eap": _VALID_SPEC["escopos"][0]["eap"],
                },
            ],
        }

        mock_ps_b = MagicMock()
        mock_ps_b.plano_id = "plan-B"
        mock_es_b = MagicMock()
        mock_es_b.create_plan.return_value = mock_ps_b

        create_call = {"n": 0}

        def create_escopo_side_effect(**kwargs):
            create_call["n"] += 1
            if create_call["n"] == 1:
                return mocks["mock_es"]
            return mock_es_b

        mocks["mock_store"].create_escopo.side_effect = create_escopo_side_effect

        with (
            patch(
                "concilium.presentation.mcp.tools.spec._validate_spec",
                return_value=[],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._runtime",
                return_value=mocks["mock_rt"],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._projetos_root",
                return_value=tmp_path,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._lifecycle_coordinator",
                return_value=mocks["mock_coord"],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._wrap_response",
                side_effect=lambda d: d,
            ),
            patch(
                "concilium.infrastructure.storage.project.ProjectStore.init",
                return_value=mocks["mock_store"],
            ),
        ):
            server = _make_server()
            register_formulario(server)
            tool = _get_tools(server)["criar_projeto"]
            result = tool(spec=spec_two)

        assert len(result["escopos"]) == 2
        assert all(e["status_skill_01"] == "OK" for e in result["escopos"])
        assert result["proxima_skill_sugerida"] == "02-produtividade-climatica"

    # -----------------------------------------------------------------------
    # regime_trabalho defaults
    # -----------------------------------------------------------------------

    def test_regime_trabalho_defaults_applied(self, _base_mocks, tmp_path):
        """When regime_trabalho is absent in meta, defaults dias=6 horas=8 are used."""
        mocks = _base_mocks

        spec_no_regime = {
            "meta": {k: v for k, v in _VALID_SPEC["meta"].items() if k != "regime_trabalho"},
            "escopos": _VALID_SPEC["escopos"],
        }

        with (
            patch(
                "concilium.presentation.mcp.tools.spec._validate_spec",
                return_value=[],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._runtime",
                return_value=mocks["mock_rt"],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._projetos_root",
                return_value=tmp_path,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._lifecycle_coordinator",
                return_value=mocks["mock_coord"],
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._wrap_response",
                side_effect=lambda d: d,
            ),
            patch(
                "concilium.infrastructure.storage.project.ProjectStore.init",
                return_value=mocks["mock_store"],
            ),
        ):
            server = _make_server()
            register_formulario(server)
            tool = _get_tools(server)["criar_projeto"]
            result = tool(spec=spec_no_regime)

        # Should succeed — not error on missing regime_trabalho
        assert "escopos" in result
        call_kwargs = mocks["mock_store"].create_escopo.call_args[1]
        assert call_kwargs["dias_semana"] == 6
        assert call_kwargs["horas_dia"] == 8



# ─── MCP spec tool ───────────────────────────────────────────────────────────


class TestMcpSpecTool:
    """ADR-116 F5: criar_projeto_spec absorvida em criar_projeto(spec=...) de formulario.py."""

    def test_register_adds_criar_projeto(self):
        from mcp.server.fastmcp import FastMCP

        from concilium.presentation.mcp.tools.formulario import register

        server = FastMCP("test")
        register(server)
        names = list(server._tool_manager._tools.keys())
        assert "criar_projeto" in names  # consolidado de criar_projeto_formulario + criar_projeto_spec

    def test_criar_projeto_spec_mode_registered(self):
        from mcp.server.fastmcp import FastMCP

        from concilium.presentation.mcp.tools.formulario import register

        server = FastMCP("test")
        register(server)
        tool = server._tool_manager._tools.get("criar_projeto")
        assert tool is not None



