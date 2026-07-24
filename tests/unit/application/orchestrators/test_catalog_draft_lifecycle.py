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
    criar_state_machine,
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


class TestCriarStateMachine:
    def test_reconstroi_ate_aprovado(self):
        # Fluxo normal: _revisado presente antes de _aprovado -> sm.revisar() e
        # sm.aprovar() são ambos disparados na reconstrução.
        sm = criar_state_machine(
            {
                "_revisado": True,
                "_revisado_por": "eng-1",
                "_aprovado": True,
                "_aprovado_por": "mgr-1",
            }
        )
        assert sm.current_state.value == ESTADO_APROVADO

    def test_reconstroi_ate_rejeitado_com_rejeitado_por(self):
        # Fluxo normal: _revisado presente antes de _rejeitado, com _rejeitado_por
        # gravado -> cobre o branch verdadeiro de `if rejeitado_por:` em on_rejeitar.
        sm = criar_state_machine(
            {
                "_revisado": True,
                "_revisado_por": "eng-1",
                "_rejeitado": True,
                "_motivo_rejeicao": "preço incoerente",
                "_rejeitado_por": "mgr-1",
            }
        )
        assert sm.current_state.value == ESTADO_REJEITADO
        assert sm.rascunho_data["_rejeitado_por"] == "mgr-1"

    def test_reconstroi_ate_revisado_sem_aprovar_nem_rejeitar(self):
        # Estado puramente REVISADO (nem aprovado, nem rejeitado): tanto o `if`
        # quanto o `elif` finais são falsos e a função cai direto em `return sm`
        # (branch 121->126).
        sm = criar_state_machine({"_revisado": True, "_revisado_por": "eng-1"})
        assert sm.current_state.value == ESTADO_REVISADO

    def test_reconstroi_rejeitado_legado_sem_revisado_nem_rejeitado_por(self):
        # Rascunho legado: rejeitado diretamente sem ter passado por _revisado e
        # sem _rejeitado_por gravado. `rejeitar` permite rascunho.to(rejeitado)
        # diretamente, e `rejeitado_por=None` cobre o branch de saída (skip) de
        # `if rejeitado_por:` em on_rejeitar.
        sm = criar_state_machine({"_rejeitado": True})
        assert sm.current_state.value == ESTADO_REJEITADO
        assert "_rejeitado_por" not in sm.rascunho_data

    def test_reconstroi_aprovado_legado_sem_revisado_levanta(self):
        # Rascunho legado inconsistente: marcado _aprovado sem nunca ter passado
        # por _revisado. A reconstrução pula sm.revisar() (branch 117->119) e
        # tenta sm.aprovar() a partir do estado inicial "rascunho", que não é uma
        # transição permitida (aprovar exige vir de "revisado").
        from statemachine.exceptions import TransitionNotAllowed

        with pytest.raises(TransitionNotAllowed):
            criar_state_machine({"_aprovado": True, "_aprovado_por": "mgr-1"})


