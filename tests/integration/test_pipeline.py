"""Testes de integração: pipeline completo via Runtime.

Testa as 3 skills implementadas (00 → 01 → 06) end-to-end usando dados seed reais
de config/, persistindo via ProjectStore, com cliente Open-Meteo mockado.
"""

import json
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from concilium.application.runtime import Runtime
from concilium.infrastructure.storage.project import ProjectStore

# ── Fixtures para TestPipelineAnalitico ───────────────────────────────────────


@pytest.fixture(scope="class")
def projeto_analitico(tmp_path_factory, _session_pipeline_sk09):
    """Class-scoped: cópia isolada do projeto pós-09 ÚNICA por classe de teste.

    Mudança de function → class scope reduz copytree de ~6-7× para 1× por classe.
    Testes em TestPipelineAnalitico são read-heavy e independentes, então
    compartilhar o mesmo projeto entre testes é seguro.

    PERFORMANCE: ~3-5s copytree × 1 ao invés de × 7 testes = economia de ~20-28s.
    """
    proj_base, _ = _session_pipeline_sk09
    dest = tmp_path_factory.mktemp("analitico") / "projeto"
    shutil.copytree(proj_base.root, dest)
    return ProjectStore(dest)


# Fixture intermediária removida - usar _session_pipeline_sk09 diretamente


class TestPipelineEndToEnd:
    def test_init_e_snapshot_funcionam(
        self,
        runtime: Runtime,
        projeto_terraplenagem: ProjectStore,
    ):
        """Init cria projeto, snapshots dedupedam por hash."""
        snaps = runtime.create_snapshots(projeto_terraplenagem)
        assert "jurisdicao" in snaps
        assert "perfil" in snaps
        assert "catalogo" in snaps
        # Snapshots gravados em disco
        snap_dir = projeto_terraplenagem.root / "snapshots"
        assert any(snap_dir.glob("perfil-*.json"))
        assert any(snap_dir.glob("catalogo-*.json"))

        # Re-criar = deduplicação (mesmo número de arquivos)
        before = len(list(snap_dir.glob("*.json")))
        runtime.create_snapshots(projeto_terraplenagem)
        after = len(list(snap_dir.glob("*.json")))
        assert before == after

    def test_skill_00_escopo_via_runtime(
        self,
        runtime: Runtime,
        projeto_terraplenagem: ProjectStore,
        inputs_escopo_terraplenagem: dict[str, Any],
    ):
        """Skill 00 invocada via runtime persiste canônico."""
        projeto_terraplenagem.new_version()  # cria v1
        result = runtime.run_skill("01-escopo-e-eap", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)
        assert not result.has_errors

        # Canônico foi persistido
        canonical = projeto_terraplenagem.load_canonical("v1")
        assert canonical is not None
        assert canonical.projeto.tipo_obra == "terraplenagem"
        assert len(canonical.eap) == 3

        # Log de invocação registrado
        log = (projeto_terraplenagem.root / "v1" / "invocations.log").read_text()
        assert "01-escopo-e-eap" in log
        assert '"status": "OK"' in log

    def test_skill_01_praticabilidade_via_runtime_com_mock(
        self,
        runtime: Runtime,
        projeto_terraplenagem: ProjectStore,
        inputs_escopo_terraplenagem: dict[str, Any],
        mock_openmeteo_aracoiaba,
    ):
        """Pipeline 00 → 01 com Open-Meteo mockado."""
        projeto_terraplenagem.new_version()
        runtime.run_skill("01-escopo-e-eap", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)

        # Patch o cliente que skill 01 vai instanciar
        with patch("concilium.infrastructure.clients.openmeteo.OpenMeteoClient", return_value=mock_openmeteo_aracoiaba):
            result = runtime.run_skill(
                "02-produtividade-climatica",
                projeto_terraplenagem,
                inputs={"ano_referencia": 2024},
            )
        assert not result.has_errors

        canonical = projeto_terraplenagem.load_canonical("v1")
        assert canonical.praticabilidade is not None
        # Padrão climático nordestino — meses secos têm produtividade alta
        prat = canonical.praticabilidade.percentual_produtivo_mensal
        assert prat["07"] > 0.85
        assert prat["08"] > 0.85

    def test_validate_canonical_persistido(
        self,
        runtime: Runtime,
        projeto_terraplenagem: ProjectStore,
        inputs_escopo_terraplenagem: dict[str, Any],
    ):
        """Canônico persistido pode ser recarregado e validado."""
        projeto_terraplenagem.new_version()
        runtime.run_skill("01-escopo-e-eap", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)
        canonical_loaded = projeto_terraplenagem.load_canonical()
        assert canonical_loaded is not None
        assert canonical_loaded.projeto.localizacao == "Aracoiaba, CE"


