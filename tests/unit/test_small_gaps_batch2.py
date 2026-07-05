"""Tests for: backtracking_pe models, jwt_config, cpu_mapper."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ─── domain/models/financial/backtracking_pe.py ───────────────────────────────


def _make_solucao(**kwargs):
    from concilium.domain.models.financial.backtracking_pe import SolucaoInversa

    defaults = dict(
        parametro="L",
        valor_atual=0.15,
        valor_requerido=0.20,
        delta_abs=0.05,
        delta_pct=33.3,
        impacto_preco_pct=5.0,
        impacto_produtividade_pct=0.0,
        impacto_recursos_pct=0.0,
        impacto_prazo_semanas=0.0,
        pe_gap_recalculado=0.001,
        roundtrip_valido=True,
        erro_roundtrip=0.001,
        confianca=4,
    )
    defaults.update(kwargs)
    return SolucaoInversa(**defaults)


class TestSolucaoInversa:
    def test_label_known_param(self):
        s = _make_solucao(parametro="L")
        assert "margem" in s.label.lower() or s.label != "L"

    def test_label_unknown_param(self):
        s = _make_solucao(parametro="CUSTOM")
        assert s.label == "CUSTOM"

    def test_impacto_cliente_descricao(self):
        s = _make_solucao(parametro="P")
        assert "Sem repasse" in s.impacto_cliente_descricao

    def test_impacto_cliente_unknown(self):
        s = _make_solucao(parametro="CUSTOM")
        assert s.impacto_cliente_descricao == "—"

    def test_estrelas_property(self):
        s = _make_solucao(confianca=3)
        assert s.estrelas == "★★★☆☆"

    def test_descricao_delta_L(self):
        s = _make_solucao(parametro="L", valor_atual=0.10, valor_requerido=0.15, delta_abs=0.05)
        assert "pp" in s.descricao_delta

    def test_descricao_delta_P(self):
        s = _make_solucao(parametro="P", valor_atual=50, valor_requerido=60, delta_pct=20)
        assert "un/h" in s.descricao_delta

    def test_descricao_delta_N_MAX(self):
        s = _make_solucao(parametro="N_MAX", valor_atual=2, valor_requerido=3, delta_abs=1)
        assert "equipes" in s.descricao_delta

    def test_descricao_delta_T0_RAMP(self):
        s = _make_solucao(parametro="T0_RAMP", delta_abs=-2)
        assert "semanas" in s.descricao_delta

    def test_descricao_delta_fallback(self):
        s = _make_solucao(parametro="COMBINADA", delta_abs=1.5)
        assert "Δ" in s.descricao_delta or "1.50" in s.descricao_delta


class TestBacktrackingPEItem:
    def _make_item(self, solucoes=()):
        from concilium.domain.models.financial.backtracking_pe import BacktrackingPEItem

        return BacktrackingPEItem(
            atividade_id="A1",
            descricao="Atividade 1",
            pe_gap_atual=0.05,
            pe_gap_alvo=0.10,
            solucoes=tuple(solucoes),
            solucao_recomendada=None,
            roundtrips_falharam=(),
        )

    def test_tem_solucao_sem_repasse_true(self):
        sol = _make_solucao(roundtrip_valido=True, impacto_preco_pct=0.2)
        item = self._make_item([sol])
        assert item.tem_solucao_sem_repasse is True

    def test_tem_solucao_sem_repasse_false(self):
        sol = _make_solucao(roundtrip_valido=True, impacto_preco_pct=5.0)
        item = self._make_item([sol])
        assert item.tem_solucao_sem_repasse is False


class TestBacktrackingPERelatorio:
    def _make_relatorio(self, n_fails=0):
        from concilium.domain.models.financial.backtracking_pe import BacktrackingPERelatorio

        return BacktrackingPERelatorio(
            projeto_id="proj-1",
            gerado_em="2026-01-01",
            pe_gap_alvo=0.10,
            itens=(),
            consistencia_global=True,
            n_roundtrips_falharam=n_fails,
        )

    def test_aviso_consistencia_none_when_no_fails(self):
        r = self._make_relatorio(n_fails=0)
        assert r.aviso_consistencia is None

    def test_aviso_consistencia_has_message_when_fails(self):
        r = self._make_relatorio(n_fails=2)
        assert "2" in r.aviso_consistencia

    def test_to_dict(self):
        r = self._make_relatorio()
        d = r.to_dict()
        assert d["projeto_id"] == "proj-1"
        assert isinstance(d["itens"], list)


# ─── infrastructure/auth/jwt_config.py ────────────────────────────────────────


class TestReadPem:
    def test_read_pem_from_env_var(self, monkeypatch):
        from concilium.infrastructure.auth.jwt_config import _read_pem

        monkeypatch.setenv("CONCILIUM__JWT_PRIVATE_KEY_PEM", "-----BEGIN RSA PRIVATE KEY-----\ntest\n")
        auth_mock = MagicMock()
        auth_mock.jwt_private_key_pem = ""
        auth_mock.jwt_private_key_path = ""
        auth_mock.jwt_public_key_pem = ""
        auth_mock.jwt_public_key_path = ""
        auth_mock.key_vault_url = ""
        with patch("concilium.infrastructure.auth.jwt_config.get_auth", return_value=auth_mock):
            result = _read_pem("CONCILIUM__JWT_PRIVATE_KEY_PEM", "CONCILIUM__JWT_PRIVATE_KEY_PATH", kv_secret="x")
        assert result is not None
        assert b"RSA" in result

    def test_read_pem_from_path(self, tmp_path, monkeypatch):
        from concilium.infrastructure.auth.jwt_config import _read_pem

        pem_file = tmp_path / "key.pem"
        pem_file.write_bytes(b"-----BEGIN RSA PRIVATE KEY-----\nfakepem\n")
        monkeypatch.delenv("CONCILIUM__JWT_PRIVATE_KEY_PEM", raising=False)
        auth_mock = MagicMock()
        auth_mock.jwt_private_key_pem = ""
        auth_mock.jwt_private_key_path = str(pem_file)
        auth_mock.key_vault_url = ""
        with patch("concilium.infrastructure.auth.jwt_config.get_auth", return_value=auth_mock):
            result = _read_pem("CONCILIUM__JWT_PRIVATE_KEY_PEM", "CONCILIUM__JWT_PRIVATE_KEY_PATH", kv_secret="x")
        assert result == pem_file.read_bytes()

    def test_read_pem_key_vault_no_url_returns_none(self, monkeypatch):
        from concilium.infrastructure.auth.jwt_config import _read_pem

        monkeypatch.delenv("CONCILIUM__JWT_PRIVATE_KEY_PEM", raising=False)
        auth_mock = MagicMock()
        auth_mock.jwt_private_key_pem = ""
        auth_mock.jwt_private_key_path = ""
        auth_mock.key_vault_url = ""
        with patch("concilium.infrastructure.auth.jwt_config.get_auth", return_value=auth_mock):
            result = _read_pem("CONCILIUM__JWT_PRIVATE_KEY_PEM", "CONCILIUM__JWT_PRIVATE_KEY_PATH", kv_secret="x")
        assert result is None

    def test_read_from_key_vault_import_error(self, monkeypatch):
        from concilium.infrastructure.auth.jwt_config import _read_from_key_vault

        auth_mock = MagicMock()
        auth_mock.key_vault_url = "https://myvault.vault.azure.net"
        with (
            patch("concilium.infrastructure.auth.jwt_config.get_auth", return_value=auth_mock),
            patch.dict("sys.modules", {"azure.identity": None, "azure.keyvault.secrets": None}),
        ):
            import warnings

            with warnings.catch_warnings(record=True):
                result = _read_from_key_vault("jwt-private-key")
        assert result is None

    def test_read_from_key_vault_exception_warns(self, monkeypatch):
        from concilium.infrastructure.auth.jwt_config import _read_from_key_vault

        auth_mock = MagicMock()
        auth_mock.key_vault_url = "https://myvault.vault.azure.net"
        azure_identity_mock = MagicMock()
        azure_secrets_mock = MagicMock()
        secret_client_mock = MagicMock()
        secret_client_mock.get_secret.side_effect = Exception("auth failed")
        azure_secrets_mock.SecretClient.return_value = secret_client_mock
        with (
            patch("concilium.infrastructure.auth.jwt_config.get_auth", return_value=auth_mock),
            patch.dict(
                "sys.modules",
                {
                    "azure.identity": azure_identity_mock,
                    "azure.keyvault.secrets": azure_secrets_mock,
                },
            ),
        ):
            import warnings

            with warnings.catch_warnings(record=True):
                result = _read_from_key_vault("jwt-private-key")
        assert result is None


# ─── application/benchmarks/validation/cpu_mapper.py ─────────────────────────


class TestCpuMapper:
    def _make_mapper(self, catalogo=None):
        from concilium.application.benchmarks.validation.cpu_mapper import CpuMapper

        mapper = CpuMapper.__new__(CpuMapper)
        mapper.contexto_id = "test"
        mapper.runtime = MagicMock()
        mapper._cpu_cache = {}
        mapper.catalogo = catalogo or {
            "cpus": [
                {"codigo": "CPU-ESC", "descricao": "Escavação 1ª categoria", "unidade": "m³", "categoria": "TERRA"},
                {"codigo": "CPU-ATE", "descricao": "Aterro compactado", "unidade": "m³", "categoria": "TERRA"},
            ]
        }
        return mapper

    def test_search_cpus_exact_match(self):
        mapper = self._make_mapper()
        results = mapper.search_cpus("Escavação")
        assert len(results) >= 1
        assert any(r["cpu_id"] == "CPU-ESC" for r in results)

    def test_search_cpus_no_match(self):
        mapper = self._make_mapper()
        results = mapper.search_cpus("pavimento concreto")
        assert results == []

    def test_search_cpus_limit(self):
        catalogo = {"cpus": [{"codigo": f"CPU-{i}", "descricao": f"Test CPU {i}"} for i in range(10)]}
        mapper = self._make_mapper(catalogo)
        results = mapper.search_cpus("Test", limit=3)
        assert len(results) <= 3

    def test_map_item_to_cpu_found(self):
        mapper = self._make_mapper()
        result = mapper.map_item_to_cpu("2.1", "Escavação")
        assert result == "CPU-ESC"
        assert "2.1" in mapper._cpu_cache

    def test_map_item_to_cpu_cached(self):
        mapper = self._make_mapper()
        mapper._cpu_cache["2.1"] = "CPU-CACHED"
        result = mapper.map_item_to_cpu("2.1", "anything")
        assert result == "CPU-CACHED"

    def test_map_item_to_cpu_fallback_word_search(self):
        mapper = self._make_mapper()
        result = mapper.map_item_to_cpu("3.1", "Aterro tipo compactado")
        assert result == "CPU-ATE"

    def test_map_item_to_cpu_no_match(self):
        mapper = self._make_mapper()
        result = mapper.map_item_to_cpu("9.9", "pavimento asfaltico especial")
        assert result is None

    def test_map_items_batch(self):
        mapper = self._make_mapper()
        items = [
            {"item_id": "1.1", "descricao": "Escavação"},
            {"item_id": "1.2", "descricao": "Aterro"},
        ]
        result = mapper.map_items_batch(items)
        assert "1.1" in result
        assert "1.2" in result

    def test_get_available_cpus(self):
        mapper = self._make_mapper()
        cpus = mapper.get_available_cpus()
        assert len(cpus) == 2
        assert all("cpu_id" in c for c in cpus)

    def test_get_mapping_stats_empty(self):
        mapper = self._make_mapper()
        stats = mapper.get_mapping_stats()
        assert stats["total_items_processed"] == 0
        assert stats["success_rate"] == 0

    def test_get_mapping_stats_with_data(self):
        mapper = self._make_mapper()
        mapper._cpu_cache = {"1.1": "CPU-ESC", "1.2": None}
        stats = mapper.get_mapping_stats()
        assert stats["total_items_processed"] == 2
        assert stats["successfully_mapped"] == 1
        assert stats["failed_mappings"] == 1
        assert stats["success_rate"] == 50.0

    def test_load_catalog_raises_on_error(self, tmp_path):
        from concilium.application.benchmarks.validation.cpu_mapper import CpuMapper

        with pytest.raises(RuntimeError, match="Failed to load catalog"):
            CpuMapper(contexto_id="nonexistent", config_root=tmp_path)

    def test_auto_detect_config_root_and_load_catalog(self):
        """Lines 29, 39-40: auto-detects config_root when None; loads catalogo and contexto."""
        from concilium.application.benchmarks.validation.cpu_mapper import CpuMapper

        with patch("concilium.application.benchmarks.validation.cpu_mapper.Runtime") as MockRuntime:
            mock_runtime = MagicMock()
            MockRuntime.return_value = mock_runtime
            mock_ctx = MagicMock()
            mock_ctx.catalogo_id = "test_cat"
            mock_runtime.load_contexto.return_value = mock_ctx
            mock_runtime.load_catalogo.return_value = {"cpus": []}

            mapper = CpuMapper(contexto_id="testctx")  # config_root=None

        call_path = MockRuntime.call_args[0][0]
        assert "config" in str(call_path).lower()
        assert mapper.contexto is mock_ctx

    def test_search_cpus_code_match_scores_higher(self):
        """Line 64: query matching CPU code adds score += 100."""
        mapper = self._make_mapper(catalogo={"cpus": [{"codigo": "escav", "descricao": "irrelevant thing"}]})
        results = mapper.search_cpus("escav")
        assert results and results[0]["cpu_id"] == "escav"

    def test_map_item_fallback_word_matches_code(self):
        """Lines 115-117: fallback word search finds CPU when full desc misses but single word matches code."""
        mapper = self._make_mapper(catalogo={"cpus": [{"codigo": "escavacao", "descricao": "unrelated_thing"}]})
        # Full desc: "prefix_xyz escavacao" → "prefix_xyz" and "escavacao" not in "unrelated_thing"
        # But fallback word "escavacao" IS the code → score 100
        result = mapper.map_item_to_cpu("9.1", "prefix_xyz escavacao")
        assert result == "escavacao"


# ─── domain/repositories/blob_storage_port.py ─────────────────────────────────


class TestBlobStoragePortDefaults:
    def _make(self):
        from concilium.domain.repositories.blob_storage_port import BlobStoragePort

        class _Impl(BlobStoragePort):
            def ler_blob(self, path):
                return b""

            def gravar_blob(self, path, content):
                pass

            def listar_blobs(self, prefix):
                return []

            def blob_existe(self, path):
                return False

        return _Impl()

    def test_deletar_blob_default_is_noop(self):
        """Line 50: base class deletar_blob returns without raising."""
        storage = self._make()
        storage.deletar_blob("any/path.json")  # must not raise

    def test_health_check_default_returns_ok(self):
        """Line 77: base class health_check returns status ok with backend unknown."""
        storage = self._make()
        result = storage.health_check()
        assert result["status"] == "ok"
        assert result["backend"] == "unknown"

    def test_aprovar_versao_default_is_noop(self):
        """Line 58: base class aprovar_versao returns without raising."""
        storage = self._make()
        storage.aprovar_versao("any/path.json")  # must not raise

    def test_gerar_url_temporaria_default_returns_none(self):
        """Line 69: base class gerar_url_temporaria returns None."""
        storage = self._make()
        result = storage.gerar_url_temporaria("any/path.json")
        assert result is None


# ─── infrastructure/adapters/blob_storage/local.py ────────────────────────────


class TestLocalBlobStorageCoverage:
    def test_path_traversal_raises_value_error(self):
        """Line 26: accessing path outside root raises ValueError."""
        import tempfile

        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalBlobStorage(Path(tmp))
            with pytest.raises(ValueError, match="fora do diretório raiz"):
                storage._resolve_path("../../etc/passwd")

    def test_ler_blob_directory_raises_is_a_directory(self):
        """Line 34: ler_blob on a directory path raises IsADirectoryError."""
        import tempfile

        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalBlobStorage(Path(tmp))
            (Path(tmp) / "subdir").mkdir()
            with pytest.raises(IsADirectoryError):
                storage.ler_blob("subdir")

    def test_blob_existe_path_traversal_returns_false(self):
        """Lines 69-70: blob_existe with path traversal catches ValueError → False."""
        import tempfile

        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalBlobStorage(Path(tmp))
            result = storage.blob_existe("../../etc/passwd")
        assert result is False


# ─── infrastructure/catalog/extraction/engine_refs.py ─────────────────────────


class TestEngineRefs:
    def test_safe_float_with_non_numeric_returns_zero(self):
        """Lines 20-23: _safe_float with non-numeric input returns 0.0."""
        from concilium.infrastructure.catalog.extraction.engine_refs import _safe_float

        assert _safe_float("not_a_number") == 0.0
        assert _safe_float(None) == 0.0

    def test_safe_float_with_valid_number(self):
        from concilium.infrastructure.catalog.extraction.engine_refs import _safe_float

        assert _safe_float("3.14") == pytest.approx(3.14)

    def test_check_project_dir_invalid_json_returns_best(self, tmp_path):
        """Lines 52-53: _check_project_dir with invalid JSON meta returns best."""

        from concilium.infrastructure.catalog.extraction.engine_refs import _check_project_dir

        d = tmp_path / "proj1"
        d.mkdir()
        (d / "meta.json").write_text("NOT JSON", encoding="utf-8")

        sentinel = ("2026-01-01", tmp_path / "other")
        result = _check_project_dir(d, "ANY", sentinel)
        assert result is sentinel

    def test_check_project_dir_older_candidate_returns_best(self, tmp_path):
        """Line 60: existing best is newer → returns best unchanged."""

        from concilium.infrastructure.catalog.extraction.engine_refs import _check_project_dir

        d = tmp_path / "proj_old"
        d.mkdir()
        (d / "meta.json").write_text(
            json.dumps({"nome": "Test Project", "criado_em": "2025-01-01"}),
            encoding="utf-8",
        )
        best = ("2026-06-01", tmp_path / "newer_proj")
        result = _check_project_dir(d, "TEST PROJECT", best)
        assert result is best


# ─── application/scheduling/mob_scheduling.py ─────────────────────────────────


class TestParseDate:
    def test_parse_date_from_iso_string(self):
        """Line 27: _parse_date with ISO string returns date."""
        from datetime import date

        from concilium.application.scheduling.mob_scheduling import _parse_date

        result = _parse_date("2026-06-01")
        assert result == date(2026, 6, 1)

    def test_parse_date_invalid_type_raises_type_error(self):
        """Line 30: _parse_date with invalid type raises TypeError."""
        from concilium.application.scheduling.mob_scheduling import _parse_date

        with pytest.raises(TypeError, match="Expected date or str"):
            _parse_date(20260601)


# ─── application/runtime/deliverables/visualizations/cube/__init__.py ─────────


class TestCubeInit:
    def test_build_graficos_dict_non_dict_returns_empty(self):
        """Line 61: _build_graficos_dict with non-dict relatorio returns {}."""
        from concilium.application.runtime.deliverables.visualizations.cube import _build_graficos_dict

        assert _build_graficos_dict("not_a_dict") == {}
        assert _build_graficos_dict(42) == {}
        assert _build_graficos_dict(None) == {}

    def test_build_faces_exception_is_swallowed(self):
        """Lines 75-76: _build_faces catches module.build() exceptions silently."""
        from concilium.application.runtime.deliverables.visualizations.cube import _build_faces

        def bad_build(*args, **kwargs):
            raise RuntimeError("chart failed")

        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube._FACE_BUILDERS",
            [(bad_build, "face.png", False)],
        ):
            result = _build_faces(MagicMock(), MagicMock(), {})
        assert result == {}

    def test_build_all_canonical_none_returns_empty(self):
        """Line 90: build_all with canonical=None returns {}."""
        from concilium.application.runtime.deliverables.visualizations.cube import build_all

        result = build_all(canonical=None)
        assert result == {}


# ─── infrastructure/adapters/blob_storage/_sharepoint_auth.py ─────────────────


class TestSharePointAuthCoverage:
    def test_blob_cache_ttl_expiry_returns_none(self, tmp_path):
        """Line 128: BlobCache.get returns None when TTL is expired."""
        import datetime

        from concilium.infrastructure.adapters.blob_storage._sharepoint_auth import _BlobCache

        cache = _BlobCache(tmp_path, ttl_minutes=60)
        cache.put("key.json", b"data", "etag", "Mon")
        cache._ttl = datetime.timedelta(seconds=0)
        result = cache.get("key.json")
        assert result is None

    def test_blob_cache_get_corrupt_meta_returns_none(self, tmp_path):
        """Lines 130-131: BlobCache.get with corrupt meta returns None."""
        import hashlib

        from concilium.infrastructure.adapters.blob_storage._sharepoint_auth import _BlobCache

        cache = _BlobCache(tmp_path, ttl_minutes=60)
        cache.put("key.json", b"data", "etag", "Mon")
        key = hashlib.sha256(b"key.json").hexdigest()[:24]
        (tmp_path / f"{key}.meta").write_text("CORRUPT_JSON", encoding="utf-8")
        result = cache.get("key.json")
        assert result is None

    def test_blob_cache_get_stale_corrupt_meta_returns_none(self, tmp_path):
        """Lines 141-142: BlobCache.get_stale with corrupt meta returns None."""
        import hashlib

        from concilium.infrastructure.adapters.blob_storage._sharepoint_auth import _BlobCache

        cache = _BlobCache(tmp_path, ttl_minutes=60)
        cache.put("key2.json", b"data", "etag", "Mon")
        key = hashlib.sha256(b"key2.json").hexdigest()[:24]
        (tmp_path / f"{key}.meta").write_text("CORRUPT", encoding="utf-8")
        result = cache.get_stale("key2.json")
        assert result is None

    def test_acquire_token_cert_path(self, tmp_path):
        """Lines 73-74: acquire_token uses cert credential when cert_path exists."""
        from concilium.infrastructure.adapters.blob_storage._sharepoint_auth import SharePointCredential

        cert_file = tmp_path / "cert.pem"
        cert_file.write_text("-----BEGIN PRIVATE KEY-----\nFAKE\n-----END PRIVATE KEY-----", encoding="utf-8")

        cred = SharePointCredential(
            tenant_id="tenant",
            client_id="client",
            client_secret=None,
            cert_path=cert_file,
        )

        mock_app = MagicMock()
        mock_app.acquire_token_for_client.return_value = {"access_token": "cert_token"}
        mock_msal = MagicMock()
        mock_msal.ConfidentialClientApplication.return_value = mock_app

        with patch.dict("sys.modules", {"msal": mock_msal}):
            token = cred.acquire_token()

        assert token == "cert_token"
        call_kwargs = mock_msal.ConfidentialClientApplication.call_args[1]
        assert "private_key" in call_kwargs.get("client_credential", {})
