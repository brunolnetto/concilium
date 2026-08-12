"""ADR-181 F5/D2 — pool vira fonte de custo unitário consumida pela agregação
de mob/demob de projeto em `_mob.py`.

Generaliza o guard anti-double-count (ADR-176 D4.1, F4 desta ADR) para o
terceiro modelo histórico de mob/demob — pool/`CampanhaEquipamento`
(ADR-137/176: "3 modelos desconexos"). `RecursoContrato.custo_mob_desmob_contrato`
(ADR-073, `n_cadeias × (custo_mob_unit+custo_demob_unit) × quantidade_contratada`)
já é o custo REAL realizado — inclusive já descontando movimentações evitadas
por perpetuação — então é usado direto em vez de recalcular do zero.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[4]


def _load_indir():
    path = (
        _ROOT
        / "src/concilium/application/skills/manifests"
        / "06-resultado-financeiro/_indiretos/_skill_helpers/__init__.py"
    )
    spec = importlib.util.spec_from_file_location(
        "adr181_f5_indir", path, submodule_search_locations=[str(path.parent)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["adr181_f5_indir"] = mod
    spec.loader.exec_module(mod)
    return mod


def _contrato(custo_mob_desmob_contrato=0.0):
    return SimpleNamespace(custo_mob_desmob_contrato=custo_mob_desmob_contrato)


class TestCustoPoolJaContabilizadoDireto:
    def _fn(self):
        return _load_indir()._custo_pool_ja_contabilizado_direto

    def test_none_retorna_zero(self):
        assert self._fn()(None) == 0.0

    def test_lista_vazia_retorna_zero(self):
        assert self._fn()([]) == 0.0

    def test_soma_custo_realizado_de_todos_os_contratos(self):
        contratos = [_contrato(12000.0), _contrato(8500.0)]
        assert self._fn()(contratos) == pytest.approx(20500.0)

    def test_contrato_sem_o_campo_conta_zero(self):
        contratos = [SimpleNamespace(tipo_id="ESC-3CAT")]
        assert self._fn()(contratos) == 0.0

    def test_usa_custo_realizado_nao_quantidade_bruta(self):
        """n_cadeias já reduzido pela perpetuação — não é quantidade_contratada
        ingênua × (mob_unit+demob_unit); o campo pronto reflete isso."""
        # Ex.: 5 unidades contratadas, mas perpetuação faz só 2 cadeias mobilizarem
        # de fato (custo_mob_desmob_contrato = 2 × (custo_mob+custo_demob), não 5×).
        contrato = _contrato(custo_mob_desmob_contrato=2 * (6500.0 + 800.0))
        assert self._fn()([contrato]) == pytest.approx(2 * 7300.0)


class TestProcessMobCategoriaDedupPool:
    def _fn(self):
        return _load_indir()._process_mob_categoria

    def test_desconta_custo_de_pool_do_lump(self):
        categorias_config_raw = [{"categoria": "MOB", "driver": "one_time", "custo_fixo_total": 50_000.0}]
        contratos = [_contrato(20_000.0)]
        indir, _semanal = self._fn()(
            cat={"descricao": "Mobilização"},
            categorias_config_raw=categorias_config_raw,
            dados_mob={},
            num_pessoas_direta=0,
            prazo_meses=3,
            n_semanas=12,
            dv4_policy=None,
            policy_scale={},
            contratos_recurso=contratos,
        )
        assert indir.custo_total == pytest.approx(30_000.0)

    def test_soma_com_equipe_direta_e_insumo_tagueado(self):
        """Os 3 modelos (EquipeDireta, insumo tagueado, pool) descontam juntos —
        sem double-count entre eles, sem duplo desconto do mesmo evento."""
        categorias_config_raw = [{"categoria": "MOB", "driver": "one_time", "custo_fixo_total": 100_000.0}]
        equipes = [SimpleNamespace(custo_mobilizacao_mensal=10_000.0, custo_desmobilizacao_mensal=0.0)]
        catalogo = {
            "insumos": [{"codigo": "SUPVEG-MOB-001", "preco_unitario": 20_000.0, "classificacao_mob_demob": True}],
            "cpus": [{"codigo": "CPU-MOB", "composicao_itens": [{"insumo_id": "SUPVEG-MOB-001", "coeficiente": 1.0}]}],
        }
        eap = [SimpleNamespace(item_id="eap-1", cpu_id="CPU-MOB", quantitativo=1.0)]
        contratos = [_contrato(15_000.0)]
        indir, _semanal = self._fn()(
            cat={"descricao": "Mobilização"},
            categorias_config_raw=categorias_config_raw,
            dados_mob={},
            num_pessoas_direta=0,
            prazo_meses=3,
            n_semanas=12,
            dv4_policy=None,
            policy_scale={},
            equipes_diretas=equipes,
            catalogo=catalogo,
            eap=eap,
            contratos_recurso=contratos,
        )
        # 100_000 - (10_000 equipe + 20_000 insumo + 15_000 pool) = 55_000
        assert indir.custo_total == pytest.approx(55_000.0)

    def test_sem_contratos_recurso_mantem_comportamento_anterior(self):
        categorias_config_raw = [{"categoria": "MOB", "driver": "one_time", "custo_fixo_total": 5000.0}]
        indir, _semanal = self._fn()(
            cat={"descricao": "Mobilização"},
            categorias_config_raw=categorias_config_raw,
            dados_mob={},
            num_pessoas_direta=0,
            prazo_meses=3,
            n_semanas=12,
            dv4_policy=None,
            policy_scale={},
        )
        assert indir.custo_total == 5000.0
