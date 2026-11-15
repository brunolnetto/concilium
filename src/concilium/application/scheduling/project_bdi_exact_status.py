"""Status of a project's BDI declaration as the exact price sees it (N9.1, #206).

One JSON-able description shared by every interface that shows the project BDI
(CLI ``bdi show``, the API behind the UI editor): which declaration is saved,
whether the exact price can read it, and — given the construction profile — the
effective markup layers per category with the origin of every field.

Nothing here is a new rule: the state and its reason come from
:func:`load_exact_project_bdi` (what the runtime injects into Skill06) and the
layers from :func:`profile_effective_layers` (what the price derives). Rates are
exact strings; the only rounded figure is ``markup_aprox``, a display aid that
is labelled as approximate and never fed back into anything.
"""

from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction
from typing import Any

from concilium.application.scheduling.exact_pricing_declaration import (
    CATEGORY_ROWS,
    PricingDeclarationError,
    profile_effective_layers,
)
from concilium.application.scheduling.project_bdi_exact_store import (
    HEAD,
    LEGACY_HEAD,
    _ProjectFiles,
    load_exact_project_bdi,
)

STATUS_SCHEMA = "concilium.projeto.bdi-exato-status.v1"
EXACT = "EXATO"
LEGACY_ONLY = "SOMENTE_LEGADO"
DAMAGED = "DANIFICADO"
NONE = "NENHUM"
# One wording for every interface (CLI and UI show the same status).
ESTADO_TEXTO = {
    EXACT: "declaração exata salva — é a que o preço exato usa",
    LEGACY_ONLY: (
        "só existe o perfil legado em ponto flutuante — PREÇO EXATO NÃO AVALIADO até salvar de novo em forma exata"
    ),
    DAMAGED: "declaração exata danificada — PREÇO EXATO NÃO AVALIADO até salvar de novo em forma exata",
    NONE: "o projeto não declara BDI próprio — valem as camadas do perfil da construtora",
}
_RECORD_FIELDS = ("projeto_id", "versao", "content_hash", "confirmado_em", "confirmado_por", "motivo_revisao")


def approx_percent(rate: Fraction, places: int = 4) -> str:
    """``rate`` as a percentage rounded half-even to ``places`` decimals (display only)."""
    scaled = round(rate * 100 * 10**places)
    sign = "-" if scaled < 0 else ""
    whole, frac = divmod(abs(scaled), 10**places)
    return f"{sign}{whole}.{frac:0{places}d}%"


def exact_text(value: Fraction) -> str:
    """Exact text of a rational: a finite decimal when it has one, ``p/q`` otherwise.

    ``Fraction(exact_text(x)) == x`` always; nothing is rounded.
    """
    denominator, twos, fives = value.denominator, 0, 0
    while denominator % 2 == 0:
        denominator, twos = denominator // 2, twos + 1
    while denominator % 5 == 0:
        denominator, fives = denominator // 5, fives + 1
    if denominator != 1:
        return str(value)
    places = max(twos, fives)
    scaled = abs(value.numerator) * 10**places // value.denominator
    sign = "-" if value < 0 else ""
    if places == 0:
        return f"{sign}{scaled}"
    whole, frac = divmod(scaled, 10**places)
    return f"{sign}{whole}.{frac:0{places}d}".rstrip("0").rstrip(".") if frac else f"{sign}{whole}"


def declared_fields(declaration: Mapping[str, Any]) -> list[dict[str, str]]:
    """The fields a valid declaration states, one entry per row field, in file order."""
    out: list[dict[str, str]] = []
    for row, fields in declaration["linhas"].items():
        if "l" in fields:
            out.append({"linha": row, "campo": "l", "valor": str(fields["l"])})
        for tax, entry in fields.get("tributos", {}).items():
            value = str(entry["aliquota"]) if entry["aplicavel"] else "não aplicável"
            out.append({"linha": row, "campo": tax, "valor": value})
    return out


def effective_layers_view(perfil: object, declaration: object) -> dict[str, Any]:
    """Merged layers per category, each field with its exact value and origin.

    Raises :class:`PricingDeclarationError` with the reason the price would give.
    """
    effective = profile_effective_layers(perfil, declaration)
    categories: dict[str, Any] = {}
    for category, row in CATEGORY_ROWS.items():
        rates = effective["layers"][category]
        origins = effective["layer_origins"][category]
        categories[category] = {
            "linha": row,
            "natureza": effective["natures"][category],
            "ac": {"valor": exact_text(rates.ac), "origem": origins["ac"]},
            "rsg": {"valor": exact_text(rates.rsg), "origem": origins["rsg"]},
            "df": {"valor": exact_text(rates.df), "origem": origins["df"]},
            "l": {"valor": exact_text(rates.profit), "origem": origins["l"]},
            "tributos": {
                name: {"valor": exact_text(rate), "origem": origins["taxes"][name]} for name, rate in rates.taxes
            },
            "markup": exact_text(rates.beta),
            "markup_aprox": approx_percent(rates.beta),
        }
    return {
        "fonte_perfil": effective["table_source"],
        "referencia_projeto": effective["project_reference"],
        "categorias": categories,
    }


