from __future__ import annotations

import sys
from datetime import UTC, datetime

from concilium.application.runtime import Runtime
from concilium.application.skills import run_cronograma, run_escopo_e_eap
from concilium.domain.models.canonical import (
    Cronograma,
    DistribuicaoSemanal,
    Praticabilidade,
    ScheduledActivityCanonical,
)
from concilium.domain.services.analytics.backtracking_pe_builder import BacktrackingPEBuilder
from concilium.domain.services.analytics.diagnostico_pe_builder import DiagnosticoPEBuilder
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
    # ADR-082: eficiencia = utilização = qtd_executada / capacidade_real.
    # Para tarefa pequena vs. capacidade grande, utilização é baixa mas positiva.
    assert 0.0 < dist.eficiencia <= 1.0
    # fator_total = eta_s × eta_p × eta_w ≤ fator_clima × fator_calendario
    assert dist.fator_total <= dist.fator_clima * dist.fator_calendario + 1e-6


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

    from concilium.domain.models.canonical import (
        EquipamentoEquipeDireta,
        EquipeDireta,
        FuncaoEquipeDireta,
        PontoEquilibrio,
    )

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


def test_extract_edge_thresholds_com_multiplos_predecessores_tipados_mistos():
    """ADR-081/NEP-031: um item com 2+ predecessores tipados na mesma lista
    (FF seguido de FS) exercita o laço interno de `_extract_edge_thresholds_from_eap`
    continuando para o próximo predecessor após tratar um tipo FF — cobre o caminho
    AUTO_SCHEDULE via canônico (sem rcpsp_spec), que deriva o DAG diretamente da EAP
    (fallback ``_extract_activities`` de item_id — por isso o canônico é construído
    diretamente, sem ``atividades`` explícitas, que tomariam precedência)."""
    from datetime import UTC, datetime

    from concilium.domain.models.canonical import (
        CanonicalModel,
        Coordenadas,
        EapItem,
        Meta,
        PrecedenciaItem,
        Projeto,
        RegimeTrabalho,
    )

    meta = Meta(gerado_em=datetime.now(UTC), contexto_id="test")
    projeto = Projeto(
        id="proj-multi-pred",
        nome="ADR068-multi-pred",
        tipo_obra="terraplenagem",
        localizacao="Fortaleza",
        coordenadas=Coordenadas(lat=-3.73, lng=-38.52),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio="2026-06-01",
        data_termino="2026-09-30",
        snapshot_catalogo_id="s-cat",
        snapshot_perfil_id="s-perf",
    )
    eap = [
        EapItem(item_id="eap-01", ordem=1, cpu_id="CPU-01", descricao="Desmatamento", unidade="m2", quantitativo=100.0),
        EapItem(item_id="eap-02", ordem=2, cpu_id="CPU-02", descricao="Escavacao", unidade="m3", quantitativo=100.0),
        EapItem(
            item_id="eap-03",
            ordem=3,
            cpu_id="CPU-03",
            descricao="Compactacao",
            unidade="m3",
            quantitativo=100.0,
            predecessores=[
                PrecedenciaItem(item_id="eap-01", tipo="FF", lag=0),
                PrecedenciaItem(item_id="eap-02", tipo="FS", lag=0),
            ],
        ),
    ]
    canonical = CanonicalModel(meta=meta, projeto=projeto, eap=eap)

    # AUTO_SCHEDULE via canônico puro (sem rcpsp_spec, sem num_equipes_por_item) —
    # exercita _rasfc_extract_from_canonical -> _extract_dag -> _extract_edge_thresholds_from_eap.
    result = run_cronograma(canonical, {})

    assert not any(v.status == "ERRO" for v in result.validacoes)
    assert result.canonical.cronograma is not None
    scheduled_ids = {sa.activity_id for sa in result.canonical.cronograma.scheduled_activities}
    assert scheduled_ids == {"eap-01", "eap-02", "eap-03"}


