"""Coverage batch A — targets mcp_server/__main__, semantic/__init__,
scheduling/selector, optimizer/loop, skills/__init__, cpu_insumo validations,
02-produtividade-climatica, 09-relatorio-e-artefatos, and scheduling/scheduler edge cases.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    CustoTotal,
    Meta,
    Projeto,
    RegimeTrabalho,
    Resultado,
    Venda,
)


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")

def _make_proj():
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=-3.0, lng=-38.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 7, 31),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )

def _minimal_canonical(**kw):
    return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), **kw)

def _canonical_com_resultado():
    resultado = Resultado(
        venda=Venda(total_sem_bdi=800_000.0, total_com_bdi=1_000_000.0),
        custo=CustoTotal(direto_equipes=500_000.0, total=800_000.0),
        resultado_financeiro=200_000.0,
        margem_pct=0.20,
        status_margem="VERDE",
        validacoes=[],
    )
    return _minimal_canonical(resultado=resultado)


# ══ 02-produtividade-climatica edge cases ════════════════════════════════════════════


class TestPraticabilidadeEdgeCases:
    """Cover lines 45, 56-57, 72, 82-83 in 02-produtividade-climatica/skill.py."""

    def _make_mock_dados(self, dias_semana_data=None, dias_mensal_data=None):
        from concilium.infrastructure.clients.openmeteo import DadosClimaticosMensais

        return DadosClimaticosMensais(
            fonte="test",
            ano_referencia=2024,
            latitude=-3.0,
            longitude=-38.0,
            dias_precipitacao_semanal=dias_semana_data or {},
            dias_precipitacao_mensal=dias_mensal_data or {},
        )

    def _load_praticabilidade_fns(self):
        import importlib.util
        from pathlib import Path

        path = (
            Path(__file__).parents[2]
            / "src"
            / "concilium"
            / "application"
            / "skills"
            / "manifests"
            / "02-produtividade-climatica"
            / "skill.py"
        )
        spec = importlib.util.spec_from_file_location("_skill_02_praticabilidade", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_nonstandard_limiar_mm_semanal_falls_back(self):
        """limiar_mm=15 (not 5/10/20) falls back to 10mm (line 45)."""
        mod = self._load_praticabilidade_fns()
        dados = self._make_mock_dados(dias_semana_data={"2024-W01": {"10mm": 2}})
        result = mod._calcular_percentual_produtivo_semanal(dados, 15.0, 5)
        assert "2024-W01" in result

    def test_nonstandard_limiar_mm_mensal_falls_back(self):
        """limiar_mm=7 (not 5/10/20) falls back to 10mm (line 72)."""
        mod = self._load_praticabilidade_fns()
        dados = self._make_mock_dados(dias_mensal_data={"06": {"10mm": 5}})
        result = mod._calcular_percentual_produtivo_mensal(dados, 7.0, 5)
        assert "06" in result

    def test_dias_semana_zero_semanal_returns_zero(self):
        """dias_semana=0 → dias_uteis=0 → percentual=0.0, continue (lines 56-57)."""
        mod = self._load_praticabilidade_fns()
        dados = self._make_mock_dados(dias_semana_data={"2024-W01": {"10mm": 0}})
        result = mod._calcular_percentual_produtivo_semanal(dados, 10.0, 0)
        assert result.get("2024-W01") == 0.0

    def test_dias_semana_zero_mensal_returns_zero(self):
        """dias_semana=0 → dias_uteis_mes=0 → percentual=0.0, continue (lines 82-83)."""
        mod = self._load_praticabilidade_fns()
        dados = self._make_mock_dados(dias_mensal_data={"06": {"10mm": 0}})
        result = mod._calcular_percentual_produtivo_mensal(dados, 10.0, 0)
        assert result.get("06") == 0.0



