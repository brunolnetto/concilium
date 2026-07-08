"""Settings (parte extraída de settings.py) — grupo _runtime."""

from __future__ import annotations

from dataclasses import dataclass

from ._core import _int, _refresh_if_env_changed, _str


@dataclass(frozen=True)
class RuntimeSettings:
    """Configuração de runtime do pipeline de produção."""

    pdf_renderer: str
    """CONCILIUM__PDF_RENDERER — "reportlab" (default) ou "fpdf2" (legado, NEP-033)."""

    artifact_transport: str
    """CONCILIUM__ARTIFACT_TRANSPORT — transporte de artefatos MCP: "local" (default), "zipurl", "presigned"."""

    lock_ttl_seconds: int
    """CONCILIUM__LOCK_TTL_SECONDS — TTL do lock de catálogo em segundos (default: 86400 = 24h)."""

    duckdb_memory: str
    """CONCILIUM__DUCKDB_MEMORY — [opt] Limite de RAM para DuckDB antes de drive-spill (default: 512MB)."""

    duckdb_spill_dir: str
    """CONCILIUM__DUCKDB_SPILL_DIR — [opt] Diretório para overflow DuckDB (default: tmpdir do OS)."""

    @classmethod
    def from_env(cls) -> RuntimeSettings:
        import tempfile

        return cls(
            pdf_renderer=_str("CONCILIUM__PDF_RENDERER", "reportlab"),
            artifact_transport=_str("CONCILIUM__ARTIFACT_TRANSPORT", "local"),
            lock_ttl_seconds=_int("CONCILIUM__LOCK_TTL_SECONDS", 86400),
            duckdb_memory=_str("CONCILIUM__DUCKDB_MEMORY", "512MB"),
            duckdb_spill_dir=_str("CONCILIUM__DUCKDB_SPILL_DIR", tempfile.gettempdir()),
        )


_runtime: RuntimeSettings | None = None


def get_runtime() -> RuntimeSettings:
    _refresh_if_env_changed()
    global _runtime
    if _runtime is None:
        _runtime = RuntimeSettings.from_env()
    return _runtime




def _reset_runtime() -> None:
    global _runtime
    _runtime = None
