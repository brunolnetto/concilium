"""CorreÃ§Ã£o de mapeamentos de cpu_id nos referencia.json."""

from __future__ import annotations

from pathlib import Path


def fix_referencia_mappings(bench_data_root: Path) -> list[str]:
    """Mantido por compatibilidade, sem aplicar reajustes hard-coded de catálogo.

    Args:
        bench_data_root: diretório benchmarks/data/ (não utilizado).

    Returns:
        Lista vazia.
    """
    _ = bench_data_root
    return []
