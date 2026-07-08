"""ProjectService — parte extraída de project_service.py (mixin _ValidationMixin)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._shared import _REF_YYYY_MM_RE

if TYPE_CHECKING:
    from ._host_protocol import ProjectServiceHost

    _Base = ProjectServiceHost
else:
    _Base = object


class _ValidationMixin(_Base):
    """Métodos de validation de ProjectService."""

    def _resolve_config_root(self) -> Path | None:
        for candidate in [
            Path(__file__).parents[4] / "config",
            Path(__file__).parents[5] / "config",
        ]:
            if candidate.exists():
                return candidate
        return None

    def _validate_range_field(
        self,
        fields: dict[str, Any],
        key: str,
        *,
        lower: float,
        upper: float,
    ) -> None:
        value = fields.get(key)
        if not isinstance(value, dict):
            return
        if "min" not in value or "max" not in value:
            raise ValueError(f"{key}: campos 'min' e 'max' são obrigatórios")
        try:
            vmin = float(value.get("min"))
            vmax = float(value.get("max"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key}: valores inválidos para min/max") from exc
        if vmin > vmax:
            raise ValueError(f"{key}: min deve ser <= max")
        if vmin < lower or vmax > upper:
            raise ValueError(f"{key}: valores fora do intervalo permitido [{lower}, {upper}]")

    def _validate_perfil_fields(self, fields: dict[str, Any]) -> None:
        self._validate_range_field(fields, "faixa_margem_alvo", lower=0.0, upper=1.0)
        self._validate_range_field(fields, "faixa_margem_aceitavel", lower=0.0, upper=1.0)
        self._validate_range_field(fields, "razao_indireto_direto_alvo", lower=0.0, upper=2.0)

    @staticmethod
    def _validate_field_in_registry(value: Any, valid_ids_fn: Any, field_name: str) -> None:
        """Valida que `value` (se presente) pertence ao conjunto de ids retornado por `valid_ids_fn()`.

        `valid_ids_fn` só é chamado quando `value` não é None, preservando o
        curto-circuito (evita I/O de listagem quando o campo não foi informado).
        """
        if value is None:
            return
        if value not in valid_ids_fn():
            raise ValueError(f"{field_name} inválido: '{value}'")

    def _validate_catalogo_field(self, catalogo_id: Any) -> None:
        if catalogo_id is not None:
            cfg = self._resolve_config_root()
            if cfg is None or not (cfg / "catalogos" / str(catalogo_id)).exists():
                raise ValueError(f"catalogo_id inválido: '{catalogo_id}'")

    def _validate_contexto_fields(self, fields: dict[str, Any]) -> None:
        self._validate_field_in_registry(
            fields.get("perfil_id"), lambda: {p.get("id") for p in self.list_perfis()}, "perfil_id"
        )
        self._validate_field_in_registry(
            fields.get("jurisdicao_id"), lambda: {j.get("id") for j in self.list_jurisdicoes()}, "jurisdicao_id"
        )
        self._validate_field_in_registry(
            fields.get("tema_id"), lambda: {t.get("id") for t in self.list_temas()}, "tema_id"
        )
        self._validate_catalogo_field(fields.get("catalogo_id"))

    def _validate_tema_fields(self, svc: Any, tema_id: str, fields: dict[str, Any]) -> None:
        from concilium.domain.models.catalog.tema import TemaVisual

        base = svc.resolve(tema_id) or {"id": tema_id}
        merged = {**base, **fields}
        if "id" not in merged:
            merged["id"] = tema_id
        try:
            TemaVisual.model_validate(merged)
        except Exception as exc:
            raise ValueError(f"Tema inválido: {exc}") from exc

    def _validate_jurisdicao_fields(self, fields: dict[str, Any]) -> None:
        provedores = fields.get("provedores_referencia")
        if isinstance(provedores, list):
            for idx, prov in enumerate(provedores):
                if not isinstance(prov, dict):
                    raise ValueError(f"provedores_referencia[{idx}] deve ser objeto")
                ref = str(prov.get("data_referencia") or "").strip()
                if ref and not _REF_YYYY_MM_RE.match(ref):
                    raise ValueError(
                        f"provedores_referencia[{idx}].data_referencia inválida: '{ref}' (esperado AAAA-MM)"
                    )

