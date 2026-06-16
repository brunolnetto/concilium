"""Tests for: backtracking_pe models, jwt_config, cpu_mapper."""

from __future__ import annotations

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
            patch.dict("sys.modules", {
                "azure.identity": azure_identity_mock,
                "azure.keyvault.secrets": azure_secrets_mock,
            }),
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
