"""Testes unitários — ADR-142: jurisdição por município e fallback gracioso."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from concilium.application.runtime.exceptions import RuntimeDomainError
from concilium.application.runtime.mixins.config import ConfigMixin
from concilium.application.services.catalog.geo_diesel_resolver import _uf_de_jurisdicao
from concilium.domain.models.catalog.jurisdicao import (
    FonteClimatica,
    Jurisdicao,
    MotorEncargosSociais,
    ProvedorReferencia,
)
from concilium.domain.models.catalog.versioned import DateRange, JurisdicaoVersionada, VersaoJurisdicao


def _provedor() -> ProvedorReferencia:
    return ProvedorReferencia(
        codigo="SICRO3",
        nome="SICRO 3",
        mantenedor="DNIT",
        cadencia_atualizacao="mensal",
        uso_tipico="Referência de preços de infraestrutura",
    )


def _fonte_climatica() -> FonteClimatica:
    return FonteClimatica(
        provedor="INMET",
        url_base="https://inmet.gov.br",
        metodo_consulta="API REST",
        granularidade="mensal",
    )


def _motor_encargos() -> MotorEncargosSociais:
    return MotorEncargosSociais(
        versao="2024.1",
        percentual_total=0.8,
        percentual_horista=0.8,
        percentual_mensalista=0.5,
        percentual_pj=0.1,
    )


def _make_jurisdicao(**kwargs) -> Jurisdicao:
    defaults = dict(
        codigo="BR",
        nome="Brasil",
        moeda="BRL",
        regime_trabalhista="CLT",
        provedores_referencia=[_provedor()],
        fonte_climatica=_fonte_climatica(),
        motor_encargos_sociais=_motor_encargos(),
    )
    defaults.update(kwargs)
    return Jurisdicao(**defaults)


# ── Jurisdicao.codigo: 3º segmento de município ───────────────────────────────


class TestJurisdicaoCodigoMunicipio:
    def test_aceita_codigo_com_municipio(self):
        assert _make_jurisdicao(codigo="BR-CE-FORTALEZA").codigo == "BR-CE-FORTALEZA"
        assert _make_jurisdicao(codigo="BR-RJ-RIO_DE_JANEIRO").codigo == "BR-RJ-RIO_DE_JANEIRO"

    def test_ainda_aceita_codigo_uf_sem_municipio(self):
        """Regressão: 2 segmentos continua funcionando exatamente como antes."""
        assert _make_jurisdicao(codigo="BR-CE").codigo == "BR-CE"
        assert _make_jurisdicao(codigo="BR").codigo == "BR"

    def test_ainda_rejeita_codigo_invalido(self):
        with pytest.raises(ValidationError):
            _make_jurisdicao(codigo="brasil")

    def test_ainda_rejeita_uf_mal_formada(self):
        """Regressão: UF com número errado de letras continua rejeitada mesmo
        com o pattern estendido para aceitar município."""
        with pytest.raises(ValidationError):
            _make_jurisdicao(codigo="BR-CEA")
        with pytest.raises(ValidationError):
            _make_jurisdicao(codigo="BR-")

    def test_rejeita_municipio_mal_formado(self):
        with pytest.raises(ValidationError):
            _make_jurisdicao(codigo="BR-CE-A")  # município com 1 caractere: curto demais


# ── JurisdicaoVersionada.id: mesma extensão ───────────────────────────────────


class TestJurisdicaoVersionadaMunicipio:
    def _versao(self) -> VersaoJurisdicao:
        return VersaoJurisdicao(
            versao="2026-04",
            validade=DateRange(inicio=date(2026, 4, 1), fim=None),
            percentual_encargos_clt=1.777,
            percentual_encargos_pj=0.0,
            moeda="BRL",
            auditado_por="tester",
            auditado_em=datetime(2026, 5, 1),
        )

    def test_aceita_id_com_municipio(self):
        j = JurisdicaoVersionada(
            id="BR-CE-FORTALEZA",
            nome="Brasil — Ceará — Fortaleza",
            regime_trabalhista="CLT",
            versoes=[self._versao()],
        )
        assert j.id == "BR-CE-FORTALEZA"
        assert j.id_atu == "BR-CE-FORTALEZA@2026-04"

    def test_ainda_aceita_id_uf_sem_municipio(self):
        j = JurisdicaoVersionada(
            id="BR-CE",
            nome="Brasil — Ceará",
            regime_trabalhista="CLT",
            versoes=[self._versao()],
        )
        assert j.id == "BR-CE"


# ── _uf_de_jurisdicao: parser corrigido (split, não partition) ───────────────


class TestUfDeJurisdicao:
    def test_extrai_uf_de_2_segmentos(self):
        """Regressão: comportamento atual inalterado."""
        assert _uf_de_jurisdicao("BR-CE") == "CE"
        assert _uf_de_jurisdicao("BR-SP") == "SP"

    def test_extrai_uf_de_3_segmentos(self):
        """Antes do fix: .partition('-') retornava 'CE-FORTALEZA' (errado)."""
        assert _uf_de_jurisdicao("BR-CE-FORTALEZA") == "CE"

    def test_retorna_none_para_ausente_ou_invalido(self):
        assert _uf_de_jurisdicao(None) is None
        assert _uf_de_jurisdicao("BR") is None


# ── ConfigMixin.load_jurisdicao_com_fallback ──────────────────────────────────


class TestLoadJurisdicaoComFallback:
    def _setup_config(self, tmp_path: Path) -> Path:
        root = tmp_path / "config"
        jur = root / "jurisdicoes"
        jur.mkdir(parents=True)
        (jur / "BR.json").write_text(
            json.dumps(
                {
                    "codigo": "BR",
                    "nome": "Brasil",
                    "motor_tributario_bdi": {"aliquotas": {"ISS": 0.05, "PIS": 0.0065, "COFINS": 0.03, "CPRB": 0.0}},
                }
            ),
            encoding="utf-8",
        )
        (jur / "BR-CE.json").write_text(
            json.dumps(
                {
                    "codigo": "BR-CE",
                    "nome": "Brasil - Ceará",
                    "parent_id": "BR",
                    "motor_tributario_bdi": {"aliquotas": {"ISS": 0.02}},
                }
            ),
            encoding="utf-8",
        )
        return root

    def test_municipio_com_config_propria_resolve_sem_alerta(self, tmp_path: Path):
        root = self._setup_config(tmp_path)
        (root / "jurisdicoes" / "BR-CE-FORTALEZA.json").write_text(
            json.dumps(
                {
                    "codigo": "BR-CE-FORTALEZA",
                    "nome": "Brasil - Ceará - Fortaleza",
                    "parent_id": "BR-CE",
                    "motor_tributario_bdi": {"aliquotas": {"ISS": 0.03}},
                }
            ),
            encoding="utf-8",
        )
        mixin = ConfigMixin(config_root=root)

        data, alertas = mixin.load_jurisdicao_com_fallback("BR-CE-FORTALEZA")

        assert alertas == []
        # merge em cadeia: BR (PIS/COFINS) <- BR-CE (ISS=0.02, sobrescrito) <- BR-CE-FORTALEZA (ISS=0.03)
        aliquotas = data["motor_tributario_bdi"]["aliquotas"]
        assert aliquotas["ISS"] == 0.03
        assert aliquotas["PIS"] == 0.0065

    def test_municipio_sem_config_cai_para_uf_com_alerta(self, tmp_path: Path):
        root = self._setup_config(tmp_path)
        mixin = ConfigMixin(config_root=root)

        data, alertas = mixin.load_jurisdicao_com_fallback("BR-CE-SOBRAL")

        assert len(alertas) == 1
        assert "VAL-JURISDICAO-MUNICIPIO-01" in alertas[0]
        assert "BR-CE-SOBRAL" in alertas[0]
        assert "BR-CE" in alertas[0]
        # resolveu no nível de UF (ISS=0.02, de BR-CE.json)
        assert data["motor_tributario_bdi"]["aliquotas"]["ISS"] == 0.02

    def test_uf_sem_municipio_identico_a_load_jurisdicao(self, tmp_path: Path):
        """Regressão: 2 segmentos não passa pelo fallback, comportamento idêntico."""
        root = self._setup_config(tmp_path)
        mixin = ConfigMixin(config_root=root)

        data_fallback, alertas = mixin.load_jurisdicao_com_fallback("BR-CE")
        data_direto = mixin.load_jurisdicao("BR-CE")

        assert alertas == []
        assert data_fallback == data_direto

    def test_uf_inexistente_sem_3_segmentos_relanca_erro(self, tmp_path: Path):
        """Sem 3º segmento não há para onde degradar — erro original deve
        continuar se propagando (não é a mesma situação de município ausente)."""
        root = self._setup_config(tmp_path)
        mixin = ConfigMixin(config_root=root)

        with pytest.raises(RuntimeDomainError):
            mixin.load_jurisdicao_com_fallback("BR-XX")
