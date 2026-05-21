"""Concilium — framework determinístico de planejamento de obras."""


def __getattr__(name: str):
    """Package-level dynamic attribute access."""
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__: list[str] = []
