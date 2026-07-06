"""Tests for the three activity systematics.

1. Activity as week-partitioned crew-composed interval  (AtividadeIntervalo)
2. Crew role classification on CPU  (PapelFuncao / FuncaoEquipe.papel)
3. Productivity tuning by crew/equipment composition  (Producao.fator_producao)
"""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from concilium.domain.models.canonical import (
    AtividadeIntervalo,
    DistribuicaoSemanal,
    ScheduledActivityCanonical,
)
from concilium.domain.models.catalog.catalogo import (
    ComposicaoPadraoEquipe,
    EquipamentoEquipe,
    FuncaoEquipe,
    PapelFuncao,
)
from concilium.domain.models.catalog.producao import (
    AuditoriaProducao,
    CondicoesCalibração,
    LimiteProducao,
    OrigemProducao,
    Producao,
    QualidadeProducao,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_composicao(
    equip_id: str = "ESCAV-HID-38T",
    num_equips: int = 1,
    funcao_id: str = "OPER-ESCAV",
    num_pessoas: int = 1,
    papel: PapelFuncao = "direto",
) -> ComposicaoPadraoEquipe:
    return ComposicaoPadraoEquipe(
        funcoes=[FuncaoEquipe(funcao_id=funcao_id, num_pessoas=num_pessoas, papel=papel)],
        equipamentos=[EquipamentoEquipe(equip_id=equip_id, num_unidades=num_equips)],
    )


def _make_producao(
    valor_horario: float = 234.0,
    limite: LimiteProducao = "equipamento",
    composicao: ComposicaoPadraoEquipe | None = None,
) -> Producao:
    if composicao is None:
        composicao = _make_composicao()
    agora = datetime.now()
    return Producao(
        id="PROD-001",
        codigo="ESCO-CARGA-1CAT",
        descricao="Escavação carga 1ª categoria",
        valor_horario=valor_horario,
        unidade="m3",
        limite_producao=limite,
        origem=OrigemProducao(
            tipo="tabela_referencia",
            fonte_id="SICRO-2024-CE",
            data_calibracao=agora,
            referencia="DNIT/SICRO",
        ),
        condicoes_calibracao=CondicoesCalibração(),
        qualidade=QualidadeProducao(
            confianca_pct=90,
            intervalo_confianca=(220.0, 248.0),
            quantidade_amostras=5,
            desvio_padrao=7.0,
        ),
        composicao_padrao_equipe=composicao,
        auditoria=AuditoriaProducao(
            criado_por="test",
            data_criacao=agora,
            ultima_modificacao=agora,
            modificado_por="test",
            versao="1.0",
        ),
    )


def _make_scheduled_activity(
    activity_id: str = "eap-01",
    semanas: dict[str, tuple[int, float, float, float]] | None = None,
) -> ScheduledActivityCanonical:
    """Cria um ScheduledActivityCanonical simples para testes.

    semanas: {semana_iso: (num_equipes, qtd_executada, qtd_acumulada, pct)}
    """
    if semanas is None:
        semanas = {
            "2026-W01": (2, 100.0, 100.0, 0.33),
            "2026-W02": (2, 100.0, 200.0, 0.67),
            "2026-W03": (1, 100.0, 300.0, 1.00),
        }
    distribuicao = {
        iso: DistribuicaoSemanal(
            num_equipes=ne,
            qtd_executada=qe,
            qtd_acumulada=qa,
            pct=pct,
        )
        for iso, (ne, qe, qa, pct) in semanas.items()
    }
    return ScheduledActivityCanonical(
        activity_id=activity_id,
        start_week=1,
        end_week=3,
        duration_weeks=3,
        distribuicao_semanal=distribuicao,
    )


# ── 1. AtividadeIntervalo (week-partitioned crew-composed interval) ───────────


class TestAtividadeIntervalo:
    def test_construcao_basica(self):
        iv = AtividadeIntervalo(
            atividade_id="eap-01",
            semana_iso="2026-W23",
            num_equipes=2,
            qtd_planejada=480.0,
            qtd_acumulada=480.0,
            eficiencia=0.9,
            pct_completude=0.5,
        )
        assert iv.atividade_id == "eap-01"
        assert iv.semana_iso == "2026-W23"
        assert iv.num_equipes == 2
        assert iv.eficiencia == 0.9

    def test_formato_semana_iso_valido(self):
        # Aceita formato AAAA-Www
        iv = AtividadeIntervalo(
            atividade_id="a",
            semana_iso="2026-W01",
            num_equipes=1,
            qtd_planejada=100.0,
            qtd_acumulada=100.0,
        )
        assert iv.semana_iso == "2026-W01"

    def test_formato_semana_iso_invalido(self):
        with pytest.raises(ValidationError):
            AtividadeIntervalo(
                atividade_id="a",
                semana_iso="2026-23",  # formato incorreto
                num_equipes=1,
                qtd_planejada=100.0,
                qtd_acumulada=100.0,
            )

    def test_eficiencia_default_1(self):
        iv = AtividadeIntervalo(
            atividade_id="a",
            semana_iso="2026-W05",
            num_equipes=1,
            qtd_planejada=100.0,
            qtd_acumulada=100.0,
        )
        assert iv.eficiencia == 1.0

    def test_from_scheduled_activity_gera_um_intervalo_por_semana(self):
        sa = _make_scheduled_activity()
        intervalos = AtividadeIntervalo.from_scheduled_activity(sa)
        assert len(intervalos) == 3
        assert all(iv.atividade_id == "eap-01" for iv in intervalos)

    def test_from_scheduled_activity_preserva_semana_iso(self):
        sa = _make_scheduled_activity()
        intervalos = AtividadeIntervalo.from_scheduled_activity(sa)
        semanas = {iv.semana_iso for iv in intervalos}
        assert semanas == {"2026-W01", "2026-W02", "2026-W03"}

    def test_from_scheduled_activity_preserva_num_equipes(self):
        sa = _make_scheduled_activity()
        intervalos = sorted(AtividadeIntervalo.from_scheduled_activity(sa), key=lambda x: x.semana_iso)
        assert intervalos[0].num_equipes == 2  # W01
        assert intervalos[1].num_equipes == 2  # W02
        assert intervalos[2].num_equipes == 1  # W03

    def test_from_scheduled_activity_soma_quantidades_correto(self):
        """Invariante: soma de qtd_planejada == quantitativo_atividade."""
        sa = _make_scheduled_activity()
        intervalos = AtividadeIntervalo.from_scheduled_activity(sa)
        total = sum(iv.qtd_planejada for iv in intervalos)
        assert abs(total - 300.0) < 0.01

    def test_from_scheduled_activity_sem_distribuicao_retorna_vazio(self):
        sa = ScheduledActivityCanonical(
            activity_id="eap-x",
            start_week=1,
            end_week=1,
            duration_weeks=1,
        )
        assert AtividadeIntervalo.from_scheduled_activity(sa) == []

    def test_eficiencia_baixa_nao_afeta_qtd_planejada(self):
        """Eficiência escala productividade mas não o número de intervalos."""
        sa = _make_scheduled_activity(semanas={"2026-W10": (1, 50.0, 50.0, 0.5)})
        sa.distribuicao_semanal["2026-W10"].eficiencia = 0.7
        intervalos = AtividadeIntervalo.from_scheduled_activity(sa)
        assert len(intervalos) == 1
        assert intervalos[0].eficiencia == 0.7
        assert intervalos[0].qtd_planejada == 50.0  # qtd não é ajustada pelo intervalo


# ── 2. PapelFuncao / crew role classification ─────────────────────────────────


class TestPapelFuncao:
    def test_papel_default_direto(self):
        f = FuncaoEquipe(funcao_id="OPER-ESCAV", num_pessoas=1)
        assert f.papel == "direto"

    def test_papel_indireto_explícito(self):
        f = FuncaoEquipe(funcao_id="TEC-SEG", num_pessoas=1, papel="indireto")
        assert f.papel == "indireto"

    def test_papel_gestao_explicito(self):
        f = FuncaoEquipe(funcao_id="COORD-OBRA", num_pessoas=1, papel="gestao")
        assert f.papel == "gestao"

    def test_papel_invalido_rejeitado(self):
        with pytest.raises(ValidationError):
            FuncaoEquipe(funcao_id="X", num_pessoas=1, papel="supervisor")

    def test_composicao_filtra_funcoes_diretas(self):
        comp = ComposicaoPadraoEquipe(
            funcoes=[
                FuncaoEquipe(funcao_id="OPER-ESCAV", num_pessoas=1, papel="direto"),
                FuncaoEquipe(funcao_id="TEC-SEG", num_pessoas=1, papel="indireto"),
                FuncaoEquipe(funcao_id="COORD-OBRA", num_pessoas=1, papel="gestao"),
            ],
            equipamentos=[],
        )
        assert len(comp.funcoes_diretas) == 1
        assert comp.funcoes_diretas[0].funcao_id == "OPER-ESCAV"

    def test_composicao_filtra_funcoes_indiretas(self):
        comp = ComposicaoPadraoEquipe(
            funcoes=[
                FuncaoEquipe(funcao_id="OPER-ESCAV", num_pessoas=1, papel="direto"),
                FuncaoEquipe(funcao_id="TEC-SEG", num_pessoas=1, papel="indireto"),
                FuncaoEquipe(funcao_id="INSP-CAMPO", num_pessoas=2, papel="indireto"),
            ],
            equipamentos=[],
        )
        assert len(comp.funcoes_indiretas) == 2

    def test_composicao_filtra_funcoes_gestao(self):
        comp = ComposicaoPadraoEquipe(
            funcoes=[
                FuncaoEquipe(funcao_id="OPER-ESCAV", num_pessoas=1, papel="direto"),
                FuncaoEquipe(funcao_id="COORD-OBRA", num_pessoas=1, papel="gestao"),
            ],
            equipamentos=[],
        )
        assert len(comp.funcoes_gestao) == 1

    def test_num_pessoas_diretas(self):
        comp = ComposicaoPadraoEquipe(
            funcoes=[
                FuncaoEquipe(funcao_id="OPER", num_pessoas=1, papel="direto"),
                FuncaoEquipe(funcao_id="MOTOR", num_pessoas=7, papel="direto"),
                FuncaoEquipe(funcao_id="ENCARREG", num_pessoas=1, papel="indireto"),
            ],
            equipamentos=[],
        )
        assert comp.num_pessoas_diretas == 8  # só diretos

    def test_num_pessoas_total(self):
        comp = ComposicaoPadraoEquipe(
            funcoes=[
                FuncaoEquipe(funcao_id="OPER", num_pessoas=1, papel="direto"),
                FuncaoEquipe(funcao_id="MOTOR", num_pessoas=7, papel="direto"),
                FuncaoEquipe(funcao_id="ENCARREG", num_pessoas=1, papel="indireto"),
            ],
            equipamentos=[],
        )
        assert comp.num_pessoas_total == 9  # todos

    def test_composicao_sem_classificacao_tudo_direto(self):
        """Retrocompatibilidade: JSON antigo sem campo papel → tudo direto."""
        comp = ComposicaoPadraoEquipe(
            funcoes=[
                FuncaoEquipe(funcao_id="OPER-ESCAV", num_pessoas=1),
                FuncaoEquipe(funcao_id="MOTOR-CAM-BASC", num_pessoas=7),
                FuncaoEquipe(funcao_id="ENCARREG-TERRA", num_pessoas=1),
            ],
            equipamentos=[],
        )
        # Sem papel → default "direto" para todos
        assert len(comp.funcoes_diretas) == 3
        assert len(comp.funcoes_indiretas) == 0
        assert comp.num_pessoas_diretas == 9

    def test_papel_separacao_custo_direto_vs_indireto(self):
        """Verificação do invariante de custo: direto != indireto != gestao."""
        comp = ComposicaoPadraoEquipe(
            funcoes=[
                FuncaoEquipe(funcao_id="OPER", num_pessoas=2, papel="direto"),
                FuncaoEquipe(funcao_id="SEG", num_pessoas=1, papel="indireto"),
                FuncaoEquipe(funcao_id="COORD", num_pessoas=1, papel="gestao"),
            ],
            equipamentos=[],
        )
        total_contavel = comp.num_pessoas_diretas
        total_indireto = sum(f.num_pessoas for f in comp.funcoes_indiretas)
        total_gestao = sum(f.num_pessoas for f in comp.funcoes_gestao)
        assert total_contavel + total_indireto + total_gestao == comp.num_pessoas_total


# ── 3. Producao.fator_producao / productivity tuning ──────────────────────────


class TestFatorProducao:
    def test_mesma_composicao_fator_1(self):
        prod = _make_producao()
        fator = prod.fator_producao(prod.composicao_padrao_equipe)
        assert fator == 1.0

    def test_dobra_equipamento_principal_fator_2(self):
        calib = _make_composicao(num_equips=1)
        prod = _make_producao(composicao=calib)
        nova = _make_composicao(num_equips=2)
        assert prod.fator_producao(nova) == 2.0

    def test_metade_equipamento_fator_0_5(self):
        calib = _make_composicao(num_equips=4)
        prod = _make_producao(composicao=calib)
        nova = _make_composicao(num_equips=2)
        assert abs(prod.fator_producao(nova) - 0.5) < 1e-6

    def test_limite_mao_obra_dobra_equipe(self):
        calib = ComposicaoPadraoEquipe(
            funcoes=[
                FuncaoEquipe(funcao_id="OPER", num_pessoas=2),
                FuncaoEquipe(funcao_id="AJUD", num_pessoas=4),
            ],
            equipamentos=[],
        )
        prod = _make_producao(limite="mao_obra", composicao=calib)
        nova = ComposicaoPadraoEquipe(
            funcoes=[
                FuncaoEquipe(funcao_id="OPER", num_pessoas=4),
                FuncaoEquipe(funcao_id="AJUD", num_pessoas=8),
            ],
            equipamentos=[],
        )
        assert abs(prod.fator_producao(nova) - 2.0) < 1e-6

    def test_limite_mao_obra_mesma_equipe_fator_1(self):
        calib = ComposicaoPadraoEquipe(
            funcoes=[FuncaoEquipe(funcao_id="OPER", num_pessoas=3)],
            equipamentos=[],
        )
        prod = _make_producao(limite="mao_obra", composicao=calib)
        assert prod.fator_producao(calib) == 1.0

    def test_equipamento_ausente_na_nova_retorna_1(self):
        """Equipamento principal não encontrado na nova composição → fator 1 (safe fallback)."""
        calib = _make_composicao(equip_id="ESCAV-HID-38T", num_equips=1)
        prod = _make_producao(composicao=calib)
        nova = ComposicaoPadraoEquipe(
            funcoes=[FuncaoEquipe(funcao_id="OPER", num_pessoas=1)],
            equipamentos=[EquipamentoEquipe(equip_id="OUTRO-EQUIP", num_unidades=1)],
        )
        assert prod.fator_producao(nova) == 1.0

    def test_producao_ajustada_escala_valor_horario(self):
        prod = _make_producao(valor_horario=200.0)
        nova = _make_composicao(num_equips=3)
        ajustada = prod.producao_ajustada(nova)
        assert abs(ajustada - 200.0 * 3.0) < 0.01

    def test_fator_producao_sem_equipamentos_retorna_1(self):
        """ComposicaoPadraoEquipe sem equipamentos (atividade manual) → fator 1."""
        calib = ComposicaoPadraoEquipe(
            funcoes=[FuncaoEquipe(funcao_id="OPER", num_pessoas=1)],
            equipamentos=[],
        )
        prod = _make_producao(composicao=calib, limite="equipamento")
        nova = calib.model_copy()
        assert prod.fator_producao(nova) == 1.0

    def test_limite_producao_default_equipamento(self):
        prod = _make_producao()
        assert prod.limite_producao == "equipamento"

    def test_limite_producao_mao_obra_explicito(self):
        prod = _make_producao(limite="mao_obra")
        assert prod.limite_producao == "mao_obra"

    def test_fator_fracionario_arredondado(self):
        """Fator com decimais é arredondado em 6 casas."""
        calib = _make_composicao(num_equips=3)
        prod = _make_producao(composicao=calib)
        nova = _make_composicao(num_equips=2)
        fator = prod.fator_producao(nova)
        # 2/3 = 0.666667
        assert abs(fator - round(2 / 3, 6)) < 1e-9

    def test_fator_by_equipamento_multiple_entries_same_principal_id(self):
        """Two EquipamentoEquipe entries in the calib composition share the
        principal equip_id: exercises the `for e in equips_calib` loop
        back-edge (both entries are summed into qtd_calib)."""
        calib = ComposicaoPadraoEquipe(
            funcoes=[FuncaoEquipe(funcao_id="OPER", num_pessoas=1)],
            equipamentos=[
                EquipamentoEquipe(equip_id="ESCAV-HID-38T", num_unidades=1),
                EquipamentoEquipe(equip_id="ESCAV-HID-38T", num_unidades=2),
            ],
        )
        prod = _make_producao(composicao=calib)
        nova = ComposicaoPadraoEquipe(
            funcoes=[FuncaoEquipe(funcao_id="OPER", num_pessoas=1)],
            equipamentos=[
                EquipamentoEquipe(equip_id="ESCAV-HID-38T", num_unidades=3),
                EquipamentoEquipe(equip_id="ESCAV-HID-38T", num_unidades=3),
            ],
        )
        # qtd_calib = 1+2 = 3, qtd_nova = 3+3 = 6 -> fator = 2.0
        assert prod.fator_producao(nova) == 2.0

    def test_fator_by_equipamento_calib_has_secondary_equipment_ignored(self):
        """A calib entry with an equip_id different from the principal one is
        skipped (covers the `if e.equip_id == equip_principal_id` false arc)."""
        calib = ComposicaoPadraoEquipe(
            funcoes=[FuncaoEquipe(funcao_id="OPER", num_pessoas=1)],
            equipamentos=[
                EquipamentoEquipe(equip_id="ESCAV-HID-38T", num_unidades=2),
                EquipamentoEquipe(equip_id="CAMINHAO-BASCULANTE", num_unidades=5),
            ],
        )
        prod = _make_producao(composicao=calib)
        nova = _make_composicao(equip_id="ESCAV-HID-38T", num_equips=4)
        # Only the principal (ESCAV-HID-38T) equip_id counts: qtd_calib=2, qtd_nova=4 -> fator=2.0
        assert prod.fator_producao(nova) == 2.0

    def test_fator_by_mao_obra_zero_nova_returns_1(self):
        """total_nova == 0 (funcoes vazias na nova composição) → fator 1
        safe-fallback (covers the `total_nova == 0` branch of the `or`)."""
        calib = ComposicaoPadraoEquipe(
            funcoes=[FuncaoEquipe(funcao_id="OPER", num_pessoas=3)],
            equipamentos=[],
        )
        prod = _make_producao(limite="mao_obra", composicao=calib)
        nova = ComposicaoPadraoEquipe(funcoes=[], equipamentos=[])
        assert prod.fator_producao(nova) == 1.0