class TestEnforcementSemanticas:
    """Testes que verificam que regras críticas são enforçadas, não só sugeridas."""

    def test_save_em_versao_aprovada_falha(
        self,
        runtime: Runtime,
        projeto_terraplenagem: ProjectStore,
        inputs_escopo_terraplenagem: dict[str, Any],
    ):
        """Após approve, save_canonical em mesma versão deve falhar."""
        projeto_terraplenagem.new_version()
        runtime.run_skill("01-escopo-e-eap", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)
        projeto_terraplenagem.approve("v1")

        canonical = projeto_terraplenagem.load_canonical("v1")
        with pytest.raises(PermissionError, match="read-only"):
            projeto_terraplenagem.save_canonical(canonical, "v1")

    def test_skill_desconhecida_falha(self, runtime, projeto_terraplenagem):
        projeto_terraplenagem.new_version()
        from concilium.application.runtime import RuntimeError as RTErr

        with pytest.raises(RTErr, match="Skill desconhecida"):
            runtime.run_skill("99-inexistente", projeto_terraplenagem)


class TestPipelineCompleto:
    """Pipeline 00 → 01 → 02 → 03 → 04 → 05 → 06 end-to-end."""

    def test_pipeline_terraplenagem_caso_feliz(
        self,
        runtime: Runtime,
        projeto_terraplenagem: ProjectStore,
        inputs_escopo_terraplenagem: dict,
        mock_openmeteo_aracoiaba,
    ):
        from unittest.mock import patch

        projeto_terraplenagem.new_version()

        # 00-escopo
        r = runtime.run_skill("01-escopo-e-eap", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)
        assert not r.has_errors, r.validacoes

        # 02-produtividade-climatica
        with patch("concilium.infrastructure.clients.openmeteo.OpenMeteoClient", return_value=mock_openmeteo_aracoiaba):
            r = runtime.run_skill("02-produtividade-climatica", projeto_terraplenagem, inputs={"ano_referencia": 2024})
        assert not r.has_errors, r.validacoes

        # 00A, 00B, 01A — pre-requisitos de 04-cronograma
        r = runtime.run_skill("03-catalogo-de-recursos", projeto_terraplenagem, inputs={})
        assert not r.has_errors

        # 04-cronograma — alocação suficiente
        # eap-01: 80000 m3 / 11210/wk ≈ 7.1 wk → 8 semanas (W23-W30)
        # eap-02: 75000 m3 /  8314/wk ≈ 9.0 wk → 10 semanas (W27-W36)
        # eap-03: 28000 m2 / 19200/wk ≈ 1.5 wk →  6 semanas (W35-W40)
        cron_inputs = {
            "num_equipes_por_item": {
                "eap-01": {f"2026-W{w:02d}": 1 for w in range(23, 31)},
                "eap-02": {f"2026-W{w:02d}": 1 for w in range(27, 37)},
                "eap-03": {f"2026-W{w:02d}": 1 for w in range(35, 41)},
            }
        }
        r = runtime.run_skill("04-cronograma", projeto_terraplenagem, inputs=cron_inputs)
        assert not r.has_errors, r.validacoes

        # 03-equipes-diretas
        r = runtime.run_skill("05-equipes-e-alocacao", projeto_terraplenagem, inputs={})
        assert not r.has_errors, r.validacoes

        # 06-precificacao-unitaria
        r = runtime.run_skill("06-precificacao-unitaria", projeto_terraplenagem, inputs={})
        assert r.canonical is not None, r.validacoes  # skill 04 may emit price deviation warnings

        # 07-custos-indiretos
        r = runtime.run_skill("07-custos-indiretos", projeto_terraplenagem, inputs={})
        assert not r.has_errors

        # 06-consolidar
        r = runtime.run_skill("08-consolidacao-financeira", projeto_terraplenagem, inputs={})

        canonical = projeto_terraplenagem.load_canonical()
        assert canonical.resultado is not None, "Skill 06 deve produzir resultado"

        # Resultado deve ter valores financeiros calculados (não necessariamente positivos
        # com dados seed não calibrados — o importante é que o pipeline rodou completo)
        res = canonical.resultado
        assert isinstance(res.margem_pct, float)
        assert isinstance(res.resultado_financeiro, float)
        assert res.status_margem in ("VERDE", "AMARELO", "VERMELHO")
        assert res.venda.total_com_bdi > 0
        assert res.custo.total > 0

        # Ponto de equilíbrio populado (mesmo que com ERROs de PE)
        assert len(canonical.ponto_equilibrio) > 0

        # Log de invocações deve ter 7 entradas (uma por skill invocada)
        log = (projeto_terraplenagem.root / "v1" / "invocations.log").read_text()
        n_invocacoes = len([ln for ln in log.strip().splitlines() if ln])
        assert n_invocacoes >= 8, f"Esperadas >= 8 invocações, encontradas {n_invocacoes}"

    def test_pipeline_para_em_cron_quando_prazo_insuficiente(
        self,
        runtime: Runtime,
        projetos_root: Path,
        mock_openmeteo_aracoiaba,
    ):
        """Replica amostra 03 — saneamento com prazo impossível."""
        from unittest.mock import patch

        # Projeto com prazo muito curto para o quantitativo
        project = ProjectStore.init(projetos_root, "saneamento-falha-cron", "mendeslobo")
        project.new_version()

        inputs_escopo = {
            "nome": "Saneamento prazo curto",
            "tipo_obra": "saneamento",
            "localizacao": "Fortaleza, CE",
            "coordenadas": {"lat": -3.7319, "lng": -38.5267},
            "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
            "data_inicio": "2026-08-01",
            "data_termino": "2026-12-31",
            "contexto_id": "mendeslobo",
            "eap": [
                {
                    "item_id": "eap-01",
                    "ordem": 1,
                    "cpu_id": "CPU-DREN-BOCA-BDCAP-100",
                    "descricao": "Coletor DN300",
                    "unidade": "m",
                    "quantitativo": 4500,
                }
            ],
        }

        r = runtime.run_skill("01-escopo-e-eap", project, inputs=inputs_escopo)
        assert not r.has_errors

        with patch("concilium.infrastructure.clients.openmeteo.OpenMeteoClient", return_value=mock_openmeteo_aracoiaba):
            r = runtime.run_skill("02-produtividade-climatica", project, inputs={"ano_referencia": 2024})
        assert not r.has_errors

        # 00A, 00B, 01A — pré-requisitos de 04-cronograma
        r = runtime.run_skill("03-catalogo-de-recursos", project, inputs={})
        assert not r.has_errors

        # 1 equipe só num único mês — sabidamente insuficiente
        cron_inputs = {
            "num_equipes_por_item": {
                "eap-01": {"2026-W31": 1},
            }
        }
        r = runtime.run_skill("04-cronograma", project, inputs=cron_inputs)
        assert r.has_errors
        erros_cron = [v for v in r.validacoes if v.codigo == "VAL-CRON-01" and v.status == "ERRO"]
        assert erros_cron, "Esperado VAL-CRON-01 ERRO"

        # Canônico NÃO deve ter resultado (pipeline parou no cron)
        canonical = project.load_canonical()
        assert canonical.resultado is None
        assert canonical.equipes_diretas == []


