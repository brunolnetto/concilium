"""Testes de cobertura para concilium.application.catalog.cure_plausibility.

Cobre helpers (_norm, _is_estagiario, _horas_mes), CureReport, os 4 estágios de
curação automática (erros físicos, duplicatas, stale RFI, locação mensal),
report_manual e o entrypoint main() (dry-run e --apply).
"""

from __future__ import annotations

import copy
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


class TestPrecoHora:
    def test_unidade_h_usa_preco_direto(self):
        assert cp._preco_hora({"preco_unitario": 26.9105, "unidade": "h"}) == 26.9105

    def test_unidade_hr_usa_preco_direto(self):
        assert cp._preco_hora({"preco_unitario": 30.0, "unidade": "hr"}) == 30.0

    def test_unidade_mes_divide_por_horas_mes(self):
        assert cp._preco_hora({"preco_unitario": 1830.51, "unidade": "mes"}) == 1830.51 / cp.HORAS_MES_PADRAO

    def test_unidade_ausente_assume_mes(self):
        assert cp._preco_hora({"preco_unitario": 1830.51}) == 1830.51 / cp.HORAS_MES_PADRAO


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

    def test_unidade_h_preco_plausivel_nao_e_falso_positivo(self):
        """Regressão do bug real (catálogo mendeslobo): insumo unidade="h" já é taxa
        horária com encargos — não deve ser dividido por horas_mes de novo."""
        report = cp.CureReport()
        insumos = [
            {
                "codigo": "AGIS-FN-AJUD",
                "tipo": "MAO_OBRA",
                "descricao": "Ajudante",
                "unidade": "h",
                "preco_unitario": 19.45,
            }
        ]
        cp.cure_erros_fisicos(insumos, report, apply=True)
        assert report.fixed == []
        assert report.manual == []

    def test_unidade_h_realmente_abaixo_do_minimo_ainda_vai_para_manual(self):
        report = cp.CureReport()
        insumos = [
            {
                "codigo": "MO-SUSPEITO",
                "tipo": "MAO_OBRA",
                "descricao": "Ajudante",
                "unidade": "h",
                "preco_unitario": 1.0,
            }
        ]
        cp.cure_erros_fisicos(insumos, report, apply=True)
        assert any("abaixo do mínimo legal" in m for m in report.manual)


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
        # canonical falls back to codes[0] (ordem alfabética) quando preço e estilo de código empatam
        assert dup_map == {"P0002": "MO-P0001"}

    def test_adr179_pega_duplicata_que_dedup_exato_perde_por_preco_diferente(self):
        """Caso real que motivou a ADR-179: mesma função, preço difere por fator de
        encargos (P0058 R$24.720 AGIS-com-encargos vs MO-SALA-TEC R$12.000
        CLT-normalizado) — dedup exato (igualdade de preço) nunca capturava isso."""
        insumos = [
            {"codigo": "P0058", "tipo": "MAO_OBRA", "descricao": "Sala Técnica", "preco_unitario": 24_720.0},
            {
                "codigo": "MO-SALA-TEC",
                "tipo": "MAO_OBRA",
                "descricao": "Sala Técnica",
                "preco_unitario": 12_000.0,
                "categoria": "DIVERSOS",
            },
        ]
        dup_map = cp._build_dup_map(insumos)
        assert dup_map == {"P0058": "MO-SALA-TEC"}

    def test_adr179_canonico_e_sempre_o_menor_preco_mesmo_com_estilo_p_code(self):
        """Mesmo quando o lado de MENOR preço tem estilo P####/MO-P#### (o critério
        de nomenclatura sozinho escolheria errado), o canônico deve ser o de menor
        preço — mantém a semântica "salário-base" que pu_calculator espera para
        unidade="mes" (evita dupla contagem de encargos)."""
        insumos = [
            {"codigo": "MO-P0059", "tipo": "MAO_OBRA", "descricao": "Técnico de QSMS", "preco_unitario": 4000.0},
            {"codigo": "P0059", "tipo": "MAO_OBRA", "descricao": "Técnico de QSMS", "preco_unitario": 8244.61},
        ]
        dup_map = cp._build_dup_map(insumos)
        assert dup_map == {"P0059": "MO-P0059"}

    # Papéis distintos da mesma família (mesmo preço, descrição parcialmente
    # sobreposta) — score fica na faixa "revisar" (~0,67), nunca "duplicata_provavel".
    _PAR_REVISAR = [
        {"codigo": "MO-A", "tipo": "MAO_OBRA", "descricao": "Operador de Rolo Compactador", "preco_unitario": 4002.24},
        {"codigo": "MO-B", "tipo": "MAO_OBRA", "descricao": "Operador de Rolo de Pneu", "preco_unitario": 4002.24},
    ]

    def test_adr179_revisar_nao_e_fundido_mas_vai_para_manual(self):
        """classificacao="revisar" (baixa confiança) não deve fundir automaticamente —
        só deve aparecer no relatório manual, para decisão humana."""
        report = cp.CureReport()
        dup_map = cp._build_dup_map(self._PAR_REVISAR, report)
        assert dup_map == {}
        assert any("revisar" in m for m in report.manual)

    def test_adr179_sem_report_nao_quebra_e_ainda_ignora_revisar(self):
        assert cp._build_dup_map(self._PAR_REVISAR, None) == {}

    def test_adr179_razao_ambigua_fora_das_faixas_nao_e_fundida(self):
        """Achado real ao validar: dezenas de pares com descrição idêntica e razão
        de preço sistemática (~1,335, ~1,2 etc.) fora tanto do 'idêntico' quanto do
        padrão de encargos confirmado (~2,06) — origem (erro de import vs. tabela
        paralela intencional) não confirmada com o usuário. Não deve fundir."""
        report = cp.CureReport()
        insumos = [
            {"codigo": "MO-CARPINTEIRO", "tipo": "MAO_OBRA", "descricao": "Carpinteiro", "preco_unitario": 3078.24},
            {"codigo": "MO-P0015", "tipo": "MAO_OBRA", "descricao": "Carpinteiro", "preco_unitario": 2305.6},
        ]
        dup_map = cp._build_dup_map(insumos, report)
        assert dup_map == {}
        assert any("fora das faixas validadas" in m for m in report.manual)

    def test_adr179_razao_dentro_da_faixa_de_encargos_confirmada_e_fundida(self):
        insumos = [
            {"codigo": "MO-ENCARREG-DREN", "tipo": "MAO_OBRA", "descricao": "Encarregado de Drenagem", "preco_unitario": 10_000.0},
            {"codigo": "P0020", "tipo": "MAO_OBRA", "descricao": "Encarregado de Drenagem", "preco_unitario": 20_600.0},
        ]
        dup_map = cp._build_dup_map(insumos)
        assert dup_map == {"P0020": "MO-ENCARREG-DREN"}


