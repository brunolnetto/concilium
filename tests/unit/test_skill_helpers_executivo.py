"""Tests for _skill_helpers_executivo.py (skill-09 executive report helpers)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

_NOW = datetime.now(UTC).isoformat()


def _make_proj():
    proj = MagicMock()
    proj.id = "proj-1"
    proj.revisao = "v1"
    return proj


from pathlib import Path as _Path  # noqa: E402

_MODULE_PATH = str(
    _Path(__file__).resolve().parents[2]
    / "src/concilium/application/skills/manifests/10-relatorio-e-artefatos/_skill_helpers_executivo.py"
)


def _load_executivo_mod():
    import importlib.util
    from pathlib import Path

    path = Path(_MODULE_PATH)
    spec = importlib.util.spec_from_file_location("_skill_helpers_executivo", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestRreHelpers:
    def _load(self):
        return _load_executivo_mod()

    def test_rre_get_margin_status_with_resultado(self):
        mod = self._load()
        # NEP-041: Resultado.margem_pct é o campo real (margem não existe em Resultado).
        resultado = MagicMock(status_margem="VERMELHO", margem_pct=0.02)
        status, margem = mod._rre_get_margin_status(resultado)
        assert status == "VERMELHO"
        assert margem == 0.02

    def test_rre_get_margin_status_no_resultado(self):
        mod = self._load()
        status, margem = mod._rre_get_margin_status(None)
        assert status == "VERDE"
        assert margem == 0.0

    def test_rre_build_criticidade_none_ccr(self):
        mod = self._load()
        result = mod._rre_build_criticidade(None, _make_proj(), _NOW)
        assert result == (None, None, None)

    def test_rre_build_criticidade_with_ccr(self):
        mod = self._load()
        ccr = MagicMock()
        item = MagicMock()
        item.atividade_id = "A1"
        item.descricao = "Test"
        item.classificacao = "A"
        item.pareto_frontier = True
        item.custo_share = 0.3
        item.duracao_share = 0.2
        item.sensibilidade = 0.5
        item.recurso_status = "LIVRE"
        item.decisoes_vinculadas = []
        ccr.itens = [item]
        relatorio, artifact, validacao = mod._rre_build_criticidade(ccr, _make_proj(), _NOW)
        assert relatorio is not None
        assert artifact is not None
        assert validacao.status == "OK"

    def test_rre_build_sensibilidade_no_rp(self):
        mod = self._load()
        relatorio, artifact, validacao = mod._rre_build_sensibilidade(None, _make_proj(), _NOW, "VERDE", 0.15)
        assert relatorio.status_margem == "VERDE"
        assert validacao.status == "OK"

    def test_rre_build_sensibilidade_with_rp(self):
        mod = self._load()
        rp = MagicMock()
        sugestao = MagicMock()
        sugestao.tipo = "CRONOGRAMA"
        sugestao.checkpoint = "CP1"
        sugestao.delta_margem = 0.05
        sugestao.custo_aplicacao = None
        sugestao.confianca = "ALTA"
        sugestao.atividades_afetadas = []
        rp.sugestoes = [sugestao]
        rp.margem_alvo_min = 0.10
        rp.repair_viavel = True
        rp.margem_projetada = 0.12
        relatorio, artifact, validacao = mod._rre_build_sensibilidade(rp, _make_proj(), _NOW, "VERMELHO", 0.02)
        assert relatorio.status_margem == "VERMELHO"
        assert len(relatorio.passos_repair) == 1  # VERMELHO → passos

    def test_rre_build_intervencao_no_psr(self):
        mod = self._load()
        relatorio, artifact, validacao = mod._rre_build_intervencao(None, _make_proj(), _NOW, "VERDE")
        assert relatorio.status_entrada == "VERDE"
        assert validacao.status == "OK"

    def test_rre_build_intervencao_with_psr(self):
        mod = self._load()
        psr = MagicMock()
        repair_path = MagicMock()
        repair_path.margem_projetada = 0.12
        repair_path.prazo_delta_dias = 30
        repair_path.confianca = "ALTA"
        repair_path.risco = "BAIXO"
        step = MagicMock()
        step.tipo = "CRONOGRAMA"
        repair_path.steps = [step]
        psr.repair_path = repair_path
        psr.oportunidades = []
        psr.status_entrada = "VERMELHO"
        relatorio, artifact, validacao = mod._rre_build_intervencao(psr, _make_proj(), _NOW, "VERMELHO")
        assert len(relatorio.eixos_intervencao) >= 1
        assert validacao.status == "OK"

    def test_rre_build_bridge_no_data(self):
        mod = self._load()
        artifact, validacao = mod._rre_build_bridge(None, _make_proj(), _NOW)
        assert artifact is None
        assert validacao.status == "AVISO"

    def test_rre_build_bridge_non_dict(self):
        mod = self._load()
        artifact, validacao = mod._rre_build_bridge("not a dict", _make_proj(), _NOW)
        assert artifact is None

    def test_rre_build_bridge_with_data(self):
        mod = self._load()
        bridge = {
            "nivel_1_catalogo_base": 1_000_000,
            "nivel_2_catalogo_escalado": 1_050_000,
            "nivel_3_catalogo_normalizado": 1_020_000,
            "nivel_4_operacional": 1_040_000,
            "status_alerta": "AMARELO",
            "delta_real_abs": 20_000,
            "delta_real_percentual": 2.0,
        }
        artifact, validacao = mod._rre_build_bridge(bridge, _make_proj(), _NOW)
        assert artifact is not None
        # AMARELO → AVISO (status_bridge not VERDE or SEM_DADOS)
        assert validacao.status == "AVISO"

    def test_rre_oport_eixo(self):
        mod = self._load()
        oport = MagicMock()
        oport.lever.tipo = "EQUIPES"
        oport.margem_adicional_estimada = 0.03
        oport.confianca = "ALTA"
        oport.risco = "BAIXO"
        eixo = mod._rre_oport_eixo(oport)
        assert "EQUIPES" in eixo.nome
        assert eixo.confianca == "ALTA"
