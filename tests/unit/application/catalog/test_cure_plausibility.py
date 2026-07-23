"""Testes de cobertura para concilium.application.catalog.cure_plausibility.

Cobre helpers (_norm, _is_estagiario, _horas_mes), CureReport, os 4 estágios de
curação automática (erros físicos, duplicatas, stale RFI, locação mensal),
report_manual e o entrypoint main() (dry-run e --apply).
"""

from __future__ import annotations

import json
import sys

import pytest

from concilium.application.catalog import cure_plausibility as cp

# ─── Helpers internos ────────────────────────────────────────────────────────


class TestNowIso:
    def test_returns_iso_date_string(self):
        result = cp._now_iso()
        assert len(result) == 10
        assert result.count("-") == 2


class TestNorm:
    def test_removes_accents_and_lowercases(self):
        assert cp._norm("ESTAGIÁRIO") == "estagiario"

    def test_collapses_whitespace(self):
        assert cp._norm("  a   b  ") == "a b"


class TestIsEstagiario:
    def test_true_when_keyword_in_descricao(self):
        assert cp._is_estagiario({"descricao": "Estagiário de Obras", "codigo": "X1"}) is True

    def test_true_when_keyword_in_codigo(self):
        assert cp._is_estagiario({"descricao": "Ajudante", "codigo": "MO-BOLSISTA"}) is True

    def test_false_when_no_keyword(self):
        assert cp._is_estagiario({"descricao": "Pedreiro", "codigo": "MO-PEDREIRO"}) is False

    def test_handles_missing_fields(self):
        assert cp._is_estagiario({}) is False


class TestHorasMes:
    def test_default_when_missing(self):
        assert cp._horas_mes({}) == cp.HORAS_MES_PADRAO

    def test_default_when_atributos_none(self):
        assert cp._horas_mes({"atributos_especificos": None}) == cp.HORAS_MES_PADRAO

    def test_parses_valid_value(self):
        assert cp._horas_mes({"atributos_especificos": {"horas_mes": "180"}}) == 180.0

    def test_default_when_zero(self):
        assert cp._horas_mes({"atributos_especificos": {"horas_mes": 0}}) == cp.HORAS_MES_PADRAO

    def test_default_on_invalid_value(self):
        assert cp._horas_mes({"atributos_especificos": {"horas_mes": "abc"}}) == cp.HORAS_MES_PADRAO


class TestCureReport:
    def test_add_methods_append(self):
        report = cp.CureReport()
        report.add_fixed("a")
        report.add_manual("b")
        report.add_skipped("c")
        assert report.fixed == ["a"]
        assert report.manual == ["b"]
        assert report.skipped == ["c"]


# ─── cure_erros_fisicos ──────────────────────────────────────────────────────


