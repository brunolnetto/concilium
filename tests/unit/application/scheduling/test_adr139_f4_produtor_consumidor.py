"""ADR-139 F4 — Builder catálogo→ReplenishableResource, piloto rfi-r02 e filtros de preço: TDD.

Cobre:
  - `build_replenishable_resources` (novo, fecha também a lacuna da ADR-128 F4 "sem fonte
    real de projeto/escopo"): deriva `producao_por_semana` de `Producao.materiais_gerados`
    e `consumo_por_semana` de `composicao_padrao_equipe.materiais`, ambos × horas/semana
    da atividade (pareamento atividade→Producao é dado de projeto — D5).
  - Piloto corte→aterro com dados reais de `config/catalogos/rfi-r02` (F4): escavação
    3ª cat (produtora, 142,16 m³/h) → corpo de aterro 3ª cat (consumidora, 214,92 m³/h);
    consumidora mais rápida que produtora exige acúmulo de estoque antes de iniciar.
  - price_trend exclui material `GERACAO_INTERNA` (não há preço de mercado/fornecedor).
  - VAL-INS-VAL-01 isenta material `GERACAO_INTERNA` de "preço nulo ou zerado" —
    preço 0.0 é a convenção da ADR-139 D1 (custo já capturado na CPU produtora).

Escrito antes da implementação (red phase).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from concilium.application.scheduling.cpsat_scheduler import CpSatScheduler
from concilium.application.scheduling.models import Activity, ActivityDAG, ResourcePool
from concilium.application.scheduling.replenishable import has_estoque_negativo, project_estoque_semanal
from concilium.application.scheduling.replenishable_builder import build_replenishable_resources
from concilium.domain.models.catalog.catalogo import Insumo
from concilium.domain.models.catalog.producao import Producao

# ── fixtures de modelo ────────────────────────────────────────────────────────


def _producao(pid: str, producao_horaria: float, materiais_gerados=None, materiais=None) -> Producao:
    now = datetime.now(UTC)
    return Producao.model_validate(
        {
            "id": pid,
            "codigo": pid,
            "descricao": pid,
            "producao_horaria": producao_horaria,
            "unidade": "m3",
            "origem": {
                "tipo": "estimado",
                "fonte_id": "teste",
                "data_calibracao": now.isoformat(),
                "referencia": "ADR-139 F4 fixture",
            },
            "condicoes_calibracao": {},
            "qualidade": {
                "confianca_pct": 80,
                "intervalo_confianca": (0.9 * producao_horaria, 1.1 * producao_horaria),
                "quantidade_amostras": 5,
                "desvio_padrao": 1.0,
            },
            "composicao_padrao_equipe": {
                "funcoes": [{"funcao_id": "MO-OP", "num_pessoas": 1}],
                "equipamentos": [{"equip_id": "EQ-X", "num_unidades": 1}],
                "materiais": materiais or [],
            },
            "materiais_gerados": materiais_gerados or [],
            "auditoria": {
                "criado_por": "teste",
                "data_criacao": now.isoformat(),
                "ultima_modificacao": now.isoformat(),
                "modificado_por": "teste",
                "versao": "1.0",
            },
        }
    )


def _insumo_gerado(codigo: str = "MA-SOLO-3CAT", disponibilidade=None) -> Insumo:
    return Insumo.model_validate(
        {
            "codigo": codigo,
            "tipo": "MATERIAL",
            "descricao": "Solo de corte",
            "unidade": "m3",
            "preco_unitario": 0.0,
            "fonte_preco": "catalogo_proprio",
            "origem_material": "GERACAO_INTERNA",
            "atributos_especificos": {"disponibilidade": disponibilidade} if disponibilidade else {},
        }
    )


def _insumo_comprado(codigo: str = "MA-AREIA", disponibilidade=None) -> Insumo:
    return Insumo.model_validate(
        {
            "codigo": codigo,
            "tipo": "MATERIAL",
            "descricao": "Areia comprada",
            "unidade": "m3",
            "preco_unitario": 120.0,
            "fonte_preco": "cotacao_mercado",
            "origem_material": "AQUISICAO_EXTERNA",
            "atributos_especificos": {"disponibilidade": disponibilidade} if disponibilidade else {},
        }
    )


# ── build_replenishable_resources ─────────────────────────────────────────────


class TestBuildReplenishableResources:
    def test_produtor_consumidor_basico(self):
        corte = _producao(
            "corte-prod",
            100.0,
            materiais_gerados=[{"insumo_id": "MA-SOLO-3CAT", "geracao_por_hora": 100.0, "unidade": "m3"}],
        )
        aterro = _producao(
            "aterro-prod", 200.0, materiais=[{"insumo_id": "MA-SOLO-3CAT", "consumo_por_hora": 200.0, "unidade": "m3"}]
        )
        resources = build_replenishable_resources(
            producoes_por_atividade={"corte": corte, "aterro": aterro},
            insumos_por_id={"MA-SOLO-3CAT": _insumo_gerado()},
            horas_semana=40.0,
        )
        assert len(resources) == 1
        r = resources[0]
        assert r.resource_id == "MA-SOLO-3CAT"
        assert r.producao_por_semana == {"corte": 4000.0}
        assert r.consumo_por_semana == {"aterro": 8000.0}
        # GERACAO_INTERNA sem disponibilidade declarada: estoque zero, sem reabastecimento externo.
        assert r.disponibilidade.estoque_inicial == 0.0
        assert r.disponibilidade.taxa_reabastecimento_max is None

    def test_horas_por_atividade_dict(self):
        corte = _producao(
            "corte-prod",
            100.0,
            materiais_gerados=[{"insumo_id": "MA-SOLO-3CAT", "geracao_por_hora": 100.0, "unidade": "m3"}],
        )
        resources = build_replenishable_resources(
            producoes_por_atividade={"corte": corte},
            insumos_por_id={"MA-SOLO-3CAT": _insumo_gerado()},
            horas_semana={"corte": 20.0},
        )
        assert resources[0].producao_por_semana == {"corte": 2000.0}

    def test_disponibilidade_declarada_no_insumo_e_usada(self):
        disp = {"estoque_inicial": 500.0, "capacidade_armazenamento": 10000.0}
        corte = _producao(
            "corte-prod",
            100.0,
            materiais_gerados=[{"insumo_id": "MA-SOLO-3CAT", "geracao_por_hora": 100.0, "unidade": "m3"}],
        )
        resources = build_replenishable_resources(
            producoes_por_atividade={"corte": corte},
            insumos_por_id={"MA-SOLO-3CAT": _insumo_gerado(disponibilidade=disp)},
            horas_semana=40.0,
        )
        assert resources[0].disponibilidade.estoque_inicial == 500.0
        assert resources[0].disponibilidade.capacidade_armazenamento == 10000.0

    def test_consumo_sem_disponibilidade_nem_produtor_e_irrestrito(self):
        """ADR-128: ausência de DisponibilidadeConsumivel = irrestrito — não vira recurso."""
        aterro = _producao(
            "aterro-prod", 200.0, materiais=[{"insumo_id": "MA-AREIA", "consumo_por_hora": 1.0, "unidade": "m3"}]
        )
        resources = build_replenishable_resources(
            producoes_por_atividade={"aterro": aterro},
            insumos_por_id={"MA-AREIA": _insumo_comprado()},
            horas_semana=40.0,
        )
        assert resources == []

    def test_consumo_com_disponibilidade_declarada_vira_recurso_externo(self):
        disp = {"estoque_inicial": 100.0, "taxa_reabastecimento_max": 50.0}
        aterro = _producao(
            "aterro-prod", 200.0, materiais=[{"insumo_id": "MA-AREIA", "consumo_por_hora": 1.0, "unidade": "m3"}]
        )
        resources = build_replenishable_resources(
            producoes_por_atividade={"aterro": aterro},
            insumos_por_id={"MA-AREIA": _insumo_comprado(disponibilidade=disp)},
            horas_semana=40.0,
        )
        assert len(resources) == 1
        assert resources[0].disponibilidade.taxa_reabastecimento_max == 50.0
        assert resources[0].producao_por_semana == {}

    def test_geracao_com_insumo_nao_interno_falha_alto(self):
        corte = _producao(
            "corte-prod",
            100.0,
            materiais_gerados=[{"insumo_id": "MA-AREIA", "geracao_por_hora": 100.0, "unidade": "m3"}],
        )
        with pytest.raises(ValueError, match="VAL-PROD-GERACAO-01"):
            build_replenishable_resources(
                producoes_por_atividade={"corte": corte},
                insumos_por_id={"MA-AREIA": _insumo_comprado()},
                horas_semana=40.0,
            )

    def test_consumo_de_insumo_fora_do_catalogo_e_irrestrito(self):
        """Consumo referenciando insumo desconhecido: sem disponibilidade conhecida → irrestrito."""
        aterro = _producao(
            "aterro-prod", 200.0, materiais=[{"insumo_id": "MA-DESCONHECIDO", "consumo_por_hora": 1.0, "unidade": "m3"}]
        )
        resources = build_replenishable_resources(
            producoes_por_atividade={"aterro": aterro},
            insumos_por_id={},
            horas_semana=40.0,
        )
        assert resources == []

    def test_disponibilidade_ja_instanciada_e_reaproveitada(self):
        """Insumo dict carregando DisponibilidadeConsumivel já construída (não dict)."""
        from concilium.domain.models.catalog.disponibilidade_consumivel import DisponibilidadeConsumivel

        disp = DisponibilidadeConsumivel(estoque_inicial=7.0)
        insumo = {
            "codigo": "MA-SOLO-3CAT",
            "tipo": "MATERIAL",
            "origem_material": "GERACAO_INTERNA",
            "atributos_especificos": {"disponibilidade": disp},
        }
        corte = _producao(
            "corte-prod",
            100.0,
            materiais_gerados=[{"insumo_id": "MA-SOLO-3CAT", "geracao_por_hora": 100.0, "unidade": "m3"}],
        )
        resources = build_replenishable_resources(
            producoes_por_atividade={"corte": corte},
            insumos_por_id={"MA-SOLO-3CAT": insumo},
            horas_semana=40.0,
        )
        assert resources[0].disponibilidade is disp

    def test_horas_dict_sem_atividade_falha_alto(self):
        corte = _producao(
            "corte-prod",
            100.0,
            materiais_gerados=[{"insumo_id": "MA-SOLO-3CAT", "geracao_por_hora": 100.0, "unidade": "m3"}],
        )
        with pytest.raises(ValueError, match="horas_semana"):
            build_replenishable_resources(
                producoes_por_atividade={"corte": corte},
                insumos_por_id={"MA-SOLO-3CAT": _insumo_gerado()},
                horas_semana={"outra-atividade": 40.0},
            )

    def test_override_de_projeto_sem_declaracao_de_catalogo_vira_recurso(self):
        """ADR-128 F5: override de logistica_consumiveis do Escopo/projeto é uma
        terceira fonte de restrição — mesmo sem disponibilidade de catálogo e sem
        produção interna, o insumo passa a virar ReplenishableResource restrito."""
        from concilium.domain.models.catalog.disponibilidade_consumivel import DisponibilidadeConsumivel

        aterro = _producao(
            "aterro-prod", 200.0, materiais=[{"insumo_id": "MA-DIESEL", "consumo_por_hora": 1.0, "unidade": "l"}]
        )
        override = DisponibilidadeConsumivel(estoque_inicial=100.0, taxa_reabastecimento_max=50.0)
        resources = build_replenishable_resources(
            producoes_por_atividade={"aterro": aterro},
            insumos_por_id={"MA-DIESEL": _insumo_comprado(codigo="MA-DIESEL")},
            horas_semana=40.0,
            disponibilidade_overrides={"MA-DIESEL": override},
        )
        assert len(resources) == 1
        assert resources[0].resource_id == "MA-DIESEL"
        assert resources[0].disponibilidade is override

    def test_sem_override_e_sem_declaracao_continua_irrestrito(self):
        """Regressão zero: ausência de override (default None) preserva o
        comportamento existente — não emitir recurso sem nenhuma restrição."""
        aterro = _producao(
            "aterro-prod", 200.0, materiais=[{"insumo_id": "MA-AREIA", "consumo_por_hora": 1.0, "unidade": "m3"}]
        )
        resources = build_replenishable_resources(
            producoes_por_atividade={"aterro": aterro},
            insumos_por_id={"MA-AREIA": _insumo_comprado()},
            horas_semana=40.0,
            disponibilidade_overrides=None,
        )
        assert resources == []

    def test_override_tem_prioridade_sobre_declaracao_de_catalogo(self):
        from concilium.domain.models.catalog.disponibilidade_consumivel import DisponibilidadeConsumivel

        aterro = _producao(
            "aterro-prod", 200.0, materiais=[{"insumo_id": "MA-AREIA", "consumo_por_hora": 1.0, "unidade": "m3"}]
        )
        disp_catalogo = {"estoque_inicial": 1.0}
        override = DisponibilidadeConsumivel(estoque_inicial=999.0)
        resources = build_replenishable_resources(
            producoes_por_atividade={"aterro": aterro},
            insumos_por_id={"MA-AREIA": _insumo_comprado(disponibilidade=disp_catalogo)},
            horas_semana=40.0,
            disponibilidade_overrides={"MA-AREIA": override},
        )
        assert resources[0].disponibilidade is override

    def test_geracao_com_insumo_inexistente_falha_alto(self):
        corte = _producao(
            "corte-prod",
            100.0,
            materiais_gerados=[{"insumo_id": "MA-FANTASMA", "geracao_por_hora": 1.0, "unidade": "m3"}],
        )
        with pytest.raises(ValueError, match="VAL-PROD-GERACAO-01"):
            build_replenishable_resources(
                producoes_por_atividade={"corte": corte},
                insumos_por_id={},
                horas_semana=40.0,
            )


# ── Piloto corte→aterro com dados reais do rfi-r02 ───────────────────────────

_RFI = Path("config/catalogos/rfi-r02")


def _load_rfi(rel: str) -> dict:
    path = _RFI / rel
    if not path.exists():
        pytest.skip(f"dado do piloto ausente: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


class TestPilotoRfiR02:
    def test_insumo_gerado_existe_e_classificado(self):
        d = _load_rfi("insumos/material/MA-SOLO-ESCAVADO-3CAT.json")
        assert d["tipo"] == "MATERIAL"
        assert d["origem_material"] == "GERACAO_INTERNA"
        assert d["preco_unitario"] == 0.0

    def test_produtora_declara_geracao(self):
        d = _load_rfi("produtividades/CPU-TERRA-ESCO-CARGA-3CAT-DMT3000-PROD-001.json")
        gerados = d.get("materiais_gerados") or []
        assert [g["insumo_id"] for g in gerados] == ["MA-SOLO-ESCAVADO-3CAT"]
        # 1 m³ escavado → 1 m³ de material (sem fator de empolamento no piloto):
        assert gerados[0]["geracao_por_hora"] == pytest.approx(d["producao_horaria"])

    def test_consumidora_declara_consumo_bom_convertido(self):
        d = _load_rfi("produtividades/CPU-TERRA-CORPO-ATERRO-3CAT-PROD-001.json")
        equipe = d.get("composicao_padrao_equipe") or d.get("equipe") or {}
        mats = [m for m in equipe.get("materiais") or [] if m["insumo_id"] == "MA-SOLO-ESCAVADO-3CAT"]
        assert len(mats) == 1
        assert mats[0]["origem_entrada"] == "bom_convertido"
        assert mats[0]["consumo_por_hora"] == pytest.approx(d["producao_horaria"])

    def test_piloto_end_to_end_scheduler(self):
        """Catálogo real (dicts crus, como no runtime) → builder → CP-SAT."""
        insumo = _load_rfi("insumos/material/MA-SOLO-ESCAVADO-3CAT.json")
        corte = _load_rfi("produtividades/CPU-TERRA-ESCO-CARGA-3CAT-DMT3000-PROD-001.json")
        aterro = _load_rfi("produtividades/CPU-TERRA-CORPO-ATERRO-3CAT-PROD-001.json")

        resources = build_replenishable_resources(
            producoes_por_atividade={"corte": corte, "aterro": aterro},
            insumos_por_id={insumo["codigo"]: insumo},
            horas_semana=40.0,
        )
        assert len(resources) == 1

        dag = ActivityDAG(
            activities=[
                Activity(
                    activity_id="corte", description="Corte 3ª cat", duration_weeks=4, required_resources={"EQ": 1}
                ),
                Activity(
                    activity_id="aterro", description="Corpo de aterro", duration_weeks=2, required_resources={"EQ": 1}
                ),
            ]
        )
        output = CpSatScheduler(horizon_weeks=20, timeout_seconds=10).schedule(
            dag, ResourcePool(resources={"EQ": 2}), replenishable_resources=resources
        )
        assert output.feasible
        by_id = {sa.activity_id: sa for sa in output.scheduled_activities}
        # Consumidora (8.596,8 m³/sem) mais rápida que produtora (5.686,4 m³/sem):
        # sem estoque inicial, aterro em s<2 fura o estoque — delay até s>=2.
        assert by_id["aterro"].start_week >= 2
        assert not has_estoque_negativo(project_estoque_semanal(resources[0], output.scheduled_activities))


# ── price_trend exclui GERACAO_INTERNA ────────────────────────────────────────


class TestPriceTrendExcluiGeracaoInterna:
    def test_material_gerado_fora_do_relatorio(self):
        from concilium.application.catalog.price_trend import calcular_tendencia

        insumos = [
            {"codigo": "MA-AREIA", "tipo": "MATERIAL", "preco_unitario": 120.0, "origem_material": "AQUISICAO_EXTERNA"},
            {
                "codigo": "MA-SOLO-3CAT",
                "tipo": "MATERIAL",
                "preco_unitario": 15.0,
                "origem_material": "GERACAO_INTERNA",
            },
            {"codigo": "MO-SERVENTE", "tipo": "MAO_OBRA", "preco_unitario": 12.0},
        ]
        rel = calcular_tendencia(insumos, contexto_id="teste-adr139")
        codigos = {t.codigo for i in rel.indices_por_categoria for t in i.insumos}
        assert "MA-AREIA" in codigos
        assert "MO-SERVENTE" in codigos
        assert "MA-SOLO-3CAT" not in codigos


# ── VAL-INS-VAL-01: isenção de preço zero para material gerado ────────────────


class TestValInsVal01GeracaoInterna:
    def _validador(self):
        from unittest.mock import MagicMock

        from concilium.domain.validations.cpu_insumo import ValidadorCPUInsumo

        return ValidadorCPUInsumo(MagicMock())

    def test_geracao_interna_preco_zero_sem_erro(self):
        v = self._validador()
        insumo = {
            "codigo": "MA-SOLO-3CAT",
            "tipo": "MATERIAL",
            "preco_unitario": 0.0,
            "origem_material": "GERACAO_INTERNA",
        }
        resultados = v.validar_valores_auditaveis(insumo)
        assert not any(r.codigo == "VAL-INS-VAL-01" and r.status == "ERRO" for r in resultados)

    def test_aquisicao_externa_preco_zero_continua_erro(self):
        v = self._validador()
        insumo = {
            "codigo": "MA-AREIA",
            "tipo": "MATERIAL",
            "preco_unitario": 0.0,
            "origem_material": "AQUISICAO_EXTERNA",
        }
        resultados = v.validar_valores_auditaveis(insumo)
        assert any(r.codigo == "VAL-INS-VAL-01" and r.status == "ERRO" for r in resultados)

    def test_nao_classificado_preco_zero_continua_erro(self):
        v = self._validador()
        insumo = {"codigo": "MA-X", "tipo": "MATERIAL", "preco_unitario": 0.0}
        resultados = v.validar_valores_auditaveis(insumo)
        assert any(r.codigo == "VAL-INS-VAL-01" and r.status == "ERRO" for r in resultados)
