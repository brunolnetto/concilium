"""Testes ADR-130 — Composição de Equipe como Grafo de Sinergia: Produtividade Derivada.

F1: modelos RelacaoSinergia/CapacidadeElemento/GrafoSinergiaEquipe + VAL-SINERGIA-01
F2: motor de derivação (D2) + precedência (D3) + VAL-SINERGIA-02/03
F3: re-derivação em mudança de composição + VAL-SINERGIA-04/05
F5: atualização de capacidade do elemento gargalo
"""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from concilium.domain.models.catalog.catalogo import (
    ComposicaoPadraoEquipe,
    EquipamentoEquipe,
    FuncaoEquipe,
    MaterialEquipe,
)
from concilium.domain.models.catalog.producao import (
    AuditoriaProducao,
    CapacidadeElemento,
    CondicoesCalibração,
    GrafoSinergiaEquipe,
    OrigemProducao,
    Producao,
    QualidadeProducao,
    RelacaoSinergia,
)
from concilium.domain.services.sinergia_equipe import (
    LIMIAR_DIVERGENCIA_SINERGIA,
    atualizar_capacidade_gargalo,
    derivar_producao_horaria,
    resolver_producao_efetiva,
    revalidar_apos_mudanca_composicao,
    validar_referencias_grafo,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _composicao_escavacao(
    num_escavadeiras: int = 1,
    num_caminhoes: int = 4,
) -> ComposicaoPadraoEquipe:
    """Família terraplenagem/escavação: escavadeira (gargalo) + caminhões (dimensionamento) + operador (acoplamento)."""
    return ComposicaoPadraoEquipe(
        funcoes=[FuncaoEquipe(funcao_id="OPER-ESCAV", num_pessoas=1)],
        equipamentos=[
            EquipamentoEquipe(equip_id="ESCAV-38T", num_unidades=num_escavadeiras),
            EquipamentoEquipe(equip_id="CAMINHAO-BASC", num_unidades=num_caminhoes),
        ],
        materiais=[MaterialEquipe(insumo_id="AGUA-UMECT", consumo_por_hora=0.5, unidade="m3/h")],
    )


def _grafo_escavacao(
    capacidade_escavadeira: float = 100.0,
    capacidade_caminhao_unitario: float = 30.0,
    razao_caminhoes: float | None = None,
    gargalo_declarado: str | None = None,
) -> GrafoSinergiaEquipe:
    relacoes = [
        RelacaoSinergia(tipo="acoplamento", origem="OPER-ESCAV", destino="ESCAV-38T"),
        RelacaoSinergia(
            tipo="dimensionamento",
            origem="ESCAV-38T",
            destino="CAMINHAO-BASC",
            razao=razao_caminhoes,
        ),
        RelacaoSinergia(tipo="precondicao", origem="AGUA-UMECT", destino="ESCAV-38T"),
    ]
    return GrafoSinergiaEquipe(
        relacoes=relacoes,
        capacidades=[
            CapacidadeElemento(elemento_id="ESCAV-38T", capacidade_horaria=capacidade_escavadeira, unidade="m3/h"),
            CapacidadeElemento(
                elemento_id="CAMINHAO-BASC", capacidade_horaria=capacidade_caminhao_unitario, unidade="m3/h"
            ),
        ],
        gargalo_declarado=gargalo_declarado,
    )


def _producao(
    valor_horario: float = 100.0,
    composicao: ComposicaoPadraoEquipe | None = None,
    grafo: GrafoSinergiaEquipe | None = None,
    tipo_origem: str = "tabela_referencia",
) -> Producao:
    agora = datetime.now()
    return Producao(
        id="PROD-ESCO-1",
        codigo="ESCO-CARGA-1CAT",
        descricao="Escavação carga 1ª categoria",
        valor_horario=valor_horario,
        unidade="m3",
        origem=OrigemProducao(
            tipo=tipo_origem,
            fonte_id="SICRO-2024-CE",
            data_calibracao=agora,
            referencia="DNIT/SICRO",
        ),
        condicoes_calibracao=CondicoesCalibração(),
        qualidade=QualidadeProducao(
            confianca_pct=90,
            intervalo_confianca=(80.0, 120.0),
            quantidade_amostras=5,
            desvio_padrao=7.0,
        ),
        composicao_padrao_equipe=composicao or _composicao_escavacao(),
        auditoria=AuditoriaProducao(
            criado_por="test",
            data_criacao=agora,
            ultima_modificacao=agora,
            modificado_por="test",
            versao="1.0",
        ),
        grafo_sinergia=grafo,
    )


# ── F1 — modelos ──────────────────────────────────────────────────────────────


class TestModelosF1:
    def test_grafo_sinergia_opcional_default_none(self):
        p = _producao(grafo=None)
        assert p.grafo_sinergia is None

    def test_grafo_sinergia_extra_forbid(self):
        with pytest.raises(ValidationError):
            GrafoSinergiaEquipe(relacoes=[], capacidades=[], campo_invalido=True)  # type: ignore[call-arg]

    def test_relacao_sinergia_extra_forbid(self):
        with pytest.raises(ValidationError):
            RelacaoSinergia(tipo="acoplamento", origem="A", destino="B", campo_invalido=1)  # type: ignore[call-arg]

    def test_capacidade_elemento_extra_forbid(self):
        with pytest.raises(ValidationError):
            CapacidadeElemento(elemento_id="X", capacidade_horaria=10.0, unidade="m3/h", campo_invalido=1)  # type: ignore[call-arg]

    def test_capacidade_elemento_capacidade_horaria_deve_ser_positiva(self):
        with pytest.raises(ValidationError):
            CapacidadeElemento(elemento_id="X", capacidade_horaria=0.0, unidade="m3/h")

    def test_capacidade_elemento_fonte_default_catalogo(self):
        c = CapacidadeElemento(elemento_id="X", capacidade_horaria=10.0, unidade="m3/h")
        assert c.fonte == "catalogo"

    def test_serializacao_retrocompativel_sem_grafo(self):
        p = _producao(grafo=None)
        dump = p.model_dump(by_alias=True)
        assert dump["grafo_sinergia"] is None
        # round-trip
        p2 = Producao(**dump)
        assert p2.grafo_sinergia is None

    def test_serializacao_com_grafo_round_trip(self):
        grafo = _grafo_escavacao()
        p = _producao(grafo=grafo)
        dump = p.model_dump(by_alias=True)
        p2 = Producao(**dump)
        assert p2.grafo_sinergia is not None
        assert len(p2.grafo_sinergia.relacoes) == 3
        assert len(p2.grafo_sinergia.capacidades) == 2


class TestValSinergia01ReferenciaOrfa:
    def test_sem_orfaos_retorna_vazio(self):
        grafo = _grafo_escavacao()
        composicao = _composicao_escavacao()
        assert validar_referencias_grafo(grafo, composicao) == []

    def test_relacao_com_origem_orfa_emite_erro(self):
        grafo = GrafoSinergiaEquipe(
            relacoes=[RelacaoSinergia(tipo="acoplamento", origem="INEXISTENTE", destino="ESCAV-38T")]
        )
        composicao = _composicao_escavacao()
        validacoes = validar_referencias_grafo(grafo, composicao)
        assert len(validacoes) == 1
        assert validacoes[0].codigo == "VAL-SINERGIA-01"
        assert validacoes[0].status == "ERRO"
        assert "INEXISTENTE" in validacoes[0].mensagem

    def test_relacao_com_destino_orfa_emite_erro(self):
        grafo = GrafoSinergiaEquipe(
            relacoes=[RelacaoSinergia(tipo="acoplamento", origem="ESCAV-38T", destino="INEXISTENTE")]
        )
        validacoes = validar_referencias_grafo(grafo, _composicao_escavacao())
        assert any(v.codigo == "VAL-SINERGIA-01" and v.status == "ERRO" for v in validacoes)

    def test_capacidade_com_elemento_orfao_emite_erro(self):
        grafo = GrafoSinergiaEquipe(
            capacidades=[CapacidadeElemento(elemento_id="INEXISTENTE", capacidade_horaria=1.0, unidade="m3/h")]
        )
        validacoes = validar_referencias_grafo(grafo, _composicao_escavacao())
        assert any(v.codigo == "VAL-SINERGIA-01" for v in validacoes)

    def test_gargalo_declarado_orfao_emite_erro(self):
        grafo = GrafoSinergiaEquipe(gargalo_declarado="INEXISTENTE")
        validacoes = validar_referencias_grafo(grafo, _composicao_escavacao())
        assert any(v.codigo == "VAL-SINERGIA-01" for v in validacoes)


# ── F2 — derivação (D2) e precedência (D3) ────────────────────────────────────


class TestDerivacaoD2:
    def test_sem_capacidades_retorna_none(self):
        grafo = GrafoSinergiaEquipe()
        d = derivar_producao_horaria(grafo, _composicao_escavacao())
        assert d.producao_horaria_derivada is None
        assert d.gargalo_derivado is None

    def test_gargalo_e_o_minimo_das_capacidades_efetivas(self):
        # escavadeira: 1 unidade x 100 m3/h = 100
        # caminhoes: 4 unidades x 30 m3/h = 120, saturado por dimensionamento pela escavadeira -> min(120,100)=100
        grafo = _grafo_escavacao(capacidade_escavadeira=100.0, capacidade_caminhao_unitario=30.0)
        d = derivar_producao_horaria(grafo, _composicao_escavacao(num_caminhoes=4))
        assert d.producao_horaria_derivada == 100.0
        assert d.gargalo_derivado == "ESCAV-38T"

    def test_caminhoes_insuficientes_tornam_se_gargalo(self):
        # caminhoes: 2 unidades x 30 = 60 < escavadeira 100 -> gargalo é caminhão
        grafo = _grafo_escavacao(capacidade_escavadeira=100.0, capacidade_caminhao_unitario=30.0)
        d = derivar_producao_horaria(grafo, _composicao_escavacao(num_caminhoes=2))
        assert d.producao_horaria_derivada == 60.0
        assert d.gargalo_derivado == "CAMINHAO-BASC"

    def test_acoplamento_satura_par_pelo_menor(self):
        # Operador tem capacidade declarada menor que a escavadeira -> par opera no mínimo.
        grafo = GrafoSinergiaEquipe(
            relacoes=[RelacaoSinergia(tipo="acoplamento", origem="OPER-ESCAV", destino="ESCAV-38T")],
            capacidades=[
                CapacidadeElemento(elemento_id="OPER-ESCAV", capacidade_horaria=80.0, unidade="m3/h"),
                CapacidadeElemento(elemento_id="ESCAV-38T", capacidade_horaria=100.0, unidade="m3/h"),
            ],
        )
        d = derivar_producao_horaria(grafo, _composicao_escavacao(num_caminhoes=4))
        assert d.producao_horaria_derivada == 80.0
        assert d.capacidades_efetivas["ESCAV-38T"] == 80.0

    def test_precondicao_nao_altera_a_taxa(self):
        # AGUA-UMECT é origem de precondicao; mesmo com capacidade declarada, é excluída do mínimo.
        grafo = GrafoSinergiaEquipe(
            relacoes=[RelacaoSinergia(tipo="precondicao", origem="AGUA-UMECT", destino="ESCAV-38T")],
            capacidades=[
                CapacidadeElemento(elemento_id="AGUA-UMECT", capacidade_horaria=1.0, unidade="m3/h"),
                CapacidadeElemento(elemento_id="ESCAV-38T", capacidade_horaria=100.0, unidade="m3/h"),
            ],
        )
        d = derivar_producao_horaria(grafo, _composicao_escavacao())
        assert d.producao_horaria_derivada == 100.0
        assert d.gargalo_derivado == "ESCAV-38T"


class TestPrecedenciaD3:
    def test_sem_grafo_usa_declarado(self):
        p = _producao(valor_horario=234.0, grafo=None)
        r = resolver_producao_efetiva(p)
        assert r.fonte == "declarado"
        assert r.valor == 234.0
        assert r.validacoes == []

    def test_calibrado_vence_derivado_mesmo_com_grafo(self):
        grafo = _grafo_escavacao(capacidade_escavadeira=100.0, capacidade_caminhao_unitario=30.0)
        p = _producao(valor_horario=234.0, grafo=grafo, tipo_origem="calibrado_contra_obra_real")
        r = resolver_producao_efetiva(p)
        assert r.fonte == "calibrado"
        assert r.valor == 234.0  # valor calibrado preservado, nunca sobrescrito

    def test_derivado_vence_declarado_quando_nao_calibrado(self):
        grafo = _grafo_escavacao(capacidade_escavadeira=100.0, capacidade_caminhao_unitario=30.0)
        p = _producao(valor_horario=234.0, grafo=grafo, tipo_origem="tabela_referencia")
        r = resolver_producao_efetiva(p)
        assert r.fonte == "derivado"
        assert r.valor == 100.0
        # a Producao original nunca é mutada por esta função consultiva
        assert p.valor_horario == 234.0

    def test_divergencia_alta_emite_val_sinergia_02_e_preserva_declarado(self):
        grafo = _grafo_escavacao(capacidade_escavadeira=100.0, capacidade_caminhao_unitario=30.0)
        p = _producao(valor_horario=234.0, grafo=grafo)  # diverge > 15% de 100.0
        r = resolver_producao_efetiva(p)
        assert any(v.codigo == "VAL-SINERGIA-02" and v.status == "AVISO" for v in r.validacoes)
        assert p.valor_horario == 234.0  # preservado

    def test_divergencia_dentro_do_limiar_nao_emite_val_sinergia_02(self):
        # declarado 105 vs derivado 100 -> 5% < 15%
        grafo = _grafo_escavacao(capacidade_escavadeira=100.0, capacidade_caminhao_unitario=30.0)
        p = _producao(valor_horario=105.0, grafo=grafo)
        r = resolver_producao_efetiva(p)
        assert not any(v.codigo == "VAL-SINERGIA-02" for v in r.validacoes)

    def test_divergencia_no_limiar_exato_nao_emite_aviso(self):
        # 15% exato não deve disparar (estritamente >)
        base = 100.0
        declarado = base * (1 + LIMIAR_DIVERGENCIA_SINERGIA)
        grafo = _grafo_escavacao(capacidade_escavadeira=base, capacidade_caminhao_unitario=30.0)
        p = _producao(valor_horario=declarado, grafo=grafo)
        r = resolver_producao_efetiva(p)
        assert not any(v.codigo == "VAL-SINERGIA-02" for v in r.validacoes)

    def test_gargalo_declarado_coincide_nao_emite_val_sinergia_03(self):
        grafo = _grafo_escavacao(gargalo_declarado="ESCAV-38T")
        p = _producao(valor_horario=100.0, grafo=grafo)
        r = resolver_producao_efetiva(p)
        assert not any(v.codigo == "VAL-SINERGIA-03" for v in r.validacoes)

    def test_gargalo_declarado_diverge_emite_val_sinergia_03(self):
        grafo = _grafo_escavacao(gargalo_declarado="CAMINHAO-BASC")
        p = _producao(valor_horario=100.0, grafo=grafo)
        r = resolver_producao_efetiva(p)
        assert any(v.codigo == "VAL-SINERGIA-03" and v.status == "AVISO" for v in r.validacoes)

    def test_referencia_orfa_propaga_val_sinergia_01_via_resolver(self):
        grafo = GrafoSinergiaEquipe(
            relacoes=[RelacaoSinergia(tipo="acoplamento", origem="INEXISTENTE", destino="ESCAV-38T")]
        )
        p = _producao(grafo=grafo)
        r = resolver_producao_efetiva(p)
        assert any(v.codigo == "VAL-SINERGIA-01" and v.status == "ERRO" for v in r.validacoes)

    def test_referencia_orfa_nunca_retorna_fonte_derivado(self):
        """Copilot (PR #78): um grafo com referência quebrada (VAL-SINERGIA-01 ERRO)
        não pode influenciar o resultado — mesmo que derivar_producao_horaria produza
        um valor, fonte deve cair para declarado/calibrado, nunca "derivado"."""
        grafo = GrafoSinergiaEquipe(
            capacidades=[
                CapacidadeElemento(elemento_id="ESCAV-38T", capacidade_horaria=100.0, unidade="m3/h"),
            ],
            relacoes=[RelacaoSinergia(tipo="acoplamento", origem="INEXISTENTE", destino="ESCAV-38T")],
        )
        p = _producao(valor_horario=50.0, grafo=grafo)
        r = resolver_producao_efetiva(p)
        assert r.fonte == "declarado"
        assert r.valor == 50.0


# ── F3 — reatividade (re-derivação em mudança de composição) ─────────────────


class TestReatividadeF3:
    def test_sem_grafo_retorna_vazio(self):
        p = _producao(grafo=None)
        nova = _composicao_escavacao(num_caminhoes=6)
        assert revalidar_apos_mudanca_composicao(p, nova) == []

    def test_mudanca_de_composicao_emite_val_sinergia_04_info(self):
        grafo = _grafo_escavacao()
        p = _producao(grafo=grafo)
        nova = _composicao_escavacao(num_caminhoes=6)
        validacoes = revalidar_apos_mudanca_composicao(p, nova)
        assert any(v.codigo == "VAL-SINERGIA-04" and v.status == "INFO" for v in validacoes)

    def test_razao_dimensionamento_violada_emite_val_sinergia_05(self):
        # razão: 1 caminhão por escavadeira exige >= 1 caminhão por escavadeira;
        # aqui exigimos razão alta (5 caminhões/escavadeira) violada por composição com poucos caminhões.
        grafo = _grafo_escavacao(razao_caminhoes=5.0)
        p = _producao(grafo=grafo)
        nova = _composicao_escavacao(num_escavadeiras=1, num_caminhoes=2)  # exige 5, tem 2
        validacoes = revalidar_apos_mudanca_composicao(p, nova)
        assert any(v.codigo == "VAL-SINERGIA-05" and v.status == "AVISO" for v in validacoes)

    def test_razao_dimensionamento_respeitada_nao_emite_val_sinergia_05(self):
        grafo = _grafo_escavacao(razao_caminhoes=4.0)
        p = _producao(grafo=grafo)
        nova = _composicao_escavacao(num_escavadeiras=1, num_caminhoes=4)
        validacoes = revalidar_apos_mudanca_composicao(p, nova)
        assert not any(v.codigo == "VAL-SINERGIA-05" for v in validacoes)

    def test_referencia_orfa_na_nova_composicao_emite_val_sinergia_01(self):
        grafo = _grafo_escavacao()
        p = _producao(grafo=grafo)
        nova = ComposicaoPadraoEquipe(
            funcoes=[FuncaoEquipe(funcao_id="OPER-ESCAV", num_pessoas=1)],
            equipamentos=[EquipamentoEquipe(equip_id="ESCAV-38T", num_unidades=1)],
            # CAMINHAO-BASC removido da nova composição -> agora órfão nas relações do grafo
        )
        validacoes = revalidar_apos_mudanca_composicao(p, nova)
        assert any(v.codigo == "VAL-SINERGIA-01" for v in validacoes)


# ── F5 — calibração atualiza CapacidadeElemento do gargalo ────────────────────


class TestCalibracaoF5:
    def test_atualiza_capacidade_do_gargalo_derivado(self):
        grafo = _grafo_escavacao(capacidade_escavadeira=100.0, capacidade_caminhao_unitario=30.0)
        p = _producao(grafo=grafo)  # gargalo derivado = ESCAV-38T (100 < 120)
        p2 = atualizar_capacidade_gargalo(p, nova_capacidade_horaria=110.0, fonte="medicao_obra")

        assert p2 is not p  # imutabilidade
        assert p.valor_horario == p2.valor_horario  # valor_horario não é tocado por F5
        cap_escav = next(c for c in p2.grafo_sinergia.capacidades if c.elemento_id == "ESCAV-38T")
        assert cap_escav.capacidade_horaria == 110.0
        assert cap_escav.fonte == "medicao_obra"

        d2 = derivar_producao_horaria(p2.grafo_sinergia, p2.composicao_padrao_equipe)
        assert d2.producao_horaria_derivada == 110.0

    def test_nao_altera_capacidade_de_elementos_que_nao_sao_gargalo(self):
        grafo = _grafo_escavacao(capacidade_escavadeira=100.0, capacidade_caminhao_unitario=30.0)
        p = _producao(grafo=grafo)
        p2 = atualizar_capacidade_gargalo(p, nova_capacidade_horaria=110.0)
        cap_cam = next(c for c in p2.grafo_sinergia.capacidades if c.elemento_id == "CAMINHAO-BASC")
        assert cap_cam.capacidade_horaria == 30.0

    def test_sem_grafo_levanta_erro(self):
        p = _producao(grafo=None)
        with pytest.raises(ValueError, match="sem GrafoSinergiaEquipe"):
            atualizar_capacidade_gargalo(p, nova_capacidade_horaria=50.0)

    def test_grafo_sem_capacidades_levanta_erro(self):
        p = _producao(grafo=GrafoSinergiaEquipe())
        with pytest.raises(ValueError, match="sem GrafoSinergiaEquipe"):
            atualizar_capacidade_gargalo(p, nova_capacidade_horaria=50.0)

    def test_capacidade_zero_ou_negativa_levanta_erro(self):
        """Copilot (PR #78): model_copy(update=...) não revalida em Pydantic v2 —
        Field(gt=0) de CapacidadeElemento.capacidade_horaria seria contornável sem
        validação explícita antes de construir a cópia."""
        grafo = _grafo_escavacao(capacidade_escavadeira=100.0, capacidade_caminhao_unitario=30.0)
        p = _producao(grafo=grafo)
        with pytest.raises(ValueError, match="finita e > 0"):
            atualizar_capacidade_gargalo(p, nova_capacidade_horaria=0.0)
        with pytest.raises(ValueError, match="finita e > 0"):
            atualizar_capacidade_gargalo(p, nova_capacidade_horaria=-5.0)

    def test_capacidade_infinita_ou_nan_levanta_erro(self):
        grafo = _grafo_escavacao(capacidade_escavadeira=100.0, capacidade_caminhao_unitario=30.0)
        p = _producao(grafo=grafo)
        with pytest.raises(ValueError, match="finita e > 0"):
            atualizar_capacidade_gargalo(p, nova_capacidade_horaria=float("inf"))
        with pytest.raises(ValueError, match="finita e > 0"):
            atualizar_capacidade_gargalo(p, nova_capacidade_horaria=float("nan"))
