"""Schema do catálogo — formaliza custo_mobilizacao/custo_desmobilizacao em
composicao_padrao_equipe.

TDD: testes escritos antes da alteração do schema.

Contexto: `concilium catalog validate --contexto mendeslobo` reporta 263 erros
na entidade PRODUCAO, concentrados em 4 arquivos reais
(config/catalogos/mendeslobo/producoes/PROD-REJEITO-COMP-EQ1..4-001.json).
Deste total, 105 são `custo_mobilizacao`/`custo_desmobilizacao` em itens de
`funcoes`/`equipamentos` não declarados em common.schema.json
($defs.funcaoEquipe/$defs.equipamentoEquipe, additionalProperties=false) —
dado real, lido em produção por `_accum_mob_costs_list` (skill-05,
ADR-106 F2-bis). Este módulo formaliza só esse ponto.

Os outros 154 erros nesses mesmos arquivos (`num_pessoas`/`num_unidades`
fracionário, ex.: 0.3333/0.6667) NÃO são corrigidos aqui — headcount/
quantidade de equipamento é uma contagem de entidades discretas por
definição de domínio (não existe um terço de pessoa ou de equipamento);
o valor fracionário nesses arquivos é um problema de qualidade de dado
(alocação parcial modelada incorretamente sobrecarregando a contagem, em
vez de um campo de dedicação/percentual dedicado), não uma lacuna de
schema — `num_pessoas`/`num_unidades` continuam `integer, minimum: 1`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_SCHEMA_ROOT = _ROOT / "config" / "schemas" / "catalog"
_PROD_REJEITO_FILES = [
    _ROOT / "config" / "catalogos" / "mendeslobo" / "producoes" / f"PROD-REJEITO-COMP-EQ{n}-001.json"
    for n in range(1, 5)
]


def _build_validators():
    from concilium.presentation.cli._commands_manage_helpers_d import _build_schema_validators

    return _build_schema_validators(_SCHEMA_ROOT)


def _errors_for_producao(prod_validator, item: dict) -> list[str]:
    return [
        ".".join(str(x) for x in err.absolute_path) + f" -> {err.message}" for err in prod_validator.iter_errors(item)
    ]


class TestCustoMobilizacaoDesmobilizacaoNoSchema:
    def test_funcao_com_custo_mob_demob_valida(self):
        _, prod_v, _ = _build_validators()
        item = {
            "id": "PROD-TEST-1",
            "codigo": "PROD-TEST-1",
            "descricao": "teste",
            "valor_horario": 1.0,
            "unidade": "m3/h",
            "categoria": "escavacao",
            "origem": "PROPRIA",
            "composicao_padrao_equipe": {
                "funcoes": [
                    {"funcao_id": "F0001", "num_pessoas": 1, "custo_mobilizacao": 800.0, "custo_desmobilizacao": 800.0}
                ],
                "equipamentos": [],
            },
        }
        erros = _errors_for_producao(prod_v, item)
        assert erros == [], f"esperava validar sem erros, obtive: {erros}"

    def test_equipamento_com_custo_mob_demob_valida(self):
        _, prod_v, _ = _build_validators()
        item = {
            "id": "PROD-TEST-2",
            "codigo": "PROD-TEST-2",
            "descricao": "teste",
            "valor_horario": 1.0,
            "unidade": "m3/h",
            "categoria": "escavacao",
            "origem": "PROPRIA",
            "composicao_padrao_equipe": {
                "funcoes": [],
                "equipamentos": [
                    {
                        "equip_id": "E0001",
                        "num_unidades": 1,
                        "custo_mobilizacao": 6500.0,
                        "custo_desmobilizacao": 6500.0,
                    }
                ],
            },
        }
        erros = _errors_for_producao(prod_v, item)
        assert erros == [], f"esperava validar sem erros, obtive: {erros}"

    def test_custo_mob_demob_negativo_ainda_invalido(self):
        """custo_mobilizacao/custo_desmobilizacao devem continuar exigindo >= 0."""
        _, prod_v, _ = _build_validators()
        item = {
            "id": "PROD-TEST-3",
            "codigo": "PROD-TEST-3",
            "descricao": "teste",
            "valor_horario": 1.0,
            "unidade": "m3/h",
            "categoria": "escavacao",
            "origem": "PROPRIA",
            "composicao_padrao_equipe": {
                "funcoes": [{"funcao_id": "F0001", "num_pessoas": 1, "custo_mobilizacao": -1.0}],
                "equipamentos": [],
            },
        }
        erros = _errors_for_producao(prod_v, item)
        assert erros, "esperava erro de validação para custo_mobilizacao negativo"

    def test_sem_custo_mob_demob_continua_opcional(self):
        """Campos continuam opcionais — retrocompat com composições sem esses dados."""
        _, prod_v, _ = _build_validators()
        item = {
            "id": "PROD-TEST-4",
            "codigo": "PROD-TEST-4",
            "descricao": "teste",
            "valor_horario": 1.0,
            "unidade": "m3/h",
            "categoria": "escavacao",
            "origem": "PROPRIA",
            "composicao_padrao_equipe": {
                "funcoes": [{"funcao_id": "F0001", "num_pessoas": 1}],
                "equipamentos": [],
            },
        }
        erros = _errors_for_producao(prod_v, item)
        assert erros == []


class TestNumPessoasNumUnidadesPermanecemInteiros:
    """num_pessoas/num_unidades são contagens de entidades discretas — não relaxamos
    para fracionário aqui. Valores fracionários encontrados nos arquivos reais são
    um problema de qualidade de dado (alocação parcial mal modelada), a ser corrigido
    na origem, não uma lacuna de schema."""

    def test_num_pessoas_fracionario_continua_invalido(self):
        _, prod_v, _ = _build_validators()
        item = {
            "id": "PROD-TEST-5",
            "codigo": "PROD-TEST-5",
            "descricao": "teste",
            "valor_horario": 1.0,
            "unidade": "m3/h",
            "categoria": "escavacao",
            "origem": "PROPRIA",
            "composicao_padrao_equipe": {
                "funcoes": [{"funcao_id": "F0001", "num_pessoas": 0.3333}],
                "equipamentos": [],
            },
        }
        erros = _errors_for_producao(prod_v, item)
        assert erros, "esperava erro de validação para num_pessoas fracionário"

    def test_num_unidades_fracionario_continua_invalido(self):
        _, prod_v, _ = _build_validators()
        item = {
            "id": "PROD-TEST-6",
            "codigo": "PROD-TEST-6",
            "descricao": "teste",
            "valor_horario": 1.0,
            "unidade": "m3/h",
            "categoria": "escavacao",
            "origem": "PROPRIA",
            "composicao_padrao_equipe": {
                "funcoes": [],
                "equipamentos": [{"equip_id": "E0001", "num_unidades": 0.6667}],
            },
        }
        erros = _errors_for_producao(prod_v, item)
        assert erros, "esperava erro de validação para num_unidades fracionário"

    def test_num_pessoas_zero_continua_invalido(self):
        _, prod_v, _ = _build_validators()
        item = {
            "id": "PROD-TEST-7",
            "codigo": "PROD-TEST-7",
            "descricao": "teste",
            "valor_horario": 1.0,
            "unidade": "m3/h",
            "categoria": "escavacao",
            "origem": "PROPRIA",
            "composicao_padrao_equipe": {
                "funcoes": [{"funcao_id": "F0001", "num_pessoas": 0}],
                "equipamentos": [],
            },
        }
        erros = _errors_for_producao(prod_v, item)
        assert erros, "esperava erro de validação para num_pessoas=0"

    def test_num_unidades_negativo_continua_invalido(self):
        _, prod_v, _ = _build_validators()
        item = {
            "id": "PROD-TEST-8",
            "codigo": "PROD-TEST-8",
            "descricao": "teste",
            "valor_horario": 1.0,
            "unidade": "m3/h",
            "categoria": "escavacao",
            "origem": "PROPRIA",
            "composicao_padrao_equipe": {
                "funcoes": [],
                "equipamentos": [{"equip_id": "E0001", "num_unidades": -1}],
            },
        }
        erros = _errors_for_producao(prod_v, item)
        assert erros, "esperava erro de validação para num_unidades negativo"

    def test_num_pessoas_inteiro_continua_valido(self):
        """Retrocompat: valores inteiros continuam válidos (caso comum/majoritário)."""
        _, prod_v, _ = _build_validators()
        item = {
            "id": "PROD-TEST-9",
            "codigo": "PROD-TEST-9",
            "descricao": "teste",
            "valor_horario": 1.0,
            "unidade": "m3/h",
            "categoria": "escavacao",
            "origem": "PROPRIA",
            "composicao_padrao_equipe": {
                "funcoes": [{"funcao_id": "F0001", "num_pessoas": 2}],
                "equipamentos": [{"equip_id": "E0001", "num_unidades": 1}],
            },
        }
        erros = _errors_for_producao(prod_v, item)
        assert erros == []


class TestArquivosReaisPassamAValidar:
    """Regressão direta: os 4 arquivos reais que motivaram esta mudança devem
    validar sem erros de custo_mobilizacao/custo_desmobilizacao depois da
    extensão do schema. Não afirma nada sobre num_pessoas/num_unidades
    fracionário (continuam sendo erros reais de qualidade de dado nesses
    arquivos, ver TestNumPessoasNumUnidadesPermanecemInteiros) nem sobre
    consumo_litros_hora/preco_h_unitario/custo_hora_total_referencia (outros
    erros já mapeados, fora de escopo aqui)."""

    @pytest.mark.parametrize("path", _PROD_REJEITO_FILES, ids=lambda p: p.name)
    def test_arquivo_real_sem_erros_de_mob_demob(self, path):
        assert path.exists(), f"arquivo de fixture esperado não encontrado: {path}"
        _, prod_v, _ = _build_validators()
        data = json.loads(path.read_text(encoding="utf-8"))
        erros = _errors_for_producao(prod_v, data)
        erros_relevantes = [e for e in erros if "custo_mobilizacao" in e or "custo_desmobilizacao" in e]
        assert erros_relevantes == [], f"{path.name}: erros remanescentes de mob/demob: {erros_relevantes}"

    @pytest.mark.parametrize("path", _PROD_REJEITO_FILES, ids=lambda p: p.name)
    def test_arquivo_real_ainda_reporta_num_fracionario(self, path):
        """Documenta explicitamente que o problema de dado (fracionário) segue
        sem correção — evita que uma futura mudança de schema reintroduza o
        relaxamento silenciosamente sem essa decisão ser revisitada."""
        _, prod_v, _ = _build_validators()
        data = json.loads(path.read_text(encoding="utf-8"))
        erros = _errors_for_producao(prod_v, data)
        erros_fracionario = [e for e in erros if "num_pessoas" in e or "num_unidades" in e]
        assert erros_fracionario, f"{path.name}: esperava continuar reportando num_pessoas/num_unidades fracionário"
