"""ADR-181 F4/D4 — guard anti-double-count generalizado por insumo tagueado.

O guard da ADR-176 D4.1 (`_transporte_ja_contabilizado_direto`) só enxerga
`EquipeDireta.custo_mobilizacao_mensal`/`custo_desmobilizacao_mensal`. Quando
mob/demob é decomposto como insumo de catálogo inserido direto na EAP (padrão
do `v12.json` do CMOC Ouvidor — insumos `TERCEIRIZADO`/`SERVICO` tipo
`SUPVEG-MOB-*` referenciados via `composicao_itens` de uma CPU), esse caminho
passava batido pelo guard, reproduzindo o double-count confirmado em SERRA_VERDE
(ADR-176 P5). `_custo_direto_insumo_mob_tagueado` fecha essa lacuna.
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
        "adr181_f4_indir", path, submodule_search_locations=[str(path.parent)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["adr181_f4_indir"] = mod
    spec.loader.exec_module(mod)
    return mod


def _eap_item(item_id="eap-1", cpu_id="CPU-SUPVEG-MOB", quantitativo=1.0):
    return SimpleNamespace(item_id=item_id, cpu_id=cpu_id, quantitativo=quantitativo)


def _catalogo(insumos: list[dict], cpus: list[dict]) -> dict:
    return {"insumos": insumos, "cpus": cpus}


class TestCustoDiretoInsumoMobTagueado:
    def _fn(self):
        return _load_indir()._custo_direto_insumo_mob_tagueado

    def test_none_ou_vazio_retorna_zero(self):
        fn = self._fn()
        assert fn(None, {"insumos": [], "cpus": []}) == 0.0
        assert fn([_eap_item()], None) == 0.0
        assert fn([], {"insumos": [], "cpus": []}) == 0.0

    def test_sem_insumo_tagueado_retorna_zero(self):
        catalogo = _catalogo(
            insumos=[{"codigo": "SUPVEG-MOB-001", "preco_unitario": 674932.70}],
            cpus=[
                {
                    "codigo": "CPU-SUPVEG-MOB",
                    "composicao_itens": [{"insumo_id": "SUPVEG-MOB-001", "coeficiente": 1.0}],
                }
            ],
        )
        assert self._fn()([_eap_item()], catalogo) == 0.0

    def test_soma_custo_do_insumo_tagueado_na_composicao(self):
        """Reproduz o cenário do v12.json: insumo lump SUPVEG-MOB-001 referenciado
        via composicao_itens de uma CPU usada na EAP com quantitativo=1."""
        catalogo = _catalogo(
            insumos=[
                {"codigo": "SUPVEG-MOB-001", "preco_unitario": 674932.70, "classificacao_mob_demob": True},
            ],
            cpus=[
                {
                    "codigo": "CPU-SUPVEG-MOB",
                    "composicao_itens": [{"insumo_id": "SUPVEG-MOB-001", "coeficiente": 1.0}],
                }
            ],
        )
        item = _eap_item(quantitativo=1.0)
        assert self._fn()([item], catalogo) == pytest.approx(674932.70)

    def test_multiplica_por_quantitativo_do_item(self):
        catalogo = _catalogo(
            insumos=[
                {"codigo": "SUPVEG-CANTEIRO-001", "preco_unitario": 1_366_024.06, "classificacao_mob_demob": True}
            ],
            cpus=[
                {
                    "codigo": "CPU-CANTEIRO",
                    "composicao_itens": [{"insumo_id": "SUPVEG-CANTEIRO-001", "coeficiente": 1.0}],
                }
            ],
        )
        item = _eap_item(cpu_id="CPU-CANTEIRO", quantitativo=3.0)  # 3 meses de canteiro
        assert self._fn()([item], catalogo) == pytest.approx(1_366_024.06 * 3)

    def test_soma_multiplos_itens_de_eap(self):
        catalogo = _catalogo(
            insumos=[
                {"codigo": "SUPVEG-MOB-001", "preco_unitario": 674932.70, "classificacao_mob_demob": True},
                {"codigo": "SUPVEG-DESMOB-001", "preco_unitario": 289256.87, "classificacao_mob_demob": True},
            ],
            cpus=[
                {"codigo": "CPU-MOB", "composicao_itens": [{"insumo_id": "SUPVEG-MOB-001", "coeficiente": 1.0}]},
                {"codigo": "CPU-DESMOB", "composicao_itens": [{"insumo_id": "SUPVEG-DESMOB-001", "coeficiente": 1.0}]},
            ],
        )
        itens = [_eap_item("eap-1", "CPU-MOB"), _eap_item("eap-2", "CPU-DESMOB")]
        assert self._fn()(itens, catalogo) == pytest.approx(674932.70 + 289256.87)

    def test_cpu_desconhecida_ignorada_sem_erro(self):
        catalogo = _catalogo(insumos=[], cpus=[])
        assert self._fn()([_eap_item(cpu_id="CPU-INEXISTENTE")], catalogo) == 0.0


class TestProcessMobCategoriaDedupInsumoTagueado:
    """Integração: _process_mob_categoria desconta o insumo tagueado da EAP do lump MOB,
    somado ao desconto de EquipeDireta já existente (ADR-176 D4.1)."""

    def _fn(self):
        return _load_indir()._process_mob_categoria

    def test_desconta_insumo_tagueado_do_lump(self):
        catalogo = _catalogo(
            insumos=[{"codigo": "SUPVEG-MOB-001", "preco_unitario": 674932.70, "classificacao_mob_demob": True}],
            cpus=[{"codigo": "CPU-MOB", "composicao_itens": [{"insumo_id": "SUPVEG-MOB-001", "coeficiente": 1.0}]}],
        )
        categorias_config_raw = [{"categoria": "MOB", "driver": "one_time", "custo_fixo_total": 674932.70}]
        indir, _semanal = self._fn()(
            cat={"descricao": "Mobilização"},
            categorias_config_raw=categorias_config_raw,
            dados_mob={},
            num_pessoas_direta=0,
            prazo_meses=3,
            n_semanas=12,
            dv4_policy=None,
            policy_scale={},
            catalogo=catalogo,
            eap=[_eap_item(cpu_id="CPU-MOB")],
        )
        assert indir.custo_total == 0.0

    def test_soma_com_desconto_de_equipe_direta_existente(self):
        catalogo = _catalogo(
            insumos=[{"codigo": "SUPVEG-MOB-001", "preco_unitario": 100_000.0, "classificacao_mob_demob": True}],
            cpus=[{"codigo": "CPU-MOB", "composicao_itens": [{"insumo_id": "SUPVEG-MOB-001", "coeficiente": 1.0}]}],
        )
        equipes = [SimpleNamespace(custo_mobilizacao_mensal=30_000.0, custo_desmobilizacao_mensal=0.0)]
        categorias_config_raw = [{"categoria": "MOB", "driver": "one_time", "custo_fixo_total": 200_000.0}]
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
            eap=[_eap_item(cpu_id="CPU-MOB")],
        )
        # 200_000 - (100_000 insumo tagueado + 30_000 equipe direta) = 70_000
        assert indir.custo_total == pytest.approx(70_000.0)

    def test_sem_eap_mantem_comportamento_anterior(self):
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