class TestCureDuplicatas:
    def test_no_duplicates_returns_inputs_unchanged(self):
        report = cp.CureReport()
        insumos = [{"codigo": "MO-A", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 10.0}]
        producoes = [{"id": "PR-1"}]
        result_ins, result_prod, _dup_map = cp.cure_duplicatas(insumos, producoes, report, apply=True)
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
        result_ins, result_prod, _dup_map = cp.cure_duplicatas(insumos, producoes, report, apply=True)
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
        result_ins, result_prod, _dup_map = cp.cure_duplicatas(insumos, [], report, apply=False)
        assert result_ins is insumos
        assert any("... e mais" in m for m in report.fixed)

    def test_dry_run_updates_producoes_report_without_mutating(self):
        report = cp.CureReport()
        insumos = [
            {"codigo": "MO-PEDREIRO", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 10.0},
            {"codigo": "P0001", "tipo": "MAO_OBRA", "descricao": "Pedreiro", "preco_unitario": 10.0},
        ]
        producoes = [{"id": "PR-1", "equipe": {"funcoes": [{"funcao_id": "P0001"}]}}]
        result_ins, result_prod, _dup_map = cp.cure_duplicatas(insumos, producoes, report, apply=False)
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
        result_ins, result_prod, _dup_map = cp.cure_duplicatas(insumos, producoes, report, apply=True)
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


# ─── Persistência em arquivos individuais (ADR-177/durabilidade) ────────────


class TestCaminhoInsumoIndividual:
    def test_resolve_existente_via_rglob(self, tmp_path):
        arquivo = tmp_path / "insumos" / "mao_obra" / "MO-X.json"
        arquivo.parent.mkdir(parents=True)
        arquivo.write_text("{}")
        assert cp._caminho_insumo_individual(tmp_path, "MAO_OBRA", "MO-X") == arquivo

    def test_novo_usa_convencao_tipo_lower(self, tmp_path):
        caminho = cp._caminho_insumo_individual(tmp_path, "EQUIPAMENTO", "EQ-NOVO")
        assert caminho == tmp_path / "insumos" / "equipamento" / "EQ-NOVO.json"


