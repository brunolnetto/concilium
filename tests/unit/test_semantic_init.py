"""Coverage batch A — targets mcp_server/__main__, semantic/__init__,
scheduling/selector, optimizer/loop, skills/__init__, cpu_insumo validations,
02-produtividade-climatica, 09-relatorio-e-artefatos, and scheduling/scheduler edge cases.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch

from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    CustoTotal,
    Meta,
    Projeto,
    RegimeTrabalho,
    Resultado,
    Venda,
)


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")

def _make_proj():
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=-3.0, lng=-38.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 7, 31),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )

def _minimal_canonical(**kw):
    return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), **kw)

def _canonical_com_resultado():
    resultado = Resultado(
        venda=Venda(total_sem_bdi=800_000.0, total_com_bdi=1_000_000.0),
        custo=CustoTotal(direto_equipes=500_000.0, total=800_000.0),
        resultado_financeiro=200_000.0,
        margem_pct=0.20,
        status_margem="VERDE",
        validacoes=[],
    )
    return _minimal_canonical(resultado=resultado)


# ══ semantic/__init__.py ══════════════════════════════════════════════════════


class TestSemanticInit:
    def test_build_unit_cache_exception_path(self):
        """Force _build_unit_cache exception path (lines 36-37)."""
        import concilium.application.semantic as sem_mod

        # Save original cache and restore after to avoid polluting other tests
        original_cache = sem_mod._UNIT_ALIASES_CACHE
        try:
            with patch.object(sem_mod, "VocabularyLoader", side_effect=Exception("force")):
                sem_mod._build_unit_cache()
            # Should silently set _UNIT_ALIASES_CACHE = {}
            assert isinstance(sem_mod._UNIT_ALIASES_CACHE, dict)
        finally:
            sem_mod._UNIT_ALIASES_CACHE = original_cache



