"""ADR-176 F2 — decomposição do bucket MOB composicional: TDD.

`_custo_mob_composicional` soma três componentes de negócio distintos
(transporte de recurso, benefício de pessoal recorrente, baixadas) num único
total — condição prévia para a unificação de custo de mob/demob com pool e
`EquipeDireta` (ADR-176 F4) é primeiro conseguir isolar `transporte_total`
dos outros dois, que não são mob/demob.

Escrito antes da implementação (red phase).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[4]


def _load_mob():
    path = (
        _ROOT
        / "src/concilium/application/skills/manifests"
        / "06-resultado-financeiro/_indiretos/_skill_helpers/__init__.py"
    )
    spec = importlib.util.spec_from_file_location("adr176_indir", path, submodule_search_locations=[str(path.parent)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["adr176_indir"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestCustoMobDecompostoSubTotais:
    def _fn(self):
        return _load_mob()._custo_mob_decomposto

    def test_transporte_isolado_das_mobilizacoes(self):
        dados_mob = {
            "mobilizacoes": [
                {
                    "descricao": "Mob. equip.",
                    "num_unidades": 3,
                    "origem": "Goiânia",
                    "destino": "Aracoiaba",
                    "distancia_km": 2200,
                    "custo_km": 12.5,
                }
            ],
        }
        result = self._fn()(dados_mob, num_pessoas_direta=0, prazo_meses=0)
        assert result.transporte_total == pytest.approx(3 * 2200 * 12.5)
        assert result.beneficio_pessoal_total == 0.0
        assert result.baixadas_total == 0.0
        assert len(result.mobilizacoes) == 1

    def test_beneficio_pessoal_isolado_do_legado(self):
        dados_mob = {"custo_pessoa_mes": 1850}
        result = self._fn()(dados_mob, num_pessoas_direta=5, prazo_meses=3)
        assert result.transporte_total == 0.0
        assert result.beneficio_pessoal_total == pytest.approx(5 * 1850 * 3)
        assert result.baixadas_total == 0.0

    def test_baixadas_isoladas(self):
        dados_mob = {
            "mobilizacoes": [],
            "baixadas": [
                {"num_pessoas": 3, "valor_por_pessoa": 500.0, "meses_ocorrencia": ["jan", "fev"]},
            ],
        }
        result = self._fn()(dados_mob, num_pessoas_direta=0, prazo_meses=0)
        assert result.baixadas_total == pytest.approx(3 * 500.0 * 2)
        assert result.transporte_total == 0.0
        assert result.beneficio_pessoal_total == 0.0

    def test_total_e_soma_dos_tres_subtotais(self):
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
            ],
            "custo_pessoa_mes": 1000,
            "baixadas": [{"num_pessoas": 1, "valor_por_pessoa": 200.0, "meses_ocorrencia": ["jan"]}],
        }
        result = self._fn()(dados_mob, num_pessoas_direta=4, prazo_meses=2)
        assert result.total == pytest.approx(
            result.transporte_total + result.beneficio_pessoal_total + result.baixadas_total
        )
        assert result.total == pytest.approx(2 * 100 * 10.0 + 4 * 1000 * 2 + 1 * 200.0 * 1)

    def test_beneficio_bottom_up_conta_como_beneficio_pessoal_nao_transporte(self):
        equipes = [
            SimpleNamespace(
                funcoes=[SimpleNamespace(funcao_id="P0001", num_pessoas=2)],
                permanencia_efetiva_meses=3.0,
            )
        ]
        catalogo = {
            "insumos": [
                {
                    "codigo": "BEN-VA",
                    "tipo": "BENEFICIO",
                    "status": "ativo",
                    "preco_unitario": 35.0,
                    "atributos_especificos": {"periodicidade_beneficio": "mensal", "aplicavel_tipo_contrato": None},
                }
            ]
        }
        result = self._fn()(
            {"custo_pessoa_mes": 1850}, num_pessoas_direta=2, prazo_meses=3, equipes_diretas=equipes, catalogo=catalogo
        )
        assert result.beneficio_pessoal_total == pytest.approx(2 * 35.0 * 3.0)
        assert result.transporte_total == 0.0


class TestCustoMobComposicionalRetrocompativel:
    """Paridade numérica exata entre o wrapper legado e o breakdown novo."""

    def _decomposto(self):
        return _load_mob()._custo_mob_decomposto

    def _composicional(self):
        return _load_mob()._custo_mob_composicional

    def _dados(self):
        return {
            "mobilizacoes": [
                {
                    "descricao": "Mob. equip.",
                    "num_unidades": 3,
                    "origem": "A",
                    "destino": "B",
                    "distancia_km": 2200,
                    "custo_km": 12.5,
                }
            ],
            "custo_pessoa_mes": 1850,
            "baixadas": [{"num_pessoas": 2, "valor_por_pessoa": 300.0, "meses_ocorrencia": ["mar"]}],
        }

    def test_wrapper_retorna_mesmo_total_e_mobilizacoes_do_breakdown(self):
        dados = self._dados()
        breakdown = self._decomposto()(dados, num_pessoas_direta=10, prazo_meses=4)
        total, mobs = self._composicional()(dados, num_pessoas_direta=10, prazo_meses=4)
        assert total == breakdown.total
        assert mobs == breakdown.mobilizacoes

    def test_wrapper_bate_com_calculo_manual_pre_adr176(self):
        dados = self._dados()
        total, _mobs = self._composicional()(dados, num_pessoas_direta=10, prazo_meses=4)
        esperado = round(3 * 2200 * 12.5 + 10 * 1850 * 4 + 2 * 300.0 * 1, 2)
        assert total == esperado
