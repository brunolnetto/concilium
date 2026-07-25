"""ADR-139 F5-ter — Vincula produção de solo às escavações do mendeslobo: QA de dados.

Valida o resultado de `scripts/catalog/cure_producao_escavacao_solo_mendeslobo.py`:

  - As 6 produtividades de escavação (1CAT/2CAT/3CAT × DMT2000/DMT3000) declaram
    `materiais_gerados` com `geracao_por_hora` == `valor_horario` (coeficiente 1
    m³/m³, mesmo padrão já correto de rfi-r02).
  - Idempotência do script.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.catalog.cure_producao_escavacao_solo_mendeslobo import _ESCAVACOES, run_cure

_CAT = Path("config/catalogos/mendeslobo")

pytestmark = pytest.mark.skipif(not _CAT.exists(), reason="catálogo mendeslobo indisponível")


def _load(rel: str) -> dict:
    return json.loads((_CAT / rel).read_text(encoding="utf-8-sig"))


class TestProducaoVinculada:
    @pytest.mark.parametrize("pid", sorted(_ESCAVACOES))
    def test_materiais_gerados_presente_com_coeficiente_1_para_1(self, pid):
        prod = _load(f"produtividades/{pid}.json")
        (gerado,) = prod["materiais_gerados"]
        assert gerado["insumo_id"] == _ESCAVACOES[pid]
        assert gerado["geracao_por_hora"] == pytest.approx(prod["valor_horario"])
        assert "ADR-139" in gerado["descricao"]


class TestScriptIdempotente:
    def test_reexecucao_nao_altera_nada(self):
        stats = run_cure(apply=False)
        assert stats == {"produtoras_vinculadas": 0}
