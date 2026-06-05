from __future__ import annotations

from concilium.infrastructure.settings import ApiSettings


def resolve_api_bind() -> tuple[str, int]:
    """Resolve host/port de bind da API.

    Lê env vars a cada chamada (sem singleton) para compatibilidade com
    tests que usam monkeypatch. Em produção é chamada uma vez no startup.
    """
    s = ApiSettings.from_env()
    return s.host, s.port
