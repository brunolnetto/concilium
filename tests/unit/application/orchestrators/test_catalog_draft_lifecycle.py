"""Tests for application/orchestrators/catalog_draft_lifecycle.py (ADR-120 D5, ADR-150 D1/D2)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from concilium.application.orchestrators.catalog_draft_lifecycle import (
    ESTADO_APROVADO,
    ESTADO_RASCUNHO,
    ESTADO_REJEITADO,
    ESTADO_REVISADO,
    CatalogDraftGovernanceError,
    abrir_ou_obter_rascunho_projeto,
    assert_pode_aprovar,
    assert_pode_promover_projeto,
    assert_pode_rejeitar,
    estado_rascunho,
    marcar_rascunho_projeto_aprovado,
    marcar_revisado,
    rascunho_projeto_file_path,
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


# ---------------------------------------------------------------------------
# ADR-150: rascunho de override de projeto
# ---------------------------------------------------------------------------


class TestAbrirOuObterRascunhoProjeto:
    def test_cria_estado_na_primeira_edicao(self, tmp_path: Path) -> None:
        data = abrir_ou_obter_rascunho_projeto(tmp_path, "PROJ-001", "eng-1")
        assert data == {"_rascunho": True, "created_by": "eng-1", "projeto_id": "PROJ-001"}
        assert rascunho_projeto_file_path(tmp_path, "PROJ-001").exists()

    def test_nao_sobrescreve_created_by_em_chamadas_seguintes(self, tmp_path: Path) -> None:
        abrir_ou_obter_rascunho_projeto(tmp_path, "PROJ-001", "eng-1")
        data = abrir_ou_obter_rascunho_projeto(tmp_path, "PROJ-001", "eng-2")
        assert data["created_by"] == "eng-1"

    def test_overrides_pre_existentes_sem_estado_viram_rascunho_implicito(self, tmp_path: Path) -> None:
        # Simula override gravado antes da ADR-150 (sem arquivo de estado ainda).
        overrides_dir = tmp_path / "PROJ-001" / "overrides"
        overrides_dir.mkdir(parents=True)
        (overrides_dir / "insumos_override.json").write_text(json.dumps({"INS-001::BASE": {"preco": 1.0}}))

        data = abrir_ou_obter_rascunho_projeto(tmp_path, "PROJ-001", "quem-promove")
        assert estado_rascunho(data) == ESTADO_RASCUNHO


class TestMarcarRascunhoProjetoAprovado:
    def test_marca_aprovado(self, tmp_path: Path) -> None:
        abrir_ou_obter_rascunho_projeto(tmp_path, "PROJ-001", "eng-1")
        marcar_rascunho_projeto_aprovado(tmp_path, "PROJ-001", "mgr-1")
        data = json.loads(rascunho_projeto_file_path(tmp_path, "PROJ-001").read_text(encoding="utf-8"))
        assert estado_rascunho(data) == ESTADO_APROVADO
        assert data["_aprovado_por"] == "mgr-1"

    def test_cria_arquivo_mesmo_sem_estado_previo(self, tmp_path: Path) -> None:
        marcar_rascunho_projeto_aprovado(tmp_path, "PROJ-001", "mgr-1")
        assert rascunho_projeto_file_path(tmp_path, "PROJ-001").exists()


class TestAssertPodePromoverProjeto:
    """Gate dual (ADR-150 D2): ownership (ADR-126) E quatro-olhos (ADR-120), cumulativos."""

    def test_permite_dono_do_projeto_diferente_do_criador(self) -> None:
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}):
            assert_pode_promover_projeto(
                {"created_by": "eng-1"},
                projeto_owner_id="owner-1",
                promotor_id="owner-1",
                promotor_roles=["engineer"],
            )

    def test_permite_admin_mesmo_sem_ser_dono(self) -> None:
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}):
            assert_pode_promover_projeto(
                {"created_by": "eng-1"},
                projeto_owner_id="owner-1",
                promotor_id="admin-1",
                promotor_roles=["admin"],
            )

    def test_bloqueia_quem_nao_e_dono_nem_admin(self) -> None:
        with (
            patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}),
            pytest.raises(PermissionError),
        ):
            assert_pode_promover_projeto(
                {"created_by": "eng-1"},
                projeto_owner_id="owner-1",
                promotor_id="mgr-1",
                promotor_roles=["catalog-manager"],
            )

    def test_bloqueia_mesmo_ator_que_criou_quatro_olhos(self) -> None:
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}):
            with pytest.raises(CatalogDraftGovernanceError, match="quatro olhos"):
                assert_pode_promover_projeto(
                    {"created_by": "owner-1"},
                    projeto_owner_id="owner-1",
                    promotor_id="owner-1",
                    promotor_roles=["engineer"],
                )

    def test_bloqueia_ja_aprovado(self) -> None:
        with pytest.raises(CatalogDraftGovernanceError, match="já foi promovido"):
            assert_pode_promover_projeto(
                {"created_by": "eng-1", "_aprovado": True},
                projeto_owner_id="owner-1",
                promotor_id="owner-1",
                promotor_roles=["admin"],
            )

    def test_bloqueia_rejeitado(self) -> None:
        with pytest.raises(CatalogDraftGovernanceError, match="rejeitado"):
            assert_pode_promover_projeto(
                {"created_by": "eng-1", "_rejeitado": True},
                projeto_owner_id="owner-1",
                promotor_id="owner-1",
                promotor_roles=["admin"],
            )

    def test_nao_exige_estado_revisado(self) -> None:
        """Diferente de assert_pode_aprovar — não há tool de 'revisar' para override de projeto."""
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}):
            assert_pode_promover_projeto(
                {"created_by": "eng-1"},  # estado RASCUNHO cru, sem _revisado
                projeto_owner_id="owner-1",
                promotor_id="owner-1",
                promotor_roles=["engineer"],
            )
