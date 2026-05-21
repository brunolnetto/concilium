"""Coverage tests for 01-escopo-e-eap, 00B-sequenciamento, 08-criticality, and normalizer."""

from datetime import UTC, datetime

from concilium.application.skills import run_escopo_e_eap
from concilium.domain.models.canonical import (
    ActivityDag,
    ArestaActivityDag,
    Atividade,
    CanonicalModel,
    Coordenadas,
    DistribuicaoSemanal,
    EapItem,
    Meta,
    Projeto,
    RegimeTrabalho,
)


# Shims: skills atividades/sequenciamento foram fundidas em 01-escopo-e-eap.
def _canonical_to_inputs(canonical, extra_inputs):
    """Converte um canonical existente + extra_inputs em inputs para run_escopo_e_eap."""
    proj = canonical.projeto if canonical else None
    base = {
        "contexto_id": canonical.meta.contexto_id if canonical else "test",
        "snapshot_catalogo_id": proj.snapshot_catalogo_id if proj else "s",
        "snapshot_perfil_id": proj.snapshot_perfil_id if proj else "s",
        "nome": proj.nome if proj else "test",
        "tipo_obra": proj.tipo_obra if proj else "terraplenagem",
        "localizacao": proj.localizacao if proj else "x",
        "coordenadas": {"lat": proj.coordenadas.lat if proj else 0.0, "lng": proj.coordenadas.lng if proj else 0.0},
        "regime_trabalho": {
            "dias_semana": proj.regime_trabalho.dias_semana if proj else 5,
            "horas_dia": proj.regime_trabalho.horas_dia if proj else 8,
        },
        "data_inicio": str(proj.data_inicio) if proj else "2026-01-01",
        "data_termino": str(proj.data_termino) if proj else "2026-12-31",
        "eap": [i.model_dump() for i in canonical.eap] if canonical and canonical.eap else [],
    }
    base.update(extra_inputs or {})
    return base


def run_atividades(canonical, inputs):
    return run_escopo_e_eap(None, _canonical_to_inputs(canonical, inputs))


def run_diagnostico_criticidade(canonical, inputs):
    from concilium.application.skills import run_diagnostico_criticidade

    return run_diagnostico_criticidade(canonical, inputs or {})


def run_sequenciamento(canonical, inputs):
    merged = _canonical_to_inputs(canonical, inputs)
    if canonical and canonical.atividades:
        merged["atividades"] = [a.model_dump() for a in canonical.atividades]
    return run_escopo_e_eap(None, merged)


# ── Helper ────────────────────────────────────────────────────────────────────


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")


def _make_proj():
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=0.0, lng=0.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio="2026-01-01",
        data_termino="2026-12-31",
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )


def _minimal_canonical(eap=None, atividades=None):
    return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), eap=eap or [], atividades=atividades or [])


# ══ 01-escopo-e-eap ═══════════════════════════════════════════════════════════


class TestAtividades:
    def test_precondition_eap_vazia(self):
        """EAP vazia deve retornar aviso de EAP vazia."""
        can = _minimal_canonical()
        res = run_atividades(can, {})
        codigos = {v.codigo: v.status for v in res.validacoes}
        assert "VAL-EAP-03" in codigos  # EAP vazia emite VAL-EAP-03

    def test_soma_fracoes_invalida_emite_val_atv02(self):
        """Frações que não somam 1.0 devem emitir VAL-ATV-02 ERRO."""
        eap = [EapItem(item_id="i1", ordem=1, cpu_id="CPU-X", descricao="T", unidade="m3", quantitativo=100)]
        can = _minimal_canonical(eap=eap)
        decomposicao = [
            {
                "eap_item_id": "i1",
                "atividades": [
                    {"atividade_id": "atv-1", "fracao_quantitativo": 0.4, "descricao": "A"},
                    {"atividade_id": "atv-2", "fracao_quantitativo": 0.3, "descricao": "B"},
                ],
            }
        ]
        res = run_atividades(can, {"decomposicao": decomposicao})
        codigos = [v.codigo for v in res.validacoes]
        assert "VAL-ATV-02" in codigos


# ══ 00B-sequenciamento ═══════════════════════════════════════════════════════


