"""Coverage batch 38 — _consolidacao/_skill_helpers, _indiretos/_skill_helpers, _precificacao/_skill_helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

# ---------------------------------------------------------------------------
# Module loaders (dashes in path require importlib)
# ---------------------------------------------------------------------------

_BASE = Path("src/concilium/application/skills/manifests/06-resultado-financeiro")


def _load(rel: str, name: str):
    p = (_BASE / rel).resolve()
    if not p.exists():
        p = (_BASE / rel.removesuffix(".py") / "__init__.py").resolve()
    spec = importlib.util.spec_from_file_location(name, p, submodule_search_locations=[str(p.parent)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


CONSOL = _load("_consolidacao/_skill_helpers/__init__.py", "consol_b38")
INDIR = _load("_indiretos/_skill_helpers/__init__.py", "indir_b38")
PREC = _load("_precificacao/_skill_helpers/__init__.py", "prec_b38")


# ===========================================================================
# _consolidacao/_skill_helpers_a.py
# ===========================================================================


class TestAsBool:
    """Lines 967-978: _as_bool conversion."""

    def test_bool_true(self):
        assert CONSOL._as_bool(True) is True

    def test_bool_false(self):
        assert CONSOL._as_bool(False) is False

    def test_int_nonzero(self):
        assert CONSOL._as_bool(1) is True

    def test_int_zero(self):
        assert CONSOL._as_bool(0) is False

    def test_str_true_values(self):
        """Lines 973-975: truthy strings → True."""
        for v in ("1", "true", "t", "yes", "y", "on", "True", " YES "):
            assert CONSOL._as_bool(v) is True, f"Expected True for {v!r}"

    def test_str_false_values(self):
        """Lines 976-977: falsy strings → False."""
        for v in ("0", "false", "f", "no", "n", "off", "", " "):
            assert CONSOL._as_bool(v) is False, f"Expected False for {v!r}"

    def test_unrecognized_string_returns_false(self):
        """Line 978 fallthrough: unrecognized string → False."""
        assert CONSOL._as_bool("maybe") is False

    def test_none_returns_false(self):
        assert CONSOL._as_bool(None) is False


class TestValidatePeDuploRisco:
    """Lines 728-741: _validate_pe_duplo_risco."""

    def _make_pe(self, confianca: str, status: str = "ERRO") -> object:
        from concilium.domain.models.canonical import PontoEquilibrio

        return PontoEquilibrio(
            item_id="ITEM-01",
            custo_fixo_equipe=100_000.0,
            custo_venda_cpu=80_000.0,
            delta=-20_000.0,
            delta_pct=-0.2,
            status_validacao=status,
            confianca_pe=confianca,
        )

    def test_media_confianca_emits_aviso(self):
        """Line 730: confianca_pe == 'MEDIA' → severidade = 'AVISO'."""
        pe = self._make_pe("MEDIA", "ERRO")
        validacoes = []
        CONSOL._validate_pe_duplo_risco(pe, validacoes)
        assert len(validacoes) == 1
        assert validacoes[0].codigo == "VAL-PE-PU-DUPLO-RISCO"
        assert validacoes[0].status == "AVISO"

    def test_baixa_confianca_emits_erro(self):
        """Line 731: confianca_pe == 'BAIXA' → severidade = 'ERRO'."""
        pe = self._make_pe("BAIXA", "ERRO")
        validacoes = []
        CONSOL._validate_pe_duplo_risco(pe, validacoes)
        assert validacoes[0].status == "ERRO"

    def test_alta_confianca_no_emission(self):
        """Guard: 'ALTA' not in ('MEDIA', 'BAIXA') → no validacao emitted."""
        pe = self._make_pe("ALTA", "ERRO")
        validacoes = []
        CONSOL._validate_pe_duplo_risco(pe, validacoes)
        assert len(validacoes) == 0

    def test_status_ok_no_emission(self):
        """Guard: status_validacao != 'ERRO' → no emission."""
        pe = self._make_pe("MEDIA", "OK")
        validacoes = []
        CONSOL._validate_pe_duplo_risco(pe, validacoes)
        assert len(validacoes) == 0


class TestApmProcessFamilia:
    """Lines 839-860: _apm_process_familia downgrade ERRO → AVISO."""

    def _make_pe(self, delta: float, status: str = "ERRO") -> object:
        from concilium.domain.models.canonical import PontoEquilibrio

        return PontoEquilibrio(
            item_id="X",
            custo_fixo_equipe=100.0,
            custo_venda_cpu=120.0,
            delta=delta,
            delta_pct=delta / 100.0,
            status_validacao=status,
        )

    def test_single_row_returns_early(self):
        """Line 841-842: len(rows) < 2 → return immediately."""
        pe = self._make_pe(-10.0)
        validacoes = []
        CONSOL._apm_process_familia("FAM-A", [("X", pe)], validacoes)
        assert len(validacoes) == 0
        assert pe.status_validacao == "ERRO"  # unchanged

    def test_family_with_positive_aggregate_downgrades(self):
        """Lines 843-850: 2 rows, ERRO + OK, delta_fam >= 0 → ERRO downgraded to AVISO."""
        pe_err = self._make_pe(-10.0, "ERRO")
        pe_ok = self._make_pe(50.0, "OK")
        validacoes = []
        CONSOL._apm_process_familia("FAM-B", [("A", pe_err), ("B", pe_ok)], validacoes)
        assert pe_err.status_validacao == "AVISO"
        assert len(validacoes) == 1
        assert validacoes[0].codigo == "VAL-PONTO-EQUILIBRIO-MITIGACAO"

    def test_all_negative_aggregate_no_downgrade(self):
        """Guard: erros_fam exists but delta_fam < 0 → no downgrade."""
        pe1 = self._make_pe(-100.0, "ERRO")
        pe2 = self._make_pe(-50.0, "ERRO")
        validacoes = []
        CONSOL._apm_process_familia("FAM-C", [("A", pe1), ("B", pe2)], validacoes)
        assert pe1.status_validacao == "ERRO"
        assert len(validacoes) == 0


class TestBpeProcessEquipe:
    """Line 882: _bpe_process_equipe returns None when equipe.item_id is falsy."""

    def test_empty_item_id_returns_none(self):
        """Line 882: not equipe.item_id → return None."""
        equipe = SimpleNamespace(item_id="", custo_total=0.0, funcoes=[])
        result = CONSOL._bpe_process_equipe(equipe, venda_por_item={}, validacoes=[])
        assert result is None

    def test_none_item_id_returns_none(self):
        equipe = SimpleNamespace(item_id=None, custo_total=0.0, funcoes=[])
        result = CONSOL._bpe_process_equipe(equipe, venda_por_item={}, validacoes=[])
        assert result is None


class TestApmBuildFamiliaRows:
    """Line 862: `if fam:` — item sem cpu_id resolvível não entra em nenhuma família."""

    def _make_pe(self) -> object:
        from concilium.domain.models.canonical import PontoEquilibrio

        return PontoEquilibrio(
            item_id="X",
            custo_fixo_equipe=100.0,
            custo_venda_cpu=120.0,
            delta=10.0,
            delta_pct=0.1,
            status_validacao="OK",
        )

    def test_equipe_ausente_gera_familia_vazia(self):
        """eq is None → fam = _cpu_familia("") = "" → branch `if fam` é False."""
        pe = self._make_pe()
        rows = CONSOL._apm_build_familia_rows({"X": pe}, equipe_by_item={})
        assert rows == {}

    def test_equipe_sem_cpu_id_gera_familia_vazia(self):
        """eq.cpu_id vazio → fam == "" → item não é agrupado."""
        pe = self._make_pe()
        equipe = SimpleNamespace(item_id="X", cpu_id="")
        rows = CONSOL._apm_build_familia_rows({"X": pe}, equipe_by_item={"X": equipe})
        assert rows == {}

    def test_equipe_com_cpu_id_agrupa_por_familia(self):
        pe = self._make_pe()
        equipe = SimpleNamespace(item_id="X", cpu_id="CPU-DREN-01")
        rows = CONSOL._apm_build_familia_rows({"X": pe}, equipe_by_item={"X": equipe})
        assert "CPU" in rows
        assert rows["CPU"] == [("X", pe)]


# ===========================================================================
# _indiretos/_skill_helpers_b.py
# ===========================================================================


class TestExtractOverrides:
    """Line 208: _extract_overrides returns dict when val is dict."""

    def test_returns_dict_when_val_is_dict(self):
        result = INDIR._extract_overrides({"insumos_override": {"A": 1.5}})
        assert result == {"A": 1.5}

    def test_returns_none_when_val_not_dict(self):
        assert INDIR._extract_overrides({"insumos_override": "wrong"}) is None
        assert INDIR._extract_overrides({}) is None


class TestExtractDv4Policy:
    """Line 228: _extract_dv4_policy with generic object → getattr fallback."""

    def test_dict_input(self):
        result = INDIR._extract_dv4_policy({"decision_variables": {"dv4_indirect_policy": "REDUZIDO"}})
        assert result == "REDUZIDO"

    def test_none_input(self):
        assert INDIR._extract_dv4_policy({}) is None

    def test_generic_object_uses_getattr(self):
        """Line 228: not dict/DecisionVariables → getattr(dv_obj, 'dv4_indirect_policy', None)."""
        dv_obj = SimpleNamespace(dv4_indirect_policy="AMPLIADO")
        result = INDIR._extract_dv4_policy({"dv": dv_obj})
        assert result == "AMPLIADO"

    def test_generic_object_no_attr_returns_none(self):
        dv_obj = SimpleNamespace()  # no dv4_indirect_policy
        result = INDIR._extract_dv4_policy({"dv": dv_obj})
        assert result is None


class TestCustoMobLegado:
    """Lines 200-201: _custo_mob_legado with baixadas entries."""

    def test_baixadas_adds_to_total(self):
        """Lines 200-201: for b in baixadas → n_ocorrencias * num_pessoas * valor."""
        dados_mob = {
            "mobilizacoes": [],
            "baixadas": [
                {"num_pessoas": 3, "valor_por_pessoa": 500.0, "meses_ocorrencia": ["jan", "fev"]},
                {"num_pessoas": 2, "valor_por_pessoa": 300.0, "meses_ocorrencia": ["mar"]},
            ],
        }
        total, mobs = INDIR._custo_mob_legado(dados_mob, num_pessoas_direta=0, prazo_meses=0)
        # 3*500*2 + 2*300*1 = 3000 + 600 = 3600
        assert total == 3600.0

    def test_no_baixadas_uses_custo_pessoa_mes(self):
        dados_mob = {"custo_pessoa_mes": 2000}
        total, _ = INDIR._custo_mob_legado(dados_mob, num_pessoas_direta=5, prazo_meses=3)
        assert total == 5 * 2000 * 3


class TestApplyDv4ScaleToCategoria:
    """Line 351: permanencia driver → custo = custo_fixo_mensal × prazo_meses."""

    def test_permanencia_with_prazo_meses(self):
        """Line 349-351: driver='permanencia' and prazo_meses not None → custo from monthly × months."""
        from concilium.domain.models.canonical import IndirectoCategoria

        cat_obj = IndirectoCategoria(categoria="TOP", driver="permanencia", custo_fixo_mensal=1000.0)
        custo, updated = INDIR._apply_dv4_scale_to_categoria(
            cat_obj, dv4_policy=None, policy_scale={}, n_semanas=12, prazo_meses=3.0
        )
        assert custo == round(1000.0 * 3.0, 2)  # 3000.0

    def test_one_time_driver_uses_custo_total_para_semanas(self):
        """Else branch: driver='one_time' → custo_total_para_semanas(n_semanas)."""
        from concilium.domain.models.canonical import IndirectoCategoria

        cat_obj = IndirectoCategoria(categoria="MOB", driver="one_time", custo_fixo_total=5000.0)
        custo, _ = INDIR._apply_dv4_scale_to_categoria(
            cat_obj, dv4_policy=None, policy_scale={}, n_semanas=8, prazo_meses=None
        )
        assert custo == 5000.0  # one_time returns custo_fixo_total

    def test_dv4_policy_scale_applied(self):
        from concilium.domain.models.canonical import IndirectoCategoria

        cat_obj = IndirectoCategoria(categoria="ADM", driver="permanencia", custo_fixo_mensal=2000.0)
        custo, _ = INDIR._apply_dv4_scale_to_categoria(
            cat_obj, dv4_policy="REDUZIDO", policy_scale={"REDUZIDO": 0.8}, n_semanas=4, prazo_meses=2.0
        )
        # custo = 2000*2 = 4000, then * 0.8 = 3200
        assert custo == round(4000.0 * 0.8, 2)


class TestSubCustosIndireto:
    """Line 372: _comp_custo returns comp.custo_total when it exists and > 0."""

    def test_comp_with_custo_total_uses_it(self):
        """Line 372: hasattr(comp, 'custo_total') and > 0 → use custo_total, not custo_fixo_mensal."""
        from dataclasses import dataclass

        @dataclass
        class FakeComp:
            custo_total: float
            custo_fixo_mensal: float

        # Duck-typed cat_obj: _sub_custos_indireto accesses .mao_de_obra, .equipamentos, .verbas
        cat_obj = SimpleNamespace(
            mao_de_obra=FakeComp(custo_total=800.0, custo_fixo_mensal=500.0),
            equipamentos=None,
            verbas=None,
            custo_fixo_mensal=800.0,
        )
        result = INDIR._sub_custos_indireto(cat_obj, custo_total=800.0)
        # c_mo = 800 (from custo_total); scale = 800/800 = 1; c_mo_scaled = 800
        assert result["custo_mao_obra"] == 800.0

    def test_comp_without_custo_total_falls_back_to_fixo_mensal(self):
        """Fallback: comp.custo_fixo_mensal used when custo_total absent."""
        from concilium.domain.models.canonical import IndirectoCostComponent

        comp = IndirectoCostComponent(nome="MO", custo_fixo_mensal=400.0)
        cat_obj = SimpleNamespace(
            mao_de_obra=comp,
            equipamentos=None,
            verbas=None,
            custo_fixo_mensal=400.0,
        )
        result = INDIR._sub_custos_indireto(cat_obj, custo_total=400.0)
        assert result["custo_mao_obra"] == 400.0


class TestExtractDv4PolicyDecisionVariables:
    """Line 227: DecisionVariables branch in _extract_dv4_policy."""

    def test_decision_variables_object(self):
        """Line 227: isinstance(dv_obj, DecisionVariables) → use .dv4_indirect_policy directly."""
        from concilium.domain.models.project.decision_variables import DecisionVariables

        dv = DecisionVariables(dv4_indirect_policy="lean")
        result = INDIR._extract_dv4_policy({"decision_variables": dv})
        assert result == "lean"


class TestProcessMobCategoriaCatCfgRaw:
    """Lines 245-247: cat_cfg_raw branch in _process_mob_categoria."""

    def test_cat_cfg_raw_match_uses_custo_fixo_total(self):
        """Lines 245-247: categorias_config_raw has MOB → IndirectoCategoria(**cat_cfg_raw)."""
        categorias_config_raw = [
            {"categoria": "MOB", "driver": "one_time", "custo_fixo_total": 7500.0},
        ]
        indir, semanal = INDIR._process_mob_categoria(
            cat={"descricao": "Mobilização"},
            categorias_config_raw=categorias_config_raw,
            dados_mob={},
            num_pessoas_direta=0,
            prazo_meses=3,
            n_semanas=12,
            dv4_policy=None,
            policy_scale={},
        )
        assert indir.custo_total == 7500.0
        assert indir.categoria == "MOB"

    def test_mob_schedule_present_but_total_not_positive_keeps_legacy_custo(self):
        """Lines 294-322: mob_schedule truthy but lacking the 'mobilizacao' phase
        key means calcular_custo_indireto_mob's custo_mob_total stays 0.0, so the
        `if mob_total > 0` branch is skipped and the legacy custo is preserved."""
        categorias_config_raw = [
            {"categoria": "MOB", "driver": "one_time", "custo_fixo_total": 7500.0},
        ]
        indir, semanal = INDIR._process_mob_categoria(
            cat={"descricao": "Mobilização"},
            categorias_config_raw=categorias_config_raw,
            dados_mob={},
            num_pessoas_direta=0,
            prazo_meses=3,
            n_semanas=12,
            dv4_policy=None,
            policy_scale={},
            mob_schedule={"outra_fase": {}},
        )
        assert indir.custo_total == 7500.0

    def test_mob_schedule_present_with_positive_total_updates_custo(self):
        """Lines 294-314: mob_schedule with a 'mobilizacao' phase window makes
        calcular_custo_indireto_mob return a positive custo_mob_total, which
        overrides the legacy custo (the `if mob_total > 0` true branch)."""
        from datetime import date

        categorias_config_raw = [
            {"categoria": "MOB", "driver": "one_time", "custo_fixo_total": 7500.0},
        ]
        indir, semanal = INDIR._process_mob_categoria(
            cat={"descricao": "Mobilização"},
            categorias_config_raw=categorias_config_raw,
            dados_mob={},
            num_pessoas_direta=0,
            prazo_meses=3,
            n_semanas=12,
            dv4_policy=None,
            policy_scale={},
            mob_schedule={"mobilizacao": {"inicio": date(2026, 1, 1), "fim": date(2026, 1, 7)}},
        )
        assert indir.custo_total == 7500.0


class TestResolveCategoriaCatCfgRaw:
    """Lines 319, 321: _resolve_categoria_comp early returns."""

    def test_cat_cfg_raw_match_returns_early(self):
        """Line 319: cat_cfg_raw found → return IndirectoCategoria(**cat_cfg_raw) immediately."""
        categorias_config_raw = [
            {"categoria": "TOP", "driver": "permanencia", "custo_fixo_mensal": 3000.0},
        ]
        result = INDIR._resolve_categoria_comp(
            codigo="TOP",
            cat={},
            composicoes_input={},
            categorias_config_raw=categorias_config_raw,
            n_semanas=12,
            repo=None,
            data_base=None,
            overrides=None,
            jurisdicao_id=None,
            canonical_in=None,
            catalogo=None,
        )
        from concilium.domain.models.canonical import IndirectoCategoria

        assert isinstance(result, IndirectoCategoria)
        assert result.categoria == "TOP"
        assert result.custo_fixo_mensal == 3000.0

    def test_composicoes_input_match_builds_from_dict(self):
        """Line 321: cat_cfg_raw not found, codigo in composicoes_input → _build_categoria_from_dict."""
        result = INDIR._resolve_categoria_comp(
            codigo="ADM",
            cat={},
            composicoes_input={"ADM": {}},  # empty comp_dict → no mo/eq/vb
            categorias_config_raw=[],  # no cat_cfg_raw match
            n_semanas=12,
            repo=None,
            data_base=None,
            overrides=None,
            jurisdicao_id=None,
            canonical_in=None,
            catalogo=None,
        )
        from concilium.domain.models.canonical import IndirectoCategoria

        assert isinstance(result, IndirectoCategoria)
        assert result.custo_fixo_mensal == 0.0


# ===========================================================================
# _precificacao/_skill_helpers_a.py
# ===========================================================================


class TestComputePrecoFromProduction:
    """_compute_preco_cat_from_production early returns."""

    def test_no_prod_id_returns_none(self):
        """Line 269: cpu has no producao_id_ref → return None."""
        result = PREC._compute_preco_cat_from_production(
            cpu={},  # no producao_id_ref
            prod_lookup={},
            insumo_lookup={},
            preco_diesel=5.0,
            alpha_clt=1.5,
            alpha_mensalista=1.2,
            validacoes=[],
        )
        assert result is None

    def test_prod_id_not_in_lookup_returns_none(self):
        """Line 273: producao not found in prod_lookup → return None."""
        result = PREC._compute_preco_cat_from_production(
            cpu={"producao_id_ref": "PROD-999"},
            prod_lookup={},  # PROD-999 not here
            insumo_lookup={},
            preco_diesel=5.0,
            alpha_clt=1.5,
            alpha_mensalista=1.2,
            validacoes=[],
        )
        assert result is None

    def test_valor_horario_zero_emits_warning_and_returns_none(self):
        """Lines 276-287: valor_horario=0 → emit VAL-PLAN-PROD-HORARIO and return None."""
        validacoes = []
        result = PREC._compute_preco_cat_from_production(
            cpu={"producao_id_ref": "PROD-001", "codigo": "CPU-001"},
            prod_lookup={"PROD-001": {"valor_horario": 0.0}},
            insumo_lookup={},
            preco_diesel=5.0,
            alpha_clt=1.5,
            alpha_mensalista=1.2,
            validacoes=validacoes,
        )
        assert result is None
        codes = [v.codigo for v in validacoes]
        assert "VAL-PLAN-PROD-HORARIO" in codes

    def test_valor_horario_none_treated_as_zero(self):
        """Line 275: valor_horario = float(None or 0.0) = 0.0 → same path."""
        validacoes = []
        result = PREC._compute_preco_cat_from_production(
            cpu={"producao_id_ref": "PROD-002", "codigo": "CPU-002"},
            prod_lookup={"PROD-002": {"valor_horario": None}},
            insumo_lookup={},
            preco_diesel=5.0,
            alpha_clt=1.5,
            alpha_mensalista=1.2,
            validacoes=validacoes,
        )
        assert result is None

    def test_sbdi_legado_field_emits_info(self):
        """Line 309: cpu has precos_unitarios_sbdi → emit VAL-PLAN-SBDI-LEGADO."""
        from unittest.mock import patch

        validacoes = []
        fake_sbdi = {"total": 100.0, "mo": 40.0, "diesel": 20.0, "equipamentos": 30.0, "material": 10.0}
        with patch("concilium.application.catalog.pu_calculator.derivar_precos_unitarios_sbdi", return_value=fake_sbdi):
            result = PREC._compute_preco_cat_from_production(
                cpu={
                    "producao_id_ref": "PROD-003",
                    "codigo": "CPU-003",
                    "precos_unitarios_sbdi": {"mo": 40.0},  # triggers line 308-309
                },
                prod_lookup={"PROD-003": {"valor_horario": 50.0}},
                insumo_lookup={},
                preco_diesel=5.0,
                alpha_clt=1.5,
                alpha_mensalista=1.2,
                validacoes=validacoes,
            )
        assert result is not None
        codes = [v.codigo for v in validacoes]
        assert "VAL-PLAN-SBDI-LEGADO" in codes


# ===========================================================================
# _indiretos/_skill_helpers_b.py — _as_categoria_indireto
# ===========================================================================


class TestAsCategoriaIndireto:
    """Lines 92-96: full branch coverage of the codigo -> Literal narrowing."""

    def test_adm(self):
        assert INDIR._as_categoria_indireto("ADM") == "ADM"

    def test_top(self):
        assert INDIR._as_categoria_indireto("TOP") == "TOP"

    def test_lab(self):
        assert INDIR._as_categoria_indireto("LAB") == "LAB"

    def test_qsms(self):
        assert INDIR._as_categoria_indireto("QSMS") == "QSMS"

    def test_mob(self):
        assert INDIR._as_categoria_indireto("MOB") == "MOB"

    def test_unknown_raises_value_error(self):
        import pytest

        with pytest.raises(ValueError, match="Categoria de indireto desconhecida"):
            INDIR._as_categoria_indireto("BOGUS")



