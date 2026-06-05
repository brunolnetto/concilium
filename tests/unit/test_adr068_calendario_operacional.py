from __future__ import annotations

from datetime import UTC, datetime

from concilium.application.runtime import Runtime
from concilium.application.skills import run_cronograma, run_escopo_e_eap
from concilium.domain.models.canonical import Cronograma, DistribuicaoSemanal, Praticabilidade, ScheduledActivityCanonical
from concilium.domain.services.backtracking_pe_builder import BacktrackingPEBuilder
from concilium.domain.services.diagnostico_pe_builder import DiagnosticoPEBuilder
from concilium.infrastructure.adapters.excel_adapter import ExcelRenderer


def _build_minimal_canonical():
    canonical = run_escopo_e_eap(
        None,
        {
            "nome": "ADR068",
            "tipo_obra": "terraplenagem",
            "localizacao": "Fortaleza",
            "coordenadas": {"lat": -3.73, "lng": -38.52},
            "regime_trabalho": {"dias_semana": 5, "horas_dia": 8},
            "data_inicio": "2026-06-01",
            "data_termino": "2026-06-30",
            "eap": [
                {
                    "item_id": "eap-01",
                    "ordem": 1,
                    "cpu_id": "CPU-01",
                    "descricao": "Escavacao",
                    "unidade": "m3",
                    "quantitativo": 200.0,
                }
            ],
            "contexto_id": "test",
            "snapshot_catalogo_id": "s-cat",
            "snapshot_perfil_id": "s-perf",
        },
        catalogo=None,
    ).canonical
    return canonical


def test_f1_runtime_carrega_calendario_com_precedencia(tmp_path):
    cfg = tmp_path / "config"
    (cfg / "calendarios" / "jurisdicao").mkdir(parents=True)
    (cfg / "calendarios" / "projeto").mkdir(parents=True)

    (cfg / "calendarios" / "global.json").write_text(
        '{"versao":"1","eventos":[{"id":"fer-01","nome":"Global","tipo":"feriado","escopo":"global","jurisdicao_id":null,"inicio":"2026-06-03","fim":"2026-06-03","recorrencia":"anual","fator_operacao":0.0}]}',
        encoding="utf-8",
    )
    (cfg / "calendarios" / "jurisdicao" / "BR-CE.json").write_text(
        '{"versao":"1","eventos":[{"id":"fer-01","nome":"CE","tipo":"feriado","escopo":"jurisdicao","jurisdicao_id":"BR-CE","inicio":"2026-06-03","fim":"2026-06-03","recorrencia":"anual","fator_operacao":0.5}]}',
        encoding="utf-8",
    )
    (cfg / "calendarios" / "projeto" / "proj-1.json").write_text(
        '{"versao":"1","eventos":[{"id":"fer-01","nome":"Projeto","tipo":"feriado","escopo":"projeto","jurisdicao_id":null,"inicio":"2026-06-03","fim":"2026-06-03","recorrencia":"anual","fator_operacao":1.0}]}',
        encoding="utf-8",
    )

    rt = Runtime(cfg)
    cal = rt.load_calendario_operacional("BR-CE", "proj-1")

    assert cal["eventos"], "Calendario deve carregar eventos"
    evento = {e["id"]: e for e in cal["eventos"]}["fer-01"]
    assert evento["fator_operacao"] == 1.0
    assert evento["escopo"] == "projeto"


def test_f2_f3_cronograma_aplica_fator_calendario_e_total():
    canonical = _build_minimal_canonical()
    canonical = canonical.model_copy(
        update={
            "praticabilidade": Praticabilidade(
                fonte="teste",
                limiar_inviabilidade_mm=20.0,
                calculada_em=datetime.now(UTC),
                percentual_produtivo_semanal={"2026-W23": 0.8},
                percentual_produtivo_mensal={},
            )
        }
    )

    result = run_cronograma(
        canonical,
        {
            "num_equipes_por_item": {"eap-01": {"2026-W23": 1}},
            "calendario_operacional": {
                "versao": "1",
                "eventos": [
                    {
                        "id": "fer-1",
                        "nome": "Feriado",
                        "tipo": "feriado",
                        "escopo": "global",
                        "jurisdicao_id": None,
                        "inicio": "2026-06-03",
                        "fim": "2026-06-03",
                        "recorrencia": "anual",
                        "fator_operacao": 0.0,
                    }
                ],
            },
        },
        catalogo={"cpus": [{"codigo": "CPU-01", "producao_horaria": 10.0}]},
    )

    out = result.canonical
    dist = out.cronograma.scheduled_activities[0].distribuicao_semanal["2026-W23"]

    assert out.fator_calendario_semanal["2026-W23"] < 1.0
    assert out.calendario_operacional, "Artefato semanal de calendario deve existir"
    assert dist.fator_clima == 0.8
    assert dist.fator_calendario < 1.0
    # ADR-082: eficiencia = utilização (m_ij); o produto clima×calendário é o fator_total
    # (η_j = praticabilidade × utilização). Semana não-parcial → utilização = 1.0.
    assert dist.eficiencia == 1.0
    assert abs(dist.fator_total - (dist.fator_clima * dist.fator_calendario)) < 1e-6


