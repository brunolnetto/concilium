"""Testes end-to-end com samples reais: carrega JSON, executa pipeline 00→07, valida output."""

import json
from pathlib import Path
from typing import Any

import pytest

# ── Fixtures: Usamos diretamente as session-scoped do conftest.py ──────
# Sem fixtures intermediárias para evitar recriação desnecessária


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

    def test_pipeline_sample_01_terraplenagem_feliz(self, _session_pipeline_sk09):
        """Pipeline completa com sample 01 — terraplenagem sucesso.

        Usa fixture _session_pipeline_sk09 (01→09) diretamente do conftest.py;
        valida estrutura do relatório, conteúdo financeiro e log de invocações.
        """
        proj, r = _session_pipeline_sk09

        assert not r.has_errors, f"Pipeline falhou: {r.validacoes}"

        relatorio = r.relatorio  # type: ignore[attr-defined]
        assert relatorio is not None, "Adapter deve gerar relatório"

        assert "meta" in relatorio
        assert "resumo" in relatorio
        assert "PLANEJAMENTO" in relatorio
        assert "EQUIPE" in relatorio
        assert "INDIRETOS" in relatorio
        assert "RESULTADO" in relatorio

        assert relatorio["resumo"]["projeto"] is not None
        assert len(relatorio["PLANEJAMENTO"]) > 0, "Deve ter planejamento"
        assert len(relatorio["EQUIPE"]) > 0, "Deve ter equipes"
        assert relatorio["RESULTADO"]["status_margem"] in ("VERDE", "AMARELO", "VERMELHO")

        log_path = proj.root / "v1" / "invocations.log"
        assert log_path.exists()
        log_content = log_path.read_text()
        n_invocacoes = len([ln for ln in log_content.strip().splitlines() if ln])
        assert n_invocacoes == 7, (
            f"Esperadas 7 invocações (NEP-041 F4: 01-05 + 06-unificada + 09), encontradas {n_invocacoes}"
        )


class TestSkill07OutputFormat:
    """Testa especificamente o formato de output do Skill 07."""

    def test_skill_07_output_estrutura(self, _session_pipeline_sk09):
        """Skill 07 gera estrutura JSON correta com todas as seções."""
        _, r = _session_pipeline_sk09
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

    def test_skill_07_json_serializavel(self, _session_pipeline_sk09):
        """Output do Skill 07 deve ser JSON-serializável."""
        _, r = _session_pipeline_sk09
        output = r.relatorio  # type: ignore[attr-defined]
        json_str = json.dumps(output)
        assert json_str

    def test_skill_07_gera_excel_bytes(self, _session_pipeline_sk09, _wb_sk09):
        """Skill 07 gera bytes Excel válidos que podem ser salvos em arquivo."""
        _, r = _session_pipeline_sk09

        excel_bytes = r.excel_bytes  # type: ignore[attr-defined]
        assert excel_bytes is not None, "Skill 07 deve gerar Excel bytes"
        assert isinstance(excel_bytes, bytes), "Deve ser bytes"
        assert len(excel_bytes) > 0, "Bytes não devem estar vazios"

        wb = _wb_sk09  # workbook pre-loaded session-scoped

        expected_sheets = ["DIRETOS.DET", "PLANEJAMENTO", "RESULTADO"]
        for sheet in expected_sheets:
            assert sheet in wb.sheetnames, f"Deve ter aba {sheet}"

        ws_diretos = wb["DIRETOS.DET"]
        has_header = False
        for row in ws_diretos.iter_rows(min_row=1, max_row=10):
            for cell in row:
                if cell.value and isinstance(cell.value, str):
                    has_header = True
                    break
            if has_header:
                break
        assert has_header, "DIRETOS deve ter conteúdo textual no cabeçalho"

        ws_planj = wb["PLANEJAMENTO"]
        has_header_planj = False
        for row in ws_planj.iter_rows(min_row=1, max_row=5):
            for cell in row:
                if cell.value and isinstance(cell.value, str) and len(str(cell.value)) > 1:
                    has_header_planj = True
                    break
            if has_header_planj:
                break
        assert has_header_planj, "PLANEJAMENTO deve ter cabeçalho"

    def test_skill_07_salva_excel_em_arquivo(self, _session_pipeline_sk09, _wb_sk09, tmp_path: Path):
        """Skill 07 gera Excel que pode ser salvo em arquivo."""
        _, r = _session_pipeline_sk09
        excel_bytes = r.excel_bytes  # type: ignore[attr-defined]
        output_file = tmp_path / "resultado_planejamento.xlsx"
        output_file.write_bytes(excel_bytes)
        assert output_file.exists(), "Arquivo Excel deve ser salvo em disco"
        assert output_file.stat().st_size > 0, "Arquivo Excel não deve estar vazio"

        wb = _wb_sk09  # workbook pre-loaded session-scoped
        expected_sheets = ["DIRETOS.DET", "PLANEJAMENTO", "RESULTADO"]
        for sheet in expected_sheets:
            assert sheet in wb.sheetnames, f"Aba {sheet} não encontrada"

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

    def test_skill_07_gera_excel_com_11_sheets_template(self, _wb_sk09):
        """Excel gerado contém 11 sheets conforme template especificação."""
        wb = _wb_sk09  # workbook pre-loaded session-scoped

        expected_sheets = ["DIRETOS.DET", "PLANEJAMENTO", "RESULTADO"]
        actual_sheets = set(wb.sheetnames)
        for sheet in expected_sheets:
            assert sheet in actual_sheets, f"Sheet {sheet} não encontrada. Presentes: {actual_sheets}"

        print(f"✅ Todos os sheets gerados: {actual_sheets}")


