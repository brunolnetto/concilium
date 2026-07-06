"""Tests for concilium.presentation.api.schemas — ConfigVersionCreateRequest /
PerfilVersionCreateRequest coverage gaps.

Coverage targets:
  ConfigVersionCreateRequest.extract_fields: explicit 'fields' dict shape
  PerfilVersionCreateRequest.validate_ranges: out-of-bounds range raises ValueError
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from concilium.presentation.api.schemas import (
    ConfigVersionCreateRequest,
    PerfilVersionCreateRequest,
    RangeInput,
)


class TestConfigVersionCreateRequestExtractFields:
    def test_explicit_fields_dict_is_returned(self):
        req = ConfigVersionCreateRequest(motivo="ajuste", fields={"nome": "novo"})
        assert req.extract_fields() == {"nome": "novo"}

    def test_flat_shape_returns_extra_fields(self):
        req = ConfigVersionCreateRequest(motivo="ajuste", nome="novo")
        result = req.extract_fields()
        assert result == {"nome": "novo"}


class TestPerfilVersionCreateRequestValidateRanges:
    def test_valid_ranges_pass(self):
        req = PerfilVersionCreateRequest(
            motivo="ajuste",
            faixa_margem_alvo=RangeInput(min=0.1, max=0.2),
        )
        assert req.faixa_margem_alvo.min == 0.1

    def test_min_greater_than_max_raises(self):
        with pytest.raises(ValidationError, match="min deve ser <= max"):
            PerfilVersionCreateRequest(
                motivo="ajuste",
                faixa_margem_alvo=RangeInput(min=0.5, max=0.1),
            )

    def test_out_of_bounds_raises(self):
        with pytest.raises(ValidationError, match="fora do intervalo permitido"):
            PerfilVersionCreateRequest(
                motivo="ajuste",
                razao_indireto_direto_alvo=RangeInput(min=0.0, max=3.0),
            )

    def test_none_faixa_is_skipped(self):
        req = PerfilVersionCreateRequest(motivo="ajuste")
        assert req.faixa_margem_alvo is None
        assert req.faixa_margem_aceitavel is None
        assert req.razao_indireto_direto_alvo is None
