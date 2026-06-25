"""Testes adicionais para ADR-112 F8 — CrossDomainBuilder e default_canonical_provider.

Cobre linhas não alcançadas pelo test_adr112_f7_f8.py:
  - _read_silver_logs: exception silenciosa ao ler blob individual (40-41)
  - build: canonical_provider levanta exceção — loga warning e continua (68-69)
  - default_canonical_provider: função completa, incluindo casos sem diretório,
    sem canonical.json, canonical parseado corretamente e falha de leitura (94-118)
"""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _storage_with_bad_blob():
    """BlobStoragePort fake: lista 1 blob mas falha ao lê-lo."""
    storage = MagicMock()
    storage.listar_blobs.return_value = ["observability/silver/logs/bad.ndjson"]
    storage.ler_blob.side_effect = OSError("disco morreu")
    return storage


def _storage_with_good_blobs(records: list[dict]):
    """BlobStoragePort fake: retorna registros NDJSON válidos."""
    ndjson = "\n".join(json.dumps(r) for r in records)
    storage = MagicMock()
    storage.listar_blobs.return_value = ["observability/silver/logs/ok.ndjson"]
    storage.ler_blob.return_value = ndjson.encode("utf-8")
    return storage


# ─────────────────────────────────────────────────────────────────────────────
# _read_silver_logs: exception em ler_blob deve ser silenciada (linhas 40-41)
# ─────────────────────────────────────────────────────────────────────────────


class TestReadSilverLogs:
    def test_exception_in_ler_blob_is_silenced(self):
        from concilium.infrastructure.observability.cross_domain import CrossDomainBuilder

        storage = _storage_with_bad_blob()
        builder = CrossDomainBuilder(storage, canonical_provider=lambda pid: None)
        # build() não deve levantar — exception é silenciada internamente
        result = builder.build()
        # sem logs processados → lista vazia
        assert result == []

    def test_empty_lines_in_blob_are_skipped(self):
        from concilium.infrastructure.observability.cross_domain import CrossDomainBuilder

        storage = MagicMock()
        storage.listar_blobs.return_value = ["observability/silver/logs/blanks.ndjson"]
        # blob com linhas em branco entre registros válidos
        storage.ler_blob.return_value = (
            b'\n{"project_id": "P1", "fallback_type": "MINSLK"}\n\n{"project_id": "P1"}\n'
        )

        builder = CrossDomainBuilder(storage, canonical_provider=lambda pid: None)
        rows = builder.build()
        assert len(rows) == 1
        assert rows[0]["n_total"] == 2
        assert rows[0]["n_fallbacks"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# build: canonical_provider levanta exceção → warning logged, continua (68-69)
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildCanonicalProviderException:
    def test_canonical_provider_exception_is_logged_and_skipped(self, caplog):
        from concilium.infrastructure.observability.cross_domain import CrossDomainBuilder

        records = [{"project_id": "P-BOOM", "fallback_type": "MINSLK"}]
        storage = _storage_with_good_blobs(records)

        def _boom(pid):
            raise ValueError("banco explodiu")

        with caplog.at_level(logging.WARNING, logger="concilium.infrastructure.observability.cross_domain"):
            builder = CrossDomainBuilder(storage, canonical_provider=_boom)
            rows = builder.build()

        assert len(rows) == 1
        row = rows[0]
        assert row["project_id"] == "P-BOOM"
        assert row["custo_direto"] is None
        assert row["margem_pct"] is None
        # deve ter logado warning com o nome do projeto
        assert any("P-BOOM" in msg for msg in caplog.messages)

    def test_multiple_projects_one_canonical_error(self):
        """Erro em 1 projeto não impede os demais de receber canonical."""
        from concilium.infrastructure.observability.cross_domain import CrossDomainBuilder

        records = [
            {"project_id": "OK", "fallback_type": None},
            {"project_id": "BOOM"},
        ]
        storage = _storage_with_good_blobs(records)

        def _provider(pid):
            if pid == "BOOM":
                raise RuntimeError("broken")
            return {"custo_direto": 99.0, "margem_pct": 0.05}

        builder = CrossDomainBuilder(storage, canonical_provider=_provider)
        rows = builder.build()
        by_id = {r["project_id"]: r for r in rows}
        assert by_id["OK"]["custo_direto"] == 99.0
        assert by_id["BOOM"]["custo_direto"] is None


# ─────────────────────────────────────────────────────────────────────────────
# default_canonical_provider (linhas 94-118)
# ─────────────────────────────────────────────────────────────────────────────


class TestDefaultCanonicalProvider:
    def test_returns_none_when_project_dir_missing(self, tmp_path):
        from concilium.infrastructure.observability.cross_domain import default_canonical_provider

        provider = default_canonical_provider(tmp_path)
        result = provider("projeto-inexistente")
        assert result is None

    def test_returns_none_when_no_canonical_json(self, tmp_path):
        from concilium.infrastructure.observability.cross_domain import default_canonical_provider

        proj_dir = tmp_path / "proj-vazio"
        proj_dir.mkdir()
        # v1/ existe mas sem canonical.json
        (proj_dir / "v1").mkdir()

        provider = default_canonical_provider(tmp_path)
        result = provider("proj-vazio")
        assert result is None

    def test_reads_canonical_from_latest_version(self, tmp_path):
        from concilium.infrastructure.observability.cross_domain import default_canonical_provider

        proj_dir = tmp_path / "proj-ok"
        proj_dir.mkdir()
        v1 = proj_dir / "v1"
        v1.mkdir()
        v2 = proj_dir / "v2"
        v2.mkdir()
        # v1 tem dados antigos, v2 tem os mais recentes (sorted pega o maior)
        (v1 / "canonical.json").write_text(
            json.dumps({"resultado": {"custo": {"direto_equipes": 1.0}, "margem_pct": 0.1}}),
            encoding="utf-8",
        )
        (v2 / "canonical.json").write_text(
            json.dumps({"resultado": {"custo": {"direto_equipes": 2_000_000.0}, "margem_pct": 0.18}}),
            encoding="utf-8",
        )

        provider = default_canonical_provider(tmp_path)
        result = provider("proj-ok")
        assert result is not None
        assert result["custo_direto"] == 2_000_000.0
        assert result["margem_pct"] == 0.18

    def test_returns_none_fields_when_resultado_missing(self, tmp_path):
        from concilium.infrastructure.observability.cross_domain import default_canonical_provider

        proj_dir = tmp_path / "proj-sem-resultado"
        proj_dir.mkdir()
        v1 = proj_dir / "v1"
        v1.mkdir()
        (v1 / "canonical.json").write_text(json.dumps({}), encoding="utf-8")

        provider = default_canonical_provider(tmp_path)
        result = provider("proj-sem-resultado")
        assert result is not None
        assert result["custo_direto"] is None
        assert result["margem_pct"] is None

    def test_silences_json_parse_error_and_returns_none(self, tmp_path, caplog):
        from concilium.infrastructure.observability.cross_domain import default_canonical_provider

        proj_dir = tmp_path / "proj-broken"
        proj_dir.mkdir()
        v1 = proj_dir / "v1"
        v1.mkdir()
        (v1 / "canonical.json").write_text("this is not json {{{", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="concilium.infrastructure.observability.cross_domain"):
            provider = default_canonical_provider(tmp_path)
            result = provider("proj-broken")

        assert result is None
        assert any("proj-broken" in msg for msg in caplog.messages)

    def test_returns_callable(self, tmp_path):
        from concilium.infrastructure.observability.cross_domain import default_canonical_provider

        provider = default_canonical_provider(tmp_path)
        assert callable(provider)