def exact_project_bdi_status(
    project: _ProjectFiles,
    perfil: object = None,
    *,
    perfil_id: str | None = None,
    perfil_motivo: str | None = None,
) -> dict[str, Any]:
    """Describe the project's BDI declaration for the exact price.

    ``estado`` is ``EXATO`` (an intact exact declaration is saved),
    ``SOMENTE_LEGADO`` (only the float profile: never converted),
    ``DANIFICADO`` (the exact head is not a valid saved declaration) or
    ``NENHUM`` (the project declares nothing: the profile's layers apply).
    ``preco_exato_bloqueado`` tells whether this declaration alone leaves the
    exact price not evaluated, with ``motivo``. ``camadas`` needs ``perfil``
    (the construction profile); without it ``camadas_motivo`` says why
    (``perfil_motivo`` when the caller could not resolve the profile).
    """
    declaration, reason = load_exact_project_bdi(project)
    has_exact_head = project.exists(HEAD)
    if declaration is not None:
        estado = EXACT
    elif has_exact_head:
        estado = DAMAGED
    elif reason is not None:
        estado = LEGACY_ONLY
    else:
        estado = NONE

    registro: dict[str, Any] | None = None
    if declaration is not None:
        stored = project.read_json(HEAD, None)
        registro = {name: stored.get(name) for name in _RECORD_FIELDS}

    legado: dict[str, Any] = {"existe": project.exists(LEGACY_HEAD)}
    if legado["existe"]:
        raw = project.read_json(LEGACY_HEAD, None)
        if isinstance(raw, Mapping):
            legado.update({name: raw.get(name) for name in ("versao", "confirmado_por", "content_hash")})

    camadas: dict[str, Any] | None = None
    camadas_motivo: str | None = None
    if reason is not None:
        camadas_motivo = "the effective layers are not derived while the project declaration is unreadable"
    elif perfil is None:
        camadas_motivo = perfil_motivo or "the construction profile was not provided"
    else:
        try:
            camadas = effective_layers_view(perfil, declaration)
        except PricingDeclarationError as exc:
            camadas_motivo = str(exc)

    # A declaration that cannot be merged over a known profile blocks the price too.
    motivo = reason
    if motivo is None and perfil is not None and camadas is None:
        motivo = camadas_motivo
    return {
        "schema": STATUS_SCHEMA,
        "estado": estado,
        "preco_exato_bloqueado": motivo is not None,
        "motivo": motivo,
        "registro": registro,
        "declaracao": declaration,
        "campos_declarados": declared_fields(declaration) if declaration is not None else [],
        "perfil_legado": legado,
        "perfil_id": perfil_id,
        "camadas": camadas,
        "camadas_motivo": camadas_motivo,
    }


def profile_rows_for_validation(perfil: object) -> Mapping[str, object] | None:
    """The profile's ``tabela_bdi.linhas`` when the profile is complete on its own.

    Handed to :func:`save_exact_project_bdi` so that a declaration is checked
    merged over the real rows, exactly as the price will; ``None`` (profile
    unknown or incomplete) leaves the store's structural/exactness check.
    """
    try:
        return profile_effective_layers(perfil, None)["rows"]
    except PricingDeclarationError:
        return None


def load_project_profile(runtime: Any, meta: Mapping[str, Any]) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """``(perfil_id, perfil, reason)``: the project's construction profile as configured now.

    The profile is the one of the project's ``contexto_id``; a failure to
    resolve it is a reason, never a default profile.
    """
    contexto_id = meta.get("contexto_id")
    if not isinstance(contexto_id, str) or not contexto_id:
        return None, None, "the project declares no contexto_id, so its construction profile is unknown"
    try:
        perfil_id = runtime.load_contexto(contexto_id).perfil_id
        return perfil_id, runtime.load_perfil(perfil_id), None
    except Exception as exc:  # config errors of any kind are a reason, not a crash
        return None, None, f"the construction profile of context {contexto_id!r} could not be loaded: {exc}"
