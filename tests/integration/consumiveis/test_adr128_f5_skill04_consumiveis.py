"""ADR-128/139 F5 — Estoque de consumíveis no cronograma automático (skill-04), fim a fim.

Cobre a integração real (não isolada) do motor de estoque de consumíveis no pipeline
de skill-04 (`run_cronograma`), incluindo a config de projeto (`logistica_consumiveis`,
via `Escopo`/`gerir_escopo`) e o relatório causal (`VAL-ESTOQUE-DELAY-01/02`).

Cenários (mínimo necessário para provar a integração, não exaustivo):
  1. Zero regressão sem config nenhuma (nem catálogo, nem logistica_consumiveis).
  2. Zero regressão com disponibilidade só de catálogo (path ADR-128 já testado
     isoladamente — aqui, pela primeira vez, alcançável a partir do skill-04 real).
  3. Atraso causal feasible (logistica_consumiveis força um atraso reparável).
  4. Infeasibilidade por estoque (ERRO, sem crash).
  5. Round-trip Escopo.logistica_consumiveis via create_escopo/to_escopo — ver
     tests/integration/test_multi_escopo.py (plumbing testada ali, independente do
     scheduler).
"""

from __future__ import annotations

from datetime import date, timedelta

from concilium.application.skills import run_cronograma, run_escopo_e_eap

_INSUMO_DIESEL = "MA-DIESEL-TESTE"


def _catalogo(consumo_por_hora: float, disponibilidade: dict | None = None) -> dict:
    """Catálogo cru mínimo: 1 CPU -> 1 Producao consumindo diesel via a equipe padrão.

    ``disponibilidade`` (opcional) simula uma restrição declarada NO CATÁLOGO
    (ADR-128 clássico) — quando ``None``, o insumo fica irrestrito por catálogo e
    só uma config de projeto (``logistica_consumiveis``) pode restringi-lo (ADR-128 F5).
    """
    insumo: dict = {
        "codigo": _INSUMO_DIESEL,
        "tipo": "MATERIAL",
        "descricao": "Diesel de teste",
        "unidade": "l",
        "preco_unitario": 6.5,
        "fonte_preco": "cotacao_mercado",
        "origem_material": "AQUISICAO_EXTERNA",
    }
    if disponibilidade is not None:
        insumo["atributos_especificos"] = {"disponibilidade": disponibilidade}

    return {
        "cpus": [{"codigo": "CPU-01", "descricao": "CPU teste", "producao_id_ref": "PROD-01"}],
        "produtividades": [
            {
                "id": "PROD-01",
                "codigo": "PROD-01",
                "descricao": "Producao teste",
                "producao_horaria": 50.0,
                "unidade": "m3",
                "composicao_padrao_equipe": {
                    "equipamentos": [{"equip_id": "EQ-X", "num_unidades": 1}],
                    "materiais": [{"insumo_id": _INSUMO_DIESEL, "consumo_por_hora": consumo_por_hora}],
                },
            }
        ],
        "insumos": [insumo],
    }


def _canonical():
    inputs = {
        "nome": "Teste F5 Diesel",
        "tipo_obra": "terraplenagem",
        "localizacao": "Test, CE",
        "coordenadas": {"lat": -4.0, "lng": -38.0},
        "regime_trabalho": {"dias_semana": 5, "horas_dia": 8},
        "data_inicio": "2026-06-01",
        "data_termino": (date(2026, 6, 1) + timedelta(days=90)).isoformat(),
        "eap": [
            {
                "item_id": "eap-01",
                "ordem": 1,
                "cpu_id": "CPU-01",
                "descricao": "Item único",
                "unidade": "m3",
                "quantitativo": 1000.0,
            }
        ],
        "contexto_id": "test",
        "snapshot_catalogo_id": "snap-cat",
        "snapshot_perfil_id": "snap-perfil",
    }
    return run_escopo_e_eap(None, inputs, catalogo=None).canonical


_RCPSP_SPEC = {
    "activities": [
        {"item_id": "eap-01", "descricao": "Item único", "duration_weeks": 1, "required_resources": {"EQ-X": 1}},
    ],
    "resource_pool": {"EQ-X": 1},
    "precedence": [],
    "deadline_weeks": 8,
}


