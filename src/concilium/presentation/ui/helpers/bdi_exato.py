"""Lógica (sem Streamlit) do editor da declaração exata de BDI do projeto (N9.1, #206).

O formulário guarda apenas textos. A declaração é montada com esses textos tal
como digitados — nenhum número passa por ponto flutuante — e validada com o
mesmo código do preço exato (`validate_project_declaration`); o servidor repete
a validação fundida sobre as linhas do perfil da construtora antes de gravar.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from concilium.application.scheduling.exact_pricing_declaration import (
    CATEGORY_ROWS,
    PROJECT_SCHEMA,
    PricingDeclarationError,
    validate_project_declaration,
)
from concilium.application.scheduling.project_bdi_exact_status import (
    DAMAGED,
    ESTADO_TEXTO,
    EXACT,
    LEGACY_ONLY,
)

ROWS: tuple[str, ...] = tuple(CATEGORY_ROWS.values())
ROW_LABELS = {
    "mao_obra": "Mão de obra (MO)",
    "servicos": "Serviços / equipamentos (EQ)",
    "material": "Material (MAT)",
    "diesel": "Diesel (COMB)",
    "indireto": "Indireto (IND)",
}
TAXES: tuple[str, ...] = ("cofins", "iss", "pis", "cssl", "ir")
FROM_PROFILE = "perfil"
APPLICABLE = "aplicavel"
NOT_APPLICABLE = "nao_aplicavel"
TAX_MODES: tuple[str, ...] = (FROM_PROFILE, APPLICABLE, NOT_APPLICABLE)
TAX_MODE_LABELS = {
    FROM_PROFILE: "do perfil (não declarado)",
    APPLICABLE: "aplicável — alíquota declarada",
    NOT_APPLICABLE: "não aplicável (zero)",
}
_ORIGEM = {"profile": "perfil", "project": "projeto"}


def empty_form() -> dict[str, Any]:
    """Formulário sem nada declarado: todos os campos seguem o perfil."""
    return {
        "fonte": "",
        "linhas": {
            row: {"l": "", "tributos": {tax: {"modo": FROM_PROFILE, "aliquota": ""} for tax in TAXES}} for row in ROWS
        },
    }


def form_from_declaration(declaration: object) -> dict[str, Any]:
    """Formulário preenchido com a declaração salva (ou vazio quando não há)."""
    form = empty_form()
    if not isinstance(declaration, Mapping):
        return form
    form["fonte"] = str(declaration.get("fonte") or "")
    lines = declaration.get("linhas")
    for row, fields in (lines.items() if isinstance(lines, Mapping) else ()):
        if row not in form["linhas"] or not isinstance(fields, Mapping):
            continue
        if isinstance(fields.get("l"), str):
            form["linhas"][row]["l"] = fields["l"]
        taxes = fields.get("tributos")
        for tax, entry in (taxes.items() if isinstance(taxes, Mapping) else ()):
            if tax not in TAXES or not isinstance(entry, Mapping):
                continue
            if entry.get("aplicavel") is True:
                form["linhas"][row]["tributos"][tax] = {"modo": APPLICABLE, "aliquota": str(entry.get("aliquota", ""))}
            elif entry.get("aplicavel") is False:
                form["linhas"][row]["tributos"][tax] = {"modo": NOT_APPLICABLE, "aliquota": ""}
    return form


def _text(value: object, label: str) -> str:
    # Only text ever enters the declaration: a number here would be a float in disguise.
    if not isinstance(value, str):
        raise TypeError(f"{label} must be text, got {type(value).__name__}")
    return value.strip()


def declaration_from_form(form: Mapping[str, Any]) -> dict[str, Any]:
    """Declaração `concilium.projeto.bdi-exato.v1` com os textos do formulário.

    Campo vazio / tributo "do perfil" não é declarado (a fusão é esparsa). Uma
    alíquota digitada num tributo "não aplicável" é mantida para que a validação
    a rejeite, em vez de ser descartada em silêncio.
    """
    lines: dict[str, Any] = {}
    for row in ROWS:
        fields = form["linhas"][row]
        declared: dict[str, Any] = {}
        profit = _text(fields["l"], f"{row}.l")
        if profit:
            declared["l"] = profit
        taxes: dict[str, Any] = {}
        for tax in TAXES:
            entry = fields["tributos"][tax]
            mode = entry["modo"]
            rate = _text(entry["aliquota"], f"{row}.{tax}.aliquota")
            if mode == FROM_PROFILE:
                if rate:
                    raise PricingDeclarationError(
                        f"{row}.{tax}: uma alíquota foi digitada mas o tributo está marcado como 'do perfil'; "
                        "marque 'aplicável' para declará-la ou apague o valor"
                    )
                continue
            if mode == APPLICABLE:
                taxes[tax] = {"aplicavel": True, **({"aliquota": rate} if rate else {})}
            elif mode == NOT_APPLICABLE:
                taxes[tax] = {"aplicavel": False, **({"aliquota": rate} if rate else {})}
            else:
                raise PricingDeclarationError(f"{row}.{tax}: modo desconhecido {mode!r}")
        if taxes:
            declared["tributos"] = taxes
        if declared:
            lines[row] = declared
    return {"schema": PROJECT_SCHEMA, "fonte": _text(form["fonte"], "fonte"), "linhas": lines}


def build_save_request(
    form: Mapping[str, Any], *, confirmado_por: str, motivo_revisao: str, versao_atual: int | None
) -> tuple[dict[str, Any] | None, str | None]:
    """`(payload do POST /bdi-exato, None)` ou `(None, motivo da recusa)`.

    Mesmas exigências do armazenamento: `confirmado_por` sempre; `motivo_revisao`
    a partir da versão 2 (isto é, quando já há uma versão salva).
    """
    try:
        declaration = declaration_from_form(form)
        validate_project_declaration(declaration)
    except (PricingDeclarationError, TypeError) as exc:
        return None, f"Declaração exata inválida: {exc}"
    if not confirmado_por.strip():
        return None, "confirmado_por é obrigatório."
    if versao_atual is not None and not motivo_revisao.strip():
        return None, f"motivo_revisao é obrigatório para revisar a declaração (versão atual: {versao_atual})."
    return {
        "declaracao": declaration,
        "confirmado_por": confirmado_por.strip(),
        "motivo_revisao": motivo_revisao.strip() or None,
    }, None


def status_banner(status: Mapping[str, Any]) -> tuple[str, str]:
    """`(nível, texto)` do aviso de estado — mesmo texto do `concilium bdi show`."""
    estado = status["estado"]
    text = f"{estado} — {ESTADO_TEXTO[estado]}"
    if status.get("motivo"):
        text += f"\n\nMotivo: {status['motivo']}"
    if estado in (LEGACY_ONLY, DAMAGED) or status.get("preco_exato_bloqueado"):
        return "error", text
    return ("success" if estado == EXACT else "info"), text


def current_version(status: Mapping[str, Any]) -> int | None:
    registro = status.get("registro")
    return registro["versao"] if isinstance(registro, Mapping) else None


def layers_rows(status: Mapping[str, Any]) -> list[dict[str, str]]:
    """Linhas da tabela de camadas efetivas: valor exato e origem de cada campo."""
    camadas = status.get("camadas")
    if not isinstance(camadas, Mapping):
        return []

    def cell(field: Mapping[str, str]) -> str:
        return f"{field['valor']} ({_ORIGEM[field['origem']]})"

    rows: list[dict[str, str]] = []
    for category, c in camadas["categorias"].items():
        rows.append(
            {
                "Categoria": category,
                "Linha": c["linha"],
                "Natureza": c["natureza"],
                "AC": cell(c["ac"]),
                "R+S+G": cell(c["rsg"]),
                "DF": cell(c["df"]),
                "L": cell(c["l"]),
                **{tax.upper(): cell(field) for tax, field in c["tributos"].items()},
                "Markup (exato)": c["markup"],
                "Markup ≈ (aproximado)": c["markup_aprox"],
            }
        )
    return rows


def profile_value(status: Mapping[str, Any], row: str, field: str) -> str | None:
    """Valor efetivo atual de `l` ou de um tributo da linha, para servir de dica no formulário."""
    camadas = status.get("camadas")
    if not isinstance(camadas, Mapping):
        return None
    for c in camadas["categorias"].values():
        if c["linha"] == row:
            entry = c["l"] if field == "l" else c["tributos"].get(field)
            return f"{entry['valor']} ({_ORIGEM[entry['origem']]})" if entry else None
    return None
