"""issue #121 (item 6): validação de margem líquida mínima embutida no BDI.

Puramente aditiva — sem inputs.lucro_minimo_pct, nenhum comportamento muda.
"""

from __future__ import annotations

import sys

import pytest


def _load_precificacao():
    from concilium.application.skills import load_skill_stage

    fn = load_skill_stage("06-resultado-financeiro", "_precificacao", "run_precificacao_unitaria")
    return sys.modules[fn.__module__]


class TestValidarBdiMargemMinima:
    def test_sem_lucro_minimo_pct_nao_valida(self):
        mod = _load_precificacao()
        validacoes = []
        mod._resolve_bdi({}, validacoes)
        assert not any(v.codigo == "VAL-BDI-MARGEM-INSUFICIENTE" for v in validacoes)

    def test_lucro_minimo_baixo_nao_dispara(self):
        """DEFAULT_BDI_TABELA tem L=9% em mao_obra/servicos, L=4% em material/diesel,
        L=5% em indireto — pedir 1% não deve disparar em nenhuma categoria."""
        mod = _load_precificacao()
        validacoes = []
        mod._resolve_bdi({"lucro_minimo_pct": 0.01}, validacoes)
        assert not any(v.codigo == "VAL-BDI-MARGEM-INSUFICIENTE" for v in validacoes)

    def test_lucro_minimo_alto_dispara_para_material(self):
        """Material/diesel têm L=4% (só lucro, sem overhead) — pedir 20% deve disparar."""
        mod = _load_precificacao()
        validacoes = []
        mod._resolve_bdi({"lucro_minimo_pct": 0.20}, validacoes)
        aviso = [v for v in validacoes if v.codigo == "VAL-BDI-MARGEM-INSUFICIENTE"]
        assert len(aviso) == 1
        assert aviso[0].status == "AVISO"
        assert "material" in aviso[0].mensagem

    def test_lucro_minimo_pct_nao_numerico_ignorado(self):
        mod = _load_precificacao()
        validacoes = []
        mod._resolve_bdi({"lucro_minimo_pct": "20%"}, validacoes)
        assert not any(v.codigo == "VAL-BDI-MARGEM-INSUFICIENTE" for v in validacoes)

    def test_manual_bdi_override_nao_e_afetado(self):
        """Override manual (bdi_aplicado) não passa por _resolve_bdi_tabela — sem
        ComponentesBdi, não há decomposição para validar; não deve quebrar nem falso-positivar."""
        mod = _load_precificacao()
        validacoes = []
        mod._resolve_bdi(
            {"lucro_minimo_pct": 0.20, "bdi_aplicado": {"material": 0.04, "diesel": 0.04, "mao_obra": 0.30}},
            validacoes,
        )
        assert not any(v.codigo == "VAL-BDI-MARGEM-INSUFICIENTE" for v in validacoes)
