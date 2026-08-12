"""ADR-176 F3 — mob/demob diferenciado por tipo de transporte no catálogo real.

Achado da ADR-137 D2 (confirmado pela investigação da ADR-176): todo
equipamento das composições `PROD-REJEITO-COMP-EQ1..4` (mendeslobo, obra
SERRA_VERDE) tinha o mesmo valor uniforme de mobilização/desmobilização
(R$6.500,00), independente do tipo — inclusive para os 2 caminhões
(Caminhão Pipa E0013, Caminhão Basculante E0005), que rodam por conta própria
até o canteiro e não exigem prancha, ao contrário dos demais 6 equipamentos
(trator de esteiras, motoniveladora, trator de pneus, pá carregadeira,
escavadeira, rolo compactador — todos fora-de-estrada, exigem transporte
especial).

Decisão do usuário: diferenciar só essa distinção estrutural (rodoviário vs.
requer prancha), sem fingir precisão por peso/tipo específico de cada
máquina fora-de-estrada — caminhões passam a R$1.300,00 (20% do valor de
prancha), os demais 6 equipamentos mantêm R$6.500,00 inalterado.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[4]
# ADR-053/#154 (main, pós-fork desta branch): producoes/ unificada em produtividades/.
_PRODUCOES = _ROOT / "config/catalogos/mendeslobo/produtividades"

_ARQUIVOS = [f"PROD-REJEITO-COMP-EQ{n}-001.json" for n in (1, 2, 3, 4)]

_RODOVIARIOS = {"E0013", "E0005"}  # Caminhão Pipa, Caminhão Basculante — sem prancha
_REQUER_PRANCHA = {"E0027", "E0035", "E0021", "E0034", "E0024", "E0014"}


@pytest.mark.parametrize("arquivo", _ARQUIVOS)
class TestMobDemobDiferenciadoPorTransporte:
    def _equipamentos(self, arquivo: str) -> list[dict]:
        d = json.loads((_PRODUCOES / arquivo).read_text())
        return d["composicao_padrao_equipe"]["equipamentos"]

    def test_caminhoes_tem_valor_reduzido(self, arquivo):
        for e in self._equipamentos(arquivo):
            if e["equip_id"] in _RODOVIARIOS:
                assert e["custo_mobilizacao"] == 1300.0
                assert e["custo_desmobilizacao"] == 1300.0

    def test_equipamentos_fora_de_estrada_mantem_valor_de_prancha(self, arquivo):
        for e in self._equipamentos(arquivo):
            if e["equip_id"] in _REQUER_PRANCHA:
                assert e["custo_mobilizacao"] == 6500.0
                assert e["custo_desmobilizacao"] == 6500.0

    def test_todos_os_8_equipamentos_cobertos(self, arquivo):
        ids = {e["equip_id"] for e in self._equipamentos(arquivo)}
        assert ids == _RODOVIARIOS | _REQUER_PRANCHA