def test_f4_f5_diagnostico_e_backtracking_com_calendario():
    canonical = _build_minimal_canonical()
    dist = {
        "2026-W23": DistribuicaoSemanal(
            num_equipes=3,
            qtd_executada=50.0,
            qtd_acumulada=50.0,
            pct=0.25,
            eficiencia=0.4,
            fator_clima=0.8,
            fator_calendario=0.5,
            fator_total=0.4,
        ),
        "2026-W24": DistribuicaoSemanal(
            num_equipes=3,
            qtd_executada=50.0,
            qtd_acumulada=100.0,
            pct=0.5,
            eficiencia=0.9,
            fator_clima=0.9,
            fator_calendario=1.0,
            fator_total=0.9,
        ),
    }

    canonical = canonical.model_copy(
        update={
            "cronograma": Cronograma(
                algorithm="manual_allocation",
                quality_score=1.0,
                makespan_weeks=2,
                is_feasible=True,
                scheduled_activities=[
                    ScheduledActivityCanonical(
                        activity_id="eap-01",
                        start_week=0,
                        end_week=1,
                        duration_weeks=2,
                        distribuicao_semanal=dist,
                    )
                ],
            )
        }
    )

    from concilium.domain.models.canonical import EquipamentoEquipeDireta, EquipeDireta, FuncaoEquipeDireta, PontoEquilibrio

    canonical = canonical.model_copy(
        update={
            "equipes_diretas": [
                EquipeDireta(
                    equipe_id="eq1",
                    item_id="eap-01",
                    cpu_id="CPU-01",
                    funcoes=[FuncaoEquipeDireta(funcao_id="f1", num_pessoas=1, custo_mensal_unitario=10000)],
                    equipamentos=[EquipamentoEquipeDireta(equip_id="eqp1", num_unidades=1, custo_mensal=20000)],
                    custo_mao_obra_mensal=10000,
                    custo_equipamentos_mensal=20000,
                    custo_total=60000,
                )
            ],
            "ponto_equilibrio": [
                PontoEquilibrio(
                    item_id="eap-01",
                    custo_fixo_equipe=60000,
                    custo_venda_cpu=50000,
                    delta=-10000,
                    delta_pct=-0.2,
                    status_validacao="AVISO",
                    custo_operacional_real=60000,
                )
            ],
        }
    )

    diag = DiagnosticoPEBuilder().build(canonical)
    assert diag.itens_deficit
    item = diag.itens_deficit[0]
    codigos = {f.codigo for f in item.fatores}
    assert any(c.startswith("F_CALENDARIO") for c in codigos)

    back = BacktrackingPEBuilder().build(diag, canonical)
    assert back.itens
    params = {s.parametro for s in back.itens[0].solucoes}
    # F_CALENDARIO_ESTRUTURAL = structural deficit; backtracking offers P/N/L solutions
    # T0_CALENDARIO only appears when timing-avoidable F_CALENDARIO is present
    assert params, "Backtracking deve produzir pelo menos uma solucao"


def test_f7_excel_renderiza_aba_calendario_operacional():
    canonical = _build_minimal_canonical().model_copy(
        update={
            "fator_calendario_semanal": {"2026-W23": 0.8},
            "calendario_operacional": [
                {
                    "semana_iso": "2026-W23",
                    "dias_uteis_base": 5,
                    "dias_uteis_efetivos": 4,
                    "fator_calendario": 0.8,
                    "eventos_aplicados": ["fer-1"],
                }
            ],
        }
    )
    wb = ExcelRenderer(canonical).render()
    assert "CALENDARIO.OP" in wb.sheetnames
