"""ADR-139 F4-ter — Consolidação de agregados canônicos: QA de dados (mendeslobo).

Valida `scripts/catalog/consolida_agregados_canonicos.py`:

  - Um canônico por material, com preço vigente = cotação de mercado mais recente da
    empresa (AGIS 2026; ou 2025-05 quando única, com `_alerta_preco` de defasagem).
  - Preço SICRO 202604-SP preservado em `historico_precos` (referência de sanidade).
  - Os 10 códigos consolidados (`*-SICRO` gêmeos + `MA-{BSTC,BDTC,BTTC}-CORPO-*`)
    estão `_superseded_por` e sem NENHUM consumidor no catálogo.
  - Usinagens referenciam canônicos; preços re-concluídos na base da empresa
    (validado em test_adr139_f4_usinagem_preco_concluido.py).
  - Idempotência do script.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.catalog.consolida_agregados_canonicos import _SUPERSEDED, run_consolidation

_CAT = Path("config/catalogos/mendeslobo")

pytestmark = pytest.mark.skipif(not _CAT.exists(), reason="catálogo mendeslobo indisponível")

_VIGENTES = {
    "MA-BRITA-0-PEDRISCO": (145.0, "cotacao_mercado"),
    "MA-BRITA-2": (145.0, "cotacao_mercado"),
    "MA-BRITA-3": (140.0, "cotacao_mercado"),
    "MA-BRITA-4-RACHAO": (147.0, "cotacao_mercado"),
    "MA-PO-DE-PEDRA": (165.0, "cotacao_mercado"),
    "MA-AREIA-GROSSA-LAVADA": (120.0, "cotacao_mercado"),
    "MA-AREIA-FINA": (100.0, "cotacao_mercado"),
    "MA-BRITA-1": (78.0, "cotacao_mercado"),
    "MA-AREIA-MEDIA": (68.0, "cotacao_mercado"),
}

_COM_SICRO_NO_HISTORICO = {
    "MA-BRITA-0-PEDRISCO": 184.71,
    "MA-BRITA-2": 170.77,
    "MA-BRITA-3": 162.63,
    "MA-PO-DE-PEDRA": 160.63,
    "MA-BRITA-1": 172.79,
    "MA-AREIA-MEDIA": 140.84,
}


def _insumo(codigo: str) -> dict:
    return json.loads((_CAT / "insumos" / "material" / f"{codigo}.json").read_text(encoding="utf-8-sig"))


class TestCanonicosVigentes:
    @pytest.mark.parametrize("codigo", sorted(_VIGENTES))
    def test_preco_vigente_e_fonte(self, codigo):
        preco, fonte = _VIGENTES[codigo]
        ins = _insumo(codigo)
        assert ins["preco_unitario"] == preco
        assert ins["fonte_preco"] == fonte
        assert ins.get("origem_material") == "AQUISICAO_EXTERNA"

    @pytest.mark.parametrize("codigo", sorted(_COM_SICRO_NO_HISTORICO))
    def test_referencia_sicro_no_historico(self, codigo):
        ins = _insumo(codigo)
        historicos = [h["preco_unitario"] for h in ins.get("historico_precos") or []]
        assert _COM_SICRO_NO_HISTORICO[codigo] in historicos

    @pytest.mark.parametrize("codigo", ["MA-BRITA-1", "MA-AREIA-MEDIA"])
    def test_alerta_de_defasagem_registrado(self, codigo):
        ins = _insumo(codigo)
        assert "recotar" in (ins.get("_alerta_preco") or "")


class TestSupersededSemConsumidores:
    def test_todos_marcados_e_orfaos(self):
        consumidos: set[str] = set()
        for sub in ("produtividades", "producoes"):
            for p in (_CAT / sub).glob("*.json"):
                d = json.loads(p.read_text(encoding="utf-8-sig"))
                eq = d.get("composicao_padrao_equipe") or d.get("equipe") or {}
                consumidos.update(m["insumo_id"] for m in eq.get("materiais") or [])
        for p in (_CAT / "cpus").glob("*.json"):
            d = json.loads(p.read_text(encoding="utf-8-sig"))
            consumidos.update(ci.get("insumo_id") for ci in d.get("composicao_itens") or [])

        for antigo, novo in _SUPERSEDED.items():
            ins = _insumo(antigo)
            assert ins.get("_superseded_por") == novo, antigo
            assert antigo not in consumidos, f"{antigo} ainda tem consumidor"


class TestUsinagensUsamCanonicos:
    @pytest.mark.parametrize("pid", ["PROD-USINAGEM-BGTC-001", "PROD-USINAGEM-CBUQ-001"])
    def test_sem_referencias_a_gemeos_sicro(self, pid):
        d = json.loads((_CAT / "producoes" / f"{pid}.json").read_text(encoding="utf-8-sig"))
        eq = d.get("composicao_padrao_equipe") or {}
        ids = {m["insumo_id"] for m in eq.get("materiais") or []}
        assert not any(i.endswith("-SICRO") for i in ids)


class TestScriptIdempotente:
    def test_reexecucao_nao_altera_nada(self):
        stats = run_consolidation(apply=False)
        assert stats == {
            "canonicos_atualizados": 0,
            "canonicos_criados": 0,
            "repoints": 0,
            "superseded_marcados": 0,
            "alertas": 0,
        }
