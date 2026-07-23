"""ADR-130 — consolidação de Producao duplicadas no catálogo rfi-r02.

Ao popular grafo_sinergia nas 75 CPUs do catálogo (ver
test_adr130_grafo_sinergia_rfi_r02_cluster{1..7}.py), 9 pares de CPUs se
revelaram duplicatas literais de produtividade: mesma composição de equipe
(funções+equipamentos+materiais), mesmo valor_horario, mesma unidade e — por
consequência direta da mesma fórmula de derivação — o mesmo grafo_sinergia
numérico (capacidades/gargalo_declarado/relacoes), diferindo apenas na
descrição/código da atividade.

Producao.valor_horario é o dado calibrado real de uma atividade; quando duas
CPUs de fato compartilham esse dado (não apenas equipamentos parecidos, mas o
número real idêntico), manter 2 arquivos de Producao idênticos é redundância
sem ganho de fidelidade — CPU.producao_id_ref já suporta N CPUs apontando
para a mesma Producao (relação M:1, não 1:1), conforme
_cure_contextual.py (prod_by_id é um dict, não assume unicidade reversa).

Resolução: cada par manteve a Producao do código de menor numeração (winner)
e repontou o producao_id_ref da CPU do código maior (loser) para ela,
removendo o arquivo de Producao duplicado.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_CPUS = _ROOT / "config" / "catalogos" / "rfi-r02" / "cpus"
_PRODUTIVIDADES = _ROOT / "config" / "catalogos" / "rfi-r02" / "produtividades"

# (winner_ati, loser_ati)
_PARES_CONSOLIDADOS = [
    ("ATI-002", "ATI-004"),
    ("ATI-025", "ATI-026"),
    ("ATI-027", "ATI-028"),
    ("ATI-029", "ATI-030"),
    ("ATI-033", "ATI-034"),
    ("ATI-036", "ATI-037"),
    ("ATI-045", "ATI-046"),
    ("ATI-047", "ATI-048"),
    ("ATI-054", "ATI-055"),
]


def _build_validators():
    from concilium.presentation.cli._commands_manage_helpers_d import _build_schema_validators

    return _build_schema_validators(_ROOT / "config" / "schemas" / "catalog")


def _errors(validator, item: dict) -> list[str]:
    return [".".join(str(x) for x in err.absolute_path) + f" -> {err.message}" for err in validator.iter_errors(item)]


class TestConsolidacaoDuplicatasRfiR02:
    @pytest.mark.parametrize(("winner", "loser"), _PARES_CONSOLIDADOS)
    def test_loser_cpu_aponta_para_producao_do_winner(self, winner, loser):
        loser_cpu = json.loads((_CPUS / f"CPU-TERRA-{loser}.json").read_text(encoding="utf-8"))
        assert loser_cpu["producao_id_ref"] == f"CPU-TERRA-{winner}-PROD-001"

    @pytest.mark.parametrize(("winner", "loser"), _PARES_CONSOLIDADOS)
    def test_producao_do_loser_nao_existe_mais(self, winner, loser):
        assert not (_PRODUTIVIDADES / f"CPU-TERRA-{loser}-PROD-001.json").exists()

    @pytest.mark.parametrize(("winner", "loser"), _PARES_CONSOLIDADOS)
    def test_producao_do_winner_ainda_existe_e_valida(self, winner, loser):
        _, prod_v, _ = _build_validators()
        path = _PRODUTIVIDADES / f"CPU-TERRA-{winner}-PROD-001.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert _errors(prod_v, data) == []

    @pytest.mark.parametrize(("winner", "loser"), _PARES_CONSOLIDADOS)
    def test_ambas_cpus_ainda_existem_como_entidades_distintas(self, winner, loser):
        """A consolidação afeta apenas Producao — cada CPU continua sendo um
        item de custo/descrição próprio (codigo, descricao, unidade), só
        compartilhando o dado de produtividade real."""
        winner_cpu_path = _CPUS / f"CPU-TERRA-{winner}.json"
        loser_cpu_path = _CPUS / f"CPU-TERRA-{loser}.json"
        assert winner_cpu_path.exists()
        assert loser_cpu_path.exists()
        winner_cpu = json.loads(winner_cpu_path.read_text(encoding="utf-8"))
        loser_cpu = json.loads(loser_cpu_path.read_text(encoding="utf-8"))
        assert winner_cpu["codigo"] != loser_cpu["codigo"]

    @pytest.mark.parametrize(("winner", "loser"), _PARES_CONSOLIDADOS)
    def test_resolucao_via_producao_id_ref_da_o_mesmo_valor_horario_para_as_2_cpus(self, winner, loser):
        """Simula o join real (CPU.producao_id_ref -> Producao.valor_horario)
        usado por _cure_contextual._cure_contextual_valor_horario_row e
        confirma que ambas as CPUs resolvem para o mesmo valor_horario real —
        a garantia de que a consolidação não perdeu fidelidade de dado."""
        winner_cpu = json.loads((_CPUS / f"CPU-TERRA-{winner}.json").read_text(encoding="utf-8"))
        loser_cpu = json.loads((_CPUS / f"CPU-TERRA-{loser}.json").read_text(encoding="utf-8"))
        prod = json.loads((_PRODUTIVIDADES / f"CPU-TERRA-{winner}-PROD-001.json").read_text(encoding="utf-8"))

        assert winner_cpu["producao_id_ref"] == prod["id"]
        assert loser_cpu["producao_id_ref"] == prod["id"]

    def test_total_de_producoes_reflete_a_consolidacao(self):
        """75 CPUs, mas apenas 66 Producao (75 - 9 pares consolidados) — a
        relação deixou de ser 1:1 exatamente nos pares que eram duplicatas
        literais."""
        total_cpus = len(list(_CPUS.glob("CPU-TERRA-*.json")))
        total_producoes = len(list(_PRODUTIVIDADES.glob("CPU-TERRA-*.json")))
        assert total_cpus == 75
        assert total_producoes == 66
