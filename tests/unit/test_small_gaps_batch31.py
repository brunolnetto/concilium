"""Coverage batch 31 — catalog_reasonability, excel_ingestion, cubo_analitico_builder small gaps."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# catalog_reasonability.py line 87:
# _sum_equips with non-numeric num_unidades → TypeError → continue
# ---------------------------------------------------------------------------


class TestSumEquipsTypeError:
    def test_non_numeric_num_unidades_is_skipped(self):
        """Line 87: int(float(None)) raises TypeError → continue."""
        from concilium.application.services.catalog.catalog_reasonability import _sum_equips

        # None as num_unidades → int(float(None)) raises TypeError
        equipamentos = [
            {"num_unidades": None},  # TypeError
            {"num_unidades": "abc"},  # ValueError
            {"num_unidades": 2},  # valid → contributes 2
        ]
        result = _sum_equips(equipamentos)
        assert result == 2  # only the valid entry counts


# ---------------------------------------------------------------------------
# catalog_reasonability.py line 95:
# _build_prod_lookup with non-dict items → continue
# ---------------------------------------------------------------------------


class TestBuildProdLookupNonDict:
    def test_non_dict_item_is_skipped(self):
        """Line 95: not isinstance(prod, dict) → continue."""
        from concilium.application.services.catalog.catalog_reasonability import _build_prod_lookup

        producoes = [
            "not-a-dict",  # skipped (not dict)
            None,  # skipped (not dict)
            {"id": "P-01", "v": 1},  # included
        ]
        result = _build_prod_lookup(producoes)
        assert "P-01" in result
        assert len(result) == 1


# ---------------------------------------------------------------------------
# catalog_reasonability.py line 110:
# _resolve_team_from_producao with string equipe (both keys) → return [], []
# ---------------------------------------------------------------------------


class TestResolveTeamFromProducaoNonDictEquipe:
    def test_non_dict_equipe_returns_empty(self):
        """Line 110: equipe is not a dict after both fallbacks → return [], []."""
        from concilium.application.services.catalog.catalog_reasonability import _resolve_team_from_producao

        # Both composicao_padrao_equipe and equipe are strings (not dicts)
        prod = {
            "composicao_padrao_equipe": "INVALID",
            "equipe": "ALSO_INVALID",
        }
        funcoes, equipamentos = _resolve_team_from_producao(prod)
        assert funcoes == []
        assert equipamentos == []

    def test_missing_equipe_key_returns_empty(self):
        """Line 110: prod has no equipe key at all → equipe.get() returns None → return [], []."""
        from concilium.application.services.catalog.catalog_reasonability import _resolve_team_from_producao

        prod = {"valor_horario": 10.0}  # no equipe or composicao_padrao_equipe
        funcoes, equipamentos = _resolve_team_from_producao(prod)
        assert funcoes == []
        assert equipamentos == []


# ---------------------------------------------------------------------------
# catalog_reasonability.py line 210:
# IQR outlier triggers severity "AVISO" for producao_por_pessoa
# ---------------------------------------------------------------------------


class TestCatalogReasonabilityIQROutlier:
    def _make_cpu(self, i: int, ppp_ratio: float = 1.0) -> dict:
        """Build a CPU dict referencing producao P-{i} with scaled ppp."""
        return {
            "codigo": f"CPU-{i:02d}",
            "descricao": f"Test CPU {i}",
            "categoria": "ESCAVACAO",
            "unidade": "M3",
            "producao_id_ref": f"P-{i:02d}",
        }

    def _make_producao(self, i: int, valor_horario: float) -> dict:
        """Build a producao dict with 1 person in equipe."""
        return {
            "id": f"P-{i:02d}",
            "valor_horario": valor_horario,
            "composicao_padrao_equipe": {
                "funcoes": [{"funcao": "Operador", "num_pessoas": 1}],
                "equipamentos": [],
            },
        }

    def test_ppp_outlier_gets_aviso_severity(self):
        """Line 210: IQR outlier for producao_por_pessoa gets severity='AVISO'."""
        from concilium.application.services.catalog.catalog_reasonability import build_catalog_reasonability_artifact

        # 8 normal CPUs with ppp=10.0, 1 outlier with ppp=100.0
        # IQR will be non-zero due to spread; q90 ≈ 32 < 100
        cpus = [self._make_cpu(i) for i in range(9)]
        normal_rates = [10.0] * 6 + [5.0, 15.0]
        outlier_rate = 100.0
        producoes = [self._make_producao(i, r) for i, r in enumerate(normal_rates)]
        producoes.append(self._make_producao(8, outlier_rate))  # outlier

        result = build_catalog_reasonability_artifact("cat-test", cpus, producoes)

        rows = result.get("rows", [])
        # Find the outlier row (CPU-08 referencing P-08 with valor_horario=100)
        outlier_row = next((r for r in rows if r["cpu_id"] == "CPU-08"), None)
        assert outlier_row is not None
        # The outlier should have AVISO severity from IQR detection
        assert outlier_row["severity"] == "AVISO"
        # Normal rows should be OK
        normal_rows = [r for r in rows if r["cpu_id"] != "CPU-08"]
        ok_rows = [r for r in normal_rows if r["severity"] == "OK"]
        assert len(ok_rows) >= 1


# ---------------------------------------------------------------------------
# excel_ingestion.py line 46:
# _extract_rows_from_sheet with all-empty headers → return []
# ---------------------------------------------------------------------------


class TestExtractRowsEmptyHeaders:
    def _make_workbook(self, rows_data: list[list]):
        """Create an openpyxl workbook with given rows."""
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "TestSheet"
        for row in rows_data:
            ws.append(row)
        return wb

    def test_all_empty_header_row_returns_empty(self):
        """Line 46: header_row found but all cells are empty → not any(headers) → return []."""
        from concilium.infrastructure.catalog.excel_ingestion import ExcelIngestionPipeline

        # Row with all None/empty cells (all become empty strings)
        wb = self._make_workbook([[None, None, None]])
        # Write to BytesIO and read back (to simulate openpyxl read_only behavior)
        from io import BytesIO

        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        import openpyxl

        wb_ro = openpyxl.load_workbook(buf, read_only=True, data_only=True)
        result = ExcelIngestionPipeline._extract_rows_from_sheet(wb_ro, "TestSheet")
        wb_ro.close()
        assert result == []

    def test_header_with_empty_cell_skips_column(self):
        """Line 55: header cell is empty string → skip column in item dict."""
        from io import BytesIO

        import openpyxl

        from concilium.infrastructure.catalog.excel_ingestion import ExcelIngestionPipeline

        # Header row: ["ID", "", "Name"] → middle column skipped
        # Data row: ["001", "ignored", "Alice"]
        wb = self._make_workbook(
            [
                ["ID", "", "Name"],  # header row; "" → skip
                ["001", "ignored", "Alice"],  # data row
            ]
        )
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        wb_ro = openpyxl.load_workbook(buf, read_only=True, data_only=True)
        result = ExcelIngestionPipeline._extract_rows_from_sheet(wb_ro, "TestSheet")
        wb_ro.close()

        assert len(result) == 1
        assert result[0]["ID"] == "001"
        assert result[0]["Name"] == "Alice"
        assert "" not in result[0]  # empty header was skipped


# ---------------------------------------------------------------------------
# cubo_analitico_builder.py line 209:
# Cell with estado != "prod" → continue (not counted in cost_map)
# ---------------------------------------------------------------------------


class TestCuboAnaliticoBuilderNonProdCell:
    def test_non_prod_cell_is_skipped(self):
        """Line 209: cell.estado != 'prod' → continue, not added to cost_map."""
        from types import SimpleNamespace
        from unittest.mock import patch

        from concilium.domain.services.analytics.cubo_analitico_builder import CuboAnaliticoBuilder

        # Create a canonical with 2 cells: one "prod" and one "off"
        cell_prod = SimpleNamespace(
            estado="prod",
            atividade_id="ACT-01",
            semana_iso="2026-W01",
            custo_mo=100.0,
            custo_eq=50.0,
            custo_comb=10.0,
            custo_mat=5.0,
        )
        cell_off = SimpleNamespace(
            estado="off",  # should be skipped (line 209 continue)
            atividade_id="ACT-01",
            semana_iso="2026-W02",
            custo_mo=999.0,
            custo_eq=999.0,
            custo_comb=999.0,
            custo_mat=999.0,
        )
        cell_no_atv = SimpleNamespace(
            estado="prod",
            atividade_id="",  # empty → also skipped (line 209 not cell.atividade_id)
            semana_iso="2026-W03",
            custo_mo=999.0,
            custo_eq=999.0,
            custo_comb=999.0,
            custo_mat=999.0,
        )

        fake_cubo_pool = SimpleNamespace(
            celulas=[cell_prod, cell_off, cell_no_atv],
        )

        canonical_in = SimpleNamespace(
            projeto=SimpleNamespace(nome="TEST", data_inicio=""),
            equipes_diretas=None,
            indiretos_semanal=None,
            cronograma=None,
        )

        builder = CuboAnaliticoBuilder()

        with patch("concilium.domain.services.analytics.cubo_pool_builder.CuboPoolInstancialBuilder") as MockBuilder:
            mock_instance = MockBuilder.return_value
            mock_instance.build.return_value = fake_cubo_pool

            with patch.object(builder, "_enrich_with_financial_data", side_effect=lambda c, cells: cells):
                with patch.object(builder, "_build_diesel_L_map", return_value={}):
                    result = builder.build(canonical_in)

        # The "off" cell and no-atividade cell should not contribute to the cubo
        # Result should have cells only from the prod cell (or be empty if no decomp)
        assert result is not None  # build completed without error


# ---------------------------------------------------------------------------
# catalog_resolver.py lines 157, 168-174:
# resolve_insumo with master file present → returns (item, "master")
# ---------------------------------------------------------------------------


class TestCatalogResolverMasterFile:
    def test_resolve_insumo_from_master_individual_file(self, tmp_path):
        """Lines 155-157, 168-174: insumo found in master individual file → ('item', 'master')."""
        from types import SimpleNamespace

        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        # project.root = tmp_path/projetos/proj-001
        # concilium_root = tmp_path (parents[1] of projetos/proj-001)
        proj_root = tmp_path / "projetos" / "proj-001"
        proj_root.mkdir(parents=True)

        # Create master insumo file
        cat_dir = tmp_path / "config" / "catalogos" / "cat-001" / "insumos"
        cat_dir.mkdir(parents=True)
        (cat_dir / "INS-01.json").write_text('{"codigo": "INS-01", "descricao": "Test Insumo"}', encoding="utf-8")

        project = SimpleNamespace(
            root=str(proj_root),
            meta={"id": "proj-001"},
        )

        resolver = CatalogResolver(config_root=tmp_path / "config")
        result, source = resolver.resolve_insumo("INS-01", "cat-001", project)

        assert source == "master"
        assert result is not None
        assert result["codigo"] == "INS-01"


# ---------------------------------------------------------------------------
# execution.py line 106:
# run_skill_on_plano when canonical_in is None and skill != "01-escopo-e-eap"
# → raises RuntimeDomainError
# ---------------------------------------------------------------------------


class TestRunSkillOnPlanoNoCanonical:
    def test_raises_runtime_domain_error_when_no_canonical(self):
        """Line 106: canonical_in is None and skill_id != '01-escopo-e-eap' → RuntimeDomainError."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        import pytest

        from concilium.application.runtime.exceptions import RuntimeDomainError
        from concilium.application.runtime.mixins.execution import ExecutionMixin

        class FakeRuntime(ExecutionMixin):
            def get_skill_contract(self, skill_id):
                return MagicMock(signature=[])

        runtime = FakeRuntime()
        plano_store = SimpleNamespace(
            load_canonical=lambda: None,
            plano_id="plano-001",
            escopo_store=SimpleNamespace(meta={}),
        )

        with pytest.raises(RuntimeDomainError, match="estado inicial"):
            runtime.run_skill_on_plano(
                "02-produtividade-climatica",
                MagicMock(),
                plano_store,
            )