class TestSequenciamento:
    def _canonical_with_atividades(self):
        eap = [
            EapItem(item_id="i1", ordem=1, cpu_id="CPU-X", descricao="T1", unidade="m3", quantitativo=100),
            EapItem(item_id="i2", ordem=2, cpu_id="CPU-X", descricao="T2", unidade="m3", quantitativo=100),
            EapItem(item_id="i3", ordem=3, cpu_id="CPU-X", descricao="T3", unidade="m3", quantitativo=100),
        ]
        ativs = [
            Atividade(
                atividade_id="a1",
                eap_item_id="i1",
                descricao="A1",
                fracao_quantitativo=1.0,
                quantitativo_atividade=100,
                cpu_id="CPU-X",
            ),
            Atividade(
                atividade_id="a2",
                eap_item_id="i2",
                descricao="A2",
                fracao_quantitativo=1.0,
                quantitativo_atividade=100,
                cpu_id="CPU-X",
            ),
            Atividade(
                atividade_id="a3",
                eap_item_id="i3",
                descricao="A3",
                fracao_quantitativo=1.0,
                quantitativo_atividade=100,
                cpu_id="CPU-X",
            ),
        ]
        return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), eap=eap, atividades=ativs)

    def test_sucessora_invalida_emite_dag01(self):
        """If successora doesn't exist, should emit VAL-DAG-01 ERRO."""
        can = self._canonical_with_atividades()
        inputs = {"precedencias": [{"predecessora": "a1", "sucessora": "nonexistent"}]}
        res = run_sequenciamento(can, inputs)
        codigos = {v.codigo: v.status for v in res.validacoes}
        assert "VAL-DAG-01" in codigos and codigos["VAL-DAG-01"] == "ERRO"

    def test_predecessora_invalida_emite_dag01(self):
        """If predecessora doesn't exist, should emit VAL-DAG-01 ERRO (lines 82-87)."""
        can = self._canonical_with_atividades()
        inputs = {"precedencias": [{"predecessora": "nonexistent", "sucessora": "a1"}]}
        res = run_sequenciamento(can, inputs)
        codigos = {v.codigo: v.status for v in res.validacoes}
        assert "VAL-DAG-01" in codigos and codigos["VAL-DAG-01"] == "ERRO"

    def test_atividades_vazias_emite_precondicao(self):
        """Empty EAP/atividades should emit EAP warning."""
        can = _minimal_canonical()  # no atividades
        res = run_sequenciamento(can, {})
        codigos = {v.codigo: v.status for v in res.validacoes}
        assert "VAL-EAP-03" in codigos  # EAP vazia emite VAL-EAP-03

    def test_ciclo_emite_dag02_e_seq01(self):
        """Cycle in precedences should emit VAL-SEQ-01 ERRO."""
        can = self._canonical_with_atividades()
        # skill 01 creates atividade IDs as "{item_id}-atv-1"
        inputs = {
            "precedencias": [
                {"predecessora": "i1-atv-1", "sucessora": "i2-atv-1"},
                {"predecessora": "i2-atv-1", "sucessora": "i3-atv-1"},
                {"predecessora": "i3-atv-1", "sucessora": "i1-atv-1"},
            ]
        }
        res = run_sequenciamento(can, inputs)
        codigos = [v.codigo for v in res.validacoes]
        assert "VAL-SEQ-01" in codigos  # cycle detected

    def test_prazo_contrato_excedido_emite_seq02(self):
        """When prazo_contrato is exceeded, should emit VAL-SEQ-02 ERRO."""
        can = self._canonical_with_atividades()
        # skill 01 creates atividade IDs as "{item_id}-atv-1"
        inputs = {
            "precedencias": [
                {"predecessora": "i1-atv-1", "sucessora": "i2-atv-1"},
                {"predecessora": "i2-atv-1", "sucessora": "i3-atv-1"},
            ],
            "prazo_contrato": 1,
        }
        res = run_sequenciamento(can, inputs)
        codigos = {v.codigo: v.status for v in res.validacoes}
        assert "VAL-SEQ-02" in codigos and codigos["VAL-SEQ-02"] == "ERRO"

    def test_prazo_contrato_ok(self):
        """When prazo_contrato is sufficient, should emit VAL-SEQ-02 OK."""
        can = self._canonical_with_atividades()
        inputs = {
            "precedencias": [
                {"predecessora": "i1-atv-1", "sucessora": "i2-atv-1"},
            ],
            "prazo_contrato": 10,
        }
        res = run_sequenciamento(can, inputs)
        codigos = {v.codigo: v.status for v in res.validacoes}
        assert "VAL-SEQ-02" in codigos and codigos["VAL-SEQ-02"] == "OK"


# ══ 08-criticality ═══════════════════════════════════════════════════════════


