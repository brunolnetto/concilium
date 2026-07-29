"""ADR-165 — Catálogo de Treinamentos, Exames, EPIs e Benefícios de MO: TDD.

Cobre:
  - D1: `TipoInsumo` ganha `TREINAMENTO`/`EXAME`/`BENEFICIO`; EPI permanece `MATERIAL`.
  - D2: `AtributosInsumo.vida_util_dias` — ciclo de substituição/revalidação em dias.
  - D3: `AtributosInsumo.funcoes_aplicaveis` — elegibilidade por função (`None` = comum).
  - D4: `AtributosInsumo.periodicidade_beneficio`/`aplicavel_tipo_contrato` (só BENEFICIO).
  - D5: `model_validator` restringindo cada campo novo ao(s) tipo(s) correto(s)
    (VAL-INSUMO-VIDA-UTIL-01 / VAL-INSUMO-FUNCOES-01 / VAL-INSUMO-BENEFICIO-01).

Escrito antes da implementação (red phase).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from concilium.domain.models.catalog.catalogo import AtributosInsumo, Insumo


def _codigo_seguro(tipo: str) -> str:
    return f"COD-{tipo.replace('_', '-')}"


def _insumo_kwargs(**overrides) -> dict:
    base = {
        "codigo": "EPI-CAPACETE-3M",
        "tipo": "MATERIAL",
        "descricao": "Capacete 3M",
        "unidade": "unid",
        "preco_unitario": 170.0,
        "fonte_preco": "catalogo_proprio",
    }
    base.update(overrides)
    return base


class TestTipoInsumoNovosValores:
    @pytest.mark.parametrize("tipo", ["TREINAMENTO", "EXAME", "BENEFICIO"])
    def test_aceita_tipo_novo(self, tipo):
        insumo = Insumo(
            **_insumo_kwargs(
                codigo="TRE-NR35-ALTURA" if tipo == "TREINAMENTO" else f"XXX-{tipo}",
                tipo=tipo,
                descricao="Item de teste",
            )
        )
        assert insumo.tipo == tipo

    def test_epi_permanece_material_sem_tipo_novo(self):
        insumo = Insumo(**_insumo_kwargs())
        assert insumo.tipo == "MATERIAL"


class TestVidaUtilDias:
    @pytest.mark.parametrize("tipo", ["MATERIAL", "TREINAMENTO", "EXAME"])
    def test_aceita_em_tipos_validos(self, tipo):
        insumo = Insumo(
            **_insumo_kwargs(
                codigo=_codigo_seguro(tipo),
                tipo=tipo,
                atributos_especificos=AtributosInsumo(vida_util_dias=360),
            )
        )
        assert insumo.atributos_especificos.vida_util_dias == 360

    @pytest.mark.parametrize("tipo", ["MAO_OBRA", "EQUIPAMENTO", "TERCEIRIZADO", "BENEFICIO"])
    def test_val_insumo_vida_util_01_tipo_invalido_falha_alto(self, tipo):
        with pytest.raises(ValidationError, match="VAL-INSUMO-VIDA-UTIL-01"):
            Insumo(
                **_insumo_kwargs(
                    codigo=_codigo_seguro(tipo),
                    tipo=tipo,
                    atributos_especificos=AtributosInsumo(vida_util_dias=360),
                )
            )

    def test_valor_nao_positivo_rejeitado(self):
        with pytest.raises(ValidationError):
            AtributosInsumo(vida_util_dias=0)

    def test_default_none_retrocompativel(self):
        assert AtributosInsumo().vida_util_dias is None


class TestFuncoesAplicaveis:
    @pytest.mark.parametrize("tipo", ["MATERIAL", "TREINAMENTO"])
    def test_aceita_em_tipos_validos(self, tipo):
        insumo = Insumo(
            **_insumo_kwargs(
                codigo=_codigo_seguro(tipo),
                tipo=tipo,
                atributos_especificos=AtributosInsumo(funcoes_aplicaveis=["MO-OP-MOTOSSERRA"]),
            )
        )
        assert insumo.atributos_especificos.funcoes_aplicaveis == ["MO-OP-MOTOSSERRA"]

    @pytest.mark.parametrize("tipo", ["MAO_OBRA", "EQUIPAMENTO", "TERCEIRIZADO", "EXAME", "BENEFICIO"])
    def test_val_insumo_funcoes_01_tipo_invalido_falha_alto(self, tipo):
        with pytest.raises(ValidationError, match="VAL-INSUMO-FUNCOES-01"):
            Insumo(
                **_insumo_kwargs(
                    codigo=_codigo_seguro(tipo),
                    tipo=tipo,
                    atributos_especificos=AtributosInsumo(funcoes_aplicaveis=["MO-OP-MOTOSSERRA"]),
                )
            )

    def test_default_none_significa_comum_a_todas_funcoes(self):
        assert AtributosInsumo().funcoes_aplicaveis is None


class TestBeneficio:
    def test_aceita_periodicidade_e_tipo_contrato_em_beneficio(self):
        insumo = Insumo(
            **_insumo_kwargs(
                codigo="BEN-JANTAR",
                tipo="BENEFICIO",
                descricao="Jantar",
                atributos_especificos=AtributosInsumo(
                    periodicidade_beneficio="diaria",
                    aplicavel_tipo_contrato=["CLT"],
                ),
            )
        )
        assert insumo.atributos_especificos.periodicidade_beneficio == "diaria"
        assert insumo.atributos_especificos.aplicavel_tipo_contrato == ["CLT"]

    @pytest.mark.parametrize("tipo", ["MATERIAL", "MAO_OBRA", "EQUIPAMENTO", "TERCEIRIZADO", "TREINAMENTO", "EXAME"])
    def test_val_insumo_beneficio_01_periodicidade_fora_de_beneficio_falha_alto(self, tipo):
        with pytest.raises(ValidationError, match="VAL-INSUMO-BENEFICIO-01"):
            Insumo(
                **_insumo_kwargs(
                    codigo=_codigo_seguro(tipo),
                    tipo=tipo,
                    atributos_especificos=AtributosInsumo(periodicidade_beneficio="mensal"),
                )
            )

    @pytest.mark.parametrize("tipo", ["MATERIAL", "MAO_OBRA", "EQUIPAMENTO", "TERCEIRIZADO", "TREINAMENTO", "EXAME"])
    def test_val_insumo_beneficio_01_tipo_contrato_fora_de_beneficio_falha_alto(self, tipo):
        with pytest.raises(ValidationError, match="VAL-INSUMO-BENEFICIO-01"):
            Insumo(
                **_insumo_kwargs(
                    codigo=_codigo_seguro(tipo),
                    tipo=tipo,
                    atributos_especificos=AtributosInsumo(aplicavel_tipo_contrato=["PJ"]),
                )
            )

    def test_default_none_significa_aplica_a_ambos_regimes(self):
        assert AtributosInsumo().aplicavel_tipo_contrato is None
        assert AtributosInsumo().periodicidade_beneficio is None


class TestRetrocompatibilidade:
    def test_insumo_mao_obra_existente_continua_valido(self):
        insumo = Insumo(
            codigo="MO-ARMADOR",
            tipo="MAO_OBRA",
            descricao="Armador",
            unidade="h",
            preco_unitario=25.0,
            fonte_preco="catalogo_proprio",
            atributos_especificos=AtributosInsumo(salario_mensal=3000.0, tipo_contrato="CLT"),
        )
        assert insumo.atributos_especificos.vida_util_dias is None
        assert insumo.atributos_especificos.funcoes_aplicaveis is None
