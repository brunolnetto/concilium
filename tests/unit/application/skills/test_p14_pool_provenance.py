"""P14: legacy synthetic pools cannot masquerade as physical resource evidence."""
from __future__ import annotations

from concilium.domain.models.canonical import RecursoPool


def _pool(**overrides) -> RecursoPool:
    values = {
        "id": "pool",
        "tipo_id": "FUNC-operator",
        "projeto_id": "p1",
        "quantidade_total": 1000,
        "quantidade_disponivel": 1000,
        "custo_aquisicao_total": 0,
    }
    values.update(overrides)
    return RecursoPool(**values)


def test_synthetic_looking_legacy_pool_without_origin_is_quarantined() -> None:
    assert _pool().proveniencia == "LEGACY_UNVERIFIED"


def test_explicit_configured_pool_is_preserved_even_if_shape_matches_default() -> None:
    assert _pool(proveniencia="CONFIGURADO").proveniencia == "CONFIGURADO"


def test_different_legacy_quantity_is_not_automatically_reclassified() -> None:
    assert _pool(quantidade_total=7, quantidade_disponivel=7).proveniencia == "CONFIGURADO"


def test_boolean_quantity_is_not_mistaken_for_exact_synthetic_default() -> None:
    # The strict pre-coercion classifier must not treat True as one/1000.
    # An invalid quantity remains rejected by Pydantic rather than trusted.
    import pytest

    with pytest.raises((ValueError, TypeError)):
        _pool(quantidade_total=True, quantidade_disponivel=1000)