class TestCaminhoProducaoIndividual:
    def test_usa_producoes_se_existir(self, tmp_path):
        arquivo = tmp_path / "producoes" / "PR-1.json"
        arquivo.parent.mkdir(parents=True)
        arquivo.write_text("{}")
        assert cp._caminho_producao_individual(tmp_path, "PR-1") == arquivo

    def test_usa_produtividades_se_so_ela_existir(self, tmp_path):
        arquivo = tmp_path / "produtividades" / "PR-2.json"
        arquivo.parent.mkdir(parents=True)
        arquivo.write_text("{}")
        assert cp._caminho_producao_individual(tmp_path, "PR-2") == arquivo

    def test_novo_default_producoes(self, tmp_path):
        assert cp._caminho_producao_individual(tmp_path, "PR-3") == tmp_path / "producoes" / "PR-3.json"


class TestPersistirInsumosIndividuais:
    def test_escreve_insumo_alterado(self, tmp_path):
        originais = [{"codigo": "MO-A", "tipo": "MAO_OBRA", "preco_unitario": 100.0}]
        finais = [{"codigo": "MO-A", "tipo": "MAO_OBRA", "preco_unitario": 200.0}]
        escritos, removidos = cp._persistir_insumos_individuais(tmp_path, originais, finais, set())
        assert escritos == 1
        assert removidos == 0
        salvo = json.loads((tmp_path / "insumos" / "mao_obra" / "MO-A.json").read_text())
        assert salvo["preco_unitario"] == 200.0

    def test_nao_escreve_insumo_inalterado(self, tmp_path):
        item = {"codigo": "MO-A", "tipo": "MAO_OBRA", "preco_unitario": 100.0}
        escritos, removidos = cp._persistir_insumos_individuais(tmp_path, [dict(item)], [dict(item)], set())
        assert escritos == 0
        assert not (tmp_path / "insumos" / "mao_obra" / "MO-A.json").exists()

    def test_escreve_fix_de_campo_aninhado_em_atributos_especificos(self, tmp_path):
        """Regressão do bug real: fix em atributos_especificos.percentual_encargos_local
        (campo aninhado) precisa ser detectado e persistido — não só campos de
        topo como preco_unitario."""
        originais = [
            {
                "codigo": "MO-A",
                "tipo": "MAO_OBRA",
                "preco_unitario": 5000.0,
                "atributos_especificos": {"percentual_encargos_local": 1.777},
            }
        ]
        report = cp.CureReport()
        finais = cp.cure_erros_fisicos(copy.deepcopy(originais), report, apply=True)
        escritos, _ = cp._persistir_insumos_individuais(tmp_path, originais, finais, set())
        assert escritos == 1
        salvo = json.loads((tmp_path / "insumos" / "mao_obra" / "MO-A.json").read_text())
        assert salvo["atributos_especificos"]["percentual_encargos_local"] == pytest.approx(0.777, abs=1e-4)
        # `originais` não pode ter sido corrompido pela mutação (aliasing) —
        # senão o diff acima teria comparado igual e pulado a escrita.
        assert originais[0]["atributos_especificos"]["percentual_encargos_local"] == 1.777

    def test_remove_arquivo_de_insumo_deletado(self, tmp_path):
        arquivo = tmp_path / "insumos" / "mao_obra" / "MO-DUP.json"
        arquivo.parent.mkdir(parents=True)
        arquivo.write_text("{}")
        originais = [{"codigo": "MO-DUP", "tipo": "MAO_OBRA", "preco_unitario": 10.0}]
        escritos, removidos = cp._persistir_insumos_individuais(tmp_path, originais, [], {"MO-DUP"})
        assert removidos == 1
        assert not arquivo.exists()

    def test_removido_sem_arquivo_no_disco_nao_quebra(self, tmp_path):
        originais = [{"codigo": "MO-DUP", "tipo": "MAO_OBRA", "preco_unitario": 10.0}]
        escritos, removidos = cp._persistir_insumos_individuais(tmp_path, originais, [], {"MO-DUP"})
        assert removidos == 0

    def test_removido_sem_original_correspondente_e_ignorado(self, tmp_path):
        escritos, removidos = cp._persistir_insumos_individuais(tmp_path, [], [], {"MO-FANTASMA"})
        assert removidos == 0


