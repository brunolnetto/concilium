"""ADR-176 F4 — indireto MOB não conta de novo o transporte já pago pelo direto.

Achado (ADR-137 P5, confirmado em produção no benchmark SERRA_VERDE): quando
`EquipeDireta.custo_mobilizacao_mensal`/`custo_desmobilizacao_mensal` (skill-05,
populados a partir do mesmo dado de catálogo `custo_mobilizacao`/
`custo_desmobilizacao` por equipamento/função) já contam o custo de transportar
um recurso até o canteiro, a categoria MOB indireta (skill-06) não deveria somar
esse mesmo evento físico de novo — nem no caminho pré-agregado
(`categorias_config`, usado por todos os benchmarks reais hoje) nem no caminho
composicional (`_custo_mob_decomposto`).

Escrito antes da implementação (red phase).
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
        "adr176_indir_dedup", path, submodule_search_locations=[str(path.parent)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["adr176_indir_dedup"] = mod
    spec.loader.exec_module(mod)
    return mod


def _equipe(custo_mob=0.0, custo_demob=0.0):
    return SimpleNamespace(
        funcoes=[],
        permanencia_efetiva_meses=0.0,
        custo_mobilizacao_mensal=custo_mob,
        custo_desmobilizacao_mensal=custo_demob,
    )


class TestTransporteJaContabilizadoDireto:
    def _fn(self):
        return _load_indir()._transporte_ja_contabilizado_direto

    def test_none_retorna_zero(self):
        assert self._fn()(None) == 0.0

    def test_lista_vazia_retorna_zero(self):
        assert self._fn()([]) == 0.0

    def test_soma_mob_e_demob_de_todas_as_equipes(self):
        equipes = [_equipe(1000.0, 500.0), _equipe(2000.0, 300.0)]
        assert self._fn()(equipes) == pytest.approx(3800.0)

    def test_equipe_sem_os_campos_conta_zero(self):
        equipes = [SimpleNamespace(funcoes=[], permanencia_efetiva_meses=0.0)]
        assert self._fn()(equipes) == 0.0


class TestProcessMobCategoriaDedupCategoriasConfig:
    """Caminho pré-agregado (categorias_config) — usado por todos os benchmarks reais."""

    def _fn(self):
        return _load_indir()._process_mob_categoria

    def test_desconta_transporte_ja_contabilizado_do_lump(self):
        categorias_config_raw = [
            {"categoria": "MOB", "driver": "one_time", "custo_fixo_total": 10689489.96},
        ]
        equipes = [_equipe(30000.0, 15000.0), _equipe(20000.0, 10000.0)]  # soma = 75000.0
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
        )
        assert indir.custo_total == pytest.approx(10689489.96 - 75000.0)

    def test_sem_equipes_diretas_mantem_lump_intacto(self):
        categorias_config_raw = [
            {"categoria": "MOB", "driver": "one_time", "custo_fixo_total": 7500.0},
        ]
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
        assert indir.custo_total == 7500.0

    def test_desconto_maior_que_lump_nao_fica_negativo(self):
        categorias_config_raw = [
            {"categoria": "MOB", "driver": "one_time", "custo_fixo_total": 1000.0},
        ]
        equipes = [_equipe(5000.0, 5000.0)]  # soma = 10000.0 > lump de 1000.0
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
        )
        assert indir.custo_total == 0.0


class TestProcessMobCategoriaDedupComposicional:
    """Caminho composicional (_custo_mob_decomposto) — só desconta de transporte_total."""

    def _fn(self):
        return _load_indir()._process_mob_categoria

    def test_desconta_so_do_transporte_nao_do_beneficio(self):
        dados_mob = {
            "mobilizacoes": [
                {
                    "descricao": "Mob. equip.",
                    "num_unidades": 2,
                    "origem": "A",
                    "destino": "B",
                    "distancia_km": 100,
                    "custo_km": 10.0,
                }
            ],  # transporte_total = 2*100*10 = 2000.0
        }
        # equipes_diretas presente (não-vazia) roteia o benefício para o cálculo
        # por equipe (_custo_alimentacao_por_equipe); com funcoes=[] e permanência
        # 0.0, essa parcela é 0 — o que importa aqui é que ela não é afetada pelo
        # desconto de transporte_ja_contabilizado_direto.
        equipes = [_equipe(300.0, 200.0)]  # já contabilizado direto = 500.0
        indir, _semanal = self._fn()(
            cat={"descricao": "Mobilização"},
            categorias_config_raw=[],
            dados_mob=dados_mob,
            num_pessoas_direta=4,
            prazo_meses=2,
            n_semanas=8,
            dv4_policy=None,
            policy_scale={},
            equipes_diretas=equipes,
        )
        # transporte deduplicado: 2000 - 500 = 1500; benefício = 0 (funcoes vazias); baixadas = 0.
        assert indir.custo_total == pytest.approx(1500.0)
