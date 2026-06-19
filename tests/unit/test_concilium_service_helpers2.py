"""Tests for _concilium_service_helpers to boost coverage."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


class TestValidateCpuData:
    def _call(self, **kwargs):
        from concilium.application.services._concilium_service_helpers import _validate_cpu_data

        data = {"codigo": "CPU-1", "descricao": "Test", "unidade": "m³", **kwargs}
        return _validate_cpu_data(data, "CPU-1", "motivo teste")

    def test_valid_passes(self):
        self._call()  # should not raise

    def test_missing_codigo_raises(self):
        from concilium.application.services._concilium_service_helpers import _validate_cpu_data

        with pytest.raises(ValueError, match="codigo"):
            _validate_cpu_data({"descricao": "x", "unidade": "m"}, "CPU-1", "m")

    def test_mismatched_codigo_raises(self):
        from concilium.application.services._concilium_service_helpers import _validate_cpu_data

        with pytest.raises(ValueError, match="coincidir"):
            _validate_cpu_data({"codigo": "CPU-2", "descricao": "x", "unidade": "m"}, "CPU-1", "m")

    def test_missing_descricao_raises(self):
        from concilium.application.services._concilium_service_helpers import _validate_cpu_data

        with pytest.raises(ValueError, match="descricao"):
            _validate_cpu_data({"codigo": "CPU-1", "unidade": "m"}, "CPU-1", "m")

    def test_missing_unidade_raises(self):
        from concilium.application.services._concilium_service_helpers import _validate_cpu_data

        with pytest.raises(ValueError, match="unidade"):
            _validate_cpu_data({"codigo": "CPU-1", "descricao": "x"}, "CPU-1", "m")

    def test_missing_motivo_raises(self):
        from concilium.application.services._concilium_service_helpers import _validate_cpu_data

        with pytest.raises(ValueError, match="motivo"):
            _validate_cpu_data({"codigo": "CPU-1", "descricao": "x", "unidade": "m"}, "CPU-1", "")

    def test_composicao_itens_not_list_raises(self):
        from concilium.application.services._concilium_service_helpers import _validate_cpu_data

        with pytest.raises(ValueError, match="lista"):
            _validate_cpu_data(
                {"codigo": "CPU-1", "descricao": "x", "unidade": "m", "composicao_itens": "not-a-list"}, "CPU-1", "m"
            )

    def test_composicao_itens_list_passes(self):
        self._call(composicao_itens=[{"id": "INS-1"}])  # should not raise


class TestEnrichHelpers:
    def test_build_prod_lookup_basic(self):
        from concilium.application.services._concilium_service_helpers import _build_prod_lookup

        prods = [{"id": "P1", "valor_horario": 10}, {"id": "P2", "valor_horario": 20}]
        lookup = _build_prod_lookup(prods)
        assert lookup["P1"]["valor_horario"] == 10
        assert "P2" in lookup

    def test_build_prod_lookup_skips_missing_id(self):
        from concilium.application.services._concilium_service_helpers import _build_prod_lookup

        prods = [{"valor_horario": 10}, {"id": "P2"}]
        lookup = _build_prod_lookup(prods)
        assert "P2" in lookup
        assert len(lookup) == 1

    def test_enrich_cpu_no_prod_ref(self):
        from concilium.application.services._concilium_service_helpers import _enrich_cpu_with_prod

        cpu = {"codigo": "CPU-1"}
        result = _enrich_cpu_with_prod(cpu, {})
        assert result is cpu  # no patch, returns same

    def test_enrich_cpu_prod_not_in_lookup(self):
        from concilium.application.services._concilium_service_helpers import _enrich_cpu_with_prod

        cpu = {"codigo": "CPU-1", "producao_id_ref": "P-MISSING"}
        result = _enrich_cpu_with_prod(cpu, {})
        assert result is cpu

    def test_enrich_cpu_adds_producao_horaria(self):
        from concilium.application.services._concilium_service_helpers import _enrich_cpu_with_prod

        cpu = {"codigo": "CPU-1", "producao_id_ref": "P1"}
        prod_lookup = {"P1": {"valor_horario": 50}}
        result = _enrich_cpu_with_prod(cpu, prod_lookup)
        assert result["producao_horaria"] == 50

    def test_enrich_cpu_does_not_override_existing_producao_horaria(self):
        from concilium.application.services._concilium_service_helpers import _enrich_cpu_with_prod

        cpu = {"codigo": "CPU-1", "producao_id_ref": "P1", "producao_horaria": 99}
        prod_lookup = {"P1": {"valor_horario": 50}}
        result = _enrich_cpu_with_prod(cpu, prod_lookup)
        assert result["producao_horaria"] == 99

    def test_enrich_cpu_adds_equipe_from_equipe_field(self):
        from concilium.application.services._concilium_service_helpers import _enrich_cpu_with_prod

        cpu = {"codigo": "CPU-1", "producao_id_ref": "P1"}
        prod_lookup = {"P1": {"equipe": {"op": 1, "aux": 2}}}
        result = _enrich_cpu_with_prod(cpu, prod_lookup)
        assert result["equipe"] == {"op": 1, "aux": 2}

    def test_enrich_cpu_adds_equipe_from_composicao_padrao(self):
        from concilium.application.services._concilium_service_helpers import _enrich_cpu_with_prod

        cpu = {"codigo": "CPU-1", "producao_id_ref": "P1"}
        prod_lookup = {"P1": {"equipe": "not-a-dict", "composicao_padrao_equipe": {"op": 1}}}
        result = _enrich_cpu_with_prod(cpu, prod_lookup)
        assert result["equipe"] == {"op": 1}

    def test_enrich_cpu_does_not_override_existing_equipe(self):
        from concilium.application.services._concilium_service_helpers import _enrich_cpu_with_prod

        cpu = {"codigo": "CPU-1", "producao_id_ref": "P1", "equipe": {"existing": 1}}
        prod_lookup = {"P1": {"equipe": {"new": 2}}}
        result = _enrich_cpu_with_prod(cpu, prod_lookup)
        assert result["equipe"] == {"existing": 1}

    def test_enrich_cpus_with_producao_uses_produtividades(self):
        from concilium.application.services._concilium_service_helpers import _enrich_cpus_with_producao

        cat = {
            "produtividades": [{"id": "P1", "valor_horario": 10}],
            "cpus": [{"codigo": "CPU-1", "producao_id_ref": "P1"}],
        }
        result = _enrich_cpus_with_producao(cat)
        assert result[0]["producao_horaria"] == 10

    def test_enrich_cpus_with_producao_falls_back_to_producoes(self):
        from concilium.application.services._concilium_service_helpers import _enrich_cpus_with_producao

        cat = {
            "producoes": [{"id": "P1", "valor_horario": 20}],
            "cpus": [{"codigo": "CPU-1", "producao_id_ref": "P1"}],
        }
        result = _enrich_cpus_with_producao(cat)
        assert result[0]["producao_horaria"] == 20

    def test_enrich_cpus_skips_non_dict(self):
        from concilium.application.services._concilium_service_helpers import _enrich_cpus_with_producao

        cat = {"cpus": [{"codigo": "CPU-1"}, "not-a-dict"]}
        result = _enrich_cpus_with_producao(cat)
        assert len(result) == 1


class TestUpsertCatalogCpu:
    def _make_svc(self, tmp_path, cat_id="cat-test"):
        svc = MagicMock()
        cats_dir = tmp_path / "catalogos" / cat_id
        cats_dir.mkdir(parents=True)
        svc.config_root = tmp_path
        return svc

    def _cpu_data(self):
        return {"codigo": "CPU-1", "descricao": "Test CPU", "unidade": "m³"}

    def test_upsert_creates_file_and_audit(self, tmp_path):
        from concilium.application.services._concilium_service_helpers import _cs_upsert_catalog_cpu

        svc = self._make_svc(tmp_path)
        result = _cs_upsert_catalog_cpu(svc, "cat-test", "CPU-1", self._cpu_data(), motivo="testing")
        assert result["cpu_id"] == "CPU-1"
        assert (tmp_path / "catalogos" / "cat-test" / "cpus" / "CPU-1.json").exists()
        audit_path = tmp_path / "catalogos" / "cat-test" / ".catalog_audit.jsonl"
        assert audit_path.exists()
        entry = json.loads(audit_path.read_text())
        assert entry["event"] == "upsert_cpu"
        assert entry["previous_snapshot"] is None

    def test_upsert_records_previous(self, tmp_path):
        from concilium.application.services._concilium_service_helpers import _cs_upsert_catalog_cpu

        svc = self._make_svc(tmp_path)
        cpus_dir = tmp_path / "catalogos" / "cat-test" / "cpus"
        cpus_dir.mkdir(parents=True, exist_ok=True)
        (cpus_dir / "CPU-1.json").write_text('{"codigo": "CPU-1", "old": true}')
        _cs_upsert_catalog_cpu(svc, "cat-test", "CPU-1", self._cpu_data(), motivo="update")
        audit_path = tmp_path / "catalogos" / "cat-test" / ".catalog_audit.jsonl"
        entry = json.loads(audit_path.read_text())
        assert entry["previous_snapshot"]["old"] is True

    def test_upsert_deletes_bundle(self, tmp_path):
        from concilium.application.services._concilium_service_helpers import _cs_upsert_catalog_cpu

        svc = self._make_svc(tmp_path)
        bundle = tmp_path / "catalogos" / "cat-test" / ".catalog_bundle.json"
        bundle.write_text("{}")
        _cs_upsert_catalog_cpu(svc, "cat-test", "CPU-1", self._cpu_data(), motivo="test")
        assert not bundle.exists()
        # result should say invalidated
        result = _cs_upsert_catalog_cpu(svc, "cat-test", "CPU-1", self._cpu_data(), motivo="test")
        assert result["bundle_invalidated"] is True

    def test_upsert_catalog_not_found(self, tmp_path):
        from concilium.application.services._concilium_service_helpers import _cs_upsert_catalog_cpu

        svc = MagicMock()
        svc.config_root = tmp_path
        with pytest.raises(FileNotFoundError, match="cat-missing"):
            _cs_upsert_catalog_cpu(svc, "cat-missing", "CPU-1", self._cpu_data(), motivo="x")

    def test_upsert_validation_error_propagates(self, tmp_path):
        from concilium.application.services._concilium_service_helpers import _cs_upsert_catalog_cpu

        svc = self._make_svc(tmp_path)
        with pytest.raises(ValueError):
            _cs_upsert_catalog_cpu(svc, "cat-test", "CPU-1", {}, motivo="")


class TestWmpHelpers:
    def test_build_wmp_lookup_basic(self):
        from concilium.application.services._concilium_service_helpers import _build_wmp_lookup

        items = [{"item_id": "A", "val": 1}, {"item_id": "B", "val": 2}]
        lookup = _build_wmp_lookup(items, "item_id")
        assert lookup["A"]["val"] == 1

    def test_build_wmp_lookup_skips_missing_key(self):
        from concilium.application.services._concilium_service_helpers import _build_wmp_lookup

        items = [{"val": 1}, {"item_id": "B"}]
        lookup = _build_wmp_lookup(items, "item_id")
        assert len(lookup) == 1

    def test_build_wmp_lookup_none_iterable(self):
        from concilium.application.services._concilium_service_helpers import _build_wmp_lookup

        result = _build_wmp_lookup(None, "id")
        assert result == {}

    def test_resolve_producao_horaria_from_producao_lookup(self):
        from concilium.application.services._concilium_service_helpers import _resolve_producao_horaria

        eap = {"cpu_id": "CPU-1"}
        cpu_lookup = {"CPU-1": {"producao_id_ref": "P1"}}
        producao_lookup = {"P1": {"valor_horario": 75.0}}
        result = _resolve_producao_horaria(eap, cpu_lookup, producao_lookup)
        assert result == 75.0

    def test_resolve_producao_horaria_from_cpu_producao_horaria(self):
        from concilium.application.services._concilium_service_helpers import _resolve_producao_horaria

        eap = {"cpu_id": "CPU-1"}
        cpu_lookup = {"CPU-1": {"producao_horaria": 50.0}}
        result = _resolve_producao_horaria(eap, cpu_lookup, {})
        assert result == 50.0

    def test_resolve_producao_horaria_zero_when_missing(self):
        from concilium.application.services._concilium_service_helpers import _resolve_producao_horaria

        result = _resolve_producao_horaria({}, {}, {})
        assert result == 0.0

    def test_build_wmp_codigo_ok(self):
        from concilium.application.services._concilium_service_helpers import _build_wmp_codigo

        curva = MagicMock(is_complete=True)
        policy = MagicMock()
        assert _build_wmp_codigo(curva, policy) == "VAL-WMP-OK"

    def test_build_wmp_codigo_desmob(self):
        from concilium.application.services._concilium_service_helpers import _build_wmp_codigo

        curva = MagicMock(is_complete=False)
        policy = MagicMock(semanas_plateau=2, taxa_desmobilizacao=0.5)
        assert _build_wmp_codigo(curva, policy) == "VAL-WMP-DESMOB"

    def test_build_wmp_codigo_05(self):
        from concilium.application.services._concilium_service_helpers import _build_wmp_codigo

        curva = MagicMock(is_complete=False)
        policy = MagicMock(semanas_plateau=0, taxa_desmobilizacao=0)
        assert _build_wmp_codigo(curva, policy) == "VAL-WMP-05"

    def test_process_wmp_invalid_policy(self):
        from concilium.application.services._concilium_service_helpers import _process_wmp_policy

        sim = MagicMock()
        results: list = []
        # Pass invalid policy_dict that will fail MobilizacaoPolicy(**...)
        _process_wmp_policy(sim, "item-1", {"n_minimo": "not-int"}, {}, {}, {}, results)
        assert any(r["codigo"] == "VAL-WMP-03" for r in results)

    def _valid_policy_dict(self):
        from concilium.domain.models.planning.mobilizacao import MobilizacaoPolicy

        return MobilizacaoPolicy(
            n_inicial=1, n_maximo=2, taxa_mobilizacao=1.0, taxa_desmobilizacao=0.0, semanas_plateau=None
        ).model_dump()

    def test_process_wmp_q_zero(self):
        from concilium.application.services._concilium_service_helpers import _process_wmp_policy

        sim = MagicMock()
        results: list = []
        _process_wmp_policy(sim, "item-1", self._valid_policy_dict(), {}, {}, {}, results)
        assert any(r["codigo"] == "VAL-WMP-04" for r in results)

    def test_process_wmp_p_zero_still_runs(self):
        from concilium.application.services._concilium_service_helpers import _process_wmp_policy

        sim = MagicMock()
        curva = MagicMock(is_complete=True, duration_weeks=5, peak_teams=2, delivered=100.0)
        sim.simulate.return_value = curva
        results: list = []
        eap_items = {"item-1": {"quantitativo": 100.0}}
        # cpu_lookup empty → P=0
        _process_wmp_policy(sim, "item-1", self._valid_policy_dict(), eap_items, {}, {}, results)
        # Should have VAL-WMP-02 (aviso)
        codes = [r["codigo"] for r in results]
        assert "VAL-WMP-02" in codes

    def test_cs_validate_mobilizacao_no_policies(self):
        from concilium.application.services._concilium_service_helpers import _cs_validate_mobilizacao_policies

        svc = MagicMock()
        svc._dependencies.override_service.get_mobilizacao_policies.return_value = {}
        result = _cs_validate_mobilizacao_policies(svc, "proj-1")
        assert result[0]["codigo"] == "VAL-WMP-NONE"

    def test_cs_validate_mobilizacao_file_not_found(self):
        from concilium.application.services._concilium_service_helpers import _cs_validate_mobilizacao_policies

        svc = MagicMock()
        svc._dependencies.override_service.get_mobilizacao_policies.return_value = {"item-1": self._valid_policy_dict()}
        svc._dependencies.project_service.get_benchmark_reference.side_effect = FileNotFoundError("not found")
        # Should not raise — falls back to empty reference
        result = _cs_validate_mobilizacao_policies(svc, "proj-1")
        assert isinstance(result, list)