class TestCureErrosFisicos:
    def test_skips_non_mao_obra(self):
        report = cp.CureReport()
        insumos = [{"codigo": "EQ-1", "tipo": "EQUIPAMENTO", "preco_unitario": 1.0}]
        result = cp.cure_erros_fisicos(insumos, report, apply=False)
        assert result == insumos
        assert report.fixed == []
        assert report.manual == []

    def test_encargos_above_max_fixed_dry_run(self):
        report = cp.CureReport()
        insumos = [
            {
                "codigo": "MO-1",
                "tipo": "MAO_OBRA",
                "preco_unitario": 5000.0,
                "atributos_especificos": {"percentual_encargos_local": 1.777},
            }
        ]
        result = cp.cure_erros_fisicos(insumos, report, apply=False)
        assert any("percentual_encargos_local" in m for m in report.fixed)
        # dry-run: original list returned unchanged (not the deep copy)
        assert result is insumos

    def test_encargos_above_max_fixed_apply(self):
        report = cp.CureReport()
        insumos = [
            {
                "codigo": "MO-1",
                "tipo": "MAO_OBRA",
                "preco_unitario": 5000.0,
                "atributos_especificos": {"percentual_encargos_local": 1.777},
            }
        ]
        result = cp.cure_erros_fisicos(insumos, report, apply=True)
        assert result[0]["atributos_especificos"]["percentual_encargos_local"] == pytest.approx(0.777, abs=1e-4)

    def test_encargos_below_max_not_touched(self):
        report = cp.CureReport()
        insumos = [
            {
                "codigo": "MO-1",
                "tipo": "MAO_OBRA",
                "preco_unitario": 5000.0,
                "atributos_especificos": {"percentual_encargos_local": 1.2},
            }
        ]
        cp.cure_erros_fisicos(insumos, report, apply=True)
        assert report.fixed == []

    def test_encargos_non_numeric_is_ignored(self):
        report = cp.CureReport()
        insumos = [
            {
                "codigo": "MO-1",
                "tipo": "MAO_OBRA",
                "preco_unitario": 5000.0,
                "atributos_especificos": {"percentual_encargos_local": "not-a-number"},
            }
        ]
        # Should not raise, just skip the (a) branch
        result = cp.cure_erros_fisicos(insumos, report, apply=True)
        assert result[0]["atributos_especificos"]["percentual_encargos_local"] == "not-a-number"

    def test_preco_abaixo_minimo_com_referencia_rfi_apply(self):
        report = cp.CureReport()
        insumos = [{"codigo": "MO-P0001", "tipo": "MAO_OBRA", "preco_unitario": 100.0}]
        result = cp.cure_erros_fisicos(insumos, report, apply=True)
        assert result[0]["preco_unitario"] == cp.RFI_PRECO_REFERENCIA["MO-P0001"]
        assert "_cure_preco_at" in result[0]
        assert any("preco_unitario" in m for m in report.fixed)

    def test_preco_abaixo_minimo_com_referencia_rfi_dry_run(self):
        report = cp.CureReport()
        insumos = [{"codigo": "MO-P0001", "tipo": "MAO_OBRA", "preco_unitario": 100.0}]
        result = cp.cure_erros_fisicos(insumos, report, apply=False)
        assert result[0]["preco_unitario"] == 100.0
        assert any("preco_unitario" in m for m in report.fixed)

    def test_preco_abaixo_minimo_sem_referencia_vai_para_manual(self):
        report = cp.CureReport()
        insumos = [{"codigo": "MO-9999", "tipo": "MAO_OBRA", "preco_unitario": 100.0}]
        cp.cure_erros_fisicos(insumos, report, apply=True)
        assert report.fixed == []
        assert any("abaixo do mínimo legal" in m for m in report.manual)

    def test_estagiario_below_minimum_is_not_flagged(self):
        report = cp.CureReport()
        insumos = [
            {
                "codigo": "MO-EST-1",
                "tipo": "MAO_OBRA",
                "descricao": "Estagiário de Engenharia",
                "preco_unitario": 100.0,
            }
        ]
        cp.cure_erros_fisicos(insumos, report, apply=True)
        assert report.fixed == []
        assert report.manual == []

    def test_preco_within_normal_range_not_flagged(self):
        report = cp.CureReport()
        insumos = [{"codigo": "MO-OK", "tipo": "MAO_OBRA", "preco_unitario": 3000.0}]
        cp.cure_erros_fisicos(insumos, report, apply=True)
        assert report.fixed == []
        assert report.manual == []


# ─── cure_duplicatas ─────────────────────────────────────────────────────────


class TestBuildDupMap:
    def test_no_duplicates_returns_empty(self):
        insumos = [
            {"codigo": "MO-A", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 10.0},
            {"codigo": "MO-B", "tipo": "MAO_OBRA", "descricao": "Servente", "preco_unitario": 20.0},
        ]
        assert cp._build_dup_map(insumos) == {}

    def test_ignores_non_mao_obra(self):
        insumos = [
            {"codigo": "EQ-A", "tipo": "EQUIPAMENTO", "descricao": "Guindaste", "preco_unitario": 10.0},
            {"codigo": "EQ-B", "tipo": "EQUIPAMENTO", "descricao": "Guindaste", "preco_unitario": 10.0},
        ]
        assert cp._build_dup_map(insumos) == {}

    def test_detects_p_code_duplicate_of_mo_name(self):
        insumos = [
            {"codigo": "MO-PEDREIRO", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 10.0},
            {"codigo": "P0001", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 10.0},
        ]
        dup_map = cp._build_dup_map(insumos)
        assert dup_map == {"P0001": "MO-PEDREIRO"}

    def test_falls_back_to_first_code_when_all_look_like_p_codes(self):
        insumos = [
            {"codigo": "MO-P0001", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 10.0},
            {"codigo": "P0002", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 10.0},
        ]
        dup_map = cp._build_dup_map(insumos)
        # canonical falls back to codes[0] since none match the "not P####" pattern
        assert dup_map == {"P0002": "MO-P0001"}


