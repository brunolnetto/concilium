from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from concilium.presentation.mcp.tools.spec import _resolve_tributario, _validate_spec

# ---------------------------------------------------------------------------
# _validate_spec
# ---------------------------------------------------------------------------


def test_validate_spec_jsonschema_missing_returns_empty():
    """ImportError (jsonschema absent) must return []."""
    original = sys.modules.get("jsonschema")
    sys.modules["jsonschema"] = None  # type: ignore[assignment]
    try:
        result = _validate_spec({"any": "payload"})
    finally:
        if original is None:
            sys.modules.pop("jsonschema", None)
        else:
            sys.modules["jsonschema"] = original
    assert result == []


def test_validate_spec_schema_file_not_found_propagates():
    """FileNotFoundError is NOT swallowed — only ImportError is caught.

    The implementation only has `except ImportError`, so a missing schema file
    raises FileNotFoundError. This test documents that boundary explicitly.
    """
    nonexistent = Path("/tmp/does_not_exist_ever/schema.json")
    with patch("concilium.presentation.mcp.tools.spec._schema_path", return_value=nonexistent):
        with pytest.raises(FileNotFoundError):
            _validate_spec({"any": "payload"})


def test_validate_spec_with_mock_validator_returns_error_messages():
    """When jsonschema is importable and validator yields errors, return their messages."""
    fake_error_1 = MagicMock()
    fake_error_1.message = "field 'meta' is required"
    fake_error_2 = MagicMock()
    fake_error_2.message = "extra properties are not allowed"

    fake_validator_instance = MagicMock()
    fake_validator_instance.iter_errors.return_value = [fake_error_1, fake_error_2]

    fake_validator_cls = MagicMock(return_value=fake_validator_instance)

    fake_jsonschema = ModuleType("jsonschema")
    fake_jsonschema.Draft202012Validator = fake_validator_cls  # type: ignore[attr-defined]

    fake_schema_path = MagicMock()
    fake_schema_path.return_value.read_text.return_value = '{"type": "object"}'

    with (
        patch.dict(sys.modules, {"jsonschema": fake_jsonschema}),
        patch("concilium.presentation.mcp.tools.spec._schema_path", fake_schema_path),
    ):
        result = _validate_spec({"escopos": []})

    assert result == ["field 'meta' is required", "extra properties are not allowed"]


def test_validate_spec_with_mock_validator_no_errors_returns_empty():
    """When validator yields no errors, return []."""
    fake_validator_instance = MagicMock()
    fake_validator_instance.iter_errors.return_value = []

    fake_validator_cls = MagicMock(return_value=fake_validator_instance)

    fake_jsonschema = ModuleType("jsonschema")
    fake_jsonschema.Draft202012Validator = fake_validator_cls  # type: ignore[attr-defined]

    fake_schema_path = MagicMock()
    fake_schema_path.return_value.read_text.return_value = '{"type": "object"}'

    with (
        patch.dict(sys.modules, {"jsonschema": fake_jsonschema}),
        patch("concilium.presentation.mcp.tools.spec._schema_path", fake_schema_path),
    ):
        result = _validate_spec({"meta": {}, "escopos": []})

    assert result == []


# ---------------------------------------------------------------------------
# _resolve_tributario
# ---------------------------------------------------------------------------


def test_resolve_tributario_all_keys_present_no_defaults_no_rt_call():
    """When all 4 tax keys are already present, rt is never called and values are unchanged."""
    rt = MagicMock()
    meta = {
        "regime_tributario": {
            "iss": 0.02,
            "pis": 0.001,
            "cofins": 0.02,
            "cprb": 0.01,
        }
    }
    result = _resolve_tributario(meta, rt)
    rt.load_jurisdicao.assert_not_called()
    assert result == {"iss": 0.02, "pis": 0.001, "cofins": 0.02, "cprb": 0.01}


def test_resolve_tributario_jurisdicao_id_stripped():
    """jurisdicao_id must not appear in the returned dict."""
    rt = MagicMock()
    rt.load_jurisdicao.return_value = {}
    meta = {
        "regime_tributario": {
            "jurisdicao_id": "SP",
            "iss": 0.02,
            "pis": 0.001,
            "cofins": 0.02,
            "cprb": 0.01,
        }
    }
    result = _resolve_tributario(meta, rt)
    assert "jurisdicao_id" not in result


def test_resolve_tributario_missing_keys_no_jurisdicao_uses_br_defaults():
    """When tax keys are absent and no jurisdicao_id, BR defaults are applied."""
    rt = MagicMock()
    meta = {"regime_tributario": {}}
    result = _resolve_tributario(meta, rt)
    rt.load_jurisdicao.assert_not_called()
    assert result["iss"] == pytest.approx(0.05)
    assert result["pis"] == pytest.approx(0.0065)
    assert result["cofins"] == pytest.approx(0.03)
    assert result["cprb"] == pytest.approx(0.045)


def test_resolve_tributario_no_regime_tributario_key_uses_br_defaults():
    """When meta has no regime_tributario at all, BR defaults are applied."""
    rt = MagicMock()
    meta = {}
    result = _resolve_tributario(meta, rt)
    assert result["iss"] == pytest.approx(0.05)
    assert result["pis"] == pytest.approx(0.0065)
    assert result["cofins"] == pytest.approx(0.03)
    assert result["cprb"] == pytest.approx(0.045)


def test_resolve_tributario_jurisdicao_id_load_returns_data_uses_those_values():
    """When jurisdicao_id is given and load_jurisdicao returns alíquotas, they take precedence over BR defaults."""
    rt = MagicMock()
    rt.load_jurisdicao.return_value = {
        "motor_tributario_bdi": {
            "aliquotas": {
                "ISS": 0.03,
                "PIS": 0.002,
                "COFINS": 0.025,
                "CPRB": 0.04,
            }
        }
    }
    meta = {"regime_tributario": {"jurisdicao_id": "RJ"}}
    result = _resolve_tributario(meta, rt)
    rt.load_jurisdicao.assert_called_once_with("RJ")
    assert result["iss"] == pytest.approx(0.03)
    assert result["pis"] == pytest.approx(0.002)
    assert result["cofins"] == pytest.approx(0.025)
    assert result["cprb"] == pytest.approx(0.04)


def test_resolve_tributario_jurisdicao_id_load_raises_falls_back_to_defaults():
    """When load_jurisdicao raises any exception, BR defaults are used."""
    rt = MagicMock()
    rt.load_jurisdicao.side_effect = RuntimeError("service unavailable")
    meta = {"regime_tributario": {"jurisdicao_id": "BA"}}
    result = _resolve_tributario(meta, rt)
    assert result["iss"] == pytest.approx(0.05)
    assert result["pis"] == pytest.approx(0.0065)
    assert result["cofins"] == pytest.approx(0.03)
    assert result["cprb"] == pytest.approx(0.045)
