"""ADR-139 F1-bis — Classificação assistida de origem dos materiais: TDD.

Regras do script `scripts/catalog/classify_origem_material.py` (assistido, não chutado — A5):
  - fonte_preco de compra (cotacao_mercado, tabela_referencia, negociado, contrato_volume,
    referencia_base_original) → proposta AQUISICAO_EXTERNA (evidência: preço vem de fornecedor).
  - Placeholder AGIS (`MA-AGIS-CPU-*`, ADR-138 §D7) → SEM proposta — não é material físico
    (preço = PU legado da própria CPU); classificar seria falsear o dado.
  - fonte_preco ambígua quanto à origem física (catalogo_proprio: usina própria × compra
    de terceiro) → SEM proposta, listado para revisão do editor.
  - Insumo já classificado → nunca sobrescrito. Dry-run padrão; idempotente.
"""

from __future__ import annotations

import json

import pytest

from scripts.catalog.classify_origem_material import propose_origem, run_classification

# ── regra de proposta (unidade) ───────────────────────────────────────────────


class TestProposeOrigem:
    @pytest.mark.parametrize(
        "fonte",
        ["cotacao_mercado", "tabela_referencia", "negociado", "contrato_volume", "referencia_base_original"],
    )
    def test_fonte_de_compra_propoe_aquisicao_externa(self, fonte):
        insumo = {"codigo": "MA-ACO-CA50-12MM", "tipo": "MATERIAL", "fonte_preco": fonte}
        proposta, motivo = propose_origem(insumo)
        assert proposta == "AQUISICAO_EXTERNA"
        assert fonte in motivo

    def test_placeholder_agis_sem_proposta(self):
        insumo = {"codigo": "MA-AGIS-CPU-TERRA-COMPAC-PN", "tipo": "MATERIAL", "fonte_preco": "PLANILHA_AGIS_2026_03"}
        proposta, motivo = propose_origem(insumo)
        assert proposta is None
        assert "placeholder" in motivo.lower()

    def test_catalogo_proprio_sem_proposta_requer_revisao(self):
        """fonte_preco ambígua SEM decisão revisada permanece para o editor."""
        insumo = {"codigo": "MA-USINADO-GENERICO", "tipo": "MATERIAL", "fonte_preco": "catalogo_proprio"}
        proposta, motivo = propose_origem(insumo)
        assert proposta is None
        assert "revis" in motivo.lower()

    @pytest.mark.parametrize("codigo", ["MA-BGTC-MIX", "MA-CBUQ-FAIXA-C"])
    def test_decisoes_revisadas_usinados(self, codigo):
        """Revisão F1-bis (superada e re-revisada): usinagem modelada → geração interna."""
        insumo = {"codigo": codigo, "tipo": "MATERIAL", "fonte_preco": "catalogo_proprio"}
        proposta, motivo = propose_origem(insumo)
        assert proposta == "GERACAO_INTERNA"
        assert "decisão revisada" in motivo
        assert "PROD-USINAGEM" in motivo  # produtora modelada citada no rastro

    def test_ja_classificado_nao_sobrescreve(self):
        insumo = {
            "codigo": "MA-SOLO-CORTE",
            "tipo": "MATERIAL",
            "fonte_preco": "cotacao_mercado",
            "origem_material": "GERACAO_INTERNA",
        }
        proposta, motivo = propose_origem(insumo)
        assert proposta is None
        assert "classificado" in motivo.lower()

    def test_nao_material_ignorado(self):
        insumo = {"codigo": "MO-SERVENTE", "tipo": "MAO_OBRA", "fonte_preco": "tabela_referencia"}
        proposta, _ = propose_origem(insumo)
        assert proposta is None


# ── execução sobre catálogo (integração com tmp_path) ─────────────────────────


class TestRunClassification:
    @pytest.fixture()
    def catalogo_tmp(self, tmp_path):
        mat_dir = tmp_path / "catalogos" / "mendeslobo" / "insumos" / "material"
        mat_dir.mkdir(parents=True)
        insumos = [
            {"codigo": "MA-ACO", "tipo": "MATERIAL", "fonte_preco": "cotacao_mercado"},
            {"codigo": "MA-AGIS-CPU-X", "tipo": "MATERIAL", "fonte_preco": "PLANILHA_AGIS_2026_03"},
            {"codigo": "MA-USINADO-GENERICO", "tipo": "MATERIAL", "fonte_preco": "catalogo_proprio"},
        ]
        for i in insumos:
            (mat_dir / f"{i['codigo']}.json").write_text(json.dumps(i, ensure_ascii=False))
        return tmp_path / "catalogos"

    def test_dry_run_relata_sem_gravar(self, catalogo_tmp):
        stats = run_classification(catalogos_dir=catalogo_tmp, apply=False)
        assert stats["classificados"] == 1
        assert stats["placeholders"] == 1
        assert stats["revisao_manual"] == 1
        data = json.loads((catalogo_tmp / "mendeslobo" / "insumos" / "material" / "MA-ACO.json").read_text())
        assert "origem_material" not in data

    def test_apply_grava_somente_propostas(self, catalogo_tmp):
        run_classification(catalogos_dir=catalogo_tmp, apply=True)
        mat_dir = catalogo_tmp / "mendeslobo" / "insumos" / "material"
        aco = json.loads((mat_dir / "MA-ACO.json").read_text())
        agis = json.loads((mat_dir / "MA-AGIS-CPU-X.json").read_text())
        usinado = json.loads((mat_dir / "MA-USINADO-GENERICO.json").read_text())
        assert aco["origem_material"] == "AQUISICAO_EXTERNA"
        assert "origem_material" not in agis
        assert "origem_material" not in usinado

    def test_idempotente(self, catalogo_tmp):
        run_classification(catalogos_dir=catalogo_tmp, apply=True)
        stats2 = run_classification(catalogos_dir=catalogo_tmp, apply=True)
        assert stats2["classificados"] == 0


# ── censo do catálogo real pós-classificação ──────────────────────────────────


class TestCatalogoRealClassificado:
    def test_censo_mendeslobo(self):
        """53 compras externas (43 fonte_preco + 10 agregados/ligantes SICRO da usinagem);
        5 gerados (3 solos + 2 usinados produzidos por PROD-USINAGEM-*); 49 AGIS + 10 EPI
        (ADR-165 — origem_material não se aplica a EPI, que é sempre compra externa por
        definição mas fora do escopo de sourcing de material de construção) ficam None."""
        from pathlib import Path

        base = Path("config/catalogos/mendeslobo/insumos/material")
        if not base.exists():  # pragma: no cover
            pytest.skip("catálogo mendeslobo indisponível")
        docs = [json.loads(p.read_text(encoding="utf-8-sig")) for p in sorted(base.glob("*.json"))]
        assert len(docs) == 122
        externos = [d for d in docs if d.get("origem_material") == "AQUISICAO_EXTERNA"]
        gerados = [d for d in docs if d.get("origem_material") == "GERACAO_INTERNA"]
        sem_classe = [d for d in docs if not d.get("origem_material")]
        assert len(externos) == 58
        assert len(gerados) == 5
        assert len(sem_classe) == 59
        assert all(d["codigo"].startswith(("MA-AGIS-CPU-", "EPI-")) for d in sem_classe)
        assert not any(d["codigo"].startswith("MA-AGIS-CPU-") for d in externos)
        assert {"MA-BGTC-MIX", "MA-CBUQ-FAIXA-C"} <= {d["codigo"] for d in gerados}
