"""Tests for tiny-gap files: validador_cobertura_item, scope_guard, inputs mixin,
conversor_unidades, report_calibration_sections, domain/models/__init__,
analitica, cube __init__, artifact_transport, 04-cronograma/_skill_helpers/_dag."""

from __future__ import annotations

from unittest.mock import MagicMock

# ─── application/runtime/mixins/inputs.py (5 missing: 30, 38, 54, 71-72) ─────


class TestInputsMixin:
    def _make_mixin(self):
        from concilium.application.runtime.mixins.inputs import InputsMixin

        obj = InputsMixin.__new__(InputsMixin)
        return obj

    def _make_project(self, meta=None):
        proj = MagicMock()
        proj.meta = meta or {"nome": "Test", "tipo_obra": "terraplenagem"}
        proj.read_json.return_value = {}
        proj.id = "proj-1"
        return proj

    def _make_contexto(self):
        ctx = MagicMock()
        ctx.id = "ctx-1"
        ctx.jurisdicao_id = "jur-1"
        return ctx

    def test_apply_runtime_defaults_escopo_with_coordenadas(self):
        mixin = self._make_mixin()
        mixin.create_snapshots = MagicMock(return_value={"catalogo": "cat-v1", "perfil": "perf-v1"})
        proj = self._make_project({"nome": "P", "coordenadas": {"lat": 10, "lng": 20}})
        ctx = self._make_contexto()
        inputs = {}
        result = mixin._apply_runtime_defaults("01-escopo-e-eap", proj, ctx, inputs)
        assert result["coordenadas"] == {"lat": 10, "lng": 20}

    def test_apply_runtime_defaults_escopo_without_coordenadas(self):
        mixin = self._make_mixin()
        mixin.create_snapshots = MagicMock(return_value={"catalogo": "cat", "perfil": "perf"})
        proj = self._make_project({"nome": "P", "coordenadas_lat": 5.0, "coordenadas_lng": 10.0})
        ctx = self._make_contexto()
        result = mixin._apply_runtime_defaults("01-escopo-e-eap", proj, ctx, {})
        assert result["coordenadas"]["lat"] == 5.0

    def test_apply_runtime_defaults_escopo_adds_regime(self):
        mixin = self._make_mixin()
        mixin.create_snapshots = MagicMock(return_value={"catalogo": "cat", "perfil": "perf"})
        proj = self._make_project({"nome": "P", "dias_semana": 5, "horas_dia": 9})
        ctx = self._make_contexto()
        result = mixin._apply_runtime_defaults("01-escopo-e-eap", proj, ctx, {})
        assert result["regime_trabalho"]["dias_semana"] == 5

    def test_apply_runtime_defaults_skill05_encargos(self):
        mixin = self._make_mixin()
        mixin.load_jurisdicao = MagicMock(
            return_value={"motor_encargos_sociais": {"percentual_horista": 1.777, "percentual_mensalista": 1.06}}
        )
        proj = self._make_project()
        ctx = self._make_contexto()
        result = mixin._apply_runtime_defaults("05-equipes-e-alocacao", proj, ctx, {})
        assert result["percentual_encargos"] == 1.777
        assert result["percentual_encargos_mensalista"] == 1.06

    def test_apply_runtime_defaults_skill05_encargos_all_none_skips_fields(self):
        """Branches 59->61, 61->63: horista e mensalista None → nenhum campo setado."""
        mixin = self._make_mixin()
        mixin.load_jurisdicao = MagicMock(return_value={"motor_encargos_sociais": {}})
        proj = self._make_project()
        ctx = self._make_contexto()
        result = mixin._apply_runtime_defaults("05-equipes-e-alocacao", proj, ctx, {})
        assert "percentual_encargos" not in result
        assert "percentual_encargos_mensalista" not in result
        assert "percentual_encargos_pj" not in result

    def test_apply_runtime_defaults_skill05_encargos_pj_present(self):
        """Linha 64: percentual_pj presente → percentual_encargos_pj setado."""
        mixin = self._make_mixin()
        mixin.load_jurisdicao = MagicMock(
            return_value={
                "motor_encargos_sociais": {
                    "percentual_horista": 1.5,
                    "percentual_pj": 1.11,
                }
            }
        )
        proj = self._make_project()
        ctx = self._make_contexto()
        result = mixin._apply_runtime_defaults("05-equipes-e-alocacao", proj, ctx, {})
        assert result["percentual_encargos_pj"] == 1.11

    def test_apply_runtime_defaults_skill06_aliquotas_bdi_jurisdicao(self):
        """ADR-038: jurisdição resolvida deve alimentar aliquotas_bdi_jurisdicao."""
        mixin = self._make_mixin()
        mixin.load_jurisdicao_com_fallback = MagicMock(
            return_value=({"motor_tributario_bdi": {"aliquotas": {"ISS": 0.02, "PIS": 0.0065, "COFINS": 0.03}}}, [])
        )
        proj = self._make_project()
        ctx = self._make_contexto()
        result = mixin._apply_runtime_defaults("06-resultado-financeiro", proj, ctx, {})
        assert result["aliquotas_bdi_jurisdicao"] == {"ISS": 0.02, "PIS": 0.0065, "COFINS": 0.03}

    def test_apply_runtime_defaults_skill06_prioriza_jurisdicao_do_escopo(self):
        """Escopo.jurisdicao_id (já presente em `normalized` via escopo_meta) tem
        prioridade sobre o default de Contexto."""
        mixin = self._make_mixin()
        mixin.load_jurisdicao_com_fallback = MagicMock(
            return_value=({"motor_tributario_bdi": {"aliquotas": {"ISS": 0.05}}}, [])
        )
        proj = self._make_project()
        ctx = self._make_contexto()
        mixin._apply_runtime_defaults("06-resultado-financeiro", proj, ctx, {"jurisdicao_id": "BR-SP"})
        mixin.load_jurisdicao_com_fallback.assert_called_once_with("BR-SP")

    def test_apply_runtime_defaults_skill06_sem_motor_tributario_nao_seta_campo(self):
        """Jurisdição sem motor_tributario_bdi (ex.: config antiga) não injeta o campo
        — regressão zero, cai para DEFAULT_BDI_TABELA como hoje."""
        mixin = self._make_mixin()
        mixin.load_jurisdicao_com_fallback = MagicMock(return_value=({}, []))
        proj = self._make_project()
        ctx = self._make_contexto()
        result = mixin._apply_runtime_defaults("06-resultado-financeiro", proj, ctx, {})
        assert "aliquotas_bdi_jurisdicao" not in result

    def test_apply_runtime_defaults_skill06_propaga_alerta_de_fallback_municipio(self):
        """ADR-142: alertas do fallback município->UF são propagados para
        normalized['avisos_runtime']."""
        mixin = self._make_mixin()
        mixin.load_jurisdicao_com_fallback = MagicMock(
            return_value=(
                {"motor_tributario_bdi": {"aliquotas": {"ISS": 0.02}}},
                ["VAL-JURISDICAO-MUNICIPIO-01: 'BR-CE-SOBRAL' sem config própria, usando 'BR-CE' (nível UF)"],
            )
        )
        proj = self._make_project()
        ctx = self._make_contexto()
        result = mixin._apply_runtime_defaults(
            "06-resultado-financeiro", proj, ctx, {"jurisdicao_id": "BR-CE-SOBRAL"}
        )
        assert result["avisos_runtime"] == [
            "VAL-JURISDICAO-MUNICIPIO-01: 'BR-CE-SOBRAL' sem config própria, usando 'BR-CE' (nível UF)"
        ]

    def test_apply_runtime_defaults_skill06_nao_sobrescreve_valor_ja_presente(self):
        mixin = self._make_mixin()
        mixin.load_jurisdicao_com_fallback = MagicMock(side_effect=AssertionError("não deveria ser chamado"))
        proj = self._make_project()
        ctx = self._make_contexto()
        result = mixin._apply_runtime_defaults(
            "06-resultado-financeiro", proj, ctx, {"aliquotas_bdi_jurisdicao": {"ISS": 0.99}}
        )
        assert result["aliquotas_bdi_jurisdicao"] == {"ISS": 0.99}

    def test_apply_runtime_defaults_skill04_calendario(self):
        mixin = self._make_mixin()
        mixin.load_calendario_operacional = MagicMock(return_value={"eventos": []})
        proj = self._make_project()
        ctx = self._make_contexto()
        result = mixin._apply_runtime_defaults("04-cronograma", proj, ctx, {})
        assert "calendario_operacional" in result

    def test_apply_runtime_defaults_skill09_gerar_excel(self):
        mixin = self._make_mixin()
        proj = self._make_project()
        ctx = self._make_contexto()
        result = mixin._apply_runtime_defaults("09-relatorio-e-artefatos", proj, ctx, {})
        assert "gerar_excel" in result

    def test_build_skill_kwargs(self):
        from concilium.application.runtime.mixins.inputs import InputsMixin

        mixin = InputsMixin.__new__(InputsMixin)
        contract = MagicMock()
        contract.signature = ["canonical_in", "inputs", "catalogo"]
        result = mixin._build_skill_kwargs(
            contract,
            canonical_in={"data": "c"},
            inputs={"key": "val"},
            catalogo={"cpus": []},
            perfil={},
            contexto=MagicMock(),
            project=MagicMock(),
            version="v1",
        )
        assert "canonical_in" in result
        assert "inputs" in result
        assert "catalogo" in result