class TestCureDuplicatas:
    def test_no_duplicates_returns_inputs_unchanged(self):
        report = cp.CureReport()
        insumos = [{"codigo": "MO-A", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 10.0}]
        producoes = [{"id": "PR-1"}]
        result_ins, result_prod = cp.cure_duplicatas(insumos, producoes, report, apply=True)
        assert result_ins is insumos
        assert result_prod is producoes
        assert report.fixed == []

    def test_apply_removes_duplicates_and_updates_ref_externa(self):
        report = cp.CureReport()
        insumos = [
            {"codigo": "MO-PEDREIRO", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 10.0},
            {"codigo": "P0001", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 10.0},
        ]
        producoes = [
            {
                "id": "PR-1",
                "composicao_padrao_equipe": {
                    "funcoes": [
                        {"funcao_id": "P0001", "qtd": 1},
                        {"funcao_id": "MO-PEDREIRO", "qtd": 2},  # não está no dup_map -> ramo else do loop
                    ]
                },
            }
        ]
        result_ins, result_prod = cp.cure_duplicatas(insumos, producoes, report, apply=True)
        codigos = {i["codigo"] for i in result_ins}
        assert "P0001" not in codigos
        canon = next(i for i in result_ins if i["codigo"] == "MO-PEDREIRO")
        assert canon["codigo_referencia_externa"] == "P0001"
        funcoes = result_prod[0]["composicao_padrao_equipe"]["funcoes"]
        assert funcoes[0]["funcao_id"] == "MO-PEDREIRO"
        assert funcoes[1]["funcao_id"] == "MO-PEDREIRO"  # já era o canônico, não mapeado
        assert any("Removidos" in m for m in report.fixed)

    def test_existing_codigo_referencia_externa_is_extended_not_duplicated(self):
        report = cp.CureReport()
        insumos = [
            {
                "codigo": "MO-PEDREIRO",
                "tipo": "MAO_OBRA",
                "descricao": "Pedreiro",
                "preco_unitario": 10.0,
                "codigo_referencia_externa": "P0001",
            },
            {"codigo": "P0001", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 10.0},
        ]
        cp.cure_duplicatas(insumos, [], report, apply=True)
        # p_code already present in existing external refs -> not duplicated in report/fixed message
        assert not any("codigo_referencia_externa +=" in m for m in report.fixed)

    def test_dry_run_lists_up_to_five_and_reports_overflow(self):
        report = cp.CureReport()
        insumos = [{"codigo": "MO-PEDREIRO", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 10.0}]
        for i in range(7):
            insumos.append({"codigo": f"P000{i}", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 10.0})
        result_ins, result_prod = cp.cure_duplicatas(insumos, [], report, apply=False)
        assert result_ins is insumos
        assert any("... e mais" in m for m in report.fixed)

    def test_dry_run_updates_producoes_report_without_mutating(self):
        report = cp.CureReport()
        insumos = [
            {"codigo": "MO-PEDREIRO", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 10.0},
            {"codigo": "P0001", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 10.0},
        ]
        producoes = [{"id": "PR-1", "equipe": {"funcoes": [{"funcao_id": "P0001"}]}}]
        result_ins, result_prod = cp.cure_duplicatas(insumos, producoes, report, apply=False)
        assert result_prod is producoes
        # funcao_id unchanged in dry-run
        assert producoes[0]["equipe"]["funcoes"][0]["funcao_id"] == "P0001"
        assert any("referência(s) de funcao_id seriam atualizadas" in m for m in report.fixed)

    def test_prod_with_equipe_key_variant_and_missing_canonical_insumo(self):
        report = cp.CureReport()
        # Canonical entry not present in insumos list (defensive branch: canon_ins is None)
        insumos = [{"codigo": "P0001", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 10.0}]
        # Force a dup_map manually by monkeypatching is complex; instead exercise via
        # two P#### codes with same key so canonical is codes[0] and both are MAO_OBRA.
        insumos.append({"codigo": "P0002", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 10.0})
        producoes = [{"id": "PR-1", "equipe": {"funcoes": [{"funcao_id": "P0002"}]}}]
        result_ins, result_prod = cp.cure_duplicatas(insumos, producoes, report, apply=True)
        assert result_prod[0]["equipe"]["funcoes"][0]["funcao_id"] == "P0001"


