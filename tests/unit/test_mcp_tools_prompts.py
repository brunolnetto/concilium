"""Tier 1 coverage — scheduling/pool_validator, mcp/tools/schemas, mcp/tools/prompts."""

from __future__ import annotations

from concilium.presentation.mcp.tools import prompts

# ── MCP Prompts ───────────────────────────────────────────────────────────────


class TestMcpPrompts:
    def test_nota_eap_sugerida_nao_vazia(self):
        assert len(prompts.NOTA_EAP_SUGERIDA) > 0

    def test_dica_busca_cpu_nao_vazia(self):
        assert len(prompts.DICA_BUSCA_CPU) > 0

    def test_notas_viabilidade_tem_viavel_e_inviavel(self):
        assert "VIAVEL" in prompts.NOTAS_VIABILIDADE
        assert "INVIAVEL" in prompts.NOTAS_VIABILIDADE

    def test_notas_viabilidade_inviavel_tem_placeholder(self):
        assert "{semanas}" in prompts.NOTAS_VIABILIDADE["INVIAVEL"]

    def test_proximos_passos_replan_e_lista(self):
        assert isinstance(prompts.PROXIMOS_PASSOS_REPLAN, list)
        assert len(prompts.PROXIMOS_PASSOS_REPLAN) >= 1

    def test_err_no_active_version_nao_vazio(self):
        assert len(prompts.ERR_NO_ACTIVE_VERSION) > 0

    def test_err_canonical_not_found_nao_vazio(self):
        assert len(prompts.ERR_CANONICAL_NOT_FOUND) > 0