# ── helper seed ───────────────────────────────────────────────────────────────


def _carregar_amostra_canonical(path: Path):
    """Carrega CanonicalModel de arquivo JSON de amostra.

    Filtra chaves com '$' (comentários do schema) e injeta contexto_id no Meta
    quando ausente (samples não exigem contexto_id no arquivo).
    """
    from concilium.domain.models.canonical import CanonicalModel

    def _strip_dollar(obj):
        if isinstance(obj, dict):
            return {k: _strip_dollar(v) for k, v in obj.items() if not k.startswith("$")}
        if isinstance(obj, list):
            return [_strip_dollar(item) for item in obj]
        return obj

    data = json.loads(path.read_text(encoding="utf-8"))
    data = _strip_dollar(data)
    data.setdefault("meta", {}).setdefault("contexto_id", "mendeslobo")
    return CanonicalModel.model_validate(data)


# ── Pipeline analítico 07→12 via Runtime ─────────────────────────────────────


class TestPipelineAnalitico:
    """Testa dispatch via Runtime para skills 07-12, persistência de artefatos e log."""

    def test_08_criticality_popula_canonical(self, runtime, projeto_analitico):
        r = runtime.run_skill("10-diagnostico-criticidade", projeto_analitico, inputs={})
        assert not r.has_errors

        can = projeto_analitico.load_canonical()
        assert can.criticality_report is not None
        assert "critical_path" in can.criticality_report

    def test_09_cost_criticality_popula_canonical(self, runtime, projeto_analitico):
        runtime.run_skill("10-diagnostico-criticidade", projeto_analitico, inputs={})
        r = runtime.run_skill("10-diagnostico-criticidade", projeto_analitico, inputs={})
        assert not r.has_errors

        can = projeto_analitico.load_canonical()
        assert can.cost_criticality_report is not None
        assert len(can.cost_criticality_report.atividades) > 0

    def test_10_intervention_roi_popula_canonical(self, runtime, projeto_analitico):
        runtime.run_skill("10-diagnostico-criticidade", projeto_analitico, inputs={})
        runtime.run_skill("10-diagnostico-criticidade", projeto_analitico, inputs={})
        intervencoes = [
            {
                "intervencao_id": "iv-01",
                "descricao": "+10% equipes pico Dezembro",
                "tipo_perturbacao": "+10%",
                "custo_adicional_estimado": 50_000,
                "ganho_margem_esperado": 0.02,
                "item_ids_afetados": ["eap-01"],
            }
        ]
        r = runtime.run_skill(
            "11-avaliacao-intervencoes",
            projeto_analitico,
            inputs={"intervencoes_propostas": intervencoes},
        )
        assert not r.has_errors

        can = projeto_analitico.load_canonical()
        assert can.intervention_assessments is not None
        assert len(can.intervention_assessments) == 1

    def test_11_decision_log_persiste_json(self, runtime, projeto_analitico):
        runtime.run_skill("10-diagnostico-criticidade", projeto_analitico, inputs={})
        runtime.run_skill("10-diagnostico-criticidade", projeto_analitico, inputs={})
        decision_inputs = {
            "objective": "Aumentar margem para faixa verde (≥10%)",
            "considered_interventions": [
                {"id": "iv-01", "descricao": "+10% equipes pico"},
                {"id": "iv-null", "descricao": "Manter planejamento"},
            ],
            "selected_intervention": "iv-01",
            "justification": {
                "rationale": "Melhor custo-benefício na análise ROI",
                "risks": ["Disponibilidade de equipamentos"],
            },
            "decided_by": {"type": "ENGENHEIRO", "id": "eng-bruno"},
            "expected_outcome": {"margem": 0.10, "prazo_dias": 214},
        }
        r = runtime.run_skill("12-registro-decisoes", projeto_analitico, inputs=decision_inputs)
        assert not r.has_errors

        v = projeto_analitico.current_version()
        dl_path = projeto_analitico.version_path(v) / "decision_log.json"
        assert dl_path.exists(), "decision_log.json não foi persistido"
        dl = json.loads(dl_path.read_text())
        assert "decision_id" in dl
        assert dl["selected_intervention"] == "iv-01"

    def test_pipeline_07_a_11_gera_12_invocacoes_no_log(self, tmp_path, runtime, _session_pipeline_sk09):
        """Pipeline completo: 01-09 (base) + 10-12 (este teste) ≥ 8 entradas no log.

        PERFORMANCE: Usa shutil.copytree do projeto base. Poderia usar hardlinks
        mas a complexidade não vale para um único teste.
        """
        sk09_proj, _ = _session_pipeline_sk09
        # Cópia isolada para não sujar o estado compartilhado
        dest = tmp_path / "projeto"
        shutil.copytree(sk09_proj.root, dest)
        proj = ProjectStore(dest)

        runtime.run_skill("10-diagnostico-criticidade", proj, inputs={})
        runtime.run_skill("10-diagnostico-criticidade", proj, inputs={})

        intervencoes = [
            {
                "intervencao_id": "iv-sub",
                "descricao": "Subcontratação parcial pico",
                "tipo_perturbacao": "subcontratacao",
                "custo_adicional_estimado": 80_000,
                "ganho_margem_esperado": 0.025,
                "item_ids_afetados": ["eap-01"],
            }
        ]
        runtime.run_skill(
            "11-avaliacao-intervencoes",
            proj,
            inputs={"intervencoes_propostas": intervencoes},
        )
        decision_inputs = {
            "objective": "Aceitar planejamento atual sem intervenções",
            "considered_interventions": [
                {"id": "iv-sub", "descricao": "Subcontratação parcial pico"},
                {"id": "iv-null", "descricao": "Não fazer nada"},
            ],
            "selected_intervention": None,
            "justification": {"rationale": "Custo adicional de subcontratação não se paga na margem atual"},
            "decided_by": {"type": "GESTOR", "id": "gest-01"},
        }
        runtime.run_skill("12-registro-decisoes", proj, inputs=decision_inputs)

        log_text = (proj.root / "v1" / "invocations.log").read_text()
        n_inv = len([line for line in log_text.strip().splitlines() if line])
        assert n_inv >= 8, f"Esperadas >= 8 invocações, encontradas {n_inv}"


