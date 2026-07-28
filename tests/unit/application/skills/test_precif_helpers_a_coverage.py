from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------


def _load_precif():
    p = (
        Path("src/concilium/application/skills/manifests/06-resultado-financeiro/_precificacao/_skill_helpers")
        / "__init__.py"
    )
    spec = importlib.util.spec_from_file_location("_precif_helpers_a", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_precif_helpers_a"] = mod
    spec.loader.exec_module(mod)
    return mod


MOD = _load_precif()
PREC = MOD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_canonical(**kwargs):
    defaults = dict(
        eap=[],
        equipes_diretas=None,
        planejamento=[],
    )
    defaults.update(kwargs)
    obj = MagicMock()
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _make_validacao_item(**kwargs):
    from concilium.domain.models.canonical import ValidacaoItem

    return ValidacaoItem(**{"codigo": "V", "status": "OK", "mensagem": "ok", **kwargs})


# ---------------------------------------------------------------------------
# _create_synthetic_cpu  (lines 45-57, missing 76-77)
# ---------------------------------------------------------------------------


class TestCreateSyntheticCpu:
    def test_returns_dict_with_required_keys(self):
        validacoes = []
        result = MOD._create_synthetic_cpu("CPU-TEST-001", validacoes)
        assert result is not None
        assert result["codigo"] == "CPU-TEST-001"
        assert "producao_id_ref" in result
        assert result["producao_id_ref"] is not None

    def test_preserves_cpu_id_in_descricao(self):
        validacoes = []
        result = MOD._create_synthetic_cpu("CPU-MY-ID", validacoes)
        assert "CPU-MY-ID" in result["descricao"]


# ---------------------------------------------------------------------------
# _resolve_insumo_preco  (lines 60-77, missing 76-77)
# ---------------------------------------------------------------------------


class TestResolveInsumoPreco:
    def _make_repo(self, preco=50.0, raises=False):
        repo = MagicMock()
        if raises:
            repo.resolver_preco.side_effect = RuntimeError("not found")
        else:
            repo.resolver_preco.return_value = (preco, "catalog")
        return repo

    def test_success_returns_resolved_price(self):
        repo = self._make_repo(preco=75.0)
        result = MOD._resolve_insumo_preco(repo, "INS-01", "SP", {}, "2025-01-01", 10.0)
        assert result == pytest.approx(75.0)

    def test_exception_returns_fallback(self):
        repo = self._make_repo(raises=True)
        result = MOD._resolve_insumo_preco(repo, "INS-01", "SP", {}, "2025-01-01", 42.0)
        assert result == pytest.approx(42.0)

    def test_resolved_none_returns_fallback(self):
        repo = MagicMock()
        repo.resolver_preco.return_value = (None, "catalog")
        result = MOD._resolve_insumo_preco(repo, "INS-01", "SP", {}, "2025-01-01", 33.0)
        assert result == pytest.approx(33.0)

    def test_both_none_returns_zero(self):
        repo = MagicMock()
        repo.resolver_preco.return_value = (None, "catalog")
        result = MOD._resolve_insumo_preco(repo, "INS-01", "SP", {}, "2025-01-01", 0.0)
        assert result == 0.0


# ---------------------------------------------------------------------------
# _build_equipe_lookup  (line 80-81, missing 143-145)
# ---------------------------------------------------------------------------


class TestBuildEquipeLookup:
    def test_empty_equipes_returns_empty(self):
        canonical = _make_canonical(equipes_diretas=None)
        result = MOD._build_equipe_lookup(canonical)
        assert result == {}

    def test_builds_lookup_by_item_id(self):
        eq1 = MagicMock()
        eq1.item_id = "I-01"
        eq2 = MagicMock()
        eq2.item_id = "I-02"
        canonical = _make_canonical(equipes_diretas=[eq1, eq2])
        result = MOD._build_equipe_lookup(canonical)
        assert "I-01" in result
        assert result["I-01"] is eq1
        assert "I-02" in result


# ---------------------------------------------------------------------------
# _build_planejamento_entry  (lines 84-129, missing 143-145, 151-152)
# ---------------------------------------------------------------------------


class TestBuildPlanejamentoEntry:
    def _make_item(self, item_id="I-01", cpu_id="CPU-01", q=100.0):
        item = MagicMock()
        item.item_id = item_id
        item.cpu_id = cpu_id
        item.quantitativo = q
        return item

    def test_basic_entry_structure(self):
        item = self._make_item(q=10.0)
        preco_cat = {"material": 5.0, "diesel": 3.0, "mao_obra": 4.0, "equipamentos": 2.0}
        bdi = {"material": 0.2, "diesel": 0.1, "mao_obra": 0.15, "equipamentos": 0.12}
        preco_com_bdi = {k: preco_cat[k] * (1 + bdi[k]) for k in preco_cat}
        result = MOD._build_planejamento_entry(item, preco_cat, preco_com_bdi, bdi)
        assert result.item_id == "I-01"
        assert result.cpu_id == "CPU-01"
        assert result.preco_unitario.total == pytest.approx(sum(preco_cat.values()), abs=0.01)

    def test_subtotals_computed(self):
        item = self._make_item(q=10.0)
        preco_cat = {"material": 10.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        bdi = {"material": 0.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        preco_com_bdi = {k: preco_cat[k] for k in preco_cat}
        result = MOD._build_planejamento_entry(item, preco_cat, preco_com_bdi, bdi)
        assert result.subtotal.sem_bdi.material == pytest.approx(100.0)
        assert result.subtotal.com_bdi.material == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# _build_planejamento_entry — precificacao_via_fallback_composicao (issue #132)
# ---------------------------------------------------------------------------


class TestBuildPlanejamentoEntryFallbackFlag:
    def _make_item(self, item_id="I-01", cpu_id="CPU-01", q=10.0):
        item = MagicMock()
        item.item_id = item_id
        item.cpu_id = cpu_id
        item.quantitativo = q
        return item

    def test_default_e_false(self):
        item = self._make_item()
        preco_cat = {"material": 5.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        bdi = {"material": 0.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        result = MOD._build_planejamento_entry(item, preco_cat, preco_cat, bdi)
        assert result.precificacao_via_fallback_composicao is False

    def test_propaga_true_quando_informado(self):
        item = self._make_item()
        preco_cat = {"material": 5.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        bdi = {"material": 0.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        result = MOD._build_planejamento_entry(
            item, preco_cat, preco_cat, bdi, precificacao_via_fallback_composicao=True
        )
        assert result.precificacao_via_fallback_composicao is True


# ---------------------------------------------------------------------------
# _resolve_preco_cat_item — usou_fallback_composicao (issue #132)
# ---------------------------------------------------------------------------


class TestResolvePrecoCatItemFallbackFlag:
    _ARGS = dict(
        prod_lookup={},
        insumo_lookup={},
        repo=None,
        jurisdicao_id=None,
        overrides=None,
        data_base=None,
        erros_insumo=None,
        preco_diesel=6.2,
        alpha_clt=1.777,
        alpha_mensalista=1.060,
        catalog_session=None,
    )

    def test_fonte1_bottom_up_retorna_fallback_false(self):
        item = SimpleNamespace(item_id="I-01")
        cpu = {"codigo": "CPU-01"}
        preco_cat = {"material": 1.0, "diesel": 0.0, "mao_obra": 2.0, "equipamentos": 0.0}
        validacoes: list = []
        with patch.object(MOD._process_item, "_compute_preco_cat_from_production", return_value=preco_cat):
            result, equip_sem_decomp, usou_fallback = MOD._resolve_preco_cat_item(
                item,
                cpu,
                self._ARGS["prod_lookup"],
                self._ARGS["insumo_lookup"],
                self._ARGS["repo"],
                self._ARGS["jurisdicao_id"],
                self._ARGS["overrides"],
                self._ARGS["data_base"],
                set(),
                validacoes,
                self._ARGS["preco_diesel"],
                self._ARGS["alpha_clt"],
                self._ARGS["alpha_mensalista"],
                self._ARGS["catalog_session"],
            )
        assert result == preco_cat
        assert equip_sem_decomp == set()
        assert usou_fallback is False
        assert any(v.codigo == "VAL-PLAN-BOTTOM-UP" for v in validacoes)

    def test_fonte2_composicao_retorna_fallback_true(self):
        item = SimpleNamespace(item_id="I-02")
        cpu = {"codigo": "CPU-02"}
        preco_cat_fallback = {"material": 3.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 1.0}
        validacoes: list = []
        with (
            patch.object(MOD._process_item, "_compute_preco_cat_from_production", return_value=None),
            patch.object(
                MOD._process_item,
                "_preco_cat_fallback_composicao",
                return_value=(preco_cat_fallback, {"EQ-1"}),
            ),
        ):
            result, equip_sem_decomp, usou_fallback = MOD._resolve_preco_cat_item(
                item,
                cpu,
                self._ARGS["prod_lookup"],
                self._ARGS["insumo_lookup"],
                self._ARGS["repo"],
                self._ARGS["jurisdicao_id"],
                self._ARGS["overrides"],
                self._ARGS["data_base"],
                set(),
                validacoes,
                self._ARGS["preco_diesel"],
                self._ARGS["alpha_clt"],
                self._ARGS["alpha_mensalista"],
                self._ARGS["catalog_session"],
            )
        assert result == preco_cat_fallback
        assert equip_sem_decomp == {"EQ-1"}
        assert usou_fallback is True

    def test_fonte2_falha_ainda_marca_fallback_true(self):
        """Mesmo quando a Fonte 2 falha (preco_cat=None, ex. VAL-PLAN-MO-EQ-SEM-FONTE),
        usou_fallback_composicao é True — o item "caiu" no branch de fallback, mesmo que
        o resultado final não tenha sido precificado."""
        item = SimpleNamespace(item_id="I-03")
        cpu = {"codigo": "CPU-03"}
        validacoes: list = []
        with (
            patch.object(MOD._process_item, "_compute_preco_cat_from_production", return_value=None),
            patch.object(MOD._process_item, "_preco_cat_fallback_composicao", return_value=(None, set())),
        ):
            result, equip_sem_decomp, usou_fallback = MOD._resolve_preco_cat_item(
                item,
                cpu,
                self._ARGS["prod_lookup"],
                self._ARGS["insumo_lookup"],
                self._ARGS["repo"],
                self._ARGS["jurisdicao_id"],
                self._ARGS["overrides"],
                self._ARGS["data_base"],
                set(),
                validacoes,
                self._ARGS["preco_diesel"],
                self._ARGS["alpha_clt"],
                self._ARGS["alpha_mensalista"],
                self._ARGS["catalog_session"],
            )
        assert result is None
        assert usou_fallback is True


# ---------------------------------------------------------------------------
# _try_early_override  (lines 131-160, missing 143-145, 151-152, 159)
# ---------------------------------------------------------------------------


class TestTryEarlyOverride:
    def _make_item(self, item_id="I-01", cpu_id="CPU-01", q=10.0):
        item = MagicMock()
        item.item_id = item_id
        item.cpu_id = cpu_id
        item.quantitativo = q
        return item

    def test_no_overrides_returns_none(self):
        item = self._make_item()
        bdi = {"material": 0.1, "diesel": 0.1, "mao_obra": 0.1, "equipamentos": 0.1}
        result = MOD._try_early_override(item, None, bdi, [])
        assert result is None

    def test_non_dict_overrides_returns_none(self):
        item = self._make_item()
        bdi = {"material": 0.1, "diesel": 0.1, "mao_obra": 0.1, "equipamentos": 0.1}
        result = MOD._try_early_override(item, "invalid", bdi, [])
        assert result is None

    def test_pu_not_dict_returns_none(self):
        item = self._make_item()
        bdi = {"material": 0.1, "diesel": 0.1, "mao_obra": 0.1, "equipamentos": 0.1}
        overrides = {"I-01": {"preco_unitario": "not-a-dict"}}
        result = MOD._try_early_override(item, overrides, bdi, [])
        assert result is None

    def test_all_zero_pu_returns_none(self):
        item = self._make_item()
        bdi = {"material": 0.1, "diesel": 0.1, "mao_obra": 0.1, "equipamentos": 0.1}
        overrides = {"I-01": {"preco_unitario": {"material": 0.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}}}
        result = MOD._try_early_override(item, overrides, bdi, [])
        assert result is None

    def test_valid_override_returns_planejamento(self):
        item = self._make_item()
        bdi = {"material": 0.1, "diesel": 0.1, "mao_obra": 0.1, "equipamentos": 0.1}
        overrides = {
            "I-01": {"preco_unitario": {"material": 100.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}}
        }
        validacoes = []
        result = MOD._try_early_override(item, overrides, bdi, validacoes)
        assert result is not None
        assert any(v.codigo == "VAL-PLAN-OVR-ITEM" for v in validacoes)


# ---------------------------------------------------------------------------
# _apply_sem_bdi_override  (lines 378-396, missing 382-388, 402)
# ---------------------------------------------------------------------------


class TestApplySemBdiOverride:
    def test_non_dict_override_no_op(self):
        preco_cat = {"material": 10.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        validacoes = []
        MOD._apply_sem_bdi_override("I-01", {"preco_unitario": "bad"}, preco_cat, validacoes)
        assert preco_cat["material"] == 10.0  # unchanged
        assert validacoes == []

    def test_valid_override_updates_preco_cat(self):
        preco_cat = {"material": 10.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        validacoes = []
        override = {"preco_unitario": {"material": 50.0, "diesel": 5.0}}
        MOD._apply_sem_bdi_override("I-01", override, preco_cat, validacoes)
        assert preco_cat["material"] == pytest.approx(50.0)
        assert preco_cat["diesel"] == pytest.approx(5.0)
        assert any(v.codigo == "VAL-PLAN-OVR-ITEM" for v in validacoes)

    def test_override_invalid_value_skipped(self):
        preco_cat = {"material": 10.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        validacoes = []
        override = {"preco_unitario": {"material": "bad_value"}}
        MOD._apply_sem_bdi_override("I-01", override, preco_cat, validacoes)
        # invalid value skipped; original kept
        assert preco_cat["material"] == 10.0

    def test_missing_key_in_override_keeps_original(self):
        preco_cat = {"material": 10.0, "diesel": 3.0, "mao_obra": 2.0, "equipamentos": 1.0}
        validacoes = []
        override = {"preco_unitario": {"material": 50.0}}
        MOD._apply_sem_bdi_override("I-01", override, preco_cat, validacoes)
        assert preco_cat["diesel"] == 3.0
        assert preco_cat["mao_obra"] == 2.0


# ---------------------------------------------------------------------------
# _apply_com_bdi_override  (lines 397-420, missing 402, 410)
# ---------------------------------------------------------------------------


class TestApplyComBdiOverride:
    def test_no_com_bdi_override_uses_formula(self):
        preco_cat = {"material": 10.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        bdi = {"material": 0.2, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        validacoes = []
        result = MOD._apply_com_bdi_override("I-01", {}, preco_cat, bdi, validacoes)
        assert result["material"] == pytest.approx(10.0 * 1.2)

    def test_com_bdi_override_dict_applied(self):
        preco_cat = {"material": 10.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        bdi = {"material": 0.2, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        validacoes = []
        override = {"preco_unitario_com_bdi": {"material": 99.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}}
        result = MOD._apply_com_bdi_override("I-01", override, preco_cat, bdi, validacoes)
        assert result["material"] == pytest.approx(99.0)
        assert any(v.codigo == "VAL-PLAN-OVR-ITEM-BDI" for v in validacoes)

    def test_com_bdi_override_diverge_emite_aviso(self):
        """issue #121 item 1: override com-BDI implicando BDI diferente do aplicado
        na run agora é visível (antes, era absorvido silenciosamente)."""
        preco_cat = {"material": 10.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        bdi = {"material": 0.2, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        validacoes = []
        # material com BDI aplicado seria 10*1.2=12.0; override fixa em 99.0 (BDI implícito 8.9)
        override = {"preco_unitario_com_bdi": {"material": 99.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}}
        MOD._apply_com_bdi_override("I-01", override, preco_cat, bdi, validacoes)
        diverge = [v for v in validacoes if v.codigo == "VAL-PLAN-OVR-BDI-DIVERGE"]
        assert len(diverge) == 1
        assert diverge[0].status == "AVISO"
        assert "material" in diverge[0].mensagem

    def test_com_bdi_override_consistente_nao_emite_aviso(self):
        """Override com-BDI que respeita com_bdi = sem_bdi × (1+BDI) não deve gerar ruído."""
        preco_cat = {"material": 10.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        bdi = {"material": 0.2, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        validacoes = []
        override = {"preco_unitario_com_bdi": {"material": 12.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}}
        MOD._apply_com_bdi_override("I-01", override, preco_cat, bdi, validacoes)
        assert not any(v.codigo == "VAL-PLAN-OVR-BDI-DIVERGE" for v in validacoes)


# ---------------------------------------------------------------------------
# _get_bdi_value  (lines 594-602, missing 595-601)
# ---------------------------------------------------------------------------


class TestGetBdiValue:
    def test_first_key_found(self):
        manual = {"bdi_material": 0.25, "material": 0.10}
        result = MOD._get_bdi_value(manual, "bdi_material", "material")
        assert result == pytest.approx(0.25)

    def test_fallback_to_second_key(self):
        manual = {"material": 0.10}
        result = MOD._get_bdi_value(manual, "bdi_material", "material")
        assert result == pytest.approx(0.10)

    def test_no_key_returns_default(self):
        manual = {}
        result = MOD._get_bdi_value(manual, "bdi_material", "material", default=0.15)
        assert result == pytest.approx(0.15)

    def test_none_value_skips_to_next(self):
        manual = {"bdi_material": None, "material": 0.18}
        result = MOD._get_bdi_value(manual, "bdi_material", "material")
        assert result == pytest.approx(0.18)

    def test_invalid_float_skips(self):
        manual = {"bdi_material": "invalid", "material": 0.12}
        result = MOD._get_bdi_value(manual, "bdi_material", "material")
        assert result == pytest.approx(0.12)

    def test_zero_value_is_returned(self):
        manual = {"bdi_material": 0.0}
        result = MOD._get_bdi_value(manual, "bdi_material", default=0.5)
        assert result == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _build_lookups  (lines 604-626, missing 620, 623)
# ---------------------------------------------------------------------------


class TestBuildLookups:
    def test_empty_catalogo(self):
        catalogo = {"cpus": [], "insumos": [], "produtividades": []}
        cpus, insumos, prods = MOD._build_lookups(catalogo)
        assert cpus == {}
        assert insumos == {}
        assert prods == {}

    def test_cpus_keyed_by_codigo(self):
        catalogo = {
            "cpus": [{"codigo": "CPU-01", "descricao": "test"}],
            "insumos": [],
            "produtividades": [],
        }
        cpus, _, _ = MOD._build_lookups(catalogo)
        assert "CPU-01" in cpus
        assert cpus["CPU-01"]["descricao"] == "test"

    def test_insumos_keyed_by_codigo(self):
        catalogo = {
            "cpus": [],
            "insumos": [{"codigo": "INS-01", "preco_unitario": 10.0}],
            "produtividades": [],
        }
        _, insumos, _ = MOD._build_lookups(catalogo)
        assert "INS-01" in insumos

    def test_produtividades_keyed_by_id(self):
        catalogo = {
            "cpus": [],
            "insumos": [],
            "produtividades": [{"id": "PROD-01", "valor_horario": 5.0}],
        }
        _, _, prods = MOD._build_lookups(catalogo)
        assert "PROD-01" in prods
        assert prods["PROD-01"]["valor_horario"] == 5.0

    def test_producoes_alias_works(self):
        catalogo = {
            "cpus": [],
            "insumos": [],
            "producoes": [{"id": "PROD-02", "valor_horario": 8.0}],
        }
        _, _, prods = MOD._build_lookups(catalogo)
        assert "PROD-02" in prods

    def test_normalizes_producao_horaria_to_valor_horario(self):
        catalogo = {
            "cpus": [],
            "insumos": [],
            "produtividades": [{"id": "PROD-03", "producao_horaria": 12.0}],
        }
        _, _, prods = MOD._build_lookups(catalogo)
        assert prods["PROD-03"]["valor_horario"] == 12.0

    def test_entry_without_id_skipped(self):
        catalogo = {
            "cpus": [],
            "insumos": [],
            "produtividades": [{"valor_horario": 5.0}],  # no id
        }
        _, _, prods = MOD._build_lookups(catalogo)
        assert prods == {}


# ---------------------------------------------------------------------------
# _validate_encargos_separacao  (lines 323-377, missing 358, 382-388)
# ---------------------------------------------------------------------------


class TestValidateEncargosSeparacao:
    def _make_cpu(self, composicao_itens=None):
        return {
            "codigo": "CPU-01",
            "composicao_itens": composicao_itens or [],
        }

    def test_no_mao_obra_items_no_validacao(self):
        cpu = self._make_cpu([{"categoria_custo": "MATERIAL", "insumo_id": "INS-01"}])
        insumo_lookup = {"INS-01": {"preco_unitario": 50.0, "unidade": "m3"}}
        validacoes = []
        MOD._validate_encargos_separacao("CPU-01", cpu, insumo_lookup, validacoes)
        assert all(v.codigo != "VAL-PLAN-ENCARGOS-DUPLA" for v in validacoes)

    def test_mao_obra_high_price_per_hour_triggers_aviso(self):
        cpu = self._make_cpu([{"categoria_custo": "MAO_OBRA", "insumo_id": "INS-MO"}])
        insumo_lookup = {"INS-MO": {"preco_unitario": 200.0, "unidade": "h"}}
        validacoes = []
        MOD._validate_encargos_separacao("CPU-01", cpu, insumo_lookup, validacoes)
        assert any(v.codigo == "VAL-PLAN-ENCARGOS-DUPLA" and v.status == "AVISO" for v in validacoes)

    def test_mao_obra_low_price_no_aviso(self):
        cpu = self._make_cpu([{"categoria_custo": "MAO_OBRA", "insumo_id": "INS-MO"}])
        insumo_lookup = {"INS-MO": {"preco_unitario": 50.0, "unidade": "h"}}
        validacoes = []
        MOD._validate_encargos_separacao("CPU-01", cpu, insumo_lookup, validacoes)
        assert all(v.codigo != "VAL-PLAN-ENCARGOS-DUPLA" for v in validacoes)

    def test_mao_obra_non_hour_unit_no_aviso(self):
        cpu = self._make_cpu([{"categoria_custo": "MAO_OBRA", "insumo_id": "INS-MO"}])
        insumo_lookup = {"INS-MO": {"preco_unitario": 500.0, "unidade": "mes"}}
        validacoes = []
        MOD._validate_encargos_separacao("CPU-01", cpu, insumo_lookup, validacoes)
        assert all(v.codigo != "VAL-PLAN-ENCARGOS-DUPLA" for v in validacoes)

    def test_insumo_not_in_lookup_skipped(self):
        cpu = self._make_cpu([{"categoria_custo": "MAO_OBRA", "insumo_id": "INS-MISSING"}])
        insumo_lookup = {}
        validacoes = []
        MOD._validate_encargos_separacao("CPU-01", cpu, insumo_lookup, validacoes)
        assert validacoes == []


# ---------------------------------------------------------------------------
# _compute_preco_cat_from_cpu  (lines 180-239, missing 198-199, 203, 213, 224-225, 230, 233)
# ---------------------------------------------------------------------------


class TestComputePrecoCatFromCpu:
    def _make_repo(self, preco=10.0):
        repo = MagicMock()
        repo.resolver_preco.return_value = (preco, "catalog")
        return repo

    def test_unknown_categoria_emits_aviso(self):

        ci = MagicMock()
        ci.insumo_id = "INS-01"
        ci.categoria_custo = "DESCONHECIDO"
        ci.coeficiente = 1.0
        ci.unidade = "m3"

        cpu_model = MagicMock()
        cpu_model.composicao_completa = [ci]

        insumo_lookup = {"INS-01": {"preco_unitario": 10.0, "unidade": "m3"}}
        repo = self._make_repo()
        validacoes = []

        preco_cat, equip_set = MOD._compute_preco_cat_from_cpu(
            cpu_model=cpu_model,
            cpu_codigo="CPU-01",
            insumo_lookup=insumo_lookup,
            repo=repo,
            jurisdicao_id="SP",
            overrides={},
            data_base="2025-01-01",
            erros_insumo=set(),
            validacoes=validacoes,
        )
        assert any(v.codigo == "VAL-PLAN-CAT" for v in validacoes)

    def test_missing_insumo_adds_to_erros(self):
        ci = MagicMock()
        ci.insumo_id = "INS-MISSING"
        ci.categoria_custo = "material"
        ci.coeficiente = 1.0
        ci.unidade = "m3"

        cpu_model = MagicMock()
        cpu_model.composicao_completa = [ci]

        insumo_lookup = {}
        repo = self._make_repo()
        erros_insumo = set()
        validacoes = []

        preco_cat, _ = MOD._compute_preco_cat_from_cpu(
            cpu_model=cpu_model,
            cpu_codigo="CPU-01",
            insumo_lookup=insumo_lookup,
            repo=repo,
            jurisdicao_id="SP",
            overrides={},
            data_base="2025-01-01",
            erros_insumo=erros_insumo,
            validacoes=validacoes,
        )
        assert "INS-MISSING" in erros_insumo

    def test_valid_material_item_adds_to_preco_cat(self):
        ci = MagicMock()
        ci.insumo_id = "INS-01"
        ci.categoria_custo = "material"
        ci.coeficiente = 2.0
        ci.unidade = "m3"

        cpu_model = MagicMock()
        cpu_model.composicao_completa = [ci]

        insumo_lookup = {"INS-01": {"preco_unitario": 10.0, "unidade": "m3"}}
        repo = self._make_repo(preco=10.0)

        with patch(
            "concilium.domain.services.conversor_unidades.ConversorUnidades.resolver_coeficiente_cpu", return_value=2.0
        ):
            preco_cat, _ = MOD._compute_preco_cat_from_cpu(
                cpu_model=cpu_model,
                cpu_codigo="CPU-01",
                insumo_lookup=insumo_lookup,
                repo=repo,
                jurisdicao_id="SP",
                overrides={},
                data_base="2025-01-01",
                erros_insumo=set(),
                validacoes=[],
            )
        assert preco_cat["material"] == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# _validate_coverage  (lines 422-434, missing 478-479, 481-482, 502-503)
# ---------------------------------------------------------------------------


class TestValidateCoverage:
    def test_no_equipes_diretas_returns_early(self):
        canonical = _make_canonical(equipes_diretas=None)
        plan_out = []
        validacoes = []
        MOD._validate_coverage(canonical, plan_out, validacoes)
        assert validacoes == []

    def test_equipes_but_no_match_no_validacoes(self):
        eq = MagicMock()
        eq.item_id = "I-01"
        canonical = _make_canonical(equipes_diretas=[eq])

        plan_item = MagicMock()
        plan_item.item_id = "I-02"

        eap_item = MagicMock()
        eap_item.item_id = "I-99"
        canonical.eap = [eap_item]

        plan_out = [plan_item]
        validacoes = []

        with patch(
            "concilium.domain.services.validador_cobertura_item.validar_cobertura_item", return_value=[]
        ) as mock_val:
            MOD._validate_coverage(canonical, plan_out, validacoes)
            # No matching equipe+planej pair for I-99
            mock_val.assert_not_called()


# ---------------------------------------------------------------------------
# _process_eap_item  (missing branches: synthetic-cpu failure, early-override
# short-circuit, preco_cat None after both bottom-up and fallback sources)
# ---------------------------------------------------------------------------


class TestProcessEapItem:
    def _call(self, item, cpu_lookup, prod_lookup, plan_out, erros_eap, validacoes):
        return MOD._process_eap_item(
            item,
            cpu_lookup,
            {},
            prod_lookup,
            {},
            {},
            {},
            MagicMock(),
            None,
            None,
            None,
            plan_out,
            erros_eap,
            set(),
            set(),
            validacoes,
        )

    def test_synthetic_cpu_creation_fails_records_erro(self):
        item = SimpleNamespace(cpu_id="CPU-999", item_id="I1")
        erros_eap: list = []
        with patch.object(MOD._cpu_fallback, "_create_synthetic_cpu", return_value=None):
            self._call(item, {}, {}, [], erros_eap, [])
        assert erros_eap == ["CPU-999"]

    def test_early_override_short_circuits(self):
        item = SimpleNamespace(cpu_id="CPU-1", item_id="I2")
        cpu = {"codigo": "CPU-1", "producao_id_ref": "PR1"}
        cpu_lookup = {"CPU-1": cpu}
        prod_lookup = {"PR1": {"id": "PR1"}}
        plan_out: list = []
        early_entry = {"item_id": "I2"}
        with patch.object(MOD._process_item, "_try_early_override", return_value=early_entry):
            self._call(item, cpu_lookup, prod_lookup, plan_out, [], [])
        assert plan_out == [early_entry]

    def test_preco_cat_none_after_both_sources_returns(self):
        item = SimpleNamespace(cpu_id="CPU-2", item_id="I3")
        cpu = {"codigo": "CPU-2", "producao_id_ref": "PR2"}
        cpu_lookup = {"CPU-2": cpu}
        prod_lookup = {"PR2": {"id": "PR2"}}
        plan_out: list = []
        with (
            patch.object(MOD._process_item, "_try_early_override", return_value=None),
            patch.object(MOD._process_item, "_compute_preco_cat_from_production", return_value=None),
            patch.object(MOD._cpu_fallback, "_compute_preco_cat_from_cpu", return_value=(None, set())),
            patch(
                "concilium.domain.models.catalog.catalogo.CPU.model_validate",
                return_value=MagicMock(),
            ),
        ):
            self._call(item, cpu_lookup, prod_lookup, plan_out, [], [])
        assert plan_out == []

    def _call_com_bdi(self, item, cpu_lookup, prod_lookup, plan_out, erros_eap, validacoes):
        """Como _call, mas com bdi_aplicado completo (necessário quando preco_cat resolve
        e o fluxo chega em _apply_com_bdi_override, que indexa bdi_aplicado[cat])."""
        bdi_aplicado = {"material": 0.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        return MOD._process_eap_item(
            item,
            cpu_lookup,
            {},
            prod_lookup,
            {},
            {},
            bdi_aplicado,
            MagicMock(),
            None,
            None,
            None,
            plan_out,
            erros_eap,
            set(),
            set(),
            validacoes,
        )

    def test_fonte1_sucesso_planejamento_sem_fallback(self):
        """Issue #132: Fonte 1 (bottom-up) resolveu → Planejamento.precificacao_via_fallback_composicao=False."""
        item = SimpleNamespace(cpu_id="CPU-4", item_id="I4", quantitativo=1.0)
        cpu = {"codigo": "CPU-4", "producao_id_ref": "PR4"}
        cpu_lookup = {"CPU-4": cpu}
        prod_lookup = {"PR4": {"id": "PR4"}}
        plan_out: list = []
        preco_cat = {"material": 1.0, "diesel": 0.0, "mao_obra": 2.0, "equipamentos": 0.0}
        with (
            patch.object(MOD._process_item, "_try_early_override", return_value=None),
            patch.object(MOD._process_item, "_compute_preco_cat_from_production", return_value=preco_cat),
        ):
            self._call_com_bdi(item, cpu_lookup, prod_lookup, plan_out, [], [])
        assert len(plan_out) == 1
        assert plan_out[0].precificacao_via_fallback_composicao is False

    def test_fonte2_sucesso_planejamento_com_fallback(self):
        """Issue #132: Fonte 1 falhou, Fonte 2 (composicao_itens) resolveu →
        Planejamento.precificacao_via_fallback_composicao=True."""
        item = SimpleNamespace(cpu_id="CPU-5", item_id="I5", quantitativo=1.0)
        cpu = {"codigo": "CPU-5", "producao_id_ref": "PR5"}
        cpu_lookup = {"CPU-5": cpu}
        prod_lookup = {"PR5": {"id": "PR5"}}
        plan_out: list = []
        preco_cat_fallback = {"material": 1.0, "diesel": 0.0, "mao_obra": 2.0, "equipamentos": 3.0}
        with (
            patch.object(MOD._process_item, "_try_early_override", return_value=None),
            patch.object(MOD._process_item, "_compute_preco_cat_from_production", return_value=None),
            patch.object(
                MOD._process_item,
                "_preco_cat_fallback_composicao",
                return_value=(preco_cat_fallback, set()),
            ),
        ):
            self._call_com_bdi(item, cpu_lookup, prod_lookup, plan_out, [], [])
        assert len(plan_out) == 1
        assert plan_out[0].precificacao_via_fallback_composicao is True


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