class TestPersistirProducoesIndividuais:
    def test_escreve_producao_alterada(self, tmp_path):
        originais = [{"id": "PR-1", "valor_horario": 10.0}]
        finais = [{"id": "PR-1", "valor_horario": 20.0}]
        assert cp._persistir_producoes_individuais(tmp_path, originais, finais) == 1
        salvo = json.loads((tmp_path / "producoes" / "PR-1.json").read_text())
        assert salvo["valor_horario"] == 20.0

    def test_nao_escreve_producao_inalterada(self, tmp_path):
        item = {"id": "PR-1", "valor_horario": 10.0}
        assert cp._persistir_producoes_individuais(tmp_path, [dict(item)], [dict(item)]) == 0
        assert not (tmp_path / "producoes" / "PR-1.json").exists()


class TestCureTemplatesEstruturasIndiretas:
    def test_atualiza_funcao_id_em_estruturas_indiretas(self, tmp_path):
        path = tmp_path / "templates.json"
        path.write_text(
            json.dumps(
                {
                    "estruturas_indiretas": [
                        {"codigo": "ADM_PEQUENA", "mao_de_obra": [{"funcao_id": "MO-AUX-ADM", "quantidade": 1}]}
                    ]
                }
            ),
            encoding="utf-8",
        )
        report = cp.CureReport()
        cp._cure_templates_estruturas_indiretas(tmp_path, {"MO-AUX-ADM": "MO-P0006"}, report, apply=True)
        data = json.loads(path.read_text())
        assert data["estruturas_indiretas"][0]["mao_de_obra"][0]["funcao_id"] == "MO-P0006"
        assert any("templates.json" in m for m in report.fixed)

    def test_dry_run_nao_escreve(self, tmp_path):
        path = tmp_path / "templates.json"
        original = json.dumps(
            {"estruturas_indiretas": [{"codigo": "X", "mao_de_obra": [{"funcao_id": "MO-AUX-ADM"}]}]}
        )
        path.write_text(original, encoding="utf-8")
        report = cp.CureReport()
        cp._cure_templates_estruturas_indiretas(tmp_path, {"MO-AUX-ADM": "MO-P0006"}, report, apply=False)
        assert path.read_text() == original
        assert any("templates.json" in m for m in report.fixed)

    def test_sem_dup_map_nao_faz_nada(self, tmp_path):
        report = cp.CureReport()
        cp._cure_templates_estruturas_indiretas(tmp_path, {}, report, apply=True)
        assert report.fixed == []

    def test_arquivo_ausente_nao_quebra(self, tmp_path):
        report = cp.CureReport()
        cp._cure_templates_estruturas_indiretas(tmp_path, {"A": "B"}, report, apply=True)
        assert report.fixed == []

    def test_funcao_id_nao_mapeado_e_ignorado(self, tmp_path):
        path = tmp_path / "templates.json"
        path.write_text(
            json.dumps({"estruturas_indiretas": [{"codigo": "X", "mao_de_obra": [{"funcao_id": "MO-OUTRO"}]}]}),
            encoding="utf-8",
        )
        report = cp.CureReport()
        cp._cure_templates_estruturas_indiretas(tmp_path, {"MO-AUX-ADM": "MO-P0006"}, report, apply=True)
        assert report.fixed == []


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

    def test_apply_never_writes_the_bundle(self, tmp_path, monkeypatch, capsys):
        """ADR-177/durabilidade: --apply nunca escreve .catalog_bundle.json — só
        arquivos individuais (senão a correção reverte na próxima invalidação de
        cache, mesmo bug que a ADR-177 corrigiu em mesclar_catalogo)."""
        bundle_path = tmp_path / "config/catalogos/mendeslobo/.catalog_bundle.json"
        _write_bundle(
            bundle_path,
            insumos=[{"codigo": "MO-OK", "tipo": "MAO_OBRA", "preco_unitario": 3000.0}],
            producoes=[],
        )
        bundle_bytes_antes = bundle_path.read_bytes()
        monkeypatch.setattr(cp, "ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["cure_plausibility.py", "--contexto", "mendeslobo", "--apply"])
        # main() does not sys.exit() in apply mode
        cp.main()
        # Bundle é invalidado (apagado) ou permanece inalterado — nunca sobrescrito com dados curados
        assert not bundle_path.exists() or bundle_path.read_bytes() == bundle_bytes_antes
        out = capsys.readouterr().out
        assert "APPLY" in out
        assert "Arquivos individuais persistidos" in out
        assert "Pós-curação" in out

    def test_apply_writes_individual_insumo_file(self, tmp_path, monkeypatch, capsys):
        """Insumo alterado (aqui: EQUIPAMENTO recebe valor_locacao_mensal derivado)
        é escrito no arquivo individual insumos/{tipo}/{codigo}.json."""
        bundle_path = tmp_path / "config/catalogos/mendeslobo/.catalog_bundle.json"
        _write_bundle(
            bundle_path,
            insumos=[{"codigo": "EQ-1", "tipo": "EQUIPAMENTO", "preco_unitario": 10.0}],
            producoes=[],
        )
        monkeypatch.setattr(cp, "ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["cure_plausibility.py", "--contexto", "mendeslobo", "--apply"])
        cp.main()
        arquivo = tmp_path / "config/catalogos/mendeslobo/insumos/equipamento/EQ-1.json"
        assert arquivo.exists()
        saved = json.loads(arquivo.read_text(encoding="utf-8"))
        assert saved["atributos_especificos"]["valor_locacao_mensal"] > 0

    def test_apply_removes_individual_file_of_merged_duplicate(self, tmp_path, monkeypatch):
        """Duplicata fundida (ex.: Sala Técnica) tem o arquivo individual removido,
        não só a entrada do bundle (que nem é mais escrito)."""
        insumos_dir = tmp_path / "config/catalogos/mendeslobo/insumos/mao_obra"
        insumos_dir.mkdir(parents=True)
        p0058 = {"codigo": "P0058", "tipo": "MAO_OBRA", "descricao": "Sala Técnica", "preco_unitario": 24_720.0}
        mo_sala_tec = {
            "codigo": "MO-SALA-TEC",
            "tipo": "MAO_OBRA",
            "descricao": "Sala Técnica",
            "preco_unitario": 12_000.0,
        }
        (insumos_dir / "P0058.json").write_text(json.dumps(p0058), encoding="utf-8")
        (insumos_dir / "MO-SALA-TEC.json").write_text(json.dumps(mo_sala_tec), encoding="utf-8")
        bundle_path = tmp_path / "config/catalogos/mendeslobo/.catalog_bundle.json"
        _write_bundle(bundle_path, insumos=[p0058, mo_sala_tec], producoes=[])
        monkeypatch.setattr(cp, "ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["cure_plausibility.py", "--contexto", "mendeslobo", "--apply"])
        cp.main()
        assert not (insumos_dir / "P0058.json").exists()
        assert (insumos_dir / "MO-SALA-TEC.json").exists()
        canon = json.loads((insumos_dir / "MO-SALA-TEC.json").read_text(encoding="utf-8"))
        assert canon["codigo_referencia_externa"] == "P0058"

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

    def test_apply_writes_producao_alterada_na_subpasta_produtividades_existente(self, tmp_path, monkeypatch):
        """producoes/ e produtividades/ coexistem (legado) — o arquivo individual
        deve ser escrito onde o item JÁ EXISTE no disco, não sempre em producoes/."""
        catalog_dir = tmp_path / "config/catalogos/mendeslobo"
        insumos_dir = catalog_dir / "insumos/mao_obra"
        insumos_dir.mkdir(parents=True)
        p0058 = {"codigo": "P0058", "tipo": "MAO_OBRA", "descricao": "Sala Técnica", "preco_unitario": 24_720.0}
        mo_sala_tec = {"codigo": "MO-SALA-TEC", "tipo": "MAO_OBRA", "descricao": "Sala Técnica", "preco_unitario": 12_000.0}
        (insumos_dir / "P0058.json").write_text(json.dumps(p0058), encoding="utf-8")
        (insumos_dir / "MO-SALA-TEC.json").write_text(json.dumps(mo_sala_tec), encoding="utf-8")

        producao = {"id": "PR-1", "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "P0058"}]}}
        produtividades_dir = catalog_dir / "produtividades"
        produtividades_dir.mkdir(parents=True)
        (produtividades_dir / "PR-1.json").write_text(json.dumps(producao), encoding="utf-8")

        bundle_path = catalog_dir / ".catalog_bundle.json"
        _write_bundle(bundle_path, insumos=[p0058, mo_sala_tec], producoes=[producao])
        monkeypatch.setattr(cp, "ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["cure_plausibility.py", "--contexto", "mendeslobo", "--apply"])
        cp.main()

        saved = json.loads((produtividades_dir / "PR-1.json").read_text(encoding="utf-8"))
        assert saved["composicao_padrao_equipe"]["funcoes"][0]["funcao_id"] == "MO-SALA-TEC"
        assert not (catalog_dir / "producoes" / "PR-1.json").exists()

    def test_apply_atualiza_funcao_id_em_templates_estruturas_indiretas(self, tmp_path, monkeypatch):
        """Achado real: templates.json/estruturas_indiretas referencia funcao_id e
        producoes/produtividades não cobre essa superfície — ficaria órfão sem isso."""
        catalog_dir = tmp_path / "config/catalogos/mendeslobo"
        insumos_dir = catalog_dir / "insumos/mao_obra"
        insumos_dir.mkdir(parents=True)
        p0058 = {"codigo": "P0058", "tipo": "MAO_OBRA", "descricao": "Sala Técnica", "preco_unitario": 24_720.0}
        mo_sala_tec = {"codigo": "MO-SALA-TEC", "tipo": "MAO_OBRA", "descricao": "Sala Técnica", "preco_unitario": 12_000.0}
        (insumos_dir / "P0058.json").write_text(json.dumps(p0058), encoding="utf-8")
        (insumos_dir / "MO-SALA-TEC.json").write_text(json.dumps(mo_sala_tec), encoding="utf-8")

        templates_path = catalog_dir / "templates.json"
        templates_path.write_text(
            json.dumps(
                {
                    "templates": [],
                    "estruturas_indiretas": [
                        {"codigo": "ADM_PEQUENA", "mao_de_obra": [{"funcao_id": "P0058", "quantidade": 1}]}
                    ],
                }
            ),
            encoding="utf-8",
        )
        bundle_path = catalog_dir / ".catalog_bundle.json"
        _write_bundle(bundle_path, insumos=[p0058, mo_sala_tec], producoes=[])
        monkeypatch.setattr(cp, "ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["cure_plausibility.py", "--contexto", "mendeslobo", "--apply"])
        cp.main()

        saved = json.loads(templates_path.read_text(encoding="utf-8"))
        assert saved["estruturas_indiretas"][0]["mao_de_obra"][0]["funcao_id"] == "MO-SALA-TEC"

    def test_apply_preserva_crlf_do_templates_json_original(self, tmp_path, monkeypatch):
        """Achado real: templates.json do mendeslobo é CRLF; reescrever com LF
        (padrão do json.dumps) produzia diff de 342 linhas pra uma mudança de 3 —
        todo o arquivo aparecia como alterado no git, mascarando a mudança real."""
        catalog_dir = tmp_path / "config/catalogos/mendeslobo"
        insumos_dir = catalog_dir / "insumos/mao_obra"
        insumos_dir.mkdir(parents=True)
        p0058 = {"codigo": "P0058", "tipo": "MAO_OBRA", "descricao": "Sala Técnica", "preco_unitario": 24_720.0}
        mo_sala_tec = {"codigo": "MO-SALA-TEC", "tipo": "MAO_OBRA", "descricao": "Sala Técnica", "preco_unitario": 12_000.0}
        (insumos_dir / "P0058.json").write_text(json.dumps(p0058), encoding="utf-8")
        (insumos_dir / "MO-SALA-TEC.json").write_text(json.dumps(mo_sala_tec), encoding="utf-8")

        templates_path = catalog_dir / "templates.json"
        conteudo = json.dumps(
            {
                "estruturas_indiretas": [
                    {"codigo": "ADM_PEQUENA", "mao_de_obra": [{"funcao_id": "P0058", "quantidade": 1}]}
                ]
            },
            indent=2,
        )
        templates_path.write_bytes(conteudo.replace("\n", "\r\n").encode("utf-8"))

        bundle_path = catalog_dir / ".catalog_bundle.json"
        _write_bundle(bundle_path, insumos=[p0058, mo_sala_tec], producoes=[])
        monkeypatch.setattr(cp, "ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["cure_plausibility.py", "--contexto", "mendeslobo", "--apply"])
        cp.main()

        raw = templates_path.read_bytes()
        assert raw.count(b"\n") == raw.count(b"\r\n")  # todo \n é parte de \r\n — nenhum LF "solto"
        assert raw.count(b"\n") > 0
        saved = json.loads(raw.decode("utf-8"))
        assert saved["estruturas_indiretas"][0]["mao_de_obra"][0]["funcao_id"] == "MO-SALA-TEC"


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