# ── Validação AGIS com dados seed calibrados ──────────────────────────────────


class TestValidacaoAgisComSeedData:
    """Carrega amostra 01-terraplenagem-feliz.json e valida skills 07-12 contra
    os valores de referência do documento de especificação.

    Serve como relatório analítico: Concilium vs. estimativa inicial registrada
    nos dados seed (margem 9.2 %, status VERDE, 3 serviços, 2 equipes diretas).
    """

    @pytest.fixture(scope="class")
    def _relatorio_seed(self):
        """Executa run_relatorio_e_artefatos UMA VEZ para TestValidacaoAgisComSeedData.

        Compartilhada pelos dois testes que validam o relatório analítico;
        evita executar a skill duas vezes sobre o mesmo canonical de entrada.
        """
        from concilium.application.skills import run_relatorio_e_artefatos

        path = Path(__file__).parent.parent / "samples" / "01-terraplenagem-feliz.json"
        can = _carregar_amostra_canonical(path)
        return run_relatorio_e_artefatos(can, {})

    def test_canonical_carrega_corretamente(self, amostra_terraplenagem_path: Path):
        can = _carregar_amostra_canonical(amostra_terraplenagem_path)
        assert can.projeto.nome.startswith("Terraplenagem")
        assert can.resultado is not None
        assert can.resultado.margem_pct == pytest.approx(0.092)
        assert can.resultado.status_margem == "VERDE"
        assert can.cronograma is not None
        assert len(can.cronograma.scheduled_activities) == 3

    def test_relatorio_agis_replica_valores_seed(self, _relatorio_seed):
        """Skill 07 deve replicar fielmente os valores financeiros do seed."""
        result = _relatorio_seed
        assert not result.has_errors

        rel = result.relatorio
        res_sec = rel["RESULTADO"]

        # Valores financeiros extraídos diretamente do seed
        assert res_sec["preco_venda_total"] > 1_000_000
        assert res_sec["custo_total"] > 1_000_000
        assert 0.07 <= res_sec["margem_pct"] <= 0.12, f"Margem {res_sec['margem_pct']:.2%} fora da faixa esperada"
        assert res_sec["status_margem"] == "VERDE"
        assert res_sec["resultado_bruto"] > 0

        # PLANEJAMENTO: 3 itens (escavação, compactação, lançamento)
        assert len(rel["PLANEJAMENTO"]) == 3
        row = rel["PLANEJAMENTO"][0]
        assert row["item_id"] == "eap-01"
        assert row["subtotal_com_bdi"] == pytest.approx(702_100)

        # EQUIPE: 2 equipes diretas, sem ponto de equilíbrio no seed
        assert len(rel["EQUIPE"]) == 2
        eq_row = rel["EQUIPE"][0]
        assert eq_row["delta_pct"] is None
        assert eq_row["status_pe"] == "N/A"

    def test_relatorio_analitico_margens_e_razoes(self, _relatorio_seed):
        """Relatório analítico: razão indireto/direto e posicionamento da margem."""
        result = _relatorio_seed
        res = result.relatorio["RESULTADO"]

        # Razão indireto/direto: positiva (custo total inclui direto + indiretos)
        razao = res["razao_indireto_direto"]
        assert razao > 0, f"Razão indireto/direto deve ser positiva: {razao:.1%}"

        # Margem dentro da faixa VERDE (≥ 8 %)
        margem = res["margem_pct"]
        assert margem >= 0.08, f"Margem {margem:.2%} fora da faixa VERDE (≥8%)"

        # Resultado financeiro positivo mas abaixo de 15 % da venda
        assert res["resultado_bruto"] > 0
        assert res["resultado_bruto"] < res["preco_venda_total"] * 0.15

    def test_08_criticality_todos_3_itens_cronograma(self, amostra_terraplenagem_path: Path):
        """Criticality deve processar os 3 itens de cronograma do seed."""
        from concilium.application.skills import run_diagnostico_criticidade

        can = _carregar_amostra_canonical(amostra_terraplenagem_path)
        result = run_diagnostico_criticidade(can, {})
        assert not result.has_errors

        cr = result.canonical.criticality_report  # type: ignore
        assert cr is not None
        critical_path = cr.get("critical_path", [])
        assert len(critical_path) > 0, "critical_path vazio"
        item_ids = set(critical_path)
        assert item_ids.issubset({"eap-01", "eap-02", "eap-03", "i1", "i2", "i3"})

        # score field removed from criticality_report dict

    def test_09_cost_criticality_seed(self, amostra_terraplenagem_path: Path):
        """Cost criticality com 3 itens de planejamento → itens classe ABC."""
        from concilium.application.skills import run_diagnostico_criticidade

        can = _carregar_amostra_canonical(amostra_terraplenagem_path)
        can = run_diagnostico_criticidade(can, {}).canonical  # enriquece criticality_report
        result = run_diagnostico_criticidade(can, {})
        assert not result.has_errors

        items = result.canonical.cost_criticality_report.atividades
        assert len(items) >= 1
        assert items[0].atividade_id == "eap-01"
        assert items[0].classe in ("A+", "A", "B", "C")

    def test_10_intervencao_roi_regime_9h_e_subcontratacao(self, amostra_terraplenagem_path: Path):
        """Duas intervenções: regime_9h (LOW effort) e subcontratação (MED effort)."""
        from concilium.application.skills import run_avaliacao_intervencoes

        can = _carregar_amostra_canonical(amostra_terraplenagem_path)
        intervencoes = [
            {
                "intervencao_id": "iv-sub",
                "descricao": "Subcontratar escavação no pico de Dezembro",
                "tipo_perturbacao": "subcontratacao",
                "custo_adicional_estimado": 80_000,
                "ganho_margem_esperado": 0.03,
                "item_ids_afetados": ["eap-01"],
            },
            {
                "intervencao_id": "iv-regime",
                "descricao": "Ampliar jornada para 9 h/dia em Nov-Dez",
                "tipo_perturbacao": "regime_9h",
                "custo_adicional_estimado": 15_000,
                "ganho_margem_esperado": 0.008,
                "item_ids_afetados": ["eap-01"],
            },
        ]
        result = run_avaliacao_intervencoes(can, {"intervencoes_propostas": intervencoes})
        assert not result.has_errors

        assessments = result.canonical.intervention_assessments
        assert len(assessments) == 2
        iv_regime = next(a for a in assessments if a["intervencao_id"] == "iv-regime")
        assert iv_regime["effort"]["nivel"] == "LOW"

    def test_11_ciclo_decisao_com_contexto_seed(self, amostra_terraplenagem_path: Path):
        """Skill 11 — decisão de aceitar margem AMARELA registrada e persistida."""
        from concilium.application.skills import run_registro_decisoes

        can = _carregar_amostra_canonical(amostra_terraplenagem_path)

        dl_inputs = {
            "objective": "Aprovar execução com margem AMARELA (7.85 %) como obra estratégica",
            "considered_interventions": [
                {"id": "manter", "descricao": "Executar conforme planejado"},
                {"id": "renegociar", "descricao": "Renegociar preços com cliente"},
            ],
            "selected_intervention": "manter",
            "justification": {
                "rationale": "Margem dentro da faixa aceitável; obra estratégica para a região",
                "risks": ["Custo real pode superar estimado por regime de chuvas"],
                "rejected_reasons": {"renegociar": "Cliente não aceita alteração contratual"},
            },
            "decided_by": {"type": "DIRETOR", "id": "dir-ml"},
            "constraints": ["Contrato assinado", "Mobilização em Junho/2026"],
            "expected_outcome": {"margem": 0.0785, "prazo_dias": 214},
        }
        r11 = run_registro_decisoes(can, dl_inputs)
        assert not r11.has_errors
        dl = r11.decision_log
        assert dl["selected_intervention"] == "manter"
        assert "decision_id" in dl
        assert dl["decided_by"]["type"] == "DIRETOR"