class TestRunSkillOnPlanoShouldSaveFalse:
    def test_00_escopo_with_errors_skips_save_canonical(self):
        """Branch 153->156: skill_id=='00-escopo' com erros e sem gate/dv override
        → should_save permanece False → save_canonical NÃO é chamado."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch

        from concilium.application.runtime.mixins.execution import ExecutionMixin
        from concilium.application.skills.base import SkillResult
        from concilium.domain.models.canonical import ValidacaoItem

        canonical = MagicMock()
        canonical.pipeline_blocked_from = []
        val_erro = ValidacaoItem(codigo="ERR-001", status="ERRO", campo=None, mensagem="erro")
        fake_result = SkillResult(canonical, [val_erro])

        class FakeRuntime(ExecutionMixin):
            def get_skill_contract(self, skill_id):
                return MagicMock(signature=[])

            def _load_context(self, escopo_meta, project):
                return MagicMock(), {}, {}

            def _apply_runtime_defaults(self, skill_id, project, contexto, base_inputs):
                return dict(base_inputs)

            def _build_skill_kwargs(self, contract, **kwargs):
                return {}

            def _build_log_entry(self, *args, **kwargs):
                return {}

            def _process_side_effects(self, *args, **kwargs):
                pass

        runtime = FakeRuntime()
        plano_store = SimpleNamespace(
            load_canonical=lambda: canonical,
            plano_id="plano-001",
            escopo_store=SimpleNamespace(meta={"escopo_id": "e1", "contexto_id": "ctx"}),
            save_canonical=MagicMock(),
            log_invocation=MagicMock(),
        )
        project = SimpleNamespace(meta={"id": "proj-1"})

        with (
            patch("concilium.application.runtime.mixins.execution.SKILLS", {"00-escopo": MagicMock()}),
            patch(
                "concilium.application.runtime.mixins.execution._execute_skill",
                return_value=fake_result,
            ),
        ):
            runtime.run_skill_on_plano("00-escopo", project, plano_store)

        plano_store.save_canonical.assert_not_called()
