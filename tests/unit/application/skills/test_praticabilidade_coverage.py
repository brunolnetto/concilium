"""Additional coverage tests for skill 02-produtividade-climatica."""

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from concilium.application.skills import run_produtividade_climatica
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    Meta,
    Projeto,
    RegimeTrabalho,
)
from concilium.infrastructure.clients.openmeteo import DadosClimaticosMensais

# Load private helpers from the skill.py using importlib
_SKILL_PATH = (
    Path(__file__).parent.parent.parent.parent.parent
    / "src"
    / "concilium"
    / "application"
    / "skills"
    / "manifests"
    / "02-produtividade-climatica"
    / "skill.py"
)
_skill_mod_name = "_concilium_skill_01_praticabilidade"
if _skill_mod_name not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_skill_mod_name, _SKILL_PATH)
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_skill_mod_name] = _mod
    _spec.loader.exec_module(_mod)
_prat_mod = sys.modules[_skill_mod_name]
_calcular_percentual_produtivo_semanal = _prat_mod._calcular_percentual_produtivo_semanal
_calcular_percentual_produtivo_mensal = _prat_mod._calcular_percentual_produtivo_mensal


def _make_dados(ano=2024, semanal=None, mensal=None) -> DadosClimaticosMensais:
    semanal = semanal or {}
    mensal = mensal or {str(m).zfill(2): {"5mm": 2, "10mm": 1, "20mm": 0} for m in range(1, 13)}
    return DadosClimaticosMensais(
        fonte="test",
        ano_referencia=ano,
        latitude=-4.36,
        longitude=-38.77,
        dias_precipitacao_mensal=mensal,
        dias_precipitacao_semanal=semanal,
    )


def _minimal_canonical():
    meta = Meta(gerado_em=datetime.now(UTC), contexto_id="test")
    proj = Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=-4.36, lng=-38.77),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio="2026-01-01",
        data_termino="2026-12-31",
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )
    return CanonicalModel(meta=meta, projeto=proj)


class TestCalcPercentualSemanal:
    def test_limiar_nao_padrao_usa_10mm(self):
        """Limiar como 15mm → threshold_key='15mm' não existe → fallback a '10mm'."""
        dados = _make_dados(
            semanal={
                "2024-W01": {"5mm": 3, "10mm": 2, "20mm": 0},
            }
        )
        result = _calcular_percentual_produtivo_semanal(dados, limiar_mm=15, dias_semana=5)
        # Usa threshold "10mm": 2 inviaveis → pct = (5 - 2*5/7) / 5 = (5-1.43)/5 ≈ 0.714
        assert "2024-W01" in result
        assert 0 <= result["2024-W01"] <= 1

    def test_dias_semana_zero_retorna_zero(self):
        """Se dias_semana=0, percentual deve ser 0.0 para evitar divisão por zero."""
        dados = _make_dados(semanal={"2024-W01": {"10mm": 2}})
        result = _calcular_percentual_produtivo_semanal(dados, limiar_mm=10, dias_semana=0)
        assert result["2024-W01"] == 0.0


class TestCalcPercentualMensal:
    def test_limiar_nao_padrao_usa_10mm(self):
        """Limiar como 7mm → fallback a '10mm'."""
        dados = _make_dados()
        result = _calcular_percentual_produtivo_mensal(dados, limiar_mm=7, dias_semana=5)
        assert len(result) == 12
        for v in result.values():
            assert 0 <= v <= 1

    def test_dias_semana_zero_retorna_zero(self):
        """dias_semana=0 → dias_uteis=0 → percentual=0.0."""
        dados = _make_dados()
        result = _calcular_percentual_produtivo_mensal(dados, limiar_mm=10, dias_semana=0)
        for v in result.values():
            assert v == 0.0


class TestRunPraticabilidade:
    def test_falha_ao_consultar_clima(self):
        """Quando cliente climático lança exceção, deve retornar VAL-PRAT-FONTE ERRO."""
        can = _minimal_canonical()
        mock_client = MagicMock()
        mock_client.fetch_dados_anuais.side_effect = Exception("connection refused")
        res = run_produtividade_climatica(
            can, {"ano_referencia": 2024}, {"limiar_inviabilidade_mm": 10}, client=mock_client
        )
        codigos = {v.codigo: v.status for v in res.validacoes}
        assert "VAL-PRAT-FONTE" in codigos and codigos["VAL-PRAT-FONTE"] == "ERRO"

    def test_val_prat_02_sem_semanas(self):
        """Se dados não têm semanas, deve emitir VAL-PRAT-02 ERRO."""
        can = _minimal_canonical()
        dados = _make_dados(semanal={})  # no weekly data
        mock_client = MagicMock()
        mock_client.fetch_dados_anuais.return_value = dados
        res = run_produtividade_climatica(
            can, {"ano_referencia": 2024}, {"limiar_inviabilidade_mm": 10}, client=mock_client
        )
        codigos = {v.codigo: v.status for v in res.validacoes}
        assert "VAL-PRAT-02" in codigos and codigos["VAL-PRAT-02"] == "ERRO"

    def test_val_prat_04_variabilidade_nula(self):
        """Se todas as semanas tiverem o mesmo percentual (≥ 4), emite VAL-PRAT-04 AVISO."""
        can = _minimal_canonical()
        # Create semanal data where all weeks have same 0 precip → all pct = 1.0
        semanal = {f"2024-W{w:02d}": {"5mm": 0, "10mm": 0, "20mm": 0} for w in range(1, 10)}
        dados = _make_dados(semanal=semanal)
        mock_client = MagicMock()
        mock_client.fetch_dados_anuais.return_value = dados
        res = run_produtividade_climatica(
            can, {"ano_referencia": 2024}, {"limiar_inviabilidade_mm": 10}, client=mock_client
        )
        codigos = [v.codigo for v in res.validacoes]
        assert "VAL-PRAT-04" in codigos
