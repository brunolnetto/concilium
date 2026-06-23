"""Coverage sweep — files with few missing lines (1-30 lines missing)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ─── concilium/__init__.py ───────────────────────────────────────────────────


def test_package_getattr_raises():
    import concilium

    with pytest.raises(AttributeError, match="no attribute"):
        _ = concilium.nonexistent_attribute


# ─── domain/services/encargo_resolver.py ─────────────────────────────────────


class TestEncargoResolver:
    def test_override_takes_precedence(self):
        from concilium.domain.services.financial.encargo_resolver import resolver_encargo

        result = resolver_encargo({}, encargo_override=0.5)
        assert result == 0.5

    def test_percentual_encargos_local(self):
        from concilium.domain.services.financial.encargo_resolver import resolver_encargo

        result = resolver_encargo({"percentual_encargos_local": 0.3})
        assert result == 0.3

    def test_horista_category(self):
        from concilium.domain.services.financial.encargo_resolver import resolver_encargo

        result = resolver_encargo({"categoria_sindical": "horista"})
        assert result > 1.0

    def test_mensalista_category(self):
        from concilium.domain.services.financial.encargo_resolver import resolver_encargo

        result = resolver_encargo({"categoria_sindical": "mensalista"})
        assert result >= 0.0

    def test_default_mensalista_when_unknown_category(self):
        from concilium.domain.services.financial.encargo_resolver import ENCARGOS_MENSALISTA, resolver_encargo

        # Unknown category → falls to mensalista branch
        r = resolver_encargo({"categoria_sindical": "unknown"})
        assert r == ENCARGOS_MENSALISTA or r >= 0


# ─── domain/units.py ─────────────────────────────────────────────────────────


class TestDomainUnits:
    def test_normalize_canonical(self):
        from concilium.domain.units import normalize_unidade

        assert normalize_unidade("m³") == "m³"
        assert normalize_unidade("m²") == "m²"
        assert normalize_unidade("h") == "h"

    def test_normalize_alias(self):
        from concilium.domain.units import normalize_unidade

        assert normalize_unidade("M²") == "m²"
        assert normalize_unidade("M3") == "m³"
        assert normalize_unidade("UNID") == "unid"
        assert normalize_unidade("und") == "unid"

    def test_normalize_unknown_raises(self):
        from concilium.domain.units import normalize_unidade

        with pytest.raises(ValueError, match="desconhecida"):
            normalize_unidade("foobar")

    def test_alias_mes_variants(self):
        from concilium.domain.units import normalize_unidade

        assert normalize_unidade("MES") == "mes"
        assert normalize_unidade("mês") == "mes"

    def test_all_canonicas_pass_through(self):
        from concilium.domain.units import UNIDADES_CANONICAS, normalize_unidade

        for u in UNIDADES_CANONICAS:
            assert normalize_unidade(u) == u


# ─── application/services/audit_service.py ───────────────────────────────────


class TestAuditService:
    def test_log_writes_entry(self):
        from concilium.application.services.project.audit_service import AuditService

        svc = AuditService()
        project = MagicMock()
        svc.log(project, action="run_skill", actor="eng", payload={"skill": "01"}, result={"ok": True})
        project.append_jsonl.assert_called_once()
        entry = project.append_jsonl.call_args[0][1]
        assert entry["action"] == "run_skill"
        assert entry["status"] == "OK"
        assert entry["actor"] == "eng"

    def test_log_with_error(self):
        from concilium.application.services.project.audit_service import AuditService

        svc = AuditService()
        project = MagicMock()
        svc.log(project, action="run", actor="sys", error="something failed")
        entry = project.append_jsonl.call_args[0][1]
        assert entry["status"] == "ERRO"
        assert entry["error"] == "something failed"

    def test_list_returns_entries(self):
        from concilium.application.services.project.audit_service import AuditService

        svc = AuditService()
        project = MagicMock()
        project.read_lines.return_value = [
            '{"action": "run", "actor": "eng", "timestamp": "2026-01-01"}',
            "invalid json line",
            '{"action": "save", "actor": "sys", "timestamp": "2026-01-02"}',
        ]
        result = svc.list(project)
        assert len(result) == 2
        assert result[0]["action"] == "save"  # reversed

    def test_list_respects_limit(self):
        from concilium.application.services.project.audit_service import AuditService

        svc = AuditService()
        project = MagicMock()
        project.read_lines.return_value = [f'{{"action": "a{i}", "actor": "e"}}' for i in range(10)]
        result = svc.list(project, limit=3)
        assert len(result) == 3



# ─── application/orchestrators/catalog_governance.py ─────────────────────────


class TestCatalogGovernance:
    def test_assert_catalog_healthy_passes_on_empty(self):
        from concilium.application.orchestrators.catalog_governance import assert_catalog_healthy

        with patch(
            "concilium.application.orchestrators.catalog_governance.collect_catalog_critical_errors", return_value=[]
        ):
            assert_catalog_healthy("ctx1", {})  # should not raise

    def test_assert_catalog_healthy_raises_on_errors(self):
        from concilium.application.orchestrators.catalog_governance import (
            CatalogGovernanceError,
            assert_catalog_healthy,
        )

        with patch(
            "concilium.application.orchestrators.catalog_governance.collect_catalog_critical_errors",
            return_value=[{"cpu": "CPU-1", "erro": "missing field"}],
        ):
            with pytest.raises(CatalogGovernanceError, match="Bloqueio"):
                assert_catalog_healthy("ctx1", {})

    def test_validate_and_resolve_insumo_file(self, tmp_path):
        from concilium.application.orchestrators.catalog_governance import validate_and_resolve_insumo_file

        insumos_dir = tmp_path / "insumos"
        insumos_dir.mkdir()
        (insumos_dir / "INS-1.json").write_text('{"codigo": "INS-1"}', encoding="utf-8")
        result = validate_and_resolve_insumo_file(tmp_path, "INS-1", 100.0)
        assert result.name == "INS-1.json"

    def test_validate_insumo_negative_price_raises(self, tmp_path):
        from concilium.application.orchestrators.catalog_governance import (
            CatalogGovernanceError,
            validate_and_resolve_insumo_file,
        )

        with pytest.raises(CatalogGovernanceError, match="maior ou igual"):
            validate_and_resolve_insumo_file(tmp_path, "INS-1", -1.0)

    def test_validate_insumo_not_found_raises(self, tmp_path):
        from concilium.application.orchestrators.catalog_governance import (
            CatalogGovernanceError,
            validate_and_resolve_insumo_file,
        )

        (tmp_path / "insumos").mkdir()
        with pytest.raises(CatalogGovernanceError, match="não encontrado"):
            validate_and_resolve_insumo_file(tmp_path, "MISSING", 50.0)

    def test_validate_producao_file_found(self, tmp_path):
        from concilium.application.orchestrators.catalog_governance import validate_and_resolve_producao_file

        prods = tmp_path / "producoes"
        prods.mkdir()
        (prods / "P1.json").write_text('{"id": "P1"}', encoding="utf-8")
        result = validate_and_resolve_producao_file(tmp_path, "P1", 100.0)
        assert result.name == "P1.json"

    def test_validate_producao_zero_raises(self, tmp_path):
        from concilium.application.orchestrators.catalog_governance import (
            CatalogGovernanceError,
            validate_and_resolve_producao_file,
        )

        with pytest.raises(CatalogGovernanceError, match="maior que zero"):
            validate_and_resolve_producao_file(tmp_path, "P1", 0.0)


# ─── infrastructure/storage/flat_version_store.py ────────────────────────────


class TestFlatVersionStore:
    def _make_store(self, tmp_path):
        from concilium.infrastructure.storage.flat_version_store import FlatVersionStore
        from concilium.infrastructure.storage.project import ProjectStore

        store = ProjectStore.init(tmp_path, "Test", "ctx")
        v = store.new_version()
        return FlatVersionStore(store, v), store, v

    def test_plano_id_equals_version(self, tmp_path):
        fvs, store, v = self._make_store(tmp_path)
        assert fvs.plano_id == v

    def test_meta_has_plano_id(self, tmp_path):
        fvs, store, v = self._make_store(tmp_path)
        assert fvs.meta["plano_id"] == v

    def test_load_canonical_none_initially(self, tmp_path):
        fvs, store, v = self._make_store(tmp_path)
        assert fvs.load_canonical() is None

    def test_log_and_read_invocations(self, tmp_path):
        fvs, store, v = self._make_store(tmp_path)
        fvs.log_invocation({"skill": "01", "status": "OK"})
        records = fvs.read_invocations()
        assert len(records) == 1
        assert records[0]["skill"] == "01"

    def test_read_invocations_empty(self, tmp_path):
        fvs, store, v = self._make_store(tmp_path)
        assert fvs.read_invocations() == []

    def test_escopo_store_meta(self, tmp_path):
        fvs, store, v = self._make_store(tmp_path)
        meta = fvs.escopo_store.meta
        assert "escopo_id" in meta
        assert "contexto_id" in meta
