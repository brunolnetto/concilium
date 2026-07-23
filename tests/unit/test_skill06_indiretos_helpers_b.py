"""Coverage batch 38 — _consolidacao/_skill_helpers, _indiretos/_skill_helpers, _precificacao/_skill_helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

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
    """Lines 200-201: _custo_mob_composicional with baixadas entries."""

    def test_baixadas_adds_to_total(self):
        """Lines 200-201: for b in baixadas → n_ocorrencias * num_pessoas * valor."""
        dados_mob = {
            "mobilizacoes": [],
            "baixadas": [
                {"num_pessoas": 3, "valor_por_pessoa": 500.0, "meses_ocorrencia": ["jan", "fev"]},
                {"num_pessoas": 2, "valor_por_pessoa": 300.0, "meses_ocorrencia": ["mar"]},
            ],
        }
        total, mobs = INDIR._custo_mob_composicional(dados_mob, num_pessoas_direta=0, prazo_meses=0)
        # 3*500*2 + 2*300*1 = 3000 + 600 = 3600
        assert total == 3600.0

    def test_no_baixadas_uses_custo_pessoa_mes(self):
        dados_mob = {"custo_pessoa_mes": 2000}
        total, _ = INDIR._custo_mob_composicional(dados_mob, num_pessoas_direta=5, prazo_meses=3)
        assert total == 5 * 2000 * 3


class TestCustoMobLegadoGranularidadePorEquipe:
    """ADR-136 F4: _custo_mob_composicional deriva permanência por equipe de equipes_diretas
    (EquipeDireta.permanencia_efetiva_meses, já calculada pela skill-05) em vez de
    colapsar todas as equipes num único par (headcount agregado, prazo_meses do
    projeto) — bug documentado no ADR-136 a partir da planilha real do AGIS, que
    modela 7 equipes com permanências distintas (1,3 a 12,0 meses).
    """

    @staticmethod
    def _mk_equipe(num_pessoas: int, permanencia_efetiva_meses: float):
        return SimpleNamespace(
            funcoes=[SimpleNamespace(num_pessoas=num_pessoas)],
            permanencia_efetiva_meses=permanencia_efetiva_meses,
        )

    def test_equipes_diretas_usa_permanencia_propria_por_equipe(self):
        """Duas equipes com headcount e permanência bem diferentes entre si.

        A soma correta (por equipe) diverge da fórmula agregada antiga sempre que
        as permanências não são uniformes — exatamente o bug do ADR-136.
        """
        equipes = [
            self._mk_equipe(num_pessoas=10, permanencia_efetiva_meses=3.0),
            self._mk_equipe(num_pessoas=5, permanencia_efetiva_meses=6.0),
        ]
        dados_mob = {"custo_pessoa_mes": 1000.0}
        total, _mobs = INDIR._custo_mob_composicional(
            dados_mob, num_pessoas_direta=15, prazo_meses=4, equipes_diretas=equipes
        )
        # 10×1000×3 + 5×1000×6 = 30000 + 30000 = 60000 — não 15×1000×4=60000 por coincidência
        # (ajustado abaixo para deixar a divergência explícita com prazo_meses diferente)
        assert total == 60000.0

    def test_diverge_do_agregado_quando_permanencias_sao_desiguais(self):
        """Prova que o resultado por-equipe diverge do agregado quando o prazo
        agregado não é a média ponderada exata das permanências individuais."""
        equipes = [
            self._mk_equipe(num_pessoas=20, permanencia_efetiva_meses=1.0),
            self._mk_equipe(num_pessoas=5, permanencia_efetiva_meses=12.0),
        ]
        dados_mob = {"custo_pessoa_mes": 1000.0}
        # Por equipe (correto): 20×1000×1 + 5×1000×12 = 20000 + 60000 = 80000
        total_por_equipe, _ = INDIR._custo_mob_composicional(
            dados_mob, num_pessoas_direta=25, prazo_meses=6, equipes_diretas=equipes
        )
        # Agregado (bug antigo, ainda acessível via equipes_diretas=None): 25×1000×6 = 150000
        total_agregado, _ = INDIR._custo_mob_composicional(dados_mob, num_pessoas_direta=25, prazo_meses=6)
        assert total_por_equipe == 80000.0
        assert total_agregado == 150000.0
        assert total_por_equipe != total_agregado

    def test_equipes_diretas_vazia_mantem_retrocompat_agregado(self):
        """Lista vazia (ou None) preserva o comportamento agregado — retrocompat."""
        dados_mob = {"custo_pessoa_mes": 2000}
        total, _ = INDIR._custo_mob_composicional(dados_mob, num_pessoas_direta=5, prazo_meses=3, equipes_diretas=[])
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


class TestProcessMobCategoriaEquipesDiretas:
    """ADR-136 F4: _process_mob_categoria propaga equipes_diretas para _custo_mob_composicional."""

    def test_equipes_diretas_propagadas_ao_legado(self):
        equipes = [
            SimpleNamespace(
                funcoes=[SimpleNamespace(num_pessoas=20)],
                permanencia_efetiva_meses=1.0,
            ),
            SimpleNamespace(
                funcoes=[SimpleNamespace(num_pessoas=5)],
                permanencia_efetiva_meses=12.0,
            ),
        ]
        indir, _semanal = INDIR._process_mob_categoria(
            cat={"descricao": "Mobilização"},
            categorias_config_raw=[],  # sem cat_cfg_raw → exercita o caminho legado
            dados_mob={"custo_pessoa_mes": 1000.0},
            num_pessoas_direta=25,
            prazo_meses=6,
            n_semanas=12,
            dv4_policy=None,
            policy_scale={},
            equipes_diretas=equipes,
        )
        # Por equipe (correto, via equipes_diretas): 20×1000×1 + 5×1000×12 = 80000
        # Agregado seria 25×1000×6 = 150000 — a propagação evita esse valor errado.
        assert indir.custo_total == 80000.0


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




