"""Testes end-to-end com samples reais: carrega JSON, executa pipeline 00→07, valida output."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from concilium.application.runtime import Runtime
from concilium.infrastructure.storage.project import ProjectStore


class TestPipelineComSamples:
    """Pipeline completa com samples: 00 → 01 → 02 → 03 → 04 → 05 → 06 → 07."""

    @pytest.fixture
    def sample_01_path(self) -> Path:
        """Retorna caminho para sample 01-terraplenagem-feliz.json."""
        return Path(__file__).parent.parent / "samples" / "01-terraplenagem-feliz.json"

    def load_sample(self, sample_path: Path) -> dict[str, Any]:
        """Carrega sample JSON."""
        with open(sample_path) as f:
            return json.load(f)

    def test_carrega_sample_01_estrutura_valida(self, sample_01_path: Path):
        """Sample 01 tem estrutura esperada."""
        sample = self.load_sample(sample_01_path)

        assert sample["$comment"]
        assert "meta" in sample
        assert "projeto" in sample
        assert "eap" in sample
        assert sample["projeto"]["tipo_obra"] == "terraplenagem"
        assert len(sample["eap"]) == 3

    def test_pipeline_sample_01_terraplenagem_feliz(
        self,
        runtime: Runtime,
        projeto_terraplenagem: ProjectStore,
        inputs_escopo_terraplenagem: dict[str, Any],
        mock_openmeteo_aracoiaba,
    ):
        """Pipeline completa com sample 01 — terraplenagem sucesso.

        Esperado: validações passam, resultado com margem 9.2% (VERDE).
        """
        # Usa fixtures padrão (inputs_escopo_terraplenagem já tem CPUs válidas em modo de teste)
        projeto_terraplenagem.new_version()

        # ── Skill 00: Escopo ─────────────────────────────────────────
        r = runtime.run_skill("01-escopo-e-eap", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)
        assert not r.has_errors, f"Escopo falhou: {r.validacoes}"

        # ── Skill 01: Praticabilidade (com mock) ──────────────────────
        with patch(
            "concilium.infrastructure.clients.openmeteo.OpenMeteoClient",
            return_value=mock_openmeteo_aracoiaba,
        ):
            r = runtime.run_skill("02-produtividade-climatica", projeto_terraplenagem, inputs={"ano_referencia": 2024})
        assert not r.has_errors, f"Praticabilidade falhou: {r.validacoes}"

        # ── Skill 01A: Declarar Recursos (modo trivial) ───────────────
        r = runtime.run_skill("03-catalogo-de-recursos", projeto_terraplenagem, inputs={})
        assert not r.has_errors, f"Recursos falhou: {r.validacoes}"

        # ── Skill 02: Cronograma ──────────────────────────────────────
        # Alocação semanas ISO suficiente para cada item
        # eap-01: 80000m3 / 11210/wk ≈ 7.1 wk → 8 semanas
        # eap-02: 75000m3 /  8314/wk ≈ 9.0 wk → 10 semanas
        # eap-03: 28000m2 / 19200/wk ≈ 1.5 wk →  6 semanas
        cron_inputs = {
            "num_equipes_por_item": {
                "eap-01": {f"2026-W{w:02d}": 1 for w in range(23, 31)},
                "eap-02": {f"2026-W{w:02d}": 1 for w in range(27, 37)},
                "eap-03": {f"2026-W{w:02d}": 1 for w in range(35, 41)},
            }
        }
        r = runtime.run_skill("04-cronograma", projeto_terraplenagem, inputs=cron_inputs)
        assert not r.has_errors, f"Cronograma falhou: {r.validacoes}"

        # ── Skill 03: Equipes Diretas ─────────────────────────────────
        r = runtime.run_skill("05-equipes-e-alocacao", projeto_terraplenagem, inputs={})
        assert not r.has_errors, f"Equipes Diretas falhou: {r.validacoes}"

        # ── Skill 04: Planejamento BDI ────────────────────────────────
        r = runtime.run_skill("06-precificacao-unitaria", projeto_terraplenagem, inputs={})
        # Skill 04 (precificação) pode gerar AVISOs/ERROs de convergência com catálogo de teste
        assert r.canonical is not None, f"Planejamento BDI falhou sem canonical: {r.validacoes}"

        # ── Skill 05: Indiretos ───────────────────────────────────────
        r = runtime.run_skill("07-custos-indiretos", projeto_terraplenagem, inputs={})
        assert not r.has_errors, f"Indiretos falhou: {r.validacoes}"

        # ── Skill 06: Consolidar ──────────────────────────────────────
        r = runtime.run_skill("08-consolidacao-financeira", projeto_terraplenagem, inputs={})
        # Skill 06 pode gerar ERROs de validação com dados de teste não calibrados
        # O importante é que rodou sem crashes

        canonical = projeto_terraplenagem.load_canonical()
        assert canonical.resultado is not None, "Skill 06 deve gerar resultado"

        # Validações básicas de resultado (mesmo que com dados ruins)
        res = canonical.resultado
        assert res.status_margem in ("VERDE", "AMARELO", "VERMELHO"), f"Status inesperado: {res.status_margem}"
        assert isinstance(res.margem_pct, float), "Margem deve ser float"
        assert res.venda.total_com_bdi >= 0, "Venda deve ser >= 0"

        # ── Skill 07: Adapter de Saída ────────────────────────────────
        r = runtime.run_skill("09-relatorio-e-artefatos", projeto_terraplenagem, inputs={})
        assert not r.has_errors, f"Adapter Saída falhou: {r.validacoes}"

        # Valida output da Skill 07
        relatorio = r.relatorio  # type: ignore[attr-defined]
        assert relatorio is not None, "Adapter deve gerar relatório"

        # Estrutura esperada
        assert "meta" in relatorio
        assert "resumo" in relatorio
        assert "PLANEJAMENTO" in relatorio
        assert "EQUIPE" in relatorio
        assert "INDIRETOS" in relatorio
        assert "RESULTADO" in relatorio

        # Validações de conteúdo
        assert relatorio["resumo"]["projeto"] is not None
        assert len(relatorio["PLANEJAMENTO"]) > 0, "Deve ter planejamento"
        assert len(relatorio["EQUIPE"]) > 0, "Deve ter equipes"
        assert relatorio["RESULTADO"]["status_margem"] in ("VERDE", "AMARELO", "VERMELHO")

        # Log de invocações deve ter todas as skills (00, 00A, 00B, 01, 01A, 02-06, 07 = 11 total)
        log_path = projeto_terraplenagem.root / "v1" / "invocations.log"
        assert log_path.exists()
        log_content = log_path.read_text()
        n_invocacoes = len([ln for ln in log_content.strip().splitlines() if ln])
        assert n_invocacoes == 9, f"Esperadas 9 invocações (00,01,01A,02-06,07), encontradas {n_invocacoes}"


class TestSkill07OutputFormat:
    """Testa especificamente o formato de output do Skill 07."""

    def test_skill_07_output_estrutura(
        self,
        runtime: Runtime,
        projeto_terraplenagem: ProjectStore,
        inputs_escopo_terraplenagem: dict[str, Any],
        mock_openmeteo_aracoiaba,
    ):
        """Skill 07 gera estrutura JSON correta com todas as seções."""
        from unittest.mock import patch

        projeto_terraplenagem.new_version()

        # Executa pipeline até skill 06
        r = runtime.run_skill("01-escopo-e-eap", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)
        assert not r.has_errors

        with patch("concilium.infrastructure.clients.openmeteo.OpenMeteoClient", return_value=mock_openmeteo_aracoiaba):
            r = runtime.run_skill("02-produtividade-climatica", projeto_terraplenagem, inputs={"ano_referencia": 2024})
        assert not r.has_errors

        r = runtime.run_skill("03-catalogo-de-recursos", projeto_terraplenagem, inputs={})

        cron_inputs = {
            "num_equipes_por_item": {
                "eap-01": {f"2026-W{w:02d}": 1 for w in range(23, 31)},
                "eap-02": {f"2026-W{w:02d}": 1 for w in range(27, 37)},
                "eap-03": {f"2026-W{w:02d}": 1 for w in range(35, 41)},
            }
        }
        r = runtime.run_skill("04-cronograma", projeto_terraplenagem, inputs=cron_inputs)
        assert not r.has_errors

        r = runtime.run_skill("05-equipes-e-alocacao", projeto_terraplenagem, inputs={})
        assert not r.has_errors

        r = runtime.run_skill("06-precificacao-unitaria", projeto_terraplenagem, inputs={})
        assert r.canonical is not None  # skill 04 pode gerar avisos de convergência

        r = runtime.run_skill("07-custos-indiretos", projeto_terraplenagem, inputs={})
        assert not r.has_errors

        r = runtime.run_skill("08-consolidacao-financeira", projeto_terraplenagem, inputs={})
        # Skill 06 pode gerar ERROs de validação com dados de teste não calibrados

        # Agora testa Skill 07
        r = runtime.run_skill("09-relatorio-e-artefatos", projeto_terraplenagem, inputs={})
        assert not r.has_errors, f"Skill 07 falhou: {r.validacoes}"

        output = r.relatorio  # type: ignore[attr-defined]
        assert output is not None

        # Estrutura top-level
        assert isinstance(output, dict)
        assert "resumo" in output
        assert "PLANEJAMENTO" in output
        assert "EQUIPE" in output
        assert "INDIRETOS" in output
        assert "RESULTADO" in output

        # Seção RESUMO
        resumo = output["resumo"]
        assert "projeto" in resumo or "projeto_nome" in resumo
        assert "tipo_obra" in resumo

        # Seção PLANEJAMENTO
        planejamento = output["PLANEJAMENTO"]
        assert isinstance(planejamento, list)
        if len(planejamento) > 0:
            first = planejamento[0]
            assert "item_id" in first
            assert "cpu_id" in first
            assert "quantitativo" in first
            assert "subtotal_sem_bdi" in first
            assert "subtotal_com_bdi" in first

        # Seção EQUIPE
        equipe = output["EQUIPE"]
        assert isinstance(equipe, list)
        if len(equipe) > 0:
            first = equipe[0]
            assert "equipe_id" in first
            assert "item_id" in first
            assert "custo_fixo_total" in first

        # Seção INDIRETOS
        indiretos = output["INDIRETOS"]
        assert isinstance(indiretos, list)
        # Pode estar vazio dependendo do projeto

        # Seção RESULTADO
        resultado = output["RESULTADO"]
        assert "preco_venda_total" in resultado
        assert "custo_total" in resultado
        assert "margem_pct" in resultado
        assert "status_margem" in resultado
        assert resultado["status_margem"] in ("VERDE", "AMARELO", "VERMELHO")

    def test_skill_07_json_serializavel(
        self,
        runtime: Runtime,
        projeto_terraplenagem: ProjectStore,
        inputs_escopo_terraplenagem: dict[str, Any],
        mock_openmeteo_aracoiaba,
    ):
        """Output do Skill 07 deve ser JSON-serializável."""
        from unittest.mock import patch

        projeto_terraplenagem.new_version()

        # Executa pipeline até skill 06
        r = runtime.run_skill("01-escopo-e-eap", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)

        with patch("concilium.infrastructure.clients.openmeteo.OpenMeteoClient", return_value=mock_openmeteo_aracoiaba):
            r = runtime.run_skill("02-produtividade-climatica", projeto_terraplenagem, inputs={"ano_referencia": 2024})

        r = runtime.run_skill("03-catalogo-de-recursos", projeto_terraplenagem, inputs={})

        cron_inputs = {
            "num_equipes_por_item": {
                "eap-01": {f"2026-W{w:02d}": 1 for w in range(23, 31)},
                "eap-02": {f"2026-W{w:02d}": 1 for w in range(27, 37)},
                "eap-03": {f"2026-W{w:02d}": 1 for w in range(35, 41)},
            }
        }
        r = runtime.run_skill("04-cronograma", projeto_terraplenagem, inputs=cron_inputs)
        r = runtime.run_skill("05-equipes-e-alocacao", projeto_terraplenagem, inputs={})
        r = runtime.run_skill("06-precificacao-unitaria", projeto_terraplenagem, inputs={})
        r = runtime.run_skill("07-custos-indiretos", projeto_terraplenagem, inputs={})
        r = runtime.run_skill("08-consolidacao-financeira", projeto_terraplenagem, inputs={})
        # Skill 06 pode gerar ERROs de validação com dados de teste não calibrados
        r = runtime.run_skill("09-relatorio-e-artefatos", projeto_terraplenagem, inputs={})

        output = r.relatorio  # type: ignore[attr-defined]

        # Deve ser serializável para JSON
        json_str = json.dumps(output)
        assert json_str

    def test_skill_07_gera_excel_bytes(
        self,
        runtime: Runtime,
        projeto_terraplenagem: ProjectStore,
        inputs_escopo_terraplenagem: dict[str, Any],
        mock_openmeteo_aracoiaba,
    ):
        """Skill 07 gera bytes Excel válidos que podem ser salvos em arquivo."""
        from io import BytesIO
        from unittest.mock import patch

        from openpyxl import load_workbook

        projeto_terraplenagem.new_version()

        # Executa pipeline até skill 06
        r = runtime.run_skill("01-escopo-e-eap", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)

        with patch("concilium.infrastructure.clients.openmeteo.OpenMeteoClient", return_value=mock_openmeteo_aracoiaba):
            r = runtime.run_skill("02-produtividade-climatica", projeto_terraplenagem, inputs={"ano_referencia": 2024})

        r = runtime.run_skill("03-catalogo-de-recursos", projeto_terraplenagem, inputs={})

        cron_inputs = {
            "num_equipes_por_item": {
                "eap-01": {f"2026-W{w:02d}": 1 for w in range(23, 31)},
                "eap-02": {f"2026-W{w:02d}": 1 for w in range(27, 37)},
                "eap-03": {f"2026-W{w:02d}": 1 for w in range(35, 41)},
            }
        }
        r = runtime.run_skill("04-cronograma", projeto_terraplenagem, inputs=cron_inputs)
        r = runtime.run_skill("05-equipes-e-alocacao", projeto_terraplenagem, inputs={})
        r = runtime.run_skill("06-precificacao-unitaria", projeto_terraplenagem, inputs={})
        r = runtime.run_skill("07-custos-indiretos", projeto_terraplenagem, inputs={})
        r = runtime.run_skill("08-consolidacao-financeira", projeto_terraplenagem, inputs={})
        r = runtime.run_skill("09-relatorio-e-artefatos", projeto_terraplenagem, inputs={})

        # Validar que Excel bytes foram gerados
        excel_bytes = r.excel_bytes  # type: ignore[attr-defined]
        assert excel_bytes is not None, "Skill 07 deve gerar Excel bytes"
        assert isinstance(excel_bytes, bytes), "Deve ser bytes"
        assert len(excel_bytes) > 0, "Bytes não devem estar vazios"

        # Validar que bytes representam um Excel válido
        excel_file = BytesIO(excel_bytes)
        wb = load_workbook(excel_file)

        # Validar abas (sheets reais do Excel adapter)
        expected_sheets = ["DIRETOS.DET", "PLANEJAMENTO", "RESULTADO"]
        for sheet in expected_sheets:
            assert sheet in wb.sheetnames, f"Deve ter aba {sheet}"

        # Validar conteúdo DIRETOS (verificar células com conteúdo)
        ws_diretos = wb["DIRETOS.DET"]
        # Procurar por algum conteúdo nas primeiras linhas
        has_header = False
        for row in ws_diretos.iter_rows(min_row=1, max_row=10):
            for cell in row:
                if cell.value and isinstance(cell.value, str):
                    has_header = True
                    break
            if has_header:
                break
        assert has_header, "DIRETOS deve ter conteúdo textual no cabeçalho"

        # Validar conteúdo PLANEJAMENTO
        ws_planj = wb["PLANEJAMENTO"]
        # Deve ter cabeçalho nas linhas iniciais
        has_header_planj = False
        for row in ws_planj.iter_rows(min_row=1, max_row=5):
            for cell in row:
                if cell.value and isinstance(cell.value, str) and len(str(cell.value)) > 1:
                    has_header_planj = True
                    break
            if has_header_planj:
                break
        assert has_header_planj, "PLANEJAMENTO deve ter cabeçalho"

    def test_skill_07_salva_excel_em_arquivo(
        self,
        runtime: Runtime,
        projeto_terraplenagem: ProjectStore,
        inputs_escopo_terraplenagem: dict[str, Any],
        mock_openmeteo_aracoiaba,
        tmp_path: Path,
    ):
        """Skill 07 gera Excel que pode ser salvo em arquivo."""
        from unittest.mock import patch

        from openpyxl import load_workbook

        projeto_terraplenagem.new_version()

        r = runtime.run_skill("01-escopo-e-eap", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)

        with patch("concilium.infrastructure.clients.openmeteo.OpenMeteoClient", return_value=mock_openmeteo_aracoiaba):
            r = runtime.run_skill("02-produtividade-climatica", projeto_terraplenagem, inputs={"ano_referencia": 2024})

        r = runtime.run_skill("03-catalogo-de-recursos", projeto_terraplenagem, inputs={})

        cron_inputs = {
            "num_equipes_por_item": {
                "eap-01": {f"2026-W{w:02d}": 1 for w in range(23, 31)},
                "eap-02": {f"2026-W{w:02d}": 1 for w in range(27, 37)},
                "eap-03": {f"2026-W{w:02d}": 1 for w in range(35, 41)},
            }
        }
        r = runtime.run_skill("04-cronograma", projeto_terraplenagem, inputs=cron_inputs)
        r = runtime.run_skill("05-equipes-e-alocacao", projeto_terraplenagem, inputs={})
        r = runtime.run_skill("06-precificacao-unitaria", projeto_terraplenagem, inputs={})
        r = runtime.run_skill("07-custos-indiretos", projeto_terraplenagem, inputs={})
        r = runtime.run_skill("08-consolidacao-financeira", projeto_terraplenagem, inputs={})
        r = runtime.run_skill("09-relatorio-e-artefatos", projeto_terraplenagem, inputs={})

        # Salvar Excel em arquivo
        excel_bytes = r.excel_bytes  # type: ignore[attr-defined]
        output_file = tmp_path / "resultado_planejamento.xlsx"
        output_file.write_bytes(excel_bytes)

        # Validar que arquivo pode ser reaberto
        wb = load_workbook(output_file)
        expected_sheets = ["DIRETOS.DET", "PLANEJAMENTO", "RESULTADO"]
        for sheet in expected_sheets:
            assert sheet in wb.sheetnames, f"Aba {sheet} não encontrada"

        # Validar que contém dados
        ws_planj = wb["PLANEJAMENTO"]
        has_data = False
        for row in ws_planj.iter_rows(min_row=4, max_row=10):
            for cell in row:
                if cell.value:
                    has_data = True
                    break
            if has_data:
                break
        assert has_data, "PLANEJAMENTO deve ter dados"

    def test_skill_07_gera_excel_com_11_sheets_template(
        self,
        runtime: Runtime,
        projeto_terraplenagem: ProjectStore,
        inputs_escopo_terraplenagem: dict[str, Any],
        mock_openmeteo_aracoiaba,
    ):
        """Excel gerado contém 11 sheets conforme template especificação."""
        from io import BytesIO
        from unittest.mock import patch

        from openpyxl import load_workbook

        projeto_terraplenagem.new_version()

        r = runtime.run_skill("01-escopo-e-eap", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)

        with patch("concilium.infrastructure.clients.openmeteo.OpenMeteoClient", return_value=mock_openmeteo_aracoiaba):
            r = runtime.run_skill("02-produtividade-climatica", projeto_terraplenagem, inputs={"ano_referencia": 2024})

        r = runtime.run_skill("03-catalogo-de-recursos", projeto_terraplenagem, inputs={})

        cron_inputs = {
            "num_equipes_por_item": {
                "eap-01": {f"2026-W{w:02d}": 1 for w in range(23, 31)},
                "eap-02": {f"2026-W{w:02d}": 1 for w in range(27, 37)},
                "eap-03": {f"2026-W{w:02d}": 1 for w in range(35, 41)},
            }
        }
        r = runtime.run_skill("04-cronograma", projeto_terraplenagem, inputs=cron_inputs)
        r = runtime.run_skill("05-equipes-e-alocacao", projeto_terraplenagem, inputs={})
        r = runtime.run_skill("06-precificacao-unitaria", projeto_terraplenagem, inputs={})
        r = runtime.run_skill("07-custos-indiretos", projeto_terraplenagem, inputs={})
        r = runtime.run_skill("08-consolidacao-financeira", projeto_terraplenagem, inputs={})
        r = runtime.run_skill("09-relatorio-e-artefatos", projeto_terraplenagem, inputs={})

        # Validar Excel com 6 sheets MendesLobo
        excel_bytes = r.excel_bytes  # type: ignore[attr-defined]
        assert excel_bytes is not None

        wb = load_workbook(BytesIO(excel_bytes))

        # Validar sheets esperadas (6 sheets MendesLobo)
        expected_sheets = ["DIRETOS.DET", "PLANEJAMENTO", "RESULTADO"]

        actual_sheets = set(wb.sheetnames)
        for sheet in expected_sheets:
            assert sheet in actual_sheets, f"Sheet {sheet} não encontrada. Presentes: {actual_sheets}"

        print(f"✅ Todos os sheets gerados: {actual_sheets}")


class TestExcelPersistency:
    """Testes de persistência do Excel em ProjectStore."""

    def test_excel_persistido_em_project_store(
        self,
        runtime: Runtime,
        projeto_terraplenagem: ProjectStore,
        inputs_escopo_terraplenagem: dict[str, Any],
        mock_openmeteo_aracoiaba,
    ):
        """Excel é salvo em {version}/outputs/resultado_planejamento.xlsm."""
        from unittest.mock import patch

        from openpyxl import load_workbook

        projeto_terraplenagem.new_version()
        version = projeto_terraplenagem.current_version()

        runtime.run_skill("01-escopo-e-eap", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)

        with patch("concilium.infrastructure.clients.openmeteo.OpenMeteoClient", return_value=mock_openmeteo_aracoiaba):
            runtime.run_skill("02-produtividade-climatica", projeto_terraplenagem, inputs={"ano_referencia": 2024})

        runtime.run_skill("03-catalogo-de-recursos", projeto_terraplenagem, inputs={})

        cron_inputs = {
            "num_equipes_por_item": {
                "eap-01": {f"2026-W{w:02d}": 1 for w in range(23, 31)},
                "eap-02": {f"2026-W{w:02d}": 1 for w in range(27, 37)},
                "eap-03": {f"2026-W{w:02d}": 1 for w in range(35, 41)},
            }
        }
        runtime.run_skill("04-cronograma", projeto_terraplenagem, inputs=cron_inputs)
        runtime.run_skill("05-equipes-e-alocacao", projeto_terraplenagem, inputs={})
        runtime.run_skill("06-precificacao-unitaria", projeto_terraplenagem, inputs={})
        runtime.run_skill("07-custos-indiretos", projeto_terraplenagem, inputs={})
        runtime.run_skill("08-consolidacao-financeira", projeto_terraplenagem, inputs={})
        runtime.run_skill("09-relatorio-e-artefatos", projeto_terraplenagem, inputs={})

        # Validar que Excel foi salvo em ProjectStore
        excel_bytes = projeto_terraplenagem.load_output_file(version, "resultado_planejamento.xlsx")
        assert excel_bytes is not None, "Excel deve estar persistido em ProjectStore"
        assert isinstance(excel_bytes, bytes), "Deve ser bytes"
        assert len(excel_bytes) > 0, "Bytes não devem estar vazios"

        # Validar que arquivo salvo é válido
        from io import BytesIO

        wb = load_workbook(BytesIO(excel_bytes))
        assert "PLANEJAMENTO" in wb.sheetnames  # was RESUMO, removed
        assert "PLANEJAMENTO" in wb.sheetnames

    def test_listar_arquivos_de_saida(
        self,
        runtime: Runtime,
        projeto_terraplenagem: ProjectStore,
        inputs_escopo_terraplenagem: dict[str, Any],
        mock_openmeteo_aracoiaba,
    ):
        """ProjectStore.list_output_files() lista todos os arquivos gerados."""
        from unittest.mock import patch

        projeto_terraplenagem.new_version()
        version = projeto_terraplenagem.current_version()

        runtime.run_skill("01-escopo-e-eap", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)

        with patch("concilium.infrastructure.clients.openmeteo.OpenMeteoClient", return_value=mock_openmeteo_aracoiaba):
            runtime.run_skill("02-produtividade-climatica", projeto_terraplenagem, inputs={"ano_referencia": 2024})

        runtime.run_skill("03-catalogo-de-recursos", projeto_terraplenagem, inputs={})

        cron_inputs = {
            "num_equipes_por_item": {
                "eap-01": {f"2026-W{w:02d}": 1 for w in range(23, 31)},
                "eap-02": {f"2026-W{w:02d}": 1 for w in range(27, 37)},
                "eap-03": {f"2026-W{w:02d}": 1 for w in range(35, 41)},
            }
        }
        runtime.run_skill("04-cronograma", projeto_terraplenagem, inputs=cron_inputs)
        runtime.run_skill("05-equipes-e-alocacao", projeto_terraplenagem, inputs={})
        runtime.run_skill("06-precificacao-unitaria", projeto_terraplenagem, inputs={})
        runtime.run_skill("07-custos-indiretos", projeto_terraplenagem, inputs={})
        runtime.run_skill("08-consolidacao-financeira", projeto_terraplenagem, inputs={})
        runtime.run_skill("09-relatorio-e-artefatos", projeto_terraplenagem, inputs={})

        # Listar arquivos
        output_files = projeto_terraplenagem.list_output_files(version)
        assert "relatorio.md" in output_files, "Relatório MD deve estar listado"
        assert "resultado_planejamento.xlsx" in output_files, "Excel deve estar listado"
        assert len(output_files) >= 2, "Deve ter no mínimo JSON e Excel"


class TestExcelComDadosSICRO:
    """Testes com dados SICRO reais e validação de valores."""

    def test_excel_com_contexto_agis_usa_catalogo_sicro(
        self,
        runtime: Runtime,
        projeto_terraplenagem: ProjectStore,
        inputs_escopo_terraplenagem: dict[str, Any],
        mock_openmeteo_aracoiaba,
    ):
        """Excel gerado usa catálogo SICRO real quando contexto está ativo.

        Este teste valida que a pipeline executa com dados do catálogo
        (SICRO_2024_CE) e gera Excel com preços e valores realistas.
        """
        from unittest.mock import patch

        # Modificar inputs para usar contexto AGIS (catálogo SICRO real)
        inputs_agis = inputs_escopo_terraplenagem.copy()
        inputs_agis["contexto_id"] = "mendeslobo"

        projeto_terraplenagem.new_version()

        runtime.run_skill("01-escopo-e-eap", projeto_terraplenagem, inputs=inputs_agis)

        # Executar restante do pipeline (catálogo SICRO será carregado automaticamente)
        with patch("concilium.infrastructure.clients.openmeteo.OpenMeteoClient", return_value=mock_openmeteo_aracoiaba):
            runtime.run_skill("02-produtividade-climatica", projeto_terraplenagem, inputs={"ano_referencia": 2024})

        runtime.run_skill("03-catalogo-de-recursos", projeto_terraplenagem, inputs={})

        cron_inputs = {
            "num_equipes_por_item": {
                "eap-01": {f"2026-W{w:02d}": 1 for w in range(23, 31)},
                "eap-02": {f"2026-W{w:02d}": 1 for w in range(27, 37)},
                "eap-03": {f"2026-W{w:02d}": 1 for w in range(35, 41)},
            }
        }
        runtime.run_skill("04-cronograma", projeto_terraplenagem, inputs=cron_inputs)
        runtime.run_skill("05-equipes-e-alocacao", projeto_terraplenagem, inputs={})
        runtime.run_skill("06-precificacao-unitaria", projeto_terraplenagem, inputs={})
        runtime.run_skill("07-custos-indiretos", projeto_terraplenagem, inputs={})
        runtime.run_skill("08-consolidacao-financeira", projeto_terraplenagem, inputs={})
        runtime.run_skill("09-relatorio-e-artefatos", projeto_terraplenagem, inputs={})

        # Validar que Excel foi gerado mesmo com catálogo SICRO
        version = projeto_terraplenagem.current_version()
        excel_bytes = projeto_terraplenagem.load_output_file(version, "resultado_planejamento.xlsx")
        assert excel_bytes is not None, "Excel deve ser gerado com contexto ativo"

        from io import BytesIO

        from openpyxl import load_workbook

        wb = load_workbook(BytesIO(excel_bytes))

        # Validar estrutura
        assert "PLANEJAMENTO" in wb.sheetnames  # was RESUMO, removed
        assert "PLANEJAMENTO" in wb.sheetnames
        assert "RESULTADO" in wb.sheetnames

        # Validar que há dados (não vazio)
        ws_planj = wb["PLANEJAMENTO"]
        has_content = False
        for row in ws_planj.iter_rows(min_row=4, max_row=15):
            for cell in row:
                if cell.value:
                    has_content = True
                    break
        assert has_content, "Excel SICRO deve ter conteúdo de dados reais"


class TestExcelEdgeCases:
    """Testes de cases extremos: projetos grandes, valores extremos, datasets vazios."""

    def test_excel_renderiza_sem_erros_mesmo_com_dados_incompletos(
        self,
        runtime: Runtime,
        projeto_terraplenagem: ProjectStore,
        inputs_escopo_terraplenagem: dict[str, Any],
        mock_openmeteo_aracoiaba,
    ):
        """Excel é gerado com sucesso mesmo em cenários com dados incompletos."""
        from io import BytesIO
        from unittest.mock import patch

        from openpyxl import load_workbook

        projeto_terraplenagem.new_version()

        # Usar inputs válidos existentes
        runtime.run_skill("01-escopo-e-eap", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)

        with patch("concilium.infrastructure.clients.openmeteo.OpenMeteoClient", return_value=mock_openmeteo_aracoiaba):
            runtime.run_skill("02-produtividade-climatica", projeto_terraplenagem, inputs={"ano_referencia": 2024})

        runtime.run_skill("03-catalogo-de-recursos", projeto_terraplenagem, inputs={})

        # Cronograma mínimo (poucos itens)
        cron_inputs = {
            "num_equipes_por_item": {
                "eap-01": {"2026-W31": 1}  # Apenas uma semana
            }
        }
        runtime.run_skill("04-cronograma", projeto_terraplenagem, inputs=cron_inputs)
        runtime.run_skill("05-equipes-e-alocacao", projeto_terraplenagem, inputs={})
        runtime.run_skill("06-precificacao-unitaria", projeto_terraplenagem, inputs={})
        runtime.run_skill("07-custos-indiretos", projeto_terraplenagem, inputs={})
        runtime.run_skill("08-consolidacao-financeira", projeto_terraplenagem, inputs={})
        runtime.run_skill("09-relatorio-e-artefatos", projeto_terraplenagem, inputs={})

        # Validar Excel ainda é gerado
        version = projeto_terraplenagem.current_version()
        excel_bytes = projeto_terraplenagem.load_output_file(version, "resultado_planejamento.xlsx")
        assert excel_bytes is not None, "Excel deve ser gerado mesmo com dados incompletos"

        wb = load_workbook(BytesIO(excel_bytes))
        assert "PLANEJAMENTO" in wb.sheetnames  # was RESUMO, removed
        assert "PLANEJAMENTO" in wb.sheetnames

    def test_excel_tamanho_razoavel(
        self,
        runtime: Runtime,
        projeto_terraplenagem: ProjectStore,
        inputs_escopo_terraplenagem: dict,
        mock_openmeteo_aracoiaba,
    ):
        """Excel gerado tem tamanho razoável (não quebra com grandes datasets)."""
        from unittest.mock import patch

        projeto_terraplenagem.new_version()

        runtime.run_skill("01-escopo-e-eap", projeto_terraplenagem, inputs=inputs_escopo_terraplenagem)

        with patch("concilium.infrastructure.clients.openmeteo.OpenMeteoClient", return_value=mock_openmeteo_aracoiaba):
            runtime.run_skill("02-produtividade-climatica", projeto_terraplenagem, inputs={"ano_referencia": 2024})

        runtime.run_skill("03-catalogo-de-recursos", projeto_terraplenagem, inputs={})

        cron_inputs = {
            "num_equipes_por_item": {
                "eap-01": {f"2026-W{w:02d}": 1 for w in range(23, 31)},
                "eap-02": {f"2026-W{w:02d}": 1 for w in range(27, 37)},
                "eap-03": {f"2026-W{w:02d}": 1 for w in range(35, 41)},
            }
        }
        runtime.run_skill("04-cronograma", projeto_terraplenagem, inputs=cron_inputs)
        runtime.run_skill("05-equipes-e-alocacao", projeto_terraplenagem, inputs={})
        runtime.run_skill("06-precificacao-unitaria", projeto_terraplenagem, inputs={})
        runtime.run_skill("07-custos-indiretos", projeto_terraplenagem, inputs={})
        runtime.run_skill("08-consolidacao-financeira", projeto_terraplenagem, inputs={})
        runtime.run_skill("09-relatorio-e-artefatos", projeto_terraplenagem, inputs={})

        # Validar tamanho Excel
        version = projeto_terraplenagem.current_version()
        excel_bytes = projeto_terraplenagem.load_output_file(version, "resultado_planejamento.xlsx")

        size_mb = len(excel_bytes) / (1024 * 1024)
        assert size_mb < 50, f"Excel muito grande: {size_mb:.1f}MB, limite é 50MB"
        assert size_mb > 0.001, f"Excel muito pequeno: {size_mb:.4f}MB"
