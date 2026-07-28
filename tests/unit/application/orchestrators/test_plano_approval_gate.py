"""Tests for application/orchestrators/plano_approval_gate.py (issue #121)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from concilium.application.orchestrators.plano_approval_gate import (
    PlanoApprovalGateError,
    assert_pode_aprovar_plano,
)


def _plano_store(invocations: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(read_invocations=lambda: invocations)


class TestAssertPodeAprovarPlano:
    def test_sem_invocacoes_aprova(self):
        assert_pode_aprovar_plano(_plano_store([]))

    def test_sem_flags_bloqueantes_aprova(self):
        store = _plano_store(
            [
                {"skill": "06-resultado-financeiro", "validacoes": [{"codigo": "VAL-COB-OK", "status": "OK"}]},
            ]
        )
        assert_pode_aprovar_plano(store)

    def test_erro_bloqueia_sempre_mesmo_com_justificativa(self):
        store = _plano_store(
            [
                {"skill": "04-cronograma", "validacoes": [{"codigo": "ERR-XPTO", "status": "ERRO"}]},
            ]
        )
        with pytest.raises(PlanoApprovalGateError, match="ERRO"):
            assert_pode_aprovar_plano(store, justificativa_override="aceito o risco")

    @pytest.mark.parametrize(
        "codigo",
        [
            "VAL-COB-NEG",
            "VAL-PROD-04",
            "VAL-PROD-VS-PU",
            "VAL-GAP-CATALOGO-OPERACIONAL",
            "VAL-STALE-UPSTREAM",
            "VAL-PROD-PU-FALLBACK-DESYNC",
        ],
    )
    def test_aviso_bloqueante_sem_justificativa_bloqueia(self, codigo):
        store = _plano_store(
            [
                {"skill": "06-resultado-financeiro", "validacoes": [{"codigo": codigo, "status": "AVISO"}]},
            ]
        )
        with pytest.raises(PlanoApprovalGateError, match=codigo):
            assert_pode_aprovar_plano(store)

    def test_aviso_bloqueante_com_justificativa_aprova(self):
        store = _plano_store(
            [
                {"skill": "06-resultado-financeiro", "validacoes": [{"codigo": "VAL-COB-NEG", "status": "AVISO"}]},
            ]
        )
        assert_pode_aprovar_plano(store, justificativa_override="loss-leader deliberado, aprovado pela diretoria")

    def test_justificativa_so_espacos_nao_conta(self):
        store = _plano_store(
            [
                {"skill": "06-resultado-financeiro", "validacoes": [{"codigo": "VAL-COB-NEG", "status": "AVISO"}]},
            ]
        )
        with pytest.raises(PlanoApprovalGateError):
            assert_pode_aprovar_plano(store, justificativa_override="   ")

    def test_aviso_nao_bloqueante_nao_bloqueia(self):
        store = _plano_store(
            [
                {
                    "skill": "06-resultado-financeiro",
                    "validacoes": [{"codigo": "VAL-PLAN-OVR-ITEM", "status": "INFO"}],
                },
            ]
        )
        assert_pode_aprovar_plano(store)

    def test_usa_so_ultima_entrada_por_skill(self):
        """Skill rodou duas vezes: a primeira tinha VAL-COB-NEG, a segunda (mais
        recente) já não tem mais — não deve bloquear."""
        store = _plano_store(
            [
                {"skill": "06-resultado-financeiro", "validacoes": [{"codigo": "VAL-COB-NEG", "status": "AVISO"}]},
                {"skill": "06-resultado-financeiro", "validacoes": [{"codigo": "VAL-COB-OK", "status": "OK"}]},
            ]
        )
        assert_pode_aprovar_plano(store)
