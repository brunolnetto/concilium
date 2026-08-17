"""Schema do catálogo — formaliza campos reais do catálogo rfi-r02 (planilha
padrão RFI R02), antes ausentes de common/producao/cpu/insumo.schema.json.

TDD: testes escritos antes da alteração do schema (validados contra os schemas
reais + regressão direta sobre os arquivos do catálogo rfi-r02).

Contexto: `concilium catalog validate --contexto mendeslobo-rfi` reportava 354
erros (CPU 0 hoje / PRODUCAO 181 / INSUMO 173). Cada campo abaixo foi
confirmado como dado real usado em produção (ou, quando não usado, uma
descrição/metadado da planilha de origem sem risco de afetar cálculo — ver
PR desta mudança para o levantamento completo campo a campo):

  - equipamentoEquipe.consumo_litros_hora (sem sufixo _estimado): lido
    diretamente por `pu_calculator._consumo_diesel_equipamento` como fonte
    primária de consumo de diesel por equipamento na composição.
  - equipamentoEquipe.preco_h_unitario: lido por
    `pu_calculator._preco_h_equipamento` (ADR-132) para sobrepor o preço do
    insumo por-atividade.
  - producao.origem.tipo: enum estendido com "planilha_rfi_r02" e
    "calibrado_agis_rfi" (proveniências reais deste catálogo);
    origem.fonte_id deixou de ser obrigatório (ausente nas entradas
    calibrado_agis_rfi, sem consumidor de código).
  - producao root: patternProperties "^_" (mesma convenção já usada em
    cpu.schema.json) formaliza campos de auditoria como "_nota_calibracao".
  - cpu.cpus_alternativos/grupo_servico: cpus_alternativos é lido por
    `application/services/campaign/campaign_service._cpu_alternativo`;
    grupo_servico é metadado de agrupamento para relatórios.
  - insumo.atributos_especificos (MAO_OBRA): salario_base_hora,
    custo_hora_com_encargos_planilha, codigo_planilha — metadados de
    auditoria da planilha de origem, sem consumidor de código.
  - insumo.atributos_especificos (EQUIPAMENTO): custo_mensal,
    custo_produtivo_h, tipo_locacao — idem.
  - insumo.atributos_especificos (MATERIAL): especificacao, uso,
    codigo_planilha — idem.

Removidos dos dados (não formalizados no schema, por decisão de produto —
eram snapshots de auditoria de custo sem consumidor de código):
`custos_equipe_planilha`, `custos_equipe_rfi`. Duas entradas duplicadas de
`funcao_id` em `composicao_padrao_equipe.funcoes` (ATI-060/ATI-019) também
foram deduplicadas (removida a cópia exata, sem somar quantidade — validado
numericamente contra `custos_equipe_planilha.custo_mo_h` antes da remoção).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_SCHEMA_ROOT = _ROOT / "config" / "schemas" / "catalog"
_RFI_PRODUTIVIDADES = _ROOT / "config" / "catalogos" / "rfi-r02" / "produtividades"
_RFI_INSUMOS = _ROOT / "config" / "catalogos" / "rfi-r02" / "insumos"
_RFI_CPUS = _ROOT / "config" / "catalogos" / "rfi-r02" / "cpus"


def _build_validators():
    from concilium.presentation.cli._commands_manage_helpers_d import _build_schema_validators

    return _build_schema_validators(_SCHEMA_ROOT)


def _errors(validator, item: dict) -> list[str]:
    return [".".join(str(x) for x in err.absolute_path) + f" -> {err.message}" for err in validator.iter_errors(item)]


def _base_producao(**overrides) -> dict:
    base = {
        "id": "PROD-TEST-1",
        "codigo": "PROD-TEST-1",
        "descricao": "teste",
        "producao_horaria": 1.0,
        "unidade": "m3/h",
        "categoria": "escavacao",
        "origem": "PROPRIA",
    }
    base.update(overrides)
    return base


class TestEquipamentoEquipeCamposReais:
    def test_consumo_litros_hora_sem_sufixo_valida(self):
        _, prod_v, _ = _build_validators()
        item = _base_producao(
            composicao_padrao_equipe={
                "funcoes": [],
                "equipamentos": [{"equip_id": "E0001", "num_unidades": 1, "consumo_litros_hora": 12.5}],
            }
        )
        assert _errors(prod_v, item) == []

    def test_preco_h_unitario_valida(self):
        _, prod_v, _ = _build_validators()
        item = _base_producao(
            composicao_padrao_equipe={
                "funcoes": [],
                "equipamentos": [{"equip_id": "E0001", "num_unidades": 1, "preco_h_unitario": 138.89}],
            }
        )
        assert _errors(prod_v, item) == []

    def test_consumo_litros_hora_negativo_invalido(self):
        _, prod_v, _ = _build_validators()
        item = _base_producao(
            composicao_padrao_equipe={
                "funcoes": [],
                "equipamentos": [{"equip_id": "E0001", "num_unidades": 1, "consumo_litros_hora": -1.0}],
            }
        )
        assert _errors(prod_v, item)


class TestProducaoOrigemRfi:
    def test_origem_planilha_rfi_r02_valida(self):
        _, prod_v, _ = _build_validators()
        item = _base_producao(
            origem={
                "tipo": "planilha_rfi_r02",
                "fonte_id": "ATI-010",
                "data_calibracao": "2026-05-08",
                "referencia": "Planilha Padrão RFI R02",
            }
        )
        assert _errors(prod_v, item) == []

    def test_origem_calibrado_agis_rfi_sem_fonte_id_valida(self):
        """calibrado_agis_rfi não traz fonte_id nos dados reais — não deve ser obrigatório."""
        _, prod_v, _ = _build_validators()
        item = _base_producao(
            origem={
                "tipo": "calibrado_agis_rfi",
                "data_calibracao": "2026-05-08",
                "referencia": "Híbrido AGIS + RFI-R02",
            }
        )
        assert _errors(prod_v, item) == []

    def test_origem_tipo_desconhecido_continua_invalido(self):
        _, prod_v, _ = _build_validators()
        item = _base_producao(
            origem={
                "tipo": "tipo_inventado_qualquer",
                "data_calibracao": "2026-05-08",
                "referencia": "x",
            }
        )
        assert _errors(prod_v, item)

    def test_nota_calibracao_underscore_valida(self):
        _, prod_v, _ = _build_validators()
        item = _base_producao(_nota_calibracao="nota livre de auditoria")
        assert _errors(prod_v, item) == []

    def test_campo_root_nao_underscore_desconhecido_continua_invalido(self):
        """patternProperties ^_ não deve virar uma porta aberta para qualquer campo."""
        _, prod_v, _ = _build_validators()
        item = _base_producao(campo_totalmente_desconhecido="x")
        assert _errors(prod_v, item)


class TestCpuCamposReais:
    def test_cpus_alternativos_valida(self):
        cpu_v, _, _ = _build_validators()
        item = {
            "codigo": "CPU-TEST-0001",
            "descricao": "teste",
            "unidade": "m3",
            "origem": "PROPRIA",
            "producao_id_ref": "PROD-TEST-1",
            "categoria": "TERRAPLENAGEM",
            "composicao_itens": [],
            "cpus_alternativos": ["CPU-TEST-0002"],
        }
        assert _errors(cpu_v, item) == []

    def test_grupo_servico_valida(self):
        cpu_v, _, _ = _build_validators()
        item = {
            "codigo": "CPU-TEST-0001",
            "descricao": "teste",
            "unidade": "m3",
            "origem": "PROPRIA",
            "producao_id_ref": "PROD-TEST-1",
            "categoria": "TERRAPLENAGEM",
            "composicao_itens": [],
            "grupo_servico": "TERRA-ESCO-CARGA-1CAT",
        }
        assert _errors(cpu_v, item) == []


class TestInsumoAtributosPlanilhaRfi:
    def _base_insumo(self, tipo: str, atributos: dict) -> dict:
        return {
            "codigo": "TEST-0001",
            "tipo": tipo,
            "descricao": "teste",
            "unidade": "h",
            "preco_unitario": 1.0,
            "fonte_preco": "planilha_rfi_r02",
            "atributos_especificos": atributos,
        }

    def test_mao_obra_campos_planilha_validam(self):
        _, _, ins_v = _build_validators()
        item = self._base_insumo(
            "MAO_OBRA",
            {
                "tipo_contrato": "CLT",
                "horas_mes": 220.0,
                "salario_base_hora": 27.27,
                "custo_hora_com_encargos_planilha": 44.08,
                "codigo_planilha": "P0073",
            },
        )
        assert _errors(ins_v, item) == []

    def test_equipamento_campos_planilha_validam(self):
        _, _, ins_v = _build_validators()
        item = self._base_insumo(
            "EQUIPAMENTO",
            {
                "tipo_locacao": "locação",
                "custo_produtivo_h": 90.0,
                "pct_manutencao": 0.12,
                "custo_mensal": 20160.0,
                "codigo_planilha": "E0051",
            },
        )
        assert _errors(ins_v, item) == []

    def test_material_campos_planilha_validam(self):
        _, _, ins_v = _build_validators()
        item = self._base_insumo(
            "MATERIAL",
            {
                "especificacao": "S10 (baixo teor de enxofre)",
                "uso": "equipamentos pesados de terraplenagem",
                "codigo_planilha": "MA-DIESEL-S10",
            },
        )
        assert _errors(ins_v, item) == []

    def test_atributos_especificos_ainda_rejeita_campo_desconhecido(self):
        _, _, ins_v = _build_validators()
        item = self._base_insumo("EQUIPAMENTO", {"campo_totalmente_desconhecido": "x"})
        assert _errors(ins_v, item)


class TestCatalogoRfiR02ValidaCompleto:
    """Regressão direta: o catálogo rfi-r02 completo (75 CPU + 75 PRODUCAO +
    173 INSUMO) deve validar sem nenhum erro de schema após as mudanças."""

    def test_producoes_reais_sem_erros(self):
        _, prod_v, _ = _build_validators()
        for path in sorted(_RFI_PRODUTIVIDADES.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            erros = _errors(prod_v, data)
            assert erros == [], f"{path.name}: {erros}"

    def test_insumos_reais_sem_erros(self):
        _, _, ins_v = _build_validators()
        for path in sorted(_RFI_INSUMOS.rglob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            erros = _errors(ins_v, data)
            assert erros == [], f"{path.name}: {erros}"

    def test_cpus_reais_sem_erros(self):
        cpu_v, _, _ = _build_validators()
        for path in sorted(_RFI_CPUS.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            erros = _errors(cpu_v, data)
            assert erros == [], f"{path.name}: {erros}"

    def test_producoes_nao_tem_mais_custos_equipe_snapshot(self):
        """custos_equipe_planilha/custos_equipe_rfi foram removidos dos dados
        (decisão de produto: snapshot de auditoria sem consumidor de código,
        não formalizado no schema)."""
        for path in sorted(_RFI_PRODUTIVIDADES.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            assert "custos_equipe_planilha" not in data, path.name
            assert "custos_equipe_rfi" not in data, path.name

    @pytest.mark.parametrize(
        "codigo,funcao_esperada",
        [("ATI-060", "P0040"), ("ATI-019", "P0046")],
    )
    def test_duplicata_funcao_removida(self, codigo, funcao_esperada):
        path = next(_RFI_PRODUTIVIDADES.glob(f"CPU-TERRA-{codigo}-PROD-001.json"))
        data = json.loads(path.read_text(encoding="utf-8"))
        funcoes = data["composicao_padrao_equipe"]["funcoes"]
        ocorrencias = [f for f in funcoes if f["funcao_id"] == funcao_esperada]
        assert len(ocorrencias) == 1, (
            f"esperava 1 ocorrência de {funcao_esperada} em {path.name}, achei {len(ocorrencias)}"
        )