class TestBuildAndPersistSnapshot:
    def _catalogo(self, preco=10.0):
        return {
            "cpus": [{"codigo": "CPU-1"}],
            "insumos": [{"codigo": "INS-1", "tipo": "MATERIAL", "preco_unitario": preco}],
            "producoes": [],
        }

    def test_primeiro_snapshot_sem_latest_meta(self, tmp_path):
        from concilium.application.orchestrators.catalog_draft_lifecycle import build_and_persist_snapshot

        snapshot_id, diff_summary = build_and_persist_snapshot(
            tmp_path,
            "ctx1",
            self._catalogo(),
            actor="eng-1",
            contexto_id="ctx1",
            rascunho_id="rasc-1",
            justificativa="primeira versão",
        )
        assert snapshot_id
        assert diff_summary == "Primeiro snapshot registrado para este catálogo."
        latest_meta_file = tmp_path / "catalogos" / "ctx1" / "snapshots" / "latest_meta.json"
        assert latest_meta_file.exists()

    def test_segundo_snapshot_com_prev_snapshot_ausente(self, tmp_path):
        # latest_meta.json existe e é válido, mas o arquivo do snapshot que ele
        # referencia não existe em disco -> branch falso de
        # `if prev_snapshot_file.exists()` (223->246), sem levantar exceção.
        import json

        from concilium.application.orchestrators.catalog_draft_lifecycle import build_and_persist_snapshot

        snapshots_dir = tmp_path / "catalogos" / "ctx1" / "snapshots"
        snapshots_dir.mkdir(parents=True)
        (snapshots_dir / "latest_meta.json").write_text(
            json.dumps({"snapshot_id": "snapshot-inexistente"}), encoding="utf-8"
        )

        snapshot_id, diff_summary = build_and_persist_snapshot(
            tmp_path,
            "ctx1",
            self._catalogo(),
            actor="eng-1",
            contexto_id="ctx1",
            rascunho_id="rasc-1",
            justificativa="segunda versão",
        )
        assert snapshot_id
        # diff_summary não é recalculado (fica no valor default) pois o snapshot
        # anterior não foi encontrado.
        assert diff_summary == "Primeiro snapshot registrado para este catálogo."

    def test_segundo_snapshot_com_prev_snapshot_existente_computa_diff(self, tmp_path):
        # Duas chamadas em sequência: a segunda encontra o snapshot anterior de
        # verdade em disco -> branch verdadeiro de `if prev_snapshot_file.exists()`
        # e cálculo real do diff (linhas 224-229), incluindo a gravação do
        # arquivo de diff. `insumos` não vazio também cobre o corpo do loop de
        # `_group_insumos_by_tipo`.
        from concilium.application.orchestrators.catalog_draft_lifecycle import build_and_persist_snapshot

        build_and_persist_snapshot(
            tmp_path,
            "ctx1",
            self._catalogo(preco=10.0),
            actor="eng-1",
            contexto_id="ctx1",
            rascunho_id="rasc-1",
            justificativa="primeira versão",
        )

        snapshot_id_2, diff_summary_2 = build_and_persist_snapshot(
            tmp_path,
            "ctx1",
            self._catalogo(preco=20.0),
            actor="eng-2",
            contexto_id="ctx1",
            rascunho_id="rasc-2",
            justificativa="segunda versão com preço alterado",
        )

        assert snapshot_id_2
        assert diff_summary_2 != "Primeiro snapshot registrado para este catálogo."
        diffs_dir = tmp_path / "catalogos" / "ctx1" / "snapshots" / "diffs"
        assert diffs_dir.exists()
        assert len(list(diffs_dir.glob("*.json"))) == 1

    def test_latest_meta_corrompido_cai_no_except(self, tmp_path):
        # latest_meta.json existe mas não é JSON válido -> dispara o
        # `except Exception: pass` (linhas 243-244) sem propagar o erro.
        from concilium.application.orchestrators.catalog_draft_lifecycle import build_and_persist_snapshot

        snapshots_dir = tmp_path / "catalogos" / "ctx1" / "snapshots"
        snapshots_dir.mkdir(parents=True)
        (snapshots_dir / "latest_meta.json").write_text("isto não é json{{{", encoding="utf-8")

        snapshot_id, diff_summary = build_and_persist_snapshot(
            tmp_path,
            "ctx1",
            self._catalogo(),
            actor="eng-1",
            contexto_id="ctx1",
            rascunho_id="rasc-1",
            justificativa="terceira versão",
        )
        assert snapshot_id
        assert diff_summary == "Primeiro snapshot registrado para este catálogo."
        # latest_meta.json foi sobrescrito com o novo snapshot válido.
        latest_meta_file = snapshots_dir / "latest_meta.json"
        content = latest_meta_file.read_text(encoding="utf-8")
        assert "snapshot_id" in content


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
