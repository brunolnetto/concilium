"""Tests for application/orchestrators/catalog_draft_lifecycle.py (ADR-120 D5)."""

from __future__ import annotations

import pytest

from concilium.application.orchestrators.catalog_draft_lifecycle import (
    ESTADO_APROVADO,
    ESTADO_RASCUNHO,
    ESTADO_REJEITADO,
    ESTADO_REVISADO,
    CatalogDraftGovernanceError,
    assert_pode_aprovar,
    assert_pode_rejeitar,
    estado_rascunho,
    marcar_revisado,
)


class TestEstadoRascunho:
    def test_sem_flags_e_rascunho(self):
        assert estado_rascunho({}) == ESTADO_RASCUNHO

    def test_revisado(self):
        assert estado_rascunho({"_revisado": True}) == ESTADO_REVISADO

    def test_aprovado(self):
        assert estado_rascunho({"_aprovado": True}) == ESTADO_APROVADO

    def test_rejeitado(self):
        assert estado_rascunho({"_rejeitado": True}) == ESTADO_REJEITADO

    def test_rejeitado_prevalece_sobre_revisado(self):
        assert estado_rascunho({"_revisado": True, "_rejeitado": True}) == ESTADO_REJEITADO

    def test_aprovado_prevalece_sobre_revisado(self):
        assert estado_rascunho({"_revisado": True, "_aprovado": True}) == ESTADO_APROVADO


class TestMarcarRevisado:
    def test_marca_rascunho_cru(self):
        result = marcar_revisado({"created_by": "eng-1"}, revisor="eng-1")
        assert result["_revisado"] is True
        assert result["_revisado_por"] == "eng-1"
        assert result["created_by"] == "eng-1"

    def test_nao_reabre_aprovado(self):
        data = {"_aprovado": True}
        assert marcar_revisado(data, revisor="eng-1") == data

    def test_nao_reabre_rejeitado(self):
        data = {"_rejeitado": True}
        assert marcar_revisado(data, revisor="eng-1") == data


class TestAssertPodeAprovar:
    def test_permite_revisado_com_atores_diferentes(self):
        assert_pode_aprovar({"created_by": "eng-1", "_revisado": True}, aprovador="mgr-1")

    def test_bloqueia_rascunho_nao_revisado(self):
        with pytest.raises(CatalogDraftGovernanceError, match="não foi revisado"):
            assert_pode_aprovar({"created_by": "eng-1"}, aprovador="mgr-1")

    def test_bloqueia_rejeitado(self):
        with pytest.raises(CatalogDraftGovernanceError, match="rejeitado"):
            assert_pode_aprovar({"_revisado": True, "_rejeitado": True, "_motivo_rejeicao": "ruim"}, aprovador="mgr-1")

    def test_bloqueia_ja_aprovado(self):
        with pytest.raises(CatalogDraftGovernanceError, match="já foi aprovado"):
            assert_pode_aprovar({"_revisado": True, "_aprovado": True}, aprovador="mgr-1")

    def test_bloqueia_mesmo_ator(self):
        with pytest.raises(CatalogDraftGovernanceError, match="quatro olhos"):
            assert_pode_aprovar({"created_by": "mgr-1", "_revisado": True}, aprovador="mgr-1")

    def test_permite_sem_created_by_registrado(self):
        # Rascunhos legados sem created_by não devem travar por 4-olhos (nada a comparar).
        assert_pode_aprovar({"_revisado": True}, aprovador="mgr-1")


class TestAssertPodeRejeitar:
    def test_permite_rascunho_cru(self):
        assert_pode_rejeitar({})

    def test_permite_revisado(self):
        assert_pode_rejeitar({"_revisado": True})

    def test_bloqueia_ja_aprovado(self):
        with pytest.raises(CatalogDraftGovernanceError, match="já foi aprovado"):
            assert_pode_rejeitar({"_aprovado": True})

    def test_bloqueia_ja_rejeitado(self):
        with pytest.raises(CatalogDraftGovernanceError, match="já havia sido rejeitado"):
            assert_pode_rejeitar({"_rejeitado": True})