# ─── cure_stale_rfi ──────────────────────────────────────────────────────────


class TestCureStaleRfi:
    def test_no_rfi_date_no_changes(self):
        report = cp.CureReport()
        insumos = [{"codigo": "MO-1", "data_referencia_preco": "2020-01-01"}]
        result = cp.cure_stale_rfi(insumos, report, apply=True)
        assert result[0]["data_referencia_preco"] == "2020-01-01"
        assert report.fixed == []

    def test_rfi_updated_at_propagates_when_apply(self):
        report = cp.CureReport()
        insumos = [
            {"codigo": "MO-1", "data_referencia_preco": "2020-01-01", "_rfi_updated_at": "2025-06-01"},
        ]
        result = cp.cure_stale_rfi(insumos, report, apply=True)
        assert result[0]["data_referencia_preco"] == "2025-06-01"
        assert any("STALE" in m for m in report.fixed)

    def test_rfi_imported_at_used_as_fallback(self):
        report = cp.CureReport()
        insumos = [
            {"codigo": "MO-1", "data_referencia_preco": "2020-01-01", "_rfi_imported_at": "2025-07-01"},
        ]
        result = cp.cure_stale_rfi(insumos, report, apply=True)
        assert result[0]["data_referencia_preco"] == "2025-07-01"

    def test_dry_run_reports_but_does_not_change(self):
        report = cp.CureReport()
        insumos = [
            {"codigo": "MO-1", "data_referencia_preco": "2020-01-01", "_rfi_updated_at": "2025-06-01"},
        ]
        result = cp.cure_stale_rfi(insumos, report, apply=False)
        assert result is insumos
        assert result[0]["data_referencia_preco"] == "2020-01-01"
        assert any("STALE" in m for m in report.fixed)

    def test_current_equal_to_rfi_date_no_change_reported(self):
        report = cp.CureReport()
        insumos = [
            {"codigo": "MO-1", "data_referencia_preco": "2025-06-01", "_rfi_updated_at": "2025-06-01"},
        ]
        cp.cure_stale_rfi(insumos, report, apply=True)
        assert report.fixed == []


# ─── cure_locacao_mensal ─────────────────────────────────────────────────────


class TestCureLocacaoMensal:
    def test_skips_non_equipamento(self):
        report = cp.CureReport()
        insumos = [{"codigo": "MO-1", "tipo": "MAO_OBRA", "preco_unitario": 10.0}]
        cp.cure_locacao_mensal(insumos, report, apply=True)
        assert any("todos têm valor_locacao_mensal" in m for m in report.skipped)

    def test_skips_zero_preco(self):
        report = cp.CureReport()
        insumos = [{"codigo": "EQ-1", "tipo": "EQUIPAMENTO", "preco_unitario": 0}]
        cp.cure_locacao_mensal(insumos, report, apply=True)
        assert report.fixed == []
        assert report.skipped != []

    def test_skips_when_already_has_valor_locacao_mensal(self):
        report = cp.CureReport()
        insumos = [
            {
                "codigo": "EQ-1",
                "tipo": "EQUIPAMENTO",
                "preco_unitario": 10.0,
                "atributos_especificos": {"valor_locacao_mensal": 2200.0},
            }
        ]
        cp.cure_locacao_mensal(insumos, report, apply=True)
        assert report.fixed == []

    def test_derives_valor_locacao_mensal_with_default_horas(self):
        report = cp.CureReport()
        insumos = [{"codigo": "EQ-1", "tipo": "EQUIPAMENTO", "preco_unitario": 10.0}]
        result = cp.cure_locacao_mensal(insumos, report, apply=True)
        assert result[0]["atributos_especificos"]["valor_locacao_mensal"] == pytest.approx(2200.0)
        assert any("derivado" in m for m in report.fixed)

    def test_derives_valor_locacao_mensal_with_custom_horas_dry_run(self):
        report = cp.CureReport()
        insumos = [
            {
                "codigo": "EQ-1",
                "tipo": "EQUIPAMENTO",
                "preco_unitario": 10.0,
                "atributos_especificos": {"horas_mes": 100},
            }
        ]
        result = cp.cure_locacao_mensal(insumos, report, apply=False)
        assert result is insumos
        assert "valor_locacao_mensal" not in insumos[0]["atributos_especificos"]
        assert any("1000.0" in m or "1000" in m for m in report.fixed)


