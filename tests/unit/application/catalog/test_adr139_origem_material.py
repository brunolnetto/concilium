"""ADR-139 F1/F2 — Origem de materiais consumíveis e lado produtor no catálogo: TDD.

Cobre:
  - F1/D1: `Insumo.origem_material` (AQUISICAO_EXTERNA × GERACAO_INTERNA), default None
    retrocompatível; VAL-INSUMO-ORIGEM-01 (ERRO) quando preenchido em tipo != MATERIAL.
  - F1/D2: `MaterialEquipe.origem_entrada` (consumo_operacional × bom_convertido),
    default None — resolve a nota de design da ADR-138 §D7.
  - F1: backfill determinístico das entradas `bom_convertido` criadas pela ADR-138 F2
    (script `scripts/catalog/backfill_origem_entrada_bom_convertido.py`), idempotente.
  - F2/D3: `MaterialGerado` + `Producao.materiais_gerados` (default lista vazia).
  - F2: VAL-PROD-GERACAO-01 (ERRO) — `MaterialGerado.insumo_id` inexistente ou com
    `origem_material != "GERACAO_INTERNA"`.

Escrito antes da implementação (red phase).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from concilium.domain.models.catalog.catalogo import Insumo, MaterialEquipe
from concilium.domain.models.catalog.producao import Producao

# ── helpers ───────────────────────────────────────────────────────────────────


def _insumo_kwargs(**overrides) -> dict:
    base = {
        "codigo": "MA-AREIA-MEDIA",
        "tipo": "MATERIAL",
        "descricao": "Areia média lavada",
        "unidade": "m3",
        "preco_unitario": 120.0,
        "fonte_preco": "catalogo_proprio",
    }
    base.update(overrides)
    return base


def _producao_kwargs(**overrides) -> dict:
    now = datetime.now(UTC)
    base = {
        "id": "PROD-ESCAV-001",
        "codigo": "ESCAV-COMUM",
        "descricao": "Escavação de material comum",
        "valor_horario": 120.0,
        "unidade": "m3",
        "origem": {
            "tipo": "estimado",
            "fonte_id": "teste",
            "data_calibracao": now.isoformat(),
            "referencia": "ADR-139 fixture",
        },
        "condicoes_calibracao": {},
        "qualidade": {
            "confianca_pct": 80,
            "intervalo_confianca": (100.0, 140.0),
            "quantidade_amostras": 5,
            "desvio_padrao": 8.0,
        },
        "composicao_padrao_equipe": {
            "funcoes": [{"funcao_id": "MO-OPERADOR", "num_pessoas": 1}],
            "equipamentos": [{"equip_id": "EQ-ESCAVADEIRA", "num_unidades": 1}],
        },
        "auditoria": {
            "criado_por": "teste",
            "data_criacao": now.isoformat(),
            "ultima_modificacao": now.isoformat(),
            "modificado_por": "teste",
            "versao": "1.0",
        },
    }
    base.update(overrides)
    return base


# ── F1/D1: Insumo.origem_material ─────────────────────────────────────────────


class TestInsumoOrigemMaterial:
    def test_default_none_retrocompativel(self):
        insumo = Insumo(**_insumo_kwargs())
        assert insumo.origem_material is None

    def test_aceita_aquisicao_externa(self):
        insumo = Insumo(**_insumo_kwargs(origem_material="AQUISICAO_EXTERNA"))
        assert insumo.origem_material == "AQUISICAO_EXTERNA"

    def test_aceita_geracao_interna(self):
        insumo = Insumo(**_insumo_kwargs(codigo="MA-SOLO-CORTE", origem_material="GERACAO_INTERNA"))
        assert insumo.origem_material == "GERACAO_INTERNA"

    def test_valor_invalido_rejeitado(self):
        with pytest.raises(ValidationError):
            Insumo(**_insumo_kwargs(origem_material="COMPRADO"))

    @pytest.mark.parametrize("tipo", ["MAO_OBRA", "EQUIPAMENTO", "TERCEIRIZADO"])
    def test_val_insumo_origem_01_tipo_nao_material_falha_alto(self, tipo):
        """VAL-INSUMO-ORIGEM-01: origem_material só é válido para tipo MATERIAL."""
        with pytest.raises(ValidationError, match="VAL-INSUMO-ORIGEM-01"):
            Insumo(**_insumo_kwargs(codigo="MO-SERVENTE", tipo=tipo, origem_material="AQUISICAO_EXTERNA"))

    @pytest.mark.parametrize("tipo", ["MAO_OBRA", "EQUIPAMENTO", "TERCEIRIZADO"])
    def test_tipo_nao_material_sem_origem_continua_valido(self, tipo):
        insumo = Insumo(**_insumo_kwargs(codigo="MO-SERVENTE", tipo=tipo))
        assert insumo.origem_material is None

    def test_json_legado_sem_campo_carrega(self):
        payload = json.loads(json.dumps(_insumo_kwargs()))
        insumo = Insumo.model_validate(payload)
        assert insumo.origem_material is None


# ── F1/D2: MaterialEquipe.origem_entrada ──────────────────────────────────────


class TestMaterialEquipeOrigemEntrada:
    def test_default_none_retrocompativel(self):
        me = MaterialEquipe(insumo_id="MA-AGUA", consumo_por_hora=0.5, unidade="m3")
        assert me.origem_entrada is None

    @pytest.mark.parametrize("origem", ["consumo_operacional", "bom_convertido"])
    def test_aceita_valores_validos(self, origem):
        me = MaterialEquipe(insumo_id="MA-CIMENTO", consumo_por_hora=7.0, unidade="saco", origem_entrada=origem)
        assert me.origem_entrada == origem

    def test_valor_invalido_rejeitado(self):
        with pytest.raises(ValidationError):
            MaterialEquipe(insumo_id="MA-CIMENTO", consumo_por_hora=7.0, unidade="saco", origem_entrada="bom")

    def test_roundtrip_serializacao(self):
        me = MaterialEquipe(
            insumo_id="MA-CIMENTO", consumo_por_hora=7.0, unidade="saco", origem_entrada="bom_convertido"
        )
        assert MaterialEquipe.model_validate(me.model_dump()).origem_entrada == "bom_convertido"


# ── F1: backfill bom_convertido (ADR-138 F2 → ADR-139) ───────────────────────


class TestBackfillOrigemEntrada:
    @pytest.fixture()
    def catalogo_tmp(self, tmp_path):
        """Mini-catálogo com uma Producao contendo 2 MaterialEquipe sem origem_entrada."""
        cat = tmp_path / "catalogos" / "mendeslobo"
        prod_dir = cat / "producoes"
        prod_dir.mkdir(parents=True)
        prod = _producao_kwargs()
        prod["composicao_padrao_equipe"]["materiais"] = [
            {"insumo_id": "MA-CIMENTO-CP2", "consumo_por_hora": 7.0, "unidade": "saco"},
            {"insumo_id": "MA-AREIA-MEDIA", "consumo_por_hora": 1.2, "unidade": "m3"},
        ]
        (prod_dir / "PROD-ESCAV-001.json").write_text(json.dumps(prod, ensure_ascii=False))
        return tmp_path / "catalogos"

    def _run(self, catalogos_dir, apply: bool) -> dict:
        from scripts.catalog.backfill_origem_entrada_bom_convertido import run_backfill

        return run_backfill(catalogos_dir=catalogos_dir, apply=apply)

    def test_dry_run_nao_altera_arquivos(self, catalogo_tmp):
        antes = (catalogo_tmp / "mendeslobo" / "producoes" / "PROD-ESCAV-001.json").read_text()
        stats = self._run(catalogo_tmp, apply=False)
        depois = (catalogo_tmp / "mendeslobo" / "producoes" / "PROD-ESCAV-001.json").read_text()
        assert antes == depois
        assert stats["entradas_marcadas"] == 2

    def test_apply_marca_bom_convertido(self, catalogo_tmp):
        self._run(catalogo_tmp, apply=True)
        data = json.loads((catalogo_tmp / "mendeslobo" / "producoes" / "PROD-ESCAV-001.json").read_text())
        origens = [m["origem_entrada"] for m in data["composicao_padrao_equipe"]["materiais"]]
        assert origens == ["bom_convertido", "bom_convertido"]

    def test_idempotente(self, catalogo_tmp):
        self._run(catalogo_tmp, apply=True)
        stats2 = self._run(catalogo_tmp, apply=True)
        assert stats2["entradas_marcadas"] == 0

    def test_nao_sobrescreve_classificacao_existente(self, catalogo_tmp):
        path = catalogo_tmp / "mendeslobo" / "producoes" / "PROD-ESCAV-001.json"
        data = json.loads(path.read_text())
        data["composicao_padrao_equipe"]["materiais"][0]["origem_entrada"] = "consumo_operacional"
        path.write_text(json.dumps(data, ensure_ascii=False))
        stats = self._run(catalogo_tmp, apply=True)
        assert stats["entradas_marcadas"] == 1
        data = json.loads(path.read_text())
        assert data["composicao_padrao_equipe"]["materiais"][0]["origem_entrada"] == "consumo_operacional"

    def test_catalogo_real_mendeslobo_esta_classificado_ou_backfill_cobre(self):
        """33 entradas da ADR-138 F2 + 7 do enriquecimento F4 + 13 das usinagens BGTC/CBUQ
        + 1 do split F5-bis (CPU-TERRA-COMPAC-PN em 1CAT+2CAT) — todas classificadas."""
        from pathlib import Path

        base = Path("config/catalogos/mendeslobo")
        if not base.exists():  # pragma: no cover - proteção para execução fora do repo
            pytest.skip("catálogo mendeslobo indisponível")
        entradas = []
        for p in base.rglob("*.json"):
            d = json.loads(p.read_text(encoding="utf-8-sig"))
            if isinstance(d, dict) and "composicao_padrao_equipe" in d:
                entradas.extend((d["composicao_padrao_equipe"] or {}).get("materiais") or [])
        assert len(entradas) == 54
        # Pós-backfill (ADR-138 F2), enriquecimento e usinagens (F4): todas classificadas.
        assert all(m.get("origem_entrada") == "bom_convertido" for m in entradas)


# ── F2/D3: MaterialGerado + Producao.materiais_gerados ────────────────────────


class TestMaterialGerado:
    def test_modelo_basico(self):
        from concilium.domain.models.catalog.catalogo import MaterialGerado

        mg = MaterialGerado(insumo_id="MA-SOLO-CORTE", geracao_por_hora=120.0, unidade="m3")
        assert mg.geracao_por_hora == 120.0

    def test_geracao_deve_ser_positiva(self):
        from concilium.domain.models.catalog.catalogo import MaterialGerado

        with pytest.raises(ValidationError):
            MaterialGerado(insumo_id="MA-SOLO-CORTE", geracao_por_hora=0.0, unidade="m3")

    def test_producao_default_lista_vazia(self):
        producao = Producao(**_producao_kwargs())
        assert producao.materiais_gerados == []

    def test_producao_aceita_materiais_gerados(self):
        producao = Producao(
            **_producao_kwargs(
                materiais_gerados=[{"insumo_id": "MA-SOLO-CORTE", "geracao_por_hora": 120.0, "unidade": "m3"}]
            )
        )
        assert producao.materiais_gerados[0].insumo_id == "MA-SOLO-CORTE"

    def test_json_legado_sem_campo_carrega(self):
        payload = json.loads(json.dumps(_producao_kwargs(), default=str))
        producao = Producao.model_validate(payload)
        assert producao.materiais_gerados == []


# ── F2: cure_schema não descarta nem corrompe os campos novos ─────────────────


class TestCureSchemaToleraCamposADR139:
    def test_cure_producao_preserva_materiais_gerados_e_origem_entrada(self):
        from concilium.application.catalog.cure_schema._core import CurationReport
        from concilium.application.catalog.cure_schema._cure_producao import cure_producao

        prod = _producao_kwargs()
        prod["composicao_padrao_equipe"]["materiais"] = [
            {
                "insumo_id": "MA-CIMENTO-CP2",
                "consumo_por_hora": 7.0,
                "unidade": "saco",
                "origem_entrada": "bom_convertido",
            }
        ]
        prod["materiais_gerados"] = [{"insumo_id": "MA-SOLO-CORTE", "geracao_por_hora": 120.0, "unidade": "m3"}]

        curado = cure_producao(prod, CurationReport(), apply=True)

        assert curado["materiais_gerados"] == prod["materiais_gerados"]
        materiais = curado["composicao_padrao_equipe"]["materiais"]
        assert materiais[0]["origem_entrada"] == "bom_convertido"


# ── F2: VAL-PROD-GERACAO-01 ───────────────────────────────────────────────────


def _make_validator():
    from concilium.domain.validations.cpu_insumo import ValidadorCPUInsumo

    repo = MagicMock()
    repo.insumo_existe.return_value = True
    repo.funcao_existe.return_value = True
    repo.equipamento_existe.return_value = True
    repo.producao_existe.return_value = True
    return ValidadorCPUInsumo(repo)


class TestValidarMateriaisGerados:
    def _cpu_com_producao(self, validator, materiais_gerados, insumo=None):
        validator.repo.obter_producao.return_value = {
            "composicao_padrao_equipe": {"funcoes": [], "equipamentos": []},
            "materiais_gerados": materiais_gerados,
        }
        validator.repo.obter_insumo.return_value = insumo
        return {"codigo": "CPU-ESCAV", "producao_id_ref": "PROD-ESCAV-001"}

    def test_ok_quando_insumo_geracao_interna(self):
        v = _make_validator()
        cpu = self._cpu_com_producao(
            v,
            [{"insumo_id": "MA-SOLO-CORTE", "geracao_por_hora": 120.0, "unidade": "m3"}],
            insumo={"codigo": "MA-SOLO-CORTE", "tipo": "MATERIAL", "origem_material": "GERACAO_INTERNA"},
        )
        result = v.validar_materiais_gerados(cpu)
        assert result.codigo == "VAL-PROD-GERACAO-01"
        assert result.status == "OK"

    def test_erro_quando_insumo_inexistente(self):
        v = _make_validator()
        v.repo.insumo_existe.return_value = False
        cpu = self._cpu_com_producao(
            v, [{"insumo_id": "MA-FANTASMA", "geracao_por_hora": 1.0, "unidade": "m3"}], insumo=None
        )
        result = v.validar_materiais_gerados(cpu)
        assert result.status == "ERRO"
        assert "MA-FANTASMA" in result.mensagem

    def test_erro_quando_origem_nao_geracao_interna(self):
        v = _make_validator()
        cpu = self._cpu_com_producao(
            v,
            [{"insumo_id": "MA-AREIA-MEDIA", "geracao_por_hora": 1.0, "unidade": "m3"}],
            insumo={"codigo": "MA-AREIA-MEDIA", "tipo": "MATERIAL", "origem_material": "AQUISICAO_EXTERNA"},
        )
        result = v.validar_materiais_gerados(cpu)
        assert result.status == "ERRO"
        assert "GERACAO_INTERNA" in result.mensagem

    def test_erro_quando_origem_nao_classificada(self):
        """Insumo sem origem_material não pode ancorar MaterialGerado — classificação é pré-requisito."""
        v = _make_validator()
        cpu = self._cpu_com_producao(
            v,
            [{"insumo_id": "MA-AREIA-MEDIA", "geracao_por_hora": 1.0, "unidade": "m3"}],
            insumo={"codigo": "MA-AREIA-MEDIA", "tipo": "MATERIAL"},
        )
        result = v.validar_materiais_gerados(cpu)
        assert result.status == "ERRO"

    def test_ok_quando_sem_materiais_gerados(self):
        v = _make_validator()
        cpu = self._cpu_com_producao(v, [])
        result = v.validar_materiais_gerados(cpu)
        assert result.status == "OK"

    def test_wired_em_validar_cpu_completa(self):
        """validar_cpu_completa deve incluir VAL-PROD-GERACAO-01 no relatório."""
        v = _make_validator()
        cpu = self._cpu_com_producao(
            v, [{"insumo_id": "MA-FANTASMA", "geracao_por_hora": 1.0, "unidade": "m3"}], insumo=None
        )
        v.repo.insumo_existe.return_value = False
        cpu["unidade"] = "m3"
        cpu["categoria"] = "TERRAPLENAGEM"
        resultados = v.validar_cpu_completa(cpu)
        codigos = {r.codigo for r in resultados}
        assert "VAL-PROD-GERACAO-01" in codigos
