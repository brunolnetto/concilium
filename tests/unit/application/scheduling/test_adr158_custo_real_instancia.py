"""ADR-158 D2 — custo_real_instancia_semanal: TDD.

Combina project_ocupacao_semanal (ADR-152, status prod/idle/off por instância) com
taxas médias reais de MO/EQ (ADR-156/157), seguindo a mesma assimetria prod/idle do
LifecycleEngine (ADR-085/106): MO integral em ambos; EQ reduzido (só locação) em
idle. Sem atribuição de indivíduo/ativo a slot — pool permanece fungível.

Escrito antes da implementação (red phase).
"""

from __future__ import annotations

from concilium.application.scheduling.custo_real_instancia import custo_real_instancia_semanal
from concilium.domain.models.canonical import InstanciaRecurso, SegmentoAtividade


def _instancia(numero: int = 1, **overrides) -> InstanciaRecurso:
    defaults = dict(
        instancia_id=f"ESC-3CAT-{numero:02d}",
        contrato_id="contrato-esc-3cat",
        tipo_id="ESC-3CAT",
        numero=numero,
        semana_entrada="2026-W01",
        semana_saida="2026-W04",
    )
    defaults.update(overrides)
    return InstanciaRecurso(**defaults)


class TestCustoRealInstanciaSemanal:
    def test_semana_prod_usa_taxa_ativa_cheia(self):
        instancia = _instancia(
            segmentos_atividade=[
                SegmentoAtividade(activity_id="eap-1", semana_inicio="2026-W01", semana_fim="2026-W01")
            ],
        )
        custo = custo_real_instancia_semanal(instancia, cus_mo_real=600.0, cus_eq_real=300.0, cus_eq_idle_real=200.0)
        assert custo["2026-W01"] == 900.0

    def test_semana_idle_usa_mo_integral_e_eq_reduzido(self):
        instancia = _instancia(
            segmentos_atividade=[
                SegmentoAtividade(activity_id="eap-1", semana_inicio="2026-W01", semana_fim="2026-W01")
            ],
            segmentos_idle=[
                SegmentoAtividade(activity_id="__idle__", semana_inicio="2026-W02", semana_fim="2026-W02")
            ],
        )
        custo = custo_real_instancia_semanal(instancia, cus_mo_real=600.0, cus_eq_real=300.0, cus_eq_idle_real=200.0)
        assert custo["2026-W02"] == 800.0  # 600 (MO integral) + 200 (EQ reduzido)

    def test_semana_off_e_zero(self):
        instancia = _instancia(
            segmentos_atividade=[
                SegmentoAtividade(activity_id="eap-1", semana_inicio="2026-W01", semana_fim="2026-W01")
            ],
        )
        custo = custo_real_instancia_semanal(instancia, cus_mo_real=600.0, cus_eq_real=300.0, cus_eq_idle_real=200.0)
        # span W01-W04, só W01 tem segmento -> W02/W03/W04 são "off" (sem segmentos_idle aqui)
        assert custo["2026-W03"] == 0.0
        assert custo["2026-W04"] == 0.0

    def test_soma_de_instancias_bate_com_taxa_esperada_por_semana(self):
        # 2 instâncias do mesmo contrato, uma prod outra idle na mesma semana ->
        # soma deve bater com quantidade_contratada (2) × mistura esperada.
        inst1 = _instancia(
            numero=1,
            segmentos_atividade=[
                SegmentoAtividade(activity_id="eap-1", semana_inicio="2026-W01", semana_fim="2026-W01")
            ],
        )
        inst2 = _instancia(
            numero=2,
            segmentos_idle=[
                SegmentoAtividade(activity_id="__idle__", semana_inicio="2026-W01", semana_fim="2026-W01")
            ],
        )
        c1 = custo_real_instancia_semanal(inst1, cus_mo_real=600.0, cus_eq_real=300.0, cus_eq_idle_real=200.0)
        c2 = custo_real_instancia_semanal(inst2, cus_mo_real=600.0, cus_eq_real=300.0, cus_eq_idle_real=200.0)
        total_semana1 = c1["2026-W01"] + c2["2026-W01"]
        # prod (900) + idle (800) = 1700
        assert total_semana1 == 1700.0

    def test_sem_span_de_contrato_retorna_vazio(self):
        instancia = _instancia(semana_entrada="", semana_saida="")
        custo = custo_real_instancia_semanal(instancia, cus_mo_real=600.0, cus_eq_real=300.0, cus_eq_idle_real=200.0)
        assert custo == {}