# ─── report_manual ───────────────────────────────────────────────────────────


class TestReportManual:
    def test_flags_producao_sem_composicao(self):
        report = cp.CureReport()
        producoes = [{"id": "PR-1", "valor_horario": 100.0}]
        cp.report_manual([], producoes, report)
        assert any("sem composição de equipe" in m for m in report.manual)

    def test_producao_with_composicao_not_flagged(self):
        report = cp.CureReport()
        producoes = [{"id": "PR-1", "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "MO-1"}]}}]
        cp.report_manual([], producoes, report)
        assert report.manual == []

    def test_producao_with_equipamentos_only_not_flagged(self):
        report = cp.CureReport()
        producoes = [{"id": "PR-1", "equipe": {"equipamentos": [{"equipamento_id": "EQ-1"}]}}]
        cp.report_manual([], producoes, report)
        assert report.manual == []

    def test_flags_mao_obra_with_group_like_name(self):
        report = cp.CureReport()
        insumos = [{"codigo": "MO-X", "tipo": "MAO_OBRA", "descricao": "Sala Técnica"}]
        cp.report_manual(insumos, [], report)
        assert any("insumo MAO_OBRA com nome de grupo" in m for m in report.manual)

    def test_does_not_flag_non_mao_obra_with_group_like_name(self):
        report = cp.CureReport()
        insumos = [{"codigo": "EQ-X", "tipo": "EQUIPAMENTO", "descricao": "Sala Técnica"}]
        cp.report_manual(insumos, [], report)
        assert report.manual == []

    def test_does_not_flag_normal_descriptions(self):
        report = cp.CureReport()
        insumos = [{"codigo": "MO-X", "tipo": "MAO_OBRA", "descricao": "Pedreiro"}]
        cp.report_manual(insumos, [], report)
        assert report.manual == []


# ─── main() ──────────────────────────────────────────────────────────────────


def _write_bundle(path, insumos=None, producoes=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    bundle = {"insumos": insumos or [], "producoes": producoes or []}
    path.write_text(json.dumps(bundle), encoding="utf-8")
    return bundle


class TestMain:
    def test_bundle_not_found_exits_1(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(cp, "ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["cure_plausibility.py", "--contexto", "nope"])
        with pytest.raises(SystemExit) as exc:
            cp.main()
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "Bundle não encontrado" in captured.err

    def test_dry_run_no_manual_items_exits_0(self, tmp_path, monkeypatch, capsys):
        bundle_path = tmp_path / "config/catalogos/mendeslobo/.catalog_bundle.json"
        _write_bundle(
            bundle_path,
            insumos=[{"codigo": "MO-OK", "tipo": "MAO_OBRA", "preco_unitario": 3000.0}],
            producoes=[],
        )
        monkeypatch.setattr(cp, "ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["cure_plausibility.py", "--contexto", "mendeslobo"])
        with pytest.raises(SystemExit) as exc:
            cp.main()
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "DRY-RUN" in out

    def test_dry_run_with_manual_items_exits_1(self, tmp_path, monkeypatch, capsys):
        bundle_path = tmp_path / "config/catalogos/mendeslobo/.catalog_bundle.json"
        _write_bundle(
            bundle_path,
            insumos=[{"codigo": "MO-9999", "tipo": "MAO_OBRA", "preco_unitario": 100.0}],
            producoes=[{"id": "PR-1", "valor_horario": 10.0}],
        )
        monkeypatch.setattr(cp, "ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["cure_plausibility.py", "--contexto", "mendeslobo"])
        with pytest.raises(SystemExit) as exc:
            cp.main()
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "Intervenção manual necessária" in out

    def test_apply_writes_bundle_and_validates(self, tmp_path, monkeypatch, capsys):
        bundle_path = tmp_path / "config/catalogos/mendeslobo/.catalog_bundle.json"
        _write_bundle(
            bundle_path,
            insumos=[{"codigo": "MO-OK", "tipo": "MAO_OBRA", "preco_unitario": 3000.0}],
            producoes=[],
        )
        monkeypatch.setattr(cp, "ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["cure_plausibility.py", "--contexto", "mendeslobo", "--apply"])
        # main() does not sys.exit() in apply mode
        cp.main()
        saved = json.loads(bundle_path.read_text(encoding="utf-8"))
        assert saved["insumos"][0]["codigo"] == "MO-OK"
        out = capsys.readouterr().out
        assert "APPLY" in out
        assert "Bundle salvo" in out
        assert "Pós-curação" in out

    def test_apply_with_fixes_and_residual_errors(self, tmp_path, monkeypatch, capsys):
        """Cobre: loop de impressão de report.fixed (apply=True), o ramo em que
        report.skipped fica vazio (equipamento foi de fato corrigido) e o status
        residual 'ATENÇÃO' quando erros persistem pós-curação (item sem
        referência RFI não é corrigível automaticamente)."""
        bundle_path = tmp_path / "config/catalogos/mendeslobo/.catalog_bundle.json"
        _write_bundle(
            bundle_path,
            insumos=[
                # EQUIPAMENTO sem valor_locacao_mensal -> gera report.fixed e n!=0 (skipped fica vazio)
                {"codigo": "EQ-1", "tipo": "EQUIPAMENTO", "preco_unitario": 10.0},
                # MAO_OBRA abaixo do minimo sem referencia RFI -> vai para manual, erro residual persiste
                {"codigo": "MO-9999", "tipo": "MAO_OBRA", "preco_unitario": 100.0},
            ],
            producoes=[],
        )
        monkeypatch.setattr(cp, "ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["cure_plausibility.py", "--contexto", "mendeslobo", "--apply"])
        cp.main()
        out = capsys.readouterr().out
        assert "valor_locacao_mensal" in out  # report.fixed foi impresso com prefixo ✓
        assert "ATENÇÃO" in out  # erro residual (MO-9999 continua abaixo do mínimo)

    def test_apply_uses_produtividades_key_when_producoes_absent(self, tmp_path, monkeypatch, capsys):
        bundle_path = tmp_path / "config/catalogos/mendeslobo/.catalog_bundle.json"
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle = {"insumos": [], "produtividades": []}
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
        monkeypatch.setattr(cp, "ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["cure_plausibility.py", "--contexto", "mendeslobo", "--apply"])
        cp.main()
        saved = json.loads(bundle_path.read_text(encoding="utf-8"))
        assert "produtividades" in saved
        assert "producoes" not in saved


def test_main_module_guard_invokes_main(monkeypatch):
    """Executing cure_plausibility.py as __main__ reaches the
    `if __name__ == "__main__": main()` guard at the bottom of the module.
    A nonexistent --contexto makes main() exit(1) quickly via the
    'Bundle não encontrado' path, without touching real catalog data."""
    import runpy

    monkeypatch.setattr(sys, "argv", ["cure_plausibility.py", "--contexto", "contexto-inexistente-b100"])

    _mod = "concilium.application.catalog.cure_plausibility"
    _saved = sys.modules.pop(_mod, None)
    try:
        with pytest.raises(SystemExit) as exc:
            runpy.run_module(_mod, run_name="__main__", alter_sys=False)
        assert exc.value.code == 1
    finally:
        if _saved is not None:
            sys.modules[_mod] = _saved
