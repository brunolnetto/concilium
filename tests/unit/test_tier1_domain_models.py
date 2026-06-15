"""Tier 1 coverage — domain/models: jurisdicao, overrides, perfil, referencia."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from concilium.domain.models.catalog.jurisdicao import (
    AliquotasBdi,
    ComponenteEncargo,
    FonteClimatica,
    Jurisdicao,
    MotorEncargosSociais,
    MotorTributarioBdi,
    ProvedorReferencia,
)
from concilium.domain.models.project.overrides import (
    BDIOverride,
    CPUOverride,
    InsumoOverride,
    ProjectOverrides,
)
from concilium.domain.models.project.perfil import (
    CategoriaIndireto,
    Faixa,
    PerfilConstrutora,
    PoliticaAprovacao,
    TransicaoAprovacao,
)
from concilium.domain.models.catalog.referencia import (
    ComposicaoReferencia,
    InsumoReferencia,
    TabelaReferencia,
)

# ── helpers ───────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _provedor() -> ProvedorReferencia:
    return ProvedorReferencia(
        codigo="SICRO3",
        nome="SICRO 3",
        mantenedor="DNIT",
        cadencia_atualizacao="mensal",
        uso_tipico="Referência de preços de infraestrutura",
    )


def _fonte_climatica() -> FonteClimatica:
    return FonteClimatica(
        provedor="INMET",
        url_base="https://inmet.gov.br",
        metodo_consulta="API REST",
        granularidade="mensal",
    )


def _motor_encargos() -> MotorEncargosSociais:
    return MotorEncargosSociais(
        versao="2024.1",
        percentual_total=0.8,
        percentual_horista=0.8,
        percentual_mensalista=0.5,
        percentual_pj=0.1,
    )


def _aliquotas_bdi() -> AliquotasBdi:
    return AliquotasBdi(ISS=0.05, PIS=0.0065, COFINS=0.03, CPRB=0.0)


# ── ProvedorReferencia ────────────────────────────────────────────────────────


class TestProvedorReferencia:
    def test_instanciacao_valida(self):
        p = _provedor()
        assert p.codigo == "SICRO3"
        assert p.cadencia_atualizacao == "mensal"

    def test_rejeita_cadencia_invalida(self):
        with pytest.raises(ValidationError):
            ProvedorReferencia(
                codigo="X",
                nome="X",
                mantenedor="X",
                cadencia_atualizacao="semanal",
                uso_tipico="X",
            )

    def test_rejeita_campo_extra(self):
        with pytest.raises(ValidationError):
            ProvedorReferencia(
                codigo="X",
                nome="X",
                mantenedor="X",
                cadencia_atualizacao="mensal",
                uso_tipico="X",
                campo_extra="errado",
            )


# ── FonteClimatica ────────────────────────────────────────────────────────────


class TestFonteClimatica:
    def test_granularidade_default(self):
        f = FonteClimatica(provedor="INMET", metodo_consulta="API")
        assert f.granularidade == "mensal"
        assert f.url_base is None

    def test_granularidade_diaria(self):
        f = FonteClimatica(provedor="X", metodo_consulta="scraping", granularidade="diaria")
        assert f.granularidade == "diaria"


# ── ComponenteEncargo ─────────────────────────────────────────────────────────


class TestComponenteEncargo:
    def test_percentual_valido(self):
        c = ComponenteEncargo(nome="INSS", percentual=0.20)
        assert c.percentual == 0.20

    def test_rejeita_percentual_negativo(self):
        with pytest.raises(ValidationError):
            ComponenteEncargo(nome="X", percentual=-0.01)

    def test_rejeita_percentual_acima_limite(self):
        with pytest.raises(ValidationError):
            ComponenteEncargo(nome="X", percentual=2.1)


# ── MotorEncargosSociais ──────────────────────────────────────────────────────


class TestMotorEncargosSociais:
    def test_campos_opcionais_none(self):
        m = MotorEncargosSociais(versao="2024.1", percentual_total=0.5)
        assert m.percentual_horista is None
        assert m.percentual_mensalista is None
        assert m.percentual_pj is None
        assert m.componentes == []

    def test_com_componentes(self):
        m = MotorEncargosSociais(
            versao="2024.1",
            percentual_total=0.8,
            componentes=[ComponenteEncargo(nome="INSS", percentual=0.20)],
        )
        assert len(m.componentes) == 1

    def test_rejeita_pj_acima_limite(self):
        with pytest.raises(ValidationError):
            MotorEncargosSociais(versao="x", percentual_total=0.5, percentual_pj=1.1)


# ── MotorTributarioBdi ────────────────────────────────────────────────────────


class TestMotorTributarioBdi:
    def test_total_propriedade(self):
        aliq = _aliquotas_bdi()
        motor = MotorTributarioBdi(versao="2024.1", aliquotas=aliq)
        esperado = round(0.05 + 0.0065 + 0.03 + 0.0, 6)
        assert abs(motor.total - esperado) < 1e-9

    def test_total_todos_zerados(self):
        aliq = AliquotasBdi(ISS=0.0, PIS=0.0, COFINS=0.0, CPRB=0.0)
        motor = MotorTributarioBdi(versao="2024.1", aliquotas=aliq)
        assert motor.total == 0.0


# ── Jurisdicao ────────────────────────────────────────────────────────────────


class TestJurisdicao:
    def _make(self, **kwargs) -> Jurisdicao:
        defaults = dict(
            codigo="BR",
            nome="Brasil",
            moeda="BRL",
            regime_trabalhista="CLT",
            provedores_referencia=[_provedor()],
            fonte_climatica=_fonte_climatica(),
            motor_encargos_sociais=_motor_encargos(),
        )
        defaults.update(kwargs)
        return Jurisdicao(**defaults)

    def test_instanciacao_basica(self):
        j = self._make()
        assert j.codigo == "BR"
        assert j.motor_tributario_bdi is None

    def test_com_motor_tributario(self):
        j = self._make(
            motor_tributario_bdi=MotorTributarioBdi(versao="v1", aliquotas=_aliquotas_bdi())
        )
        assert j.motor_tributario_bdi is not None
        assert j.motor_tributario_bdi.versao == "v1"

    def test_rejeita_codigo_invalido(self):
        with pytest.raises(ValidationError):
            self._make(codigo="brasil")

    def test_rejeita_moeda_invalida(self):
        with pytest.raises(ValidationError):
            self._make(moeda="brl")

    def test_rejeita_regime_invalido(self):
        with pytest.raises(ValidationError):
            self._make(regime_trabalhista="PJ")

    def test_ignora_campos_extras(self):
        j = Jurisdicao(
            codigo="BR",
            nome="Brasil",
            moeda="BRL",
            regime_trabalhista="CLT",
            provedores_referencia=[_provedor()],
            fonte_climatica=_fonte_climatica(),
            motor_encargos_sociais=_motor_encargos(),
            campo_desconhecido="ignorado",
        )
        assert not hasattr(j, "campo_desconhecido")


# ── InsumoOverride ────────────────────────────────────────────────────────────


class TestInsumoOverride:
    def test_instanciacao_completa(self):
        o = InsumoOverride(
            codigo="DIESEL",
            preco_calibrado=6.35,
            motivo="Negociação em escala",
            aprovado_por="engenheiro",
            aprovado_em=_NOW,
        )
        assert o.preco_calibrado == 6.35
        assert o.valido_ate is None
        assert o.fonte_cotacao is None

    def test_rejeita_preco_negativo(self):
        with pytest.raises(ValidationError):
            InsumoOverride(
                codigo="X",
                preco_calibrado=-1.0,
                motivo="X",
                aprovado_por="X",
                aprovado_em=_NOW,
            )

    def test_rejeita_campo_extra(self):
        with pytest.raises(ValidationError):
            InsumoOverride(
                codigo="X",
                preco_calibrado=1.0,
                motivo="X",
                aprovado_por="X",
                aprovado_em=_NOW,
                campo_extra="x",
            )


# ── CPUOverride ───────────────────────────────────────────────────────────────


class TestCPUOverride:
    def test_campos_opcionais(self):
        o = CPUOverride(
            codigo="ATI-019",
            motivo="Produtividade de campo medida",
            aprovado_por="eng",
            aprovado_em=_NOW,
        )
        assert o.producao_horaria_calibrada is None
        assert o.permanencia_meses_calibrada is None
        assert o.observacoes is None

    def test_rejeita_producao_nao_positiva(self):
        with pytest.raises(ValidationError):
            CPUOverride(
                codigo="X",
                producao_horaria_calibrada=0.0,
                motivo="X",
                aprovado_por="X",
                aprovado_em=_NOW,
            )


# ── BDIOverride ───────────────────────────────────────────────────────────────


class TestBDIOverride:
    def test_como_dict_bdi_apenas_definidos(self):
        o = BDIOverride(
            material=0.05,
            mao_obra=None,
            diesel=0.10,
            motivo="Regime especial",
            aprovado_por="dir",
            aprovado_em=_NOW,
        )
        d = o.como_dict_bdi()
        assert d == {"material": 0.05, "diesel": 0.10}
        assert "mao_obra" not in d
        assert "equipamentos" not in d

    def test_como_dict_bdi_vazio(self):
        o = BDIOverride(motivo="X", aprovado_por="X", aprovado_em=_NOW)
        assert o.como_dict_bdi() == {}

    def test_rejeita_valor_acima_limite(self):
        with pytest.raises(ValidationError):
            BDIOverride(material=0.51, motivo="X", aprovado_por="X", aprovado_em=_NOW)


# ── ProjectOverrides ──────────────────────────────────────────────────────────


class TestProjectOverrides:
    def test_defaults_vazios(self):
        p = ProjectOverrides()
        assert p.insumos == {}
        assert p.cpus == {}
        assert p.bdi is None

    def test_com_cpu_override(self):
        cpu = CPUOverride(codigo="ATI-019", motivo="X", aprovado_por="X", aprovado_em=_NOW)
        p = ProjectOverrides(cpus={"ATI-019": cpu})
        assert "ATI-019" in p.cpus


# ── Perfil models ─────────────────────────────────────────────────────────────


class TestFaixa:
    def test_instanciacao(self):
        f = Faixa(min=0.1, max=0.3)
        assert f.min == 0.1
        assert f.max == 0.3


class TestPerfilConstrutora:
    def _make(self) -> PerfilConstrutora:
        return PerfilConstrutora(
            id="mendeslobo",
            nome="Mendes Lobo Construção",
            jurisdicao_id="BR",
            faixa_margem_alvo=Faixa(min=0.08, max=0.15),
            faixa_margem_aceitavel=Faixa(min=0.05, max=0.20),
            categorias_indireto=[CategoriaIndireto(codigo="TOP", descricao="Topografia")],
        )

    def test_instanciacao_basica(self):
        p = self._make()
        assert p.id == "mendeslobo"
        assert len(p.categorias_indireto) == 1
        assert p.razao_indireto_direto_alvo is None

    def test_rejeita_id_invalido(self):
        with pytest.raises(ValidationError):
            PerfilConstrutora(
                id="Mendes Lobo",  # espaço não permitido
                nome="X",
                jurisdicao_id="BR",
                faixa_margem_alvo=Faixa(min=0.1, max=0.2),
                faixa_margem_aceitavel=Faixa(min=0.0, max=0.3),
                categorias_indireto=[CategoriaIndireto(codigo="X", descricao="X")],
            )

    def test_rejeita_lista_categorias_vazia(self):
        with pytest.raises(ValidationError):
            PerfilConstrutora(
                id="x",
                nome="X",
                jurisdicao_id="BR",
                faixa_margem_alvo=Faixa(min=0.1, max=0.2),
                faixa_margem_aceitavel=Faixa(min=0.0, max=0.3),
                categorias_indireto=[],
            )

    def test_com_razao_indireto(self):
        p = self._make()
        p2 = p.model_copy(update={"razao_indireto_direto_alvo": Faixa(min=0.1, max=0.3)})
        assert p2.razao_indireto_direto_alvo is not None


class TestPoliticaAprovacao:
    def test_instanciacao(self):
        pol = PoliticaAprovacao(
            tipo="rigida",
            transicoes=[
                TransicaoAprovacao(de="rascunho", para="aprovado", papel_requerido="diretor")
            ],
        )
        assert pol.tipo == "rigida"
        assert len(pol.transicoes) == 1


# ── Referencia models ─────────────────────────────────────────────────────────


class TestComposicaoReferencia:
    def test_campos_opcionais_none(self):
        c = ComposicaoReferencia(
            codigo_referencia="SICRO-001",
            descricao="Terraplenagem",
            unidade="m³",
        )
        assert c.preco_unitario_publicado is None
        assert c.data_referencia_preco is None

    def test_com_preco(self):
        c = ComposicaoReferencia(
            codigo_referencia="X",
            descricao="X",
            unidade="m³",
            preco_unitario_publicado=120.50,
            data_referencia_preco=date(2026, 1, 1),
        )
        assert c.preco_unitario_publicado == 120.50

    def test_rejeita_preco_negativo(self):
        with pytest.raises(ValidationError):
            ComposicaoReferencia(
                codigo_referencia="X",
                descricao="X",
                unidade="m³",
                preco_unitario_publicado=-1.0,
            )


class TestInsumoReferencia:
    def test_tipos_validos(self):
        for tipo in ("MATERIAL", "MAO_OBRA", "EQUIPAMENTO"):
            i = InsumoReferencia(
                codigo_referencia="X",
                descricao="X",
                tipo=tipo,
                unidade="un",
                preco_publicado=10.0,
            )
            assert i.tipo == tipo

    def test_rejeita_tipo_invalido(self):
        with pytest.raises(ValidationError):
            InsumoReferencia(
                codigo_referencia="X",
                descricao="X",
                tipo="COMBUSTIVEL",
                unidade="un",
                preco_publicado=10.0,
            )


class TestTabelaReferencia:
    def test_instanciacao_minima(self):
        t = TabelaReferencia(
            codigo="SICRO3-GO-2026-01",
            provedor="DNIT",
            versao="jan/2026",
            regiao="GO",
            data_vigencia=date(2026, 1, 1),
        )
        assert t.imutavel is True
        assert t.composicoes_referencia == []
        assert t.insumos_referencia == []

    def test_rejeita_regiao_invalida(self):
        with pytest.raises(ValidationError):
            TabelaReferencia(
                codigo="X",
                provedor="X",
                versao="x",
                regiao="go",  # deve ser maiúsculo
                data_vigencia=date(2026, 1, 1),
            )

    def test_com_composicoes(self):
        t = TabelaReferencia(
            codigo="X",
            provedor="X",
            versao="x",
            regiao="GO",
            data_vigencia=date(2026, 1, 1),
            composicoes_referencia=[
                ComposicaoReferencia(codigo_referencia="A", descricao="A", unidade="m³")
            ],
        )
        assert len(t.composicoes_referencia) == 1
