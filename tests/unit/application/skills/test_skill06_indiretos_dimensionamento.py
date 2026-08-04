"""Coverage sweep 11 — files below 90%:

- _indiretos/_skill_helpers_a.py (88%) — missing: 38, 122-124, 132, 137, 170, 202-203, 216-217, 242->exit
- mixins/catalog.py (88%) — missing: 49->53, 52, 85-110, 123-124, 167->162, 215-216, 230-231, 237-238,
                                       248->251, 255->251, 259->255, 264-265, 280
- recursos.py (89%) — missing: 77, 271-295
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parents[4]

def _load_ind_helpers_a():
    path = (
        _ROOT
        / "src/concilium/application/skills/manifests"
        / "06-resultado-financeiro/_indiretos/_skill_helpers/_dimensionamento.py"
    )
    spec = importlib.util.spec_from_file_location("ind_helpers_a_sw11", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── _indiretos/_skill_helpers_a.py ────────────────────────────────────────────


class TestMesesEntre:
    def test_meses_entre_basic(self):
        """Line 38: return value of _meses_entre."""
        from datetime import date

        mod = _load_ind_helpers_a()
        result = mod._meses_entre(date(2026, 1, 1), date(2026, 6, 30))
        assert result == 6


class TestDmfFindTemplateId:
    def test_acima_de_branch_returns_template(self):
        """Lines 122-123: 'acima_de' step matches."""
        mod = _load_ind_helpers_a()
        regra = {
            "steps": [
                {"acima_de": 500_000, "equipe_base": "TPL-GRANDE"},
                {"ate_valor": 500_000, "equipe_base": "TPL-PEQUENO"},
            ]
        }
        result = mod._dmf_find_template_id(regra, 1_000_000.0)
        assert result == "TPL-GRANDE"

    def test_no_matching_step_returns_none(self):
        """Line 124: return None when no step matches."""
        mod = _load_ind_helpers_a()
        regra = {"steps": []}
        result = mod._dmf_find_template_id(regra, 100.0)
        assert result is None

    def test_first_step_no_match_continues_to_next(self):
        """Branch 122->119: primeiro step não casa nenhuma condição -> continua para o próximo."""
        mod = _load_ind_helpers_a()
        regra = {
            "steps": [
                {"acima_de": 999_999.0, "equipe_base": "TPL-NUNCA"},
                {"ate_valor": 100.0, "equipe_base": "TPL-PEQUENO"},
            ]
        }
        result = mod._dmf_find_template_id(regra, 50.0)
        assert result == "TPL-PEQUENO"


class TestDaMagnitudeFinanceira:
    def _mk_canonical(self, total_venda):
        from types import SimpleNamespace

        plan_item = SimpleNamespace(subtotal=SimpleNamespace(sem_bdi=SimpleNamespace(total=total_venda)))
        return SimpleNamespace(planejamento=[plan_item])

    def test_no_tpl_id_returns_none(self):
        """Line 132: tpl_id is None → return None."""
        mod = _load_ind_helpers_a()
        canonical = self._mk_canonical(100.0)
        regra = {"steps": []}  # no matching step
        result = mod._da_magnitude_financeira("ADM", regra, canonical, {})
        assert result is None

    def test_template_not_found_returns_none(self):
        """Line 137: tpl_id found but template not in estruturas → return None."""
        mod = _load_ind_helpers_a()
        canonical = self._mk_canonical(1_500_000.0)
        regra = {"steps": [{"acima_de": 1_000_000, "equipe_base": "TPL-X"}]}
        catalogo = {"estruturas_indiretas": [{"codigo": "OTHER", "mao_de_obra": []}]}
        result = mod._da_magnitude_financeira("ADM", regra, canonical, catalogo)
        assert result is None

    def test_template_found_returns_dict(self):
        """Line 170: magnitude_financeira returns valid result."""
        mod = _load_ind_helpers_a()
        canonical = self._mk_canonical(1_500_000.0)
        regra = {
            "driver": "magnitude_financeira",
            "steps": [{"acima_de": 1_000_000, "equipe_base": "TPL-X"}],
        }
        catalogo = {
            "estruturas_indiretas": [
                {
                    "codigo": "TPL-X",
                    "mao_de_obra": [{"funcao_id": "ENG", "quantidade": 1}],
                    "equipamentos": [],
                    "verbas": [],
                }
            ]
        }
        result = mod._dimensionar_automatico("ADM", regra, canonical, catalogo)
        assert "mao_de_obra" in result


class TestDaMagnitudeFinanceiraRealCatalogMendeslobo:
    """Regressão: catalog.py descartava 'estruturas_indiretas' de templates.json, então o driver
    magnitude_financeira do perfil mendeslobo (real) nunca escalava ADM por porte da obra — toda
    obra caía no fallback estático de _composicao_default_por_categoria. Estes testes usam o
    perfil e o catálogo reais (não sintéticos) para travar que a segmentação ADM_PEQUENA/MEDIA/
    GRANDE de fato dispara."""

    @staticmethod
    def _catalogo_real():
        import json

        path = _ROOT / "config/catalogos/mendeslobo/templates.json"
        return {"estruturas_indiretas": json.loads(path.read_text(encoding="utf-8"))["estruturas_indiretas"]}

    @staticmethod
    def _regra_adm_real():
        import json

        path = _ROOT / "config/perfis/mendeslobo.json"
        perfil = json.loads(path.read_text(encoding="utf-8"))
        adm = next(c for c in perfil["categorias_indireto"] if c["codigo"] == "ADM")
        return adm["regra_dimensionamento"]

    @staticmethod
    def _mk_canonical(total_venda):
        from types import SimpleNamespace

        plan_item = SimpleNamespace(subtotal=SimpleNamespace(sem_bdi=SimpleNamespace(total=total_venda)))
        return SimpleNamespace(planejamento=[plan_item])

    def _funcao_ids(self, mod, venda_sem_bdi):
        result = mod._dimensionar_automatico(
            "ADM", self._regra_adm_real(), self._mk_canonical(venda_sem_bdi), self._catalogo_real()
        )
        return {item["funcao_id"] for item in result["mao_de_obra"]["itens"]}

    def test_obra_pequena_usa_template_adm_pequena(self):
        mod = _load_ind_helpers_a()
        assert self._funcao_ids(mod, 5_000_000.0) == {"MO-ENCARREG-GERAL", "MO-P0006"}

    def test_obra_media_usa_template_adm_media(self):
        mod = _load_ind_helpers_a()
        assert self._funcao_ids(mod, 30_000_000.0) == {
            "MO-ENG-CIVIL",
            "MO-ENCARREG-GERAL",
            "MO-ALMOXARIFE",
            "MO-P0006",
        }

    def test_obra_grande_usa_template_adm_grande_nao_fallback_estatico(self):
        """Antes do fix, isso caía em _composicao_default_por_categoria (só 'Coordenador')."""
        mod = _load_ind_helpers_a()
        ids = self._funcao_ids(mod, 200_000_000.0)
        assert ids == {
            "MO-GERENTE",
            "MO-ENG-CIVIL",
            "MO-ENCARREG-GERAL",
            "MO-ALMOXARIFE",
            "MO-P0006",
        }
        assert "Coordenador" not in ids  # não é o item do fallback estático

    def test_obra_grande_mao_de_obra_resolve_custo_real_nao_zero(self):
        """Regressão do bug de prefixo MO-: sem 'MO-' no funcao_id, RepositorioInsumo.obter_insumo
        não encontra o insumo (chave real é 'MO-GERENTE' etc.), _bcfd_enrich_mo_item não populava
        custo_mensal, e a mão de obra inteira do ADM_GRANDE silenciosamente custava R$0."""
        import json

        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        mod = _load_ind_helpers_a()
        catalogo = self._catalogo_real()
        insumos_dir = _ROOT / "config/catalogos/mendeslobo/insumos/mao_obra"
        catalogo["insumos"] = [
            json.loads(p.read_text(encoding="utf-8")) for p in insumos_dir.glob("*.json")
        ]
        repo = RepositorioInsumo(catalogo)

        comp = mod._dimensionar_automatico(
            "ADM", self._regra_adm_real(), self._mk_canonical(200_000_000.0), catalogo
        )
        mod._bcfd_enrich_mo_itens(comp, repo, None, None, None)
        custo_total = sum(item["custo_mensal"] for item in comp["mao_de_obra"]["itens"])
        assert custo_total > 0


class TestBcfdResolveSalarioBase:
    def test_exception_returns_preco(self):
        """Lines 202-203: ConversorUnidades.converter_preco raises → returns preco."""
        mod = _load_ind_helpers_a()
        with patch(
            "concilium.domain.services.conversor_unidades.ConversorUnidades.converter_preco",
            side_effect=ValueError("unknown unit"),
        ):
            result = mod._bcfd_resolve_salario_base(5000.0, "semana_invalida")
        assert result == 5000.0


class TestBcfdApplyEncargos:
    def test_override_val_returns_override(self):
        """Line 216: custo_com_encargos override > 0 → return float(override_val)."""
        mod = _load_ind_helpers_a()
        atrib = {"custo_com_encargos": 9999.0}
        result = mod._bcfd_apply_encargos(5000.0, atrib)
        assert result == 9999.0

    def test_resolver_encargo_path(self):
        """Line 217: resolver_encargo called when no override."""
        mod = _load_ind_helpers_a()
        with patch(
            "concilium.domain.services.financial.encargo_resolver.resolver_encargo",
            return_value=0.5,
        ):
            result = mod._bcfd_apply_encargos(1000.0, {})
        assert result == pytest.approx(1500.0)


class TestBcfdEnrichMoItem:
    def test_descricao_already_present_skips_assignment(self):
        """Line 242->exit: 'descricao' already in f → if-body not executed."""
        mod = _load_ind_helpers_a()
        repo = MagicMock()
        repo.obter_insumo.return_value = {
            "preco_unitario": 1000.0,
            "unidade": "mes",
            "atributos_especificos": {},
        }
        repo.resolver_preco.return_value = (1000.0, "catalog")

        f = {"funcao_id": "ENG-001", "descricao": "Engenheiro já definido"}
        mod._bcfd_enrich_mo_item(f, repo, None, None, None)
        assert f["descricao"] == "Engenheiro já definido"
        assert "custo_mensal" in f

    def test_descricao_missing_gets_assigned(self):
        """Lines 242-243: 'descricao' not in f → assigned from insumo."""
        mod = _load_ind_helpers_a()
        repo = MagicMock()
        repo.obter_insumo.return_value = {
            "preco_unitario": 800.0,
            "unidade": "mes",
            "descricao": "Técnico de Campo",
            "atributos_especificos": {},
        }
        repo.resolver_preco.return_value = (800.0, "catalog")

        f = {"funcao_id": "TEC-001"}
        mod._bcfd_enrich_mo_item(f, repo, None, None, None)
        assert f.get("descricao") == "Técnico de Campo"

    def test_no_insumo_returns_early(self):
        """Lines 229-230: insumo not found → return early, f unchanged."""
        mod = _load_ind_helpers_a()
        repo = MagicMock()
        repo.obter_insumo.return_value = None
        f = {"funcao_id": "MISSING-001"}
        mod._bcfd_enrich_mo_item(f, repo, None, None, None)
        assert "custo_mensal" not in f



