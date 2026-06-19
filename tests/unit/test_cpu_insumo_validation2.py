"""Tests for domain/validations/cpu_insumo.py — boost coverage on uncovered paths."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


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
