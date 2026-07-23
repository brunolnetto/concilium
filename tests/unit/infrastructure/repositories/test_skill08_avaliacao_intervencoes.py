"""Coverage batch 37 — 08-avaliacao-intervencoes, producao repo, compression_analysis, matching_oracle."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path


def _load_skill(rel_path: str, name: str):
    p = Path(rel_path).resolve()
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _make_schedule_metrics(makespan: int = 4):
    from concilium.application.scheduling.models import ScheduleMetrics

    return ScheduleMetrics(
        makespan=makespan,
        resource_leveling_score=1.0,
        idle_time=0,
        activity_fragmentation=0,
        critical_path_slack_min=0.0,
        resource_utilization_avg=1.0,
    )


# 08-avaliacao-intervencoes/skill.py
# ===========================================================================


class TestRepositorioProducaoOuErro:
    def test_obter_ou_erro_raises_when_not_found(self):
        """Line 32: obter() returns None → FileNotFoundError raised."""
        import pytest

        from concilium.infrastructure.repositories.producao import RepositorioProducao

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = RepositorioProducao(tmpdir)
            with pytest.raises(FileNotFoundError, match="PROD-GHOST"):
                repo.obter_ou_erro("PROD-GHOST")

    def test_obter_ou_erro_returns_producao_when_found(self):
        """Line 33: obter() returns a Producao → returned directly."""
        from unittest.mock import patch

        from concilium.infrastructure.repositories.producao import RepositorioProducao

        fake = object()
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = RepositorioProducao(tmpdir)
            with patch.object(repo, "obter", return_value=fake):
                result = repo.obter_ou_erro("PROD-X")
        assert result is fake


# ===========================================================================