def test_extract_edge_thresholds_com_atividades_auto_derivadas_ff_ss_nao_lanca_keyerror():
    """Regressão: quando `canonical.atividades` está populado (caminho normal
    `run_escopo_e_eap` -> `run_cronograma`, sem `rcpsp_spec`), `_extract_activities`
    usa `atividade_id` (sufixo "-atv-1") como activity_id em vez do `item_id` puro.
    Antes do mapeamento item_id -> activity_id em `_extract_edge_thresholds_from_eap`,
    uma precedência FF/SS na EAP gerava uma `ExtendedPrecedence` chaveada por item_id,
    que `_add_extended_precedence_constraints` indexava direto em `starts`/`ends`
    (chaveados por activity_id) sem guarda — `KeyError` no meio do solve do CP-SAT.
    FS clássico não lançava, mas era descartado em silêncio pela guarda equivalente
    em `_add_fs_precedence_constraints` — precedência nunca era realmente aplicada."""
    inputs = {
        "nome": "ADR068-atividades-ff-ss",
        "tipo_obra": "terraplenagem",
        "localizacao": "Fortaleza",
        "coordenadas": {"lat": -3.73, "lng": -38.52},
        "regime_trabalho": {"dias_semana": 5, "horas_dia": 8},
        "data_inicio": "2026-06-01",
        "data_termino": "2026-09-30",
        "eap": [
            {
                "item_id": "eap-01",
                "ordem": 1,
                "cpu_id": "CPU-01",
                "descricao": "Item 1",
                "unidade": "m3",
                "quantitativo": 100.0,
            },
            {
                "item_id": "eap-02",
                "ordem": 2,
                "cpu_id": "CPU-01",
                "descricao": "Item 2",
                "unidade": "m3",
                "quantitativo": 100.0,
                "predecessores": [{"item_id": "eap-01", "tipo": "FF", "lag": 0}],
            },
        ],
        "contexto_id": "test",
        "snapshot_catalogo_id": "snap-cat",
        "snapshot_perfil_id": "snap-perfil",
    }
    catalogo = {
        "cpus": [{"codigo": "CPU-01", "descricao": "CPU teste", "producao_id_ref": "PROD-01"}],
        "produtividades": [
            {
                "id": "PROD-01",
                "codigo": "PROD-01",
                "descricao": "Prod",
                "valor_horario": 50.0,
                "unidade": "m3",
                "composicao_padrao_equipe": {},
            }
        ],
        "insumos": [],
    }
    canonical = run_escopo_e_eap(None, inputs, catalogo=catalogo).canonical
    assert canonical.atividades, "pré-condição: run_escopo_e_eap deve auto-derivar atividades"

    result = run_cronograma(canonical, {}, catalogo=catalogo)

    assert not any(v.status == "ERRO" for v in result.validacoes)
    assert result.canonical.cronograma is not None
    assert result.canonical.cronograma.is_feasible is True
    sched = {sa.activity_id: sa for sa in result.canonical.cronograma.scheduled_activities}
    # FF: eap-02 só pode TERMINAR depois que eap-01 termina — com CPU-01 livre para
    # ambos (sem disputa de pool), sem a constraint eap-02 rodaria em paralelo (semana 0).
    assert sched["eap-02"].end_week >= sched["eap-01"].end_week
    assert sched["eap-02"].start_week > sched["eap-01"].start_week


def test_extract_edge_thresholds_ignora_tipo_desconhecido_no_meio_do_laco():
    """`_extract_edge_thresholds_from_eap` normaliza tipo via `PrecedenciaItem`
    (Literal["FS","SS","FF"]) — nenhum dado tipado real chega com outro valor.
    O fallthrough silencioso do laço (`if`/`elif`/`elif` sem `else`, caindo direto
    de volta ao topo do laço quando nenhum tipo bate) é, portanto, apenas
    defensivo e inalcançável via a API pública tipada — exercitado aqui via
    duck-typing direto sobre o helper interno, sem passar pela validação
    Pydantic de `PrecedenciaItem`."""
    import sys

    from concilium.application.skills import run_cronograma as _rc  # noqa: F401 — garante o load lazy

    cron_mod = sys.modules["_concilium_skillpkg_04_cronograma.skill"]

    class _FakePred:
        def __init__(self, item_id, tipo, lag=0, completion_threshold_pct=1.0):
            self.item_id = item_id
            self.tipo = tipo
            self.lag = lag
            self.completion_threshold_pct = completion_threshold_pct

    class _FakeItem:
        def __init__(self, item_id, preds):
            self.item_id = item_id
            self._preds = preds

        def predecessores_tipados(self):
            return self._preds

    class _FakeCanonical:
        def __init__(self, eap):
            self.eap = eap

    # Predecessor com tipo desconhecido no MEIO da lista (não o último) — garante
    # que o laço continua para o próximo predecessor após o fallthrough (186->177).
    item = _FakeItem(
        "eap-03",
        [
            _FakePred("eap-01", "TIPO-INVALIDO"),
            _FakePred("eap-02", "FS"),
        ],
    )
    canonical = _FakeCanonical(eap=[item])

    edge_thresholds, extended = cron_mod._extract_edge_thresholds_from_eap(canonical)

    assert ("eap-01", "eap-03") not in edge_thresholds
    assert ("eap-02", "eap-03") in edge_thresholds
    assert extended == []



from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402

# 04-cronograma/_skill_helpers/_dag.py line 53->46: tipo unknown → elif False → no-op
# ---------------------------------------------------------------------------


class TestExtractDagUnknownPredecessorType:
    def test_unknown_tipo_produces_no_edge(self):
        """Line 53->46 branch: tipo='SF' is not FS and not in (SS,FF) → elif False → skip."""
        import importlib.util

        _path = (
            Path(__file__).resolve().parents[2]
            / "src/concilium/application/skills/manifests/04-cronograma/_skill_helpers/_dag.py"
        )
        _spec = importlib.util.spec_from_file_location("skill04_dag_helpers_b16", _path)
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules["skill04_dag_helpers_b16"] = _mod
        _spec.loader.exec_module(_mod)
        extract_dag_from_spec_or_eap = _mod.extract_dag_from_spec_or_eap

        pred = SimpleNamespace(item_id="A1", tipo="SF", lag=0, completion_threshold_pct=1.0)
        item = SimpleNamespace(item_id="B1", predecessores_tipados=lambda: [pred])

        dag = extract_dag_from_spec_or_eap(spec={}, activities=[], eap_items=[item])

        # No edge added since tipo "SF" is not handled
        assert dag.precedence == []
        assert dag.thresholds == {}
        assert dag.extended_precedences == []