class TestCriticality:
    def _build_canonical_with_dag_and_cron(self, weekly=True):
        """Build canonical with activity_dag and cronograma using weekly keys."""
        from concilium.domain.models.canonical import (
            CronogramaItem,
        )

        eap = [
            EapItem(item_id="i1", ordem=1, cpu_id="CPU-X", descricao="T1", unidade="m3", quantitativo=100),
            EapItem(item_id="i2", ordem=2, cpu_id="CPU-X", descricao="T2", unidade="m3", quantitativo=100),
        ]
        ativs = [
            Atividade(
                atividade_id="a1",
                eap_item_id="i1",
                descricao="A1",
                fracao_quantitativo=1.0,
                quantitativo_atividade=100,
                cpu_id="CPU-X",
            ),
            Atividade(
                atividade_id="a2",
                eap_item_id="i2",
                descricao="A2",
                fracao_quantitativo=1.0,
                quantitativo_atividade=100,
                cpu_id="CPU-X",
            ),
        ]
        dag = ActivityDag(
            nos=["a1", "a2"],
            arestas=[ArestaActivityDag(de="a1", para="a2")],
            ordem_topologica=["a1", "a2"],
            critical_path=["a1", "a2"],
            start_offset_min={"a1": 0, "a2": 1},
        )
        if weekly:
            dist_i1 = {
                "2026-W01": DistribuicaoSemanal(num_equipes=1, qtd_executada=50, qtd_acumulada=50, pct=0.5),
                "2026-W02": DistribuicaoSemanal(num_equipes=1, qtd_executada=50, qtd_acumulada=100, pct=1.0),
            }
            dist_i2 = {"2026-W03": DistribuicaoSemanal(num_equipes=1, qtd_executada=100, qtd_acumulada=100, pct=1.0)}
            cron = [
                CronogramaItem(
                    item_id="i1", dias_trabalhados_semana=5, pct_completude=1.0, distribuicao_semanal=dist_i1
                ),
                CronogramaItem(
                    item_id="i2", dias_trabalhados_semana=5, pct_completude=1.0, distribuicao_semanal=dist_i2
                ),
            ]
        else:
            dist_i1 = {"2026-01": DistribuicaoSemanal(num_equipes=1, qtd_executada=50, qtd_acumulada=50, pct=0.5)}
            dist_i2 = {"2026-02": DistribuicaoSemanal(num_equipes=1, qtd_executada=100, qtd_acumulada=100, pct=1.0)}
            cron = [
                CronogramaItem(
                    item_id="i1", dias_trabalhados_semana=5, pct_completude=1.0, distribuicao_mensal=dist_i1
                ),
                CronogramaItem(
                    item_id="i2", dias_trabalhados_semana=5, pct_completude=1.0, distribuicao_mensal=dist_i2
                ),
            ]
        from concilium.domain.models.canonical import EquipeDireta

        equipes = [
            EquipeDireta(item_id="i1", custo_total=100.0, custo_mao_obra_mensal=50.0, permanencia_meses=1.0),
            EquipeDireta(item_id="i2", custo_total=100.0, custo_mao_obra_mensal=50.0, permanencia_meses=1.0),
        ]
        return CanonicalModel(
            meta=_make_meta(),
            projeto=_make_proj(),
            eap=eap,
            atividades=ativs,
            activity_dag=dag,
            cronograma=cron,
            equipes_diretas=equipes,
        )

    def test_weekly_keys_trigger_periodo_to_ordinal_weekly_branch(self):
        """Weekly keys (AAAA-Www) trigger the weekly branch in _periodo_to_ordinal."""
        can = self._build_canonical_with_dag_and_cron(weekly=True)
        res = run_diagnostico_criticidade(can, {})
        assert res.canonical.criticality_report is not None

    def test_backward_tracing_marks_predecessors_critical(self):
        """Predecessor ending just before successor should be marked critical."""
        can = self._build_canonical_with_dag_and_cron(weekly=True)
        res = run_diagnostico_criticidade(can, {})
        report = res.canonical.criticality_report
        assert report is not None
        # Check that critical_path contains activities
        critical_ids = report.get("critical_path", [])
        assert len(critical_ids) > 0


# ══ semantic/normalizer ════════════════════════════════════════════════════════


class TestNormalizer:
    def test_infer_activity_type_unknown_code(self):
        """CPU code not in map should return 'unknown'."""
        from concilium.application.semantic.normalizer import _infer_activity_type

        result = _infer_activity_type("TOTALLY-UNKNOWN-CODE-XYZ-999")
        assert result == "unknown"

    def test_vocabulary_loader_no_yaml(self, tmp_path):
        """VocabularyLoader with no .yaml file should return empty dict."""
        from concilium.application.semantic.normalizer import VocabularyLoader

        vl = VocabularyLoader(tmp_path)
        result = vl.load("nonexistent")
        assert result == {}

    def test_attribute_normalizer_unknown_name_passthrough(self):
        """Unknown attribute name should pass through unchanged."""
        from concilium.application.semantic.normalizer import AttributeNormalizer

        n = AttributeNormalizer()
        name, val = n.normalize("totally_unknown_attribute", 42.0)
        assert name == "totally_unknown_attribute"
        assert val == 42.0