class TestZeroRegressao:
    def test_sem_config_nenhuma_nao_gera_validacoes_estoque(self):
        canonical = _canonical()
        catalogo = _catalogo(consumo_por_hora=1.0)  # sem disponibilidade de catálogo
        result = run_cronograma(canonical, {"rcpsp_spec": dict(_RCPSP_SPEC)}, catalogo=catalogo)

        assert result.canonical.cronograma is not None, [
            (v.codigo, v.status, v.mensagem) for v in result.validacoes
        ]
        assert not any(v.codigo.startswith("VAL-ESTOQUE") for v in result.validacoes)
        assert result.canonical.cronograma.estoque_delays == []
        # Sem restrição, a atividade roda na semana 0 (sem atraso nenhum).
        sched = {sa.activity_id: sa for sa in result.canonical.cronograma.scheduled_activities}
        assert sched["eap-01"].start_week == 0

    def test_catalogo_apenas_sem_logistica_consumiveis_e_alcancavel(self):
        """Path ADR-128 clássico (disponibilidade só de catálogo), agora alcançável
        pela primeira vez a partir do pipeline real de skill-04 — sem
        logistica_consumiveis, deve continuar funcionando igual ao motor isolado."""
        canonical = _canonical()
        catalogo = _catalogo(
            consumo_por_hora=1.0,
            disponibilidade={"estoque_inicial": 100000.0},  # estoque de catálogo, fartamente suficiente
        )
        result = run_cronograma(canonical, {"rcpsp_spec": dict(_RCPSP_SPEC)}, catalogo=catalogo)

        assert result.canonical.cronograma is not None, [
            (v.codigo, v.status, v.mensagem) for v in result.validacoes
        ]
        # Estoque de catálogo é suficiente — nenhum atraso, mas o path do motor foi
        # exercitado (replenishable_resources não era None).
        assert not any(v.codigo == "VAL-ESTOQUE-DELAY-02" for v in result.validacoes)
        sched = {sa.activity_id: sa for sa in result.canonical.cronograma.scheduled_activities}
        assert sched["eap-01"].start_week == 0


class TestAtrasoCausal:
    def test_logistica_consumiveis_forca_atraso_reparavel(self):
        """consumo_por_semana = 1.0 l/h × 40h = 40 l/sem; taxa_reabastecimento_max=10 l/sem,
        estoque_inicial=0 -> precisa esperar t=3 (10*4=40) para viabilizar — atraso
        reparável, cronograma permanece feasible."""
        canonical = _canonical()
        catalogo = _catalogo(consumo_por_hora=1.0)  # sem disponibilidade de catálogo
        inputs = {
            "rcpsp_spec": dict(_RCPSP_SPEC),
            "logistica_consumiveis": {_INSUMO_DIESEL: {"estoque_inicial": 0.0, "taxa_reabastecimento_max": 10.0}},
        }
        result = run_cronograma(canonical, inputs, catalogo=catalogo)

        assert result.canonical.cronograma is not None, [
            (v.codigo, v.status, v.mensagem) for v in result.validacoes
        ]
        assert result.canonical.cronograma.is_feasible is True

        aviso_codes = {v.codigo for v in result.validacoes if v.status == "AVISO"}
        assert "VAL-ESTOQUE-DELAY-01" in aviso_codes
        assert not any(v.codigo == "VAL-ESTOQUE-DELAY-02" for v in result.validacoes)

        delays = result.canonical.cronograma.estoque_delays
        assert len(delays) == 1
        assert delays[0].resource_id == _INSUMO_DIESEL
        assert delays[0].activity_id == "eap-01"
        assert delays[0].delay_weeks == 3

        sched = {sa.activity_id: sa for sa in result.canonical.cronograma.scheduled_activities}
        assert sched["eap-01"].start_week == 3


class TestInfeasibilidadePorEstoque:
    def test_estoque_irreparavel_reporta_erro_sem_crash(self):
        """Sem estoque inicial nem reabastecimento algum, o déficit nunca é reparável
        — deve reportar VAL-ESTOQUE-DELAY-02 (ERRO) e is_feasible=False, SEM levantar
        exceção (prova do branch não-raising em selector._explore_cpsat)."""
        canonical = _canonical()
        catalogo = _catalogo(consumo_por_hora=1.0)
        inputs = {
            "rcpsp_spec": dict(_RCPSP_SPEC),
            "logistica_consumiveis": {_INSUMO_DIESEL: {"estoque_inicial": 0.0, "taxa_reabastecimento_max": 0.0}},
        }
        # Não deve levantar RuntimeTechnicalError/ScheduleError.
        result = run_cronograma(canonical, inputs, catalogo=catalogo)

        erro_codes = {v.codigo for v in result.validacoes if v.status == "ERRO"}
        assert "VAL-ESTOQUE-DELAY-02" in erro_codes