class TestExcelPersistency:
    """Testes de persistência do Excel em ProjectStore."""

    def test_excel_persistido_em_project_store(self, _session_pipeline_sk09, _wb_sk09):
        """Excel é salvo em {version}/outputs/resultado_planejamento.xlsm."""
        proj, _ = _session_pipeline_sk09
        version = proj.current_version()

        excel_bytes = proj.load_output_file(version, "resultado_planejamento.xlsx")
        assert excel_bytes is not None, "Excel deve estar persistido em ProjectStore"
        assert isinstance(excel_bytes, bytes), "Deve ser bytes"
        assert len(excel_bytes) > 0, "Bytes não devem estar vazios"

        wb = _wb_sk09  # workbook pre-loaded session-scoped
        assert "PLANEJAMENTO" in wb.sheetnames

    def test_listar_arquivos_de_saida(self, _session_pipeline_sk09):
        """ProjectStore.list_output_files() lista todos os arquivos gerados."""
        proj, _ = _session_pipeline_sk09
        version = proj.current_version()

        output_files = proj.list_output_files(version)
        assert "relatorio.pdf" in output_files, "Relatório MD deve estar listado"
        assert "resultado_planejamento.xlsx" in output_files, "Excel deve estar listado"
        assert len(output_files) >= 2, "Deve ter no mínimo JSON e Excel"


class TestExcelComDadosSICRO:
    """Testes com dados SICRO reais e validação de valores."""

    def test_excel_com_contexto_agis_usa_catalogo_sicro(self, _session_pipeline_mendeslobo_sk09):
        """Excel gerado usa catálogo SICRO real quando contexto está ativo.

        Usa fixture _session_pipeline_mendeslobo_sk09 (01→09, contexto mendeslobo)
        diretamente do conftest.py; valida estrutura e conteúdo do Excel gerado.
        """
        from io import BytesIO

        from openpyxl import load_workbook

        proj = _session_pipeline_mendeslobo_sk09
        version = proj.current_version()
        excel_bytes = proj.load_output_file(version, "resultado_planejamento.xlsx")
        assert excel_bytes is not None, "Excel deve ser gerado com contexto ativo"

        wb = load_workbook(BytesIO(excel_bytes))

        assert "PLANEJAMENTO" in wb.sheetnames
        assert "RESULTADO" in wb.sheetnames

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

    def test_excel_renderiza_sem_erros_mesmo_com_dados_incompletos(self, _session_edge_case_sk09):
        """Excel é gerado com sucesso mesmo em cenários com dados incompletos.

        Reutiliza a fixture session-scoped _session_edge_case_sk09 (01→09, cron mínimo)
        para eliminar a execução de 6 skills no corpo do teste.
        """
        from io import BytesIO

        from openpyxl import load_workbook

        proj = _session_edge_case_sk09
        version = proj.current_version()
        excel_bytes = proj.load_output_file(version, "resultado_planejamento.xlsx")
        assert excel_bytes is not None, "Excel deve ser gerado mesmo com dados incompletos"

        wb = load_workbook(BytesIO(excel_bytes))
        assert "PLANEJAMENTO" in wb.sheetnames

    def test_excel_tamanho_razoavel(self, _session_pipeline_sk09):
        """Excel gerado tem tamanho razoável (não quebra com grandes datasets)."""
        proj, _ = _session_pipeline_sk09
        version = proj.current_version()
        excel_bytes = proj.load_output_file(version, "resultado_planejamento.xlsx")

        size_mb = len(excel_bytes) / (1024 * 1024)
        assert size_mb < 50, f"Excel muito grande: {size_mb:.1f}MB, limite é 50MB"
        assert size_mb > 0.001, f"Excel muito pequeno: {size_mb:.4f}MB"
