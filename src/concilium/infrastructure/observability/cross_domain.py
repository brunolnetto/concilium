"""Cross-domain Gold — ADR-112 F8.

Junta a taxa de fallback por projeto (Silver logs) com o resultado financeiro
do canonical de benchmark (custo_direto, margem). Responde perguntas como:
"benchmarks com alta taxa de fallback têm desvio de custo acima do esperado?".
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from concilium.domain.repositories.blob_storage_port import BlobStoragePort

from .silver_normalizer import dedupe_records

logger = logging.getLogger(__name__)

_SILVER_PREFIX = "observability/silver"

# canonical_provider: project_id -> {"custo_direto": float, "margem_pct": float} | None
CanonicalProvider = Callable[[str], dict[str, Any] | None]


def _aggregate_fallback_by_project(logs: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Agrega n_total/n_fallbacks por project_id a partir dos logs Silver."""
    by_project: dict[str, dict[str, int]] = {}
    for rec in logs:
        pid = rec.get("project_id") or "unknown"
        agg = by_project.setdefault(pid, {"n_total": 0, "n_fallbacks": 0})
        agg["n_total"] += 1
        if rec.get("fallback_type"):
            agg["n_fallbacks"] += 1
    return by_project


class CrossDomainBuilder:
    """Constrói a tabela Gold cross-domain (observabilidade ⋈ canonical)."""

    def __init__(self, storage: BlobStoragePort, canonical_provider: CanonicalProvider):
        self._storage = storage
        self._canonical_provider = canonical_provider

    def _read_silver_logs(self) -> list[dict[str, Any]]:
        """Lê todos os records Silver de logs, deduplicados entre arquivos.

        Mesmo motivo de ObservabilityWorker.read_silver()/GoldAggregator._read_silver():
        um dia reprocessado com particionamento diferente do original pode deixar o
        mesmo event_id em mais de um arquivo — sem dedup, conta em dobro por projeto.
        """
        blobs = sorted(self._storage.listar_blobs(f"{_SILVER_PREFIX}/logs/"))
        records: list[dict[str, Any]] = []
        for path in blobs:
            try:
                raw = self._storage.ler_blob(path)
                for line in raw.decode("utf-8").splitlines():
                    if line.strip():
                        records.append(json.loads(line))
            except Exception:
                pass
        return dedupe_records(records)

    def _build_cross_domain_row(self, pid: str, agg: dict[str, int]) -> dict[str, Any]:
        n_total = agg["n_total"]
        n_fb = agg["n_fallbacks"]
        fallback_rate = round(n_fb / n_total, 4) if n_total else 0.0

        canonical = None
        try:
            canonical = self._canonical_provider(pid)
        except Exception as e:
            logger.warning("Falha ao obter canonical de %s: %s", pid, e)

        return {
            "project_id": pid,
            "n_total": n_total,
            "n_fallbacks": n_fb,
            "fallback_rate": fallback_rate,
            "custo_direto": (canonical or {}).get("custo_direto") if canonical else None,
            "margem_pct": (canonical or {}).get("margem_pct") if canonical else None,
        }

    def build(self) -> list[dict[str, Any]]:
        """Agrega fallback_rate por project_id e junta com o canonical resultado."""
        logs = self._read_silver_logs()
        if not logs:
            return []

        # Agrega por project_id (sem DuckDB — volume por projeto é pequeno)
        by_project = _aggregate_fallback_by_project(logs)

        return [self._build_cross_domain_row(pid, agg) for pid, agg in sorted(by_project.items())]

    def write(self) -> str:
        """Persiste a tabela cross-domain em Gold como JSON. Retorna o path."""
        path = "observability/gold/cross_domain.json"
        data = self.build()
        self._storage.gravar_blob(path, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
        return path


def default_canonical_provider(benchmark_projects_root) -> CanonicalProvider:
    """Provider que lê canonical.json dos projetos de benchmark por project_id.

    Extrai custo_direto e margem_pct do resultado. Retorna None se ausente.
    """
    from pathlib import Path

    root = Path(benchmark_projects_root)

    def _provider(project_id: str) -> dict[str, Any] | None:
        proj_dir = root / project_id
        if not proj_dir.exists():
            return None
        # Pega a versão mais recente com canonical
        canonicals = sorted(proj_dir.glob("v*/canonical.json"))
        if not canonicals:
            return None
        try:
            data = json.loads(canonicals[-1].read_text(encoding="utf-8"))
            resultado = data.get("resultado") or {}
            custo = resultado.get("custo") or {}
            return {
                "custo_direto": custo.get("direto_equipes"),
                "margem_pct": resultado.get("margem_pct"),
            }
        except Exception as e:
            logger.warning("Falha ao ler canonical de %s: %s", project_id, e)
            return None

    return _provider
