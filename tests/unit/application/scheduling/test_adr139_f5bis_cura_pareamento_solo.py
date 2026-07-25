"""ADR-139 F5-bis — Cura do pareamento de solo em CPU-TERRA-COMPAC-PN (AGIS): QA de dados.

Valida o resultado de `scripts/catalog/cure_pareamento_solo_compac_pn_agis.py`:

  - BOM dividido em duas linhas (1CAT + 2CAT), proporcionais à composição real
    1CAT/2CAT da EAP AGIS (444.378,2 + 691.257,1 m³).
  - Soma das duas taxas preserva o `valor_horario` original (173,01) — a
    produtividade da equipe não muda, só a atribuição do consumo entre materiais.
  - `CPU-TERRA-COMPAC-PI` não é tocado (seu volume não bate com nenhuma soma
    residual das categorias — não é derivável objetivamente).
  - Idempotência do script.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.catalog.cure_pareamento_solo_compac_pn_agis import PRODUTIVIDADE_ID, run_cure

_CAT = Path("config/catalogos/mendeslobo")

pytestmark = pytest.mark.skipif(not _CAT.exists(), reason="catálogo mendeslobo indisponível")


def _load(rel: str) -> dict:
    return json.loads((_CAT / rel).read_text(encoding="utf-8-sig"))


def _materiais(prod: dict) -> list[dict]:
    equipe = prod.get("composicao_padrao_equipe") or prod.get("equipe") or {}
    return equipe.get("materiais") or []


class TestBomDivididoProporcional:
    def test_duas_linhas_1cat_e_2cat(self):
        prod = _load(f"produtividades/{PRODUTIVIDADE_ID}.json")
        insumo_ids = [m["insumo_id"] for m in _materiais(prod)]
        assert insumo_ids == ["MA-SOLO-ESCAVADO-1CAT", "MA-SOLO-ESCAVADO-2CAT"]

    def test_soma_das_taxas_preserva_valor_horario(self):
        prod = _load(f"produtividades/{PRODUTIVIDADE_ID}.json")
        soma = sum(m["consumo_por_hora"] for m in _materiais(prod))
        assert soma == pytest.approx(prod["valor_horario"])

    def test_fracao_proporcional_a_producao_real_da_eap(self):
        """444.378,2 (1CAT) + 691.257,1 (2CAT) = 1.135.635,3 m³ == quantitativo do item
        de EAP que usa esta CPU — a fração de cada material segue essa proporção real."""
        prod = _load(f"produtividades/{PRODUTIVIDADE_ID}.json")
        (mat_1cat,) = [m for m in _materiais(prod) if m["insumo_id"] == "MA-SOLO-ESCAVADO-1CAT"]
        (mat_2cat,) = [m for m in _materiais(prod) if m["insumo_id"] == "MA-SOLO-ESCAVADO-2CAT"]
        assert mat_1cat["consumo_por_hora"] == pytest.approx(67.70, abs=1e-2)
        assert mat_2cat["consumo_por_hora"] == pytest.approx(105.31, abs=1e-2)


class TestCpuPiNaoTocado:
    def test_pi_continua_100_por_cento_em_1cat(self):
        prod = _load("produtividades/CPU-TERRA-COMPAC-PI-PROD-001.json")
        (mat,) = _materiais(prod)
        assert mat["insumo_id"] == "MA-SOLO-ESCAVADO-1CAT"
        assert mat["consumo_por_hora"] == pytest.approx(prod["valor_horario"])


class TestScriptIdempotente:
    def test_reexecucao_nao_altera_nada(self):
        stats = run_cure(apply=False)
        assert stats == {"materiais_divididos": 0}
