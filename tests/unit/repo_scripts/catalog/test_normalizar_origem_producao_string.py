"""Testa `scripts/catalog/normalizar_origem_producao_string.py`: conversão de
`Producao.origem` de string solta (ex.: "PROPRIA") para o dict OrigemProducao
{tipo, fonte_id, data_calibracao, referencia} — bug real, PR #156."""

from __future__ import annotations

import json

import pytest

import scripts.catalog.normalizar_origem_producao_string as mod


@pytest.fixture(autouse=True)
def _catalogo_tmp(tmp_path, monkeypatch):
    prod_dir = tmp_path / "produtividades"
    prod_dir.mkdir()
    monkeypatch.setattr(mod, "CAT_DIR", tmp_path)
    return prod_dir


def _write(prod_dir, nome, data):
    (prod_dir / f"{nome}.json").write_text(json.dumps(data), encoding="utf-8")


class TestNormalizarOrigemProducaoString:
    def test_converte_string_para_dict_preservando_texto_em_referencia(self, _catalogo_tmp):
        _write(_catalogo_tmp, "PROD-1", {"id": "PROD-1", "origem": "PROPRIA"})

        stats = mod.run_normalize(apply=True)

        data = json.loads((_catalogo_tmp / "PROD-1.json").read_text())
        assert stats["normalizados"] == 1
        assert isinstance(data["origem"], dict)
        assert data["origem"]["referencia"] == "PROPRIA"
        assert data["origem"]["tipo"] == "estimado"
        assert data["origem"]["fonte_id"] == "PROD-1"
        assert "data_calibracao" in data["origem"]

    def test_dry_run_nao_grava(self, _catalogo_tmp):
        _write(_catalogo_tmp, "PROD-1", {"id": "PROD-1", "origem": "PROPRIA"})

        stats = mod.run_normalize(apply=False)

        data = json.loads((_catalogo_tmp / "PROD-1.json").read_text())
        assert stats["normalizados"] == 1
        assert data["origem"] == "PROPRIA"  # inalterado

    def test_origem_ja_dict_nao_e_tocada(self, _catalogo_tmp):
        origem_rica = {"tipo": "estimado", "fonte_id": "X", "data_calibracao": "2026-01-01", "referencia": "ref"}
        _write(_catalogo_tmp, "PROD-1", {"id": "PROD-1", "origem": origem_rica})

        stats = mod.run_normalize(apply=True)

        data = json.loads((_catalogo_tmp / "PROD-1.json").read_text())
        assert stats["normalizados"] == 0
        assert data["origem"] == origem_rica

    def test_idempotente_segunda_execucao_nao_altera_nada(self, _catalogo_tmp):
        _write(_catalogo_tmp, "PROD-1", {"id": "PROD-1", "origem": "PROPRIA"})

        mod.run_normalize(apply=True)
        stats2 = mod.run_normalize(apply=True)

        assert stats2["normalizados"] == 0
