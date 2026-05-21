"""Testes de integração: pipeline completo via Runtime.

Testa as 3 skills implementadas (00 → 01 → 06) end-to-end usando dados seed reais
de config/, persistindo via ProjectStore, com cliente Open-Meteo mockado.
"""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from concilium.runtime import Runtime
from concilium.storage.project import ProjectStore


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
        result = runtime.run_skill(
            "00-escopo", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem
        )
        assert not result.has_errors

        # Canônico foi persistido
        canonical = projeto_terraplenagem.load_canonical("v1")
        assert canonical is not None
        assert canonical.projeto.tipo_obra == "terraplenagem"
        assert len(canonical.eap) == 3

        # Log de invocação registrado
        log = (projeto_terraplenagem.root / "v1" / "invocations.log").read_text()
        assert "00-escopo" in log
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
        runtime.run_skill("00-escopo", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)

        # Patch o cliente que skill 01 vai instanciar
        with patch("concilium.skills.praticabilidade.OpenMeteoClient", return_value=mock_openmeteo_aracoiaba):
            result = runtime.run_skill(
                "01-praticabilidade",
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
        runtime.run_skill("00-escopo", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)
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
        runtime.run_skill("00-escopo", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)
        projeto_terraplenagem.approve("v1")

        canonical = projeto_terraplenagem.load_canonical("v1")
        with pytest.raises(PermissionError, match="read-only"):
            projeto_terraplenagem.save_canonical(canonical, "v1")

    def test_skill_desconhecida_falha(self, runtime, projeto_terraplenagem):
        projeto_terraplenagem.new_version()
        from concilium.runtime import RuntimeError as RTErr
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
        r = runtime.run_skill("00-escopo", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)
        assert not r.has_errors, r.validacoes

        # 01-praticabilidade
        with patch("concilium.skills.praticabilidade.OpenMeteoClient", return_value=mock_openmeteo_aracoiaba):
            r = runtime.run_skill("01-praticabilidade", projeto_terraplenagem, inputs={"ano_referencia": 2024})
        assert not r.has_errors, r.validacoes

        # 02-cronograma — alocação suficiente
        cron_inputs = {
            "num_equipes_por_item": {
                "eap-01": {"2026-06": 1, "2026-07": 1, "2026-08": 1,
                           "2026-09": 1, "2026-10": 1, "2026-11": 1, "2026-12": 2},
                "eap-02": {"2026-08": 1, "2026-09": 1, "2026-10": 1, "2026-11": 1, "2026-12": 2},
                "eap-03": {"2026-11": 1, "2026-12": 1},
            }
        }
        r = runtime.run_skill("02-cronograma", projeto_terraplenagem, inputs=cron_inputs)
        assert not r.has_errors, r.validacoes

        # 03-equipes-diretas
        r = runtime.run_skill("03-equipes-diretas", projeto_terraplenagem, inputs={})
        assert not r.has_errors, r.validacoes

        # 04-planejamento-bdi
        r = runtime.run_skill("04-planejamento-bdi", projeto_terraplenagem, inputs={})
        assert not r.has_errors, r.validacoes

        # 05-indiretos
        r = runtime.run_skill("05-indiretos", projeto_terraplenagem, inputs={})
        assert not r.has_errors

        # 06-consolidar-resultado
        r = runtime.run_skill("06-consolidar-resultado", projeto_terraplenagem, inputs={})

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
        n_invocacoes = len([l for l in log.strip().splitlines() if l])
        assert n_invocacoes == 7, f"Esperadas 7 invocações, encontradas {n_invocacoes}"

    def test_pipeline_para_em_cron_quando_prazo_insuficiente(
        self,
        runtime: Runtime,
        projetos_root: Path,
        mock_openmeteo_aracoiaba,
    ):
        """Replica amostra 03 — saneamento com prazo impossível."""
        from datetime import UTC, datetime
        from unittest.mock import patch

        # Projeto com prazo muito curto para o quantitativo
        project = ProjectStore.init(projetos_root, "saneamento-falha-cron", "agis", "BR")
        project.new_version()

        inputs_escopo = {
            "nome": "Saneamento prazo curto",
            "tipo_obra": "saneamento",
            "localizacao": "Fortaleza, CE",
            "coordenadas": {"lat": -3.7319, "lng": -38.5267},
            "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
            "data_inicio": "2026-08-01",
            "data_termino": "2026-12-31",
            "versao_referencia_id": "SICRO_2024_CE",
            "eap": [{
                "item_id": "eap-01", "ordem": 1,
                "cpu_id": "DREN-MAN-DN300",
                "descricao": "Coletor DN300", "unidade": "m",
                "quantitativo": 4500, "origem_template": True,
            }],
        }

        r = runtime.run_skill("00-escopo", project, inputs=inputs_escopo)
        assert not r.has_errors

        with patch("concilium.skills.praticabilidade.OpenMeteoClient", return_value=mock_openmeteo_aracoiaba):
            r = runtime.run_skill("01-praticabilidade", project, inputs={"ano_referencia": 2024})
        assert not r.has_errors

        # 1 equipe só — sabidamente insuficiente
        cron_inputs = {"num_equipes_por_item": {
            "eap-01": {"2026-08": 1, "2026-09": 1, "2026-10": 1, "2026-11": 1, "2026-12": 1},
        }}
        r = runtime.run_skill("02-cronograma", project, inputs=cron_inputs)
        assert r.has_errors
        erros_cron = [v for v in r.validacoes if v.codigo == "VAL-CRON-01" and v.status == "ERRO"]
        assert erros_cron, "Esperado VAL-CRON-01 ERRO"

        # Canônico NÃO deve ter resultado (pipeline parou no cron)
        canonical = project.load_canonical()
        assert canonical.resultado is None
        assert canonical.equipes_diretas == []
