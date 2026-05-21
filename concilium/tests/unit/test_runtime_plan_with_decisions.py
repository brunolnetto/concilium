"""Testes para Runtime.plan_with_decisions (v2.5)."""

from concilium.application.runtime import Runtime


def test_plan_with_decisions_exists_on_runtime():
    """Runtime deve expor o método plan_with_decisions."""
    assert hasattr(Runtime, "plan_with_decisions"), (
        "Runtime.plan_with_decisions não encontrado — gap v2.5 não implementado"
    )


def test_plan_with_decisions_is_callable():
    """Runtime.plan_with_decisions deve ser callable."""
    import inspect

    assert callable(Runtime.plan_with_decisions)
    sig = inspect.signature(Runtime.plan_with_decisions)
    assert "canonical" in sig.parameters
    assert "decisions" in sig.parameters
