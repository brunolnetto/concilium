"""ADR-128 F7 — Testes unitários para `_relax_pool` aceitando déficit exato
(`_skill_helpers/_calendario.py`), issue #117.

Antes desta ADR, `_relax_pool` só sabia multiplicar a capacidade atual por um fator
heurístico (10%) — insuficiente para capacidades pequenas (`int(4 * 1.1) == 4`, sem
nenhum crescimento) e não relacionado à quantidade real que faltou. Cobre o novo
parâmetro opcional `deficit`, que usa o pico real de demanda (`ScheduleOutput.pool_deficit`,
já implementado em `cpsat_scheduler.py`) para os recursos que o reparo de disponibilidade
identificou como insuficientes, preservando o comportamento heurístico percentual (100%
regressão zero) para os demais recursos.
"""

from __future__ import annotations

import sys

from concilium.application.scheduling.models import ResourcePool
from concilium.application.skills import run_cronograma  # noqa: F401 — trigger module loading via importlib

_mod = sys.modules["_concilium_skillpkg_04_cronograma._skill_helpers._calendario"]
_relax_pool = _mod._relax_pool


class TestRelaxPoolSemDeficit:
    """Regressão zero: sem `deficit`, comportamento idêntico ao pré-ADR-128 F7."""

    def test_percentual_padrao_preservado(self):
        pool = ResourcePool(resources={"E": 4, "F": 10})
        relaxed = _relax_pool(pool)
        assert relaxed.resources == {"E": 4, "F": 11}  # int(4*1.1)=4, int(10*1.1)=11

    def test_minimo_de_1_preservado(self):
        pool = ResourcePool(resources={"E": 0})
        relaxed = _relax_pool(pool)
        assert relaxed.resources == {"E": 1}


class TestRelaxPoolComDeficitExato:
    def test_usa_deficit_exato_em_vez_de_percentual(self):
        """4 * 1.1 truncado por int() não cresce nada — o pico real (6) precisa
        vencer, não o percentual cego."""
        pool = ResourcePool(resources={"E": 4})
        relaxed = _relax_pool(pool, deficit={"E": 6})
        assert relaxed.resources == {"E": 6}

    def test_recursos_fora_do_deficit_seguem_percentual(self):
        pool = ResourcePool(resources={"E": 4, "F": 10})
        relaxed = _relax_pool(pool, deficit={"E": 6})
        assert relaxed.resources == {"E": 6, "F": 11}

    def test_deficit_vazio_equivale_a_sem_deficit(self):
        pool = ResourcePool(resources={"E": 4})
        assert _relax_pool(pool, deficit={}).resources == _relax_pool(pool).resources

    def test_deficit_de_recurso_inexistente_no_pool_e_ignorado(self):
        """`deficit` só ajusta recursos que já existem no pool original — um
        recurso desconhecido não deveria aparecer do nada."""
        pool = ResourcePool(resources={"E": 4})
        relaxed = _relax_pool(pool, deficit={"E": 6, "G": 99})
        assert relaxed.resources == {"E": 6}
