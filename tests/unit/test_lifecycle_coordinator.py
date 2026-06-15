"""Unit tests for LifecycleCoordinator.

Covers:
- __init__: stores runtime reference
- avancar_plano: force_data_gate=True fires _audit_data_governance
- avancar_plano: force_data_gate=False skips audit
- avancar_plano: delegates to runtime.run_skill_on_plano and forwards return value
- _inject_project_catalog_layers: merges insumos_override.json when present
- _inject_project_catalog_layers: skips merge when key already in inputs
- _inject_project_catalog_layers: continues without error on absent override file
- _inject_project_catalog_layers: continues without error on unparseable JSON
- _inject_project_catalog_layers: continues without error on non-dict JSON
- _inject_project_catalog_layers: injects jurisdicao_id from contexto via enriched contexto_id
- _inject_project_catalog_layers: injects jurisdicao_id from contexto via project.meta contexto_id
- _inject_project_catalog_layers: skips jurisdicao_id injection when already in inputs
- _inject_project_catalog_layers: silently swallows errors from load_contexto
- _audit_data_governance: calls load_catalogo + load_and_audit_catalog for snapshot_catalogo_id
- _audit_data_governance: calls only load_and_audit_catalog for contexto_id (no snapshot)
- _audit_data_governance: skips audit entirely when neither snapshot nor contexto_id present
- _audit_data_governance: prefers project.meta.contexto_id when escopo_meta has none
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from concilium.application.orchestrators.lifecycle_coordinator import LifecycleCoordinator
from concilium.infrastructure.storage.project import ProjectStore


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _make_project_store(tmp_path: Path, meta: dict | None = None) -> ProjectStore:
    """Build a minimal ProjectStore backed by a real tmp directory."""
    root = tmp_path / "project"
    root.mkdir(parents=True, exist_ok=True)
    effective_meta = meta if meta is not None else {}
    (root / ProjectStore.META_FILE).write_text(
        json.dumps(effective_meta, ensure_ascii=False), encoding="utf-8"
    )
    return ProjectStore(root)


def _make_plano_store(escopo_meta: dict | None = None) -> Any:
    """Build a minimal fake PlanoStore with an escopo_store.meta dict."""
    store = MagicMock()
    store.escopo_store.meta = escopo_meta if escopo_meta is not None else {}
    return store


def _make_runtime() -> MagicMock:
    """Return a fresh MagicMock that plays the Runtime role."""
    return MagicMock()


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_stores_runtime(self):
        runtime = _make_runtime()
        coordinator = LifecycleCoordinator(runtime)
        assert coordinator.runtime is runtime


# ---------------------------------------------------------------------------
# avancar_plano — delegation and return value
# ---------------------------------------------------------------------------


class TestAvancarPlano:
    def test_returns_skill_result(self, tmp_path):
        runtime = _make_runtime()
        expected = MagicMock(name="SkillResult")
        runtime.run_skill_on_plano.return_value = expected

        project = _make_project_store(tmp_path)
        plano = _make_plano_store()

        coordinator = LifecycleCoordinator(runtime)
        result = coordinator.avancar_plano(
            "skill-01", project, plano, inputs={}, force_data_gate=False
        )

        assert result is expected

    def test_calls_run_skill_with_correct_skill_id(self, tmp_path):
        runtime = _make_runtime()
        project = _make_project_store(tmp_path)
        plano = _make_plano_store()

        coordinator = LifecycleCoordinator(runtime)
        coordinator.avancar_plano("skill-42", project, plano, force_data_gate=False)

        call_args = runtime.run_skill_on_plano.call_args
        assert call_args[0][0] == "skill-42"
        assert call_args[0][1] is project
        assert call_args[0][2] is plano

    def test_inputs_forwarded_as_normalized(self, tmp_path):
        runtime = _make_runtime()
        project = _make_project_store(tmp_path)
        plano = _make_plano_store()

        inputs = {"foo": "bar"}
        coordinator = LifecycleCoordinator(runtime)
        coordinator.avancar_plano("s", project, plano, inputs=inputs, force_data_gate=False)

        call_kwargs = runtime.run_skill_on_plano.call_args[1]
        assert "inputs" in call_kwargs
        assert call_kwargs["inputs"]["foo"] == "bar"

    def test_none_inputs_produces_empty_dict(self, tmp_path):
        runtime = _make_runtime()
        project = _make_project_store(tmp_path)
        plano = _make_plano_store()

        coordinator = LifecycleCoordinator(runtime)
        coordinator.avancar_plano("s", project, plano, inputs=None, force_data_gate=False)

        call_kwargs = runtime.run_skill_on_plano.call_args[1]
        assert isinstance(call_kwargs["inputs"], dict)


# ---------------------------------------------------------------------------
# avancar_plano — force_data_gate
# ---------------------------------------------------------------------------


class TestForceDataGate:
    def test_force_data_gate_true_calls_audit(self, tmp_path):
        runtime = _make_runtime()
        project = _make_project_store(tmp_path)
        # snapshot_catalogo_id present so audit returns early after load_catalogo
        plano = _make_plano_store({"snapshot_catalogo_id": "snap-123"})

        coordinator = LifecycleCoordinator(runtime)

        with patch(
            "concilium.application.orchestrators.lifecycle_coordinator.load_and_audit_catalog"
        ) as mock_audit:
            coordinator.avancar_plano("s", project, plano, force_data_gate=True)

        runtime.load_catalogo.assert_called_once_with("snap-123")
        mock_audit.assert_called_once()

    def test_force_data_gate_false_skips_audit(self, tmp_path):
        runtime = _make_runtime()
        project = _make_project_store(tmp_path)
        plano = _make_plano_store({"snapshot_catalogo_id": "snap-123"})

        coordinator = LifecycleCoordinator(runtime)

        with patch(
            "concilium.application.orchestrators.lifecycle_coordinator.load_and_audit_catalog"
        ) as mock_audit:
            coordinator.avancar_plano("s", project, plano, force_data_gate=False)

        runtime.load_catalogo.assert_not_called()
        mock_audit.assert_not_called()


# ---------------------------------------------------------------------------
# _audit_data_governance
# ---------------------------------------------------------------------------


class TestAuditDataGovernance:
    def test_snapshot_catalogo_id_calls_load_catalogo_and_audit(self, tmp_path):
        runtime = _make_runtime()
        project = _make_project_store(tmp_path)
        plano = _make_plano_store({"snapshot_catalogo_id": "snap-abc"})

        coordinator = LifecycleCoordinator(runtime)
        with patch(
            "concilium.application.orchestrators.lifecycle_coordinator.load_and_audit_catalog"
        ) as mock_audit:
            coordinator._audit_data_governance(project, plano)

        runtime.load_catalogo.assert_called_once_with("snap-abc")
        mock_audit.assert_called_once_with(runtime, "snap-abc")

    def test_snapshot_catalogo_id_short_circuits_contexto_path(self, tmp_path):
        """When snapshot_catalogo_id present, contexto fallback must NOT run."""
        runtime = _make_runtime()
        project = _make_project_store(tmp_path, {"contexto_id": "ctx-999"})
        plano = _make_plano_store({"snapshot_catalogo_id": "snap-abc", "contexto_id": "ctx-999"})

        coordinator = LifecycleCoordinator(runtime)
        with patch(
            "concilium.application.orchestrators.lifecycle_coordinator.load_and_audit_catalog"
        ) as mock_audit:
            coordinator._audit_data_governance(project, plano)

        # load_and_audit_catalog must receive snap-abc, not ctx-999
        mock_audit.assert_called_once_with(runtime, "snap-abc")

    def test_contexto_id_in_escopo_meta_calls_audit(self, tmp_path):
        runtime = _make_runtime()
        project = _make_project_store(tmp_path)
        plano = _make_plano_store({"contexto_id": "ctx-111"})

        coordinator = LifecycleCoordinator(runtime)
        with patch(
            "concilium.application.orchestrators.lifecycle_coordinator.load_and_audit_catalog"
        ) as mock_audit:
            coordinator._audit_data_governance(project, plano)

        # load_catalogo should NOT be called (snapshot path skipped)
        runtime.load_catalogo.assert_not_called()
        mock_audit.assert_called_once_with(runtime, "ctx-111")

    def test_contexto_id_from_project_meta_fallback(self, tmp_path):
        runtime = _make_runtime()
        project = _make_project_store(tmp_path, {"contexto_id": "ctx-from-meta"})
        plano = _make_plano_store({})  # no contexto_id in escopo_meta

        coordinator = LifecycleCoordinator(runtime)
        with patch(
            "concilium.application.orchestrators.lifecycle_coordinator.load_and_audit_catalog"
        ) as mock_audit:
            coordinator._audit_data_governance(project, plano)

        mock_audit.assert_called_once_with(runtime, "ctx-from-meta")

    def test_no_snapshot_no_contexto_skips_audit(self, tmp_path):
        runtime = _make_runtime()
        project = _make_project_store(tmp_path, {})
        plano = _make_plano_store({})

        coordinator = LifecycleCoordinator(runtime)
        with patch(
            "concilium.application.orchestrators.lifecycle_coordinator.load_and_audit_catalog"
        ) as mock_audit:
            coordinator._audit_data_governance(project, plano)

        runtime.load_catalogo.assert_not_called()
        mock_audit.assert_not_called()


# ---------------------------------------------------------------------------
# _inject_project_catalog_layers — insumos_override
# ---------------------------------------------------------------------------


class TestInjectInsumos:
    def test_loads_override_from_file_when_absent_in_inputs(self, tmp_path):
        runtime = _make_runtime()
        project = _make_project_store(tmp_path)

        # Create a valid overrides/insumos_override.json
        overrides_dir = project.root / "overrides"
        overrides_dir.mkdir(parents=True, exist_ok=True)
        override_data = {"item-01": {"preco": 100.0}}
        (overrides_dir / "insumos_override.json").write_text(
            json.dumps(override_data), encoding="utf-8"
        )

        coordinator = LifecycleCoordinator(runtime)
        result = coordinator._inject_project_catalog_layers(project, {})

        assert "insumos_override" in result
        assert result["insumos_override"] == override_data

    def test_does_not_override_existing_key_in_inputs(self, tmp_path):
        runtime = _make_runtime()
        project = _make_project_store(tmp_path)

        overrides_dir = project.root / "overrides"
        overrides_dir.mkdir(parents=True, exist_ok=True)
        (overrides_dir / "insumos_override.json").write_text(
            json.dumps({"disk-value": 1}), encoding="utf-8"
        )

        caller_value = {"caller-value": 99}
        coordinator = LifecycleCoordinator(runtime)
        result = coordinator._inject_project_catalog_layers(project, {"insumos_override": caller_value})

        # Caller-supplied value must win
        assert result["insumos_override"] is caller_value

    def test_absent_override_file_is_silently_ignored(self, tmp_path):
        runtime = _make_runtime()
        project = _make_project_store(tmp_path)
        # No overrides directory at all

        coordinator = LifecycleCoordinator(runtime)
        result = coordinator._inject_project_catalog_layers(project, {"x": 1})

        assert "insumos_override" not in result
        assert result["x"] == 1

    def test_unparseable_json_does_not_raise(self, tmp_path):
        runtime = _make_runtime()
        project = _make_project_store(tmp_path)

        overrides_dir = project.root / "overrides"
        overrides_dir.mkdir(parents=True, exist_ok=True)
        (overrides_dir / "insumos_override.json").write_text("NOT JSON", encoding="utf-8")

        coordinator = LifecycleCoordinator(runtime)
        # Must not raise
        result = coordinator._inject_project_catalog_layers(project, {})
        assert "insumos_override" not in result

    def test_non_dict_json_does_not_merge(self, tmp_path):
        runtime = _make_runtime()
        project = _make_project_store(tmp_path)

        overrides_dir = project.root / "overrides"
        overrides_dir.mkdir(parents=True, exist_ok=True)
        # Valid JSON but not a dict
        (overrides_dir / "insumos_override.json").write_text("[1, 2, 3]", encoding="utf-8")

        coordinator = LifecycleCoordinator(runtime)
        result = coordinator._inject_project_catalog_layers(project, {})
        assert "insumos_override" not in result


# ---------------------------------------------------------------------------
# _inject_project_catalog_layers — jurisdicao_id injection
# ---------------------------------------------------------------------------


class TestInjectJurisdicao:
    def _contexto_with_jurisdicao(self, jurisdicao_id: str) -> MagicMock:
        ctx = MagicMock()
        ctx.jurisdicao_id = jurisdicao_id
        return ctx

    def test_injects_jurisdicao_from_enriched_contexto_id(self, tmp_path):
        runtime = _make_runtime()
        runtime.load_contexto.return_value = self._contexto_with_jurisdicao("jur-ce")

        project = _make_project_store(tmp_path)
        coordinator = LifecycleCoordinator(runtime)

        result = coordinator._inject_project_catalog_layers(project, {"contexto_id": "ctx-abc"})

        runtime.load_contexto.assert_called_once_with("ctx-abc")
        assert result["jurisdicao_id"] == "jur-ce"

    def test_injects_jurisdicao_from_project_meta_contexto_id(self, tmp_path):
        runtime = _make_runtime()
        runtime.load_contexto.return_value = self._contexto_with_jurisdicao("jur-ba")

        project = _make_project_store(tmp_path, {"contexto_id": "ctx-from-meta"})
        coordinator = LifecycleCoordinator(runtime)

        result = coordinator._inject_project_catalog_layers(project, {})

        runtime.load_contexto.assert_called_once_with("ctx-from-meta")
        assert result["jurisdicao_id"] == "jur-ba"

    def test_skips_injection_when_jurisdicao_already_in_inputs(self, tmp_path):
        runtime = _make_runtime()
        project = _make_project_store(tmp_path, {"contexto_id": "ctx-x"})
        coordinator = LifecycleCoordinator(runtime)

        result = coordinator._inject_project_catalog_layers(
            project, {"jurisdicao_id": "jur-existing"}
        )

        runtime.load_contexto.assert_not_called()
        assert result["jurisdicao_id"] == "jur-existing"

    def test_no_contexto_id_anywhere_skips_jurisdicao(self, tmp_path):
        runtime = _make_runtime()
        project = _make_project_store(tmp_path, {})
        coordinator = LifecycleCoordinator(runtime)

        result = coordinator._inject_project_catalog_layers(project, {})

        runtime.load_contexto.assert_not_called()
        assert "jurisdicao_id" not in result

    def test_load_contexto_error_is_silently_swallowed(self, tmp_path):
        runtime = _make_runtime()
        runtime.load_contexto.side_effect = RuntimeError("contexto not found")

        project = _make_project_store(tmp_path, {"contexto_id": "ctx-missing"})
        coordinator = LifecycleCoordinator(runtime)

        # Must not raise
        result = coordinator._inject_project_catalog_layers(project, {})
        assert "jurisdicao_id" not in result

    def test_enriched_contexto_id_takes_priority_over_project_meta(self, tmp_path):
        """contexto_id supplied in inputs overrides project.meta.contexto_id."""
        runtime = _make_runtime()
        runtime.load_contexto.return_value = self._contexto_with_jurisdicao("jur-from-input")

        project = _make_project_store(tmp_path, {"contexto_id": "ctx-from-meta"})
        coordinator = LifecycleCoordinator(runtime)

        result = coordinator._inject_project_catalog_layers(
            project, {"contexto_id": "ctx-from-input"}
        )

        # Should be called with the enriched/inputs contexto_id, not the meta one
        runtime.load_contexto.assert_called_once_with("ctx-from-input")
        assert result["jurisdicao_id"] == "jur-from-input"
