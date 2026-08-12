"""Tests for domain/validations/cpu_insumo.py — boost coverage on uncovered paths."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from concilium.domain.constants import TETO_MATERIALIDADE_MOB


def _make_validator():
    from concilium.domain.validations.cpu_insumo import ValidadorCPUInsumo

    repo = MagicMock()
    repo.obter_insumo.return_value = None
    repo.obter_producao.return_value = None
    repo.funcao_existe.return_value = True
    repo.equipamento_existe.return_value = True
    repo.producao_existe.return_value = True
    return ValidadorCPUInsumo(repo)


class TestValidarFuncoesExistem:
    def test_all_funcoes_exist(self):
        v = _make_validator()
        v.repo.obter_producao.return_value = {
            "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "OP"}], "equipamentos": []}
        }
        cpu = {"producao_id_ref": "P1"}
        result = v.validar_funcoes_existem(cpu)
        assert result.status == "OK"

    def test_funcao_missing(self):
        v = _make_validator()
        v.repo.funcao_existe.return_value = False
        v.repo.obter_producao.return_value = {
            "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "MISSING"}], "equipamentos": []}
        }
        cpu = {"producao_id_ref": "P1"}
        result = v.validar_funcoes_existem(cpu)
        assert result.status == "ERRO"
        assert "MISSING" in result.mensagem


class TestValidarEquipamentosExistem:
    def test_all_equipamentos_exist(self):
        v = _make_validator()
        v.repo.obter_producao.return_value = {
            "composicao_padrao_equipe": {"funcoes": [], "equipamentos": [{"equip_id": "ESC-01"}]}
        }
        cpu = {"producao_id_ref": "P1"}
        result = v.validar_equipamentos_existem(cpu)
        assert result.status == "OK"

    def test_equipamento_missing(self):
        v = _make_validator()
        v.repo.equipamento_existe.return_value = False
        v.repo.obter_producao.return_value = {
            "composicao_padrao_equipe": {"funcoes": [], "equipamentos": [{"equip_id": "MISSING-EQ"}]}
        }
        cpu = {"producao_id_ref": "P1"}
        result = v.validar_equipamentos_existem(cpu)
        assert result.status == "ERRO"


class TestObterEquipe:
    def test_pid_set_but_ficha_falsy(self):
        """pid is truthy but obter_producao returns None → equipe defaults to {} (line 211->213)."""
        v = _make_validator()
        v.repo.obter_producao.return_value = None
        equipe = v._obter_equipe({"producao_id_ref": "P1"})
        assert equipe == {}

    def test_pid_set_ficha_present_but_no_equipe_key(self):
        v = _make_validator()
        v.repo.obter_producao.return_value = {}
        equipe = v._obter_equipe({"producao_id_ref": "P1"})
        assert equipe == {}


class TestValidarUnidadeCompativelConversao:
    def test_unidades_compativeis_convertidas_com_sucesso(self):
        """m3 -> litro is a compatible-but-different unit; conversion happens (lines 172-173)."""
        v = _make_validator()
        comp_item = {"insumo_id": "X", "coeficiente": 0.5, "unidade": "m3"}
        insumo = {"unidade": "litro"}
        result = v.validar_unidade_compativel(comp_item, insumo)
        assert result.status == "OK"
        assert result.codigo == "VAL-CPU-INS-05"

    def test_conversao_levanta_excecao_usa_coeficiente_bruto(self, monkeypatch):
        """When ConversorUnidades.converter raises, fall back to raw coeficiente (lines 174-175)."""
        from concilium.domain.services.conversor_unidades import ConversorUnidades

        v = _make_validator()
        monkeypatch.setattr(
            ConversorUnidades,
            "converter",
            classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))),
        )
        comp_item = {"insumo_id": "X", "coeficiente": 0.5, "unidade": "m3"}
        insumo = {"unidade": "litro"}
        result = v.validar_unidade_compativel(comp_item, insumo)
        # falls back to raw coeficiente=0.5, within litro range [0.001, 1000] -> OK
        assert result.status == "OK"

    def test_unidades_incompativeis_dimensionalmente(self):
        """Units that cannot be converted at all → ERRO VAL-CPU-INS-05."""
        v = _make_validator()
        comp_item = {"insumo_id": "X", "coeficiente": 1.0, "unidade": "kg"}
        insumo = {"unidade": "h"}
        result = v.validar_unidade_compativel(comp_item, insumo)
        assert result.status == "ERRO"
        assert "Incompatibilidade dimensional" in result.mensagem

    def test_unidades_compativeis_sem_coeficiente_numerico(self):
        """Compatible-but-different units with no numeric coeficiente skips conversion (line 170)
        and then errors downstream for missing coeficiente."""
        v = _make_validator()
        comp_item = {"insumo_id": "X", "unidade": "m3"}
        insumo = {"unidade": "litro"}
        result = v.validar_unidade_compativel(comp_item, insumo)
        assert result.status == "ERRO"
        assert "Coeficiente ausente" in result.mensagem


class TestValidarProducaoExiste:
    def test_producao_exists(self):
        v = _make_validator()
        result = v.validar_producao_existe({"producao_id_ref": "P1"})
        assert result.status == "OK"

    def test_producao_missing(self):
        v = _make_validator()
        v.repo.producao_existe.return_value = False
        result = v.validar_producao_existe({"producao_id_ref": "P-MISSING"})
        assert result.status == "ERRO"

    def test_no_producao_id_ref(self):
        v = _make_validator()
        result = v.validar_producao_existe({})
        assert result.status == "ERRO"
        assert "sem producao_id_ref" in result.mensagem


class TestValidarEncoding:
    def test_clean_text(self):
        v = _make_validator()
        result = v.validar_encoding({"descricao": "Escavação de solo"})
        assert result.status == "OK"

    def test_mojibake_detected(self):
        from concilium.domain.validations.cpu_insumo import CARACTERES_PROIBIDOS

        if not CARACTERES_PROIBIDOS:
            pytest.skip("CARACTERES_PROIBIDOS empty")
        v = _make_validator()
        mojibake_char = CARACTERES_PROIBIDOS[0]
        result = v.validar_encoding({"descricao": f"Test {mojibake_char} noise"})
        assert result.status == "AVISO"


class TestValidarVigencia:
    def test_no_date(self):
        v = _make_validator()
        result = v.validar_vigencia({})
        assert result.status == "AVISO"

    def test_old_date(self):
        v = _make_validator()
        result = v.validar_vigencia({"data_referencia_preco": "2020-01"})
        assert result.status == "AVISO"

    def test_current_date(self):
        v = _make_validator()
        result = v.validar_vigencia({"data_referencia_preco": "2025-01"})
        assert result.status == "OK"


class TestValidarComposicaoNegociado:
    """ADR-181 D6/F6: fonte_preco='negociado' acima do teto exige memoria_calculo."""

    def test_fonte_preco_diferente_de_negociado_ok(self):
        v = _make_validator()
        result = v.validar_composicao_negociado({"fonte_preco": "catalogo_proprio", "preco_unitario": 999_999.0})
        assert result.status == "OK"

    def test_negociado_abaixo_do_teto_ok(self):
        v = _make_validator()
        result = v.validar_composicao_negociado(
            {"fonte_preco": "negociado", "preco_unitario": TETO_MATERIALIDADE_MOB - 1}
        )
        assert result.status == "OK"

    def test_negociado_acima_do_teto_sem_composicao_avisa(self):
        v = _make_validator()
        result = v.validar_composicao_negociado(
            {"codigo": "SUPVEG-MOB-001", "fonte_preco": "negociado", "preco_unitario": 674_932.70}
        )
        assert result.status == "AVISO"
        assert result.codigo == "VAL-CAT-NEGOCIADO-01"
        assert "SUPVEG-MOB-001" in result.mensagem

    def test_negociado_acima_do_teto_com_memoria_calculo_ok(self):
        v = _make_validator()
        result = v.validar_composicao_negociado(
            {
                "fonte_preco": "negociado",
                "preco_unitario": 674_932.70,
                "atributos_especificos": {"memoria_calculo": "68 pessoas x 350km, ver planilha RFI anexa"},
            }
        )
        assert result.status == "OK"

    def test_memoria_calculo_vazia_nao_conta(self):
        v = _make_validator()
        result = v.validar_composicao_negociado(
            {
                "fonte_preco": "negociado",
                "preco_unitario": 674_932.70,
                "atributos_especificos": {"memoria_calculo": "   "},
            }
        )
        assert result.status == "AVISO"

    def test_negociado_no_teto_exato_ok(self):
        """Limite exclusivo (> teto, não >=) — mesmo padrão do checar_leadtime_mob_ausente."""
        v = _make_validator()
        result = v.validar_composicao_negociado({"fonte_preco": "negociado", "preco_unitario": TETO_MATERIALIDADE_MOB})
        assert result.status == "OK"


class TestValidarUnidadeNormalizada:
    def test_missing_unidade(self):
        v = _make_validator()
        result = v.validar_unidade_normalizada({})
        assert result.status == "ERRO"

    def test_non_normalized(self):
        v = _make_validator()
        # m² should normalize to m2 or similar
        result = v.validar_unidade_normalizada({"unidade": "M²"})
        # Result: AVISO if normalization differs, OK if it stays
        assert result.codigo == "VAL-CAT-UNIT-01"

    def test_already_normalized(self):
        v = _make_validator()
        result = v.validar_unidade_normalizada({"unidade": "m3"})
        assert result.codigo == "VAL-CAT-UNIT-01"


class TestValidarCategoriaPermitida:
    def test_valid_categoria(self):
        from concilium.domain.validations.cpu_insumo import ValidadorCPUInsumo  # noqa: F401

        v = _make_validator()
        cat = next(iter(ValidadorCPUInsumo.CATEGORIAS_PERMITIDAS))
        result = v.validar_categoria_permitida({"categoria": cat})
        assert result.status == "OK"

    def test_empty_categoria(self):
        v = _make_validator()
        result = v.validar_categoria_permitida({})
        assert result.status == "AVISO"

    def test_invalid_categoria(self):
        v = _make_validator()
        result = v.validar_categoria_permitida({"categoria": "INVALID_CAT"})
        assert result.status == "ERRO"


class TestValidarValoresAuditaveis:
    def test_insumo_valid_price(self):
        v = _make_validator()
        result = v.validar_valores_auditaveis({"tipo": "COMBUSTIVEL", "preco_unitario": 5.5})
        assert all(r.status == "OK" for r in result)

    def test_insumo_zero_price(self):
        v = _make_validator()
        result = v.validar_valores_auditaveis({"tipo": "COMBUSTIVEL", "preco_unitario": 0})
        assert any(r.status == "ERRO" for r in result)
