"""Schema do catálogo — formaliza custo_mobilizacao/custo_desmobilizacao e
fracao_dedicacao em composicao_padrao_equipe.

TDD: testes escritos antes da alteração do schema.

Contexto: `concilium catalog validate --contexto mendeslobo` reportou 263 erros
na entidade PRODUCAO, concentrados em 4 arquivos reais
(config/catalogos/mendeslobo/produtividades/PROD-REJEITO-COMP-EQ1..4-001.json).
Deste total, 105 eram `custo_mobilizacao`/`custo_desmobilizacao` em itens de
`funcoes`/`equipamentos` não declarados em common.schema.json
($defs.funcaoEquipe/$defs.equipamentoEquipe, additionalProperties=false) —
dado real, lido em produção por `_accum_mob_costs_list` (skill-05,
ADR-106 F2-bis). Este módulo formaliza esse ponto.

Revisão (achado ao investigar os 154 erros remanescentes de `num_pessoas`/
`num_unidades` fracionário, ex.: 0.3333/0.6667): uma versão anterior deste
módulo classificou esses valores como "problema de qualidade de dado" e
manteve `num_pessoas`/`num_unidades` como `integer, minimum: 1` sem
correção — mas ADR-132 D2 ("Normalização por Frente") documenta que esse
fracionário É o design correto e intencional quando `composicao_padrao_equipe`
representa 1 frente de `n_frentes` simultâneas: `num_pessoas_por_frente =
total_pessoas / n_frentes`. `pu_calculator.py` já tratava (e trata) esses
campos com `float()`, e ADR-162 valida o bottom-up puro reproduzindo os 4
CPUs Serra Verde reais com delta < 0,003%. Overriding essa avaliação anterior:
o usuário decidiu manter `num_pessoas`/`num_unidades` como contagem discreta
inteira (não relaxar o schema) e, em vez disso, introduzir um campo dedicado
`fracao_dedicacao` (0 < x ≤ 1, default 1,0) que captura o rateio por frente
sem sobrecarregar a contagem — `pu_calculator` multiplica
`num_pessoas × fracao_dedicacao` (e o equivalente para equipamento). Os 4
arquivos reais foram migrados (script único, delta de custo verificado = 0
em todos os 4) e os 154 erros foram eliminados por essa via, não por
relaxamento de schema.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_SCHEMA_ROOT = _ROOT / "config" / "schemas" / "catalog"
_PROD_REJEITO_FILES = [
    _ROOT / "config" / "catalogos" / "mendeslobo" / "produtividades" / f"PROD-REJEITO-COMP-EQ{n}-001.json"
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
    """num_pessoas/num_unidades continuam contagens de entidades discretas
    (integer, minimum: 1) — decisão do usuário de não relaxar para fracionário.
    O rateio por frente (ADR-132 D2) é capturado por `fracao_dedicacao`
    (0 < x <= 1), um campo novo e separado, não pela contagem em si."""

    def test_num_pessoas_fracionario_direto_continua_invalido(self):
        """Fracionário direto em num_pessoas continua rejeitado — o rateio por
        frente deve ir em fracao_dedicacao, não sobrecarregar a contagem."""
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

    def test_num_unidades_fracionario_direto_continua_invalido(self):
        """Fracionário direto em num_unidades continua rejeitado — mesmo
        raciocínio de test_num_pessoas_fracionario_direto_continua_invalido."""
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

    def test_fracao_dedicacao_valida_rateio_por_frente(self):
        """num_pessoas/num_unidades inteiros + fracao_dedicacao é a forma correta
        de representar rateio por frente (ADR-132 D2, revisão) — deve validar
        sem erros."""
        _, prod_v, _ = _build_validators()
        item = {
            "id": "PROD-TEST-5B",
            "codigo": "PROD-TEST-5B",
            "descricao": "teste",
            "valor_horario": 1.0,
            "unidade": "m3/h",
            "categoria": "escavacao",
            "origem": "PROPRIA",
            "composicao_padrao_equipe": {
                "funcoes": [{"funcao_id": "F0001", "num_pessoas": 1, "fracao_dedicacao": 0.3333}],
                "equipamentos": [{"equip_id": "E0001", "num_unidades": 1, "fracao_dedicacao": 0.6667}],
            },
        }
        erros = _errors_for_producao(prod_v, item)
        assert erros == [], f"esperava validar sem erros, obtive: {erros}"

    def test_fracao_dedicacao_fora_do_intervalo_invalida(self):
        """fracao_dedicacao > 1 (dedicação maior que o próprio headcount) ou
        <= 0 não faz sentido de domínio e deve continuar inválido."""
        _, prod_v, _ = _build_validators()
        item = {
            "id": "PROD-TEST-5C",
            "codigo": "PROD-TEST-5C",
            "descricao": "teste",
            "valor_horario": 1.0,
            "unidade": "m3/h",
            "categoria": "escavacao",
            "origem": "PROPRIA",
            "composicao_padrao_equipe": {
                "funcoes": [{"funcao_id": "F0001", "num_pessoas": 1, "fracao_dedicacao": 1.5}],
                "equipamentos": [],
            },
        }
        erros = _errors_for_producao(prod_v, item)
        assert erros, "esperava erro de validação para fracao_dedicacao > 1"

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
    validar sem erros nenhum. `custo_mobilizacao`/`custo_desmobilizacao` foram
    resolvidos formalizando o schema; `num_pessoas`/`num_unidades` fracionário
    foi resolvido migrando o dado (inteiro + fracao_dedicacao, script único,
    delta de custo verificado = 0 via pu_calculator) — não relaxando o schema."""

    @pytest.mark.parametrize("path", _PROD_REJEITO_FILES, ids=lambda p: p.name)
    def test_arquivo_real_sem_erros_de_mob_demob(self, path):
        assert path.exists(), f"arquivo de fixture esperado não encontrado: {path}"
        _, prod_v, _ = _build_validators()
        data = json.loads(path.read_text(encoding="utf-8"))
        erros = _errors_for_producao(prod_v, data)
        erros_relevantes = [e for e in erros if "custo_mobilizacao" in e or "custo_desmobilizacao" in e]
        assert erros_relevantes == [], f"{path.name}: erros remanescentes de mob/demob: {erros_relevantes}"

    @pytest.mark.parametrize("path", _PROD_REJEITO_FILES, ids=lambda p: p.name)
    def test_arquivo_real_sem_erros_de_num_fracionario(self, path):
        """Após a migração para inteiro + fracao_dedicacao, os 4 arquivos reais
        não devem mais reportar num_pessoas/num_unidades fracionário."""
        _, prod_v, _ = _build_validators()
        data = json.loads(path.read_text(encoding="utf-8"))
        erros = _errors_for_producao(prod_v, data)
        erros_fracionario = [e for e in erros if "num_pessoas" in e or "num_unidades" in e]
        assert erros_fracionario == [], f"{path.name}: erros remanescentes de num fracionário: {erros_fracionario}"

    @pytest.mark.parametrize("path", _PROD_REJEITO_FILES, ids=lambda p: p.name)
    def test_arquivo_real_sem_erros_nenhum(self, path):
        """Regressão final: nenhum erro de schema remanescente nos 4 arquivos."""
        _, prod_v, _ = _build_validators()
        data = json.loads(path.read_text(encoding="utf-8"))
        erros = _errors_for_producao(prod_v, data)
        assert erros == [], f"{path.name}: erros remanescentes: {erros}"
