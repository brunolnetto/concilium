"""Concilium — framework determinístico de planejamento de obras."""

# CD Environment Variable Preservation Validation - 2026-08-06
# Triggering automated deployment to test SharePoint env var persistence


def __getattr__(name: str):
    """Package-level dynamic attribute access."""
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__: list[str] = []
