"""One read-only view of the exact financial result (#206, W3-A).

Every user-facing surface (run summary, UI, MCP, CLI, version deltas) reads the
cost, the price and the markup layers of a project from this view and from
nowhere else. The view is derived only from the exact evidence the canonical
records:

* ``resultado.pricing_diagnostics`` (P20/P21 exact rationals),
* ``resultado.pricing_gates`` (regulatory and profit-layer gates),
* ``resultado.markup_layers`` (N9: cost, overhead, profit and taxes),
* the pool contracts' P16 witnesses and the P18 consumption record, used only
  to explain why the price was not evaluated,
* and, when supplied, the run's P23 certificate.

It never reads the legacy float fields of ``resultado`` (``venda``, ``custo``,
``resultado_financeiro``, ``margem_pct``, ``status_margem``): a canonical whose
legacy fields are absurd, or absent, yields the same view.

Exact values are canonical rational strings (``"159/5"``). A float exists only
as a display approximation, produced by :func:`display_float` at the
presentation edge and never fed back into a decision.

There is no margin semaphore and no ``(P - C)/P`` "margin": the product models
markup layers, and the minimum margin is a criterion on the profit layer's
share of the price (``profit_layer_share`` against ``minimum_profit_margin``).
"""
from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction
from typing import Any

SCHEMA = "concilium.exact-financial-view.v1"
DELTAS_SCHEMA = "concilium.exact-financial-deltas.v1"
AVALIADO = "AVALIADO"
NAO_AVALIADO = "NAO_AVALIADO"
CATEGORIES = ("MO", "EQ", "MAT", "COMB", "IND")

# Quantities compared between two versions, as paths into the view.
DELTA_FIELDS: dict[str, tuple[str, ...]] = {
    "custo_total": ("cost", "total"),
    "custo_direto": ("cost", "direct"),
    "custo_indireto": ("cost", "indirect"),
    "preco": ("price",),
    "camada_overhead": ("layers", "overhead"),
    "camada_lucro": ("layers", "profit"),
    "camada_tributos": ("layers", "taxes"),
    "participacao_lucro_no_preco": ("profit_layer_share",),
    "bdi_sobre_catalogo": ("bdi_on_catalog",),
}

_GENERIC_MISSING_EVIDENCE = "missing p21_pricing_evidence"
_SUMMARY_PREDATES_VIEW = (
    "Este resumo foi gravado antes do financeiro exato e não contém custo, preço ou camadas exatas."
)

# Recorded P21 reasons (``pricing_diagnostics.reason``) are written in English
# by the pricing adapter. They are always shown verbatim; this table only adds
# the norm and the corrective action when the recorded text names its cause.
_RECORDED_REASON_HINTS: tuple[tuple[tuple[str, ...], str, str, str], ...] = (
    (
        ("site_indirects", "site-indirects", "site indirects"),
        "ESCOPO_INDIRETOS_CANTEIRO",
        "O escopo de indiretos de canteiro não foi declarado de forma válida (N10).",
        "Declare `site_indirects_scope` no projeto: DECLARED com as linhas em `site_indirects`, "
        "ou NO_SITE_INDIRECTS com a procedência. Nada é assumido como zero.",
    ),
    (
        ("bdi_projeto_exato", "floating point", "exact form"),
        "BDI_PROJETO_NAO_EXATO",
        "O perfil de BDI do projeto não está disponível em forma exata (N9.1).",
        "Salve novamente o perfil de BDI do projeto em forma exata (MCP `salvar_perfil_bdi` com "
        "`declaracao_exata`, ou `concilium bdi update --from-file`). Valores em ponto flutuante não são convertidos.",
    ),
    (
        ("precificacao_exata", "tabela_bdi", "piso_bdi_regulatorio", "escopo_estoque", "faixa_margem_aceitavel",
         "regulatory BDI floor", "work type"),
        "TERMOS_DE_PRECO_DO_PERFIL",
        "O perfil da construtora não declara termos de precificação exata completos para este projeto (N9).",
        "Complete o bloco `precificacao_exata` do perfil: tabela de BDI em camadas com natureza por linha, piso de "
        "BDI por natureza e tipo de obra, escopo de estoque e a margem mínima. Nada é assumido por padrão.",
    ),
    (
        ("markup layers", "markup_layers"),
        "CAMADAS_MARKUP_NAO_DECLARADAS",
        "As camadas de markup (overhead, lucro, tributos) não foram declaradas de forma consistente (N9).",
        "Declare as camadas por categoria (MO, EQ, MAT, COMB, IND) no bloco `precificacao_exata` do perfil "
        "financeiro ou na declaração de preço do projeto.",
    ),
    (
        ("p18_consumption_preview_enabled",),
        "LEDGERS_EXATOS_DESATIVADOS",
        "A declaração de preço foi fornecida, mas os ledgers exatos (P16/P18) não estavam ativos na execução.",
        "Reexecute com os ledgers exatos ativos: todos os contratos de pool precisam da testemunha P16 (N8).",
    ),
)


def _read(source: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from a mapping (canonical JSON) or an object (canonical model)."""
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _exact(value: Any) -> str | None:
    """Return ``value`` when it is a canonical exact rational string, else None."""
    if not isinstance(value, str):
        return None
    try:
        Fraction(value)
    except (ValueError, ZeroDivisionError):
        return None
    return value


def display_float(value: Any) -> float | None:
    """Display approximation of an exact rational string (presentation edge only)."""
    exact = _exact(value)
    return float(Fraction(exact)) if exact is not None else None


def _reason(code: str, message: str, action: str | None = None, detail: str | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "action": action, "detail": detail}


def _not_evaluated(reasons: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema": SCHEMA, "status": NAO_AVALIADO, "reasons": reasons, "certificate": None}


def _has_p16_witness(contract: Any) -> bool:
    witness = _read(contract, "p16_global_assignment")
    return isinstance(witness, Mapping) and bool(witness)


def _contract_reasons(canonical: Any) -> list[dict[str, Any]]:
    """N8: what the canonical records about the exact pool ledger the price needs."""
    contracts = list(_read(canonical, "contratos_recurso") or [])
    if not contracts:
        return [
            _reason(
                "SEM_CONTRATOS_DE_POOL",
                "O canônico não registra contratos de pool de recursos; sem o ledger P16 não há custo exato (N8).",
                "Execute o pipeline até a Skill 05 com a disponibilidade de recursos e os termos contratuais "
                "(`contract_terms`) declarados.",
            )
        ]
    missing = sorted(
        str(_read(contract, "contrato_id") or _read(contract, "tipo_id") or "?")
        for contract in contracts
        if not _has_p16_witness(contract)
    )
    if missing:
        return [
            _reason(
                "CONTRATO_SEM_TESTEMUNHA_P16",
                "Contratos de pool sem testemunha P16: os termos contratuais não foram declarados ou a tarifa "
                "não é derivável do catálogo (N8). Sem ela não há custo contratual exato.",
                "Declare os termos contratuais do projeto (`contract_terms`: regime de standby, mobilização, "
                "desmobilização, gap ocioso máximo e procedência) e reexecute a partir da Skill 05.",
                ", ".join(missing),
            )
        ]
    if _read(canonical, "p18_consumption_preview") is None:
        return [
            _reason(
                "CONSUMO_P18_AUSENTE",
                "O ledger exato de consumo físico (P18) não está registrado no canônico.",
                "Reexecute a Skill 06: com todos os contratos testemunhados em P16 o ledger de consumo é "
                "construído; se falhar, a validação VAL-P18-CONSUMPTION-PREVIEW da execução indica a causa.",
            )
        ]
    return []


def _recorded_reason(recorded: str, structural: list[dict[str, Any]]) -> dict[str, Any]:
    lowered = recorded.lower()
    if _GENERIC_MISSING_EVIDENCE in lowered:
        if structural:
            return _reason(
                "DECLARACAO_PRECO_AUSENTE",
                "A declaração de preço exato (P21) não foi construída — consequência dos itens acima.",
                None,
                recorded,
            )
        return _reason(
            "MOTIVO_NAO_REGISTRADO",
            "A declaração de preço exato (P21) não foi construída e o canônico não registra qual termo "
            "faltou (motivo não registrado).",
            "Consulte a validação VAL-P21-NAO-AVALIADO da execução da Skill 06: ela lista o que falta no bloco "
            "`precificacao_exata` do perfil financeiro ou no perfil de BDI exato do projeto.",
            recorded,
        )
    for needles, code, message, action in _RECORDED_REASON_HINTS:
        if any(needle in lowered for needle in needles):
            return _reason(code, message, action, recorded)
    return _reason(
        "P21_NAO_AVALIADO",
        "A evidência de preço exato (P21) foi recusada.",
        "Corrija a causa registrada e reexecute a Skill 06.",
        recorded,
    )


def _not_evaluated_reasons(canonical: Any, diagnostics: Mapping[str, Any]) -> list[dict[str, Any]]:
    structural = _contract_reasons(canonical)
    recorded = diagnostics.get("reason")
    reasons = list(structural)
    if isinstance(recorded, str) and recorded.strip():
        reasons.append(_recorded_reason(recorded.strip(), structural))
    elif not reasons:
        reasons.append(
            _reason(
                "MOTIVO_NAO_REGISTRADO",
                "O canônico não registra o diagnóstico de preço exato (P21) nem o motivo (motivo não registrado).",
                "Reexecute o pipeline nesta versão para que a Skill 06 registre a avaliação exata.",
            )
        )
    return reasons


def _layer_amounts(raw: Any) -> dict[str, str] | None:
    """``{cost, overhead, profit, taxes, price}`` of one layered amount, all exact."""
    row = _mapping(raw)
    amounts = {
        "cost": _exact(row.get("cost")),
        "overhead": _exact(row.get("overhead")),
        "profit": _exact(row.get("profit")),
        "taxes": _exact(row.get("tax_total")),
        "price": _exact(row.get("price")),
    }
    if any(value is None for value in amounts.values()):
        return None
    return {key: value for key, value in amounts.items() if value is not None}


def _exact_map(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, Mapping):
        return None
    out = {str(key): _exact(value) for key, value in raw.items()}
    if any(value is None for value in out.values()):
        return None
    return {key: value for key, value in out.items() if value is not None}


def certificate_is_current_go(certificate: Any) -> bool:
    """GO only from a current, self-consistent P23 projection; never from a single field."""
    return (
        isinstance(certificate, Mapping)
        and certificate.get("project_go") is True
        and certificate.get("status") == "CURRENT"
        and certificate.get("effective_decision") == "GO"
    )


def certificate_decision(certificate: Any) -> str:
    """``GO`` when :func:`certificate_is_current_go`; otherwise the non-GO decision shown to users."""
    if certificate_is_current_go(certificate):
        return "GO"
    decision = certificate.get("effective_decision") if isinstance(certificate, Mapping) else None
    return str(decision) if decision and decision != "GO" else "NOT_CERTIFIABLE"


def certificate_view(certificate: Any) -> dict[str, Any] | None:
    """The P23 certificate decision as shown beside the financial view."""
    if not isinstance(certificate, Mapping):
        return None
    reasons = certificate.get("reasons")
    gates = certificate.get("gates")
    return {
        "status": certificate.get("status"),
        "decision": certificate_decision(certificate),
        "effective_decision": certificate.get("effective_decision"),
        "recorded_decision": certificate.get("recorded_decision"),
        "project_go": certificate.get("project_go") is True,
        "scope": certificate.get("scope"),
        "reasons": [str(item) for item in reasons] if isinstance(reasons, (list, tuple)) else [],
        "gates": [
            {"gate_id": gate.get("gate_id"), "status": gate.get("status"), "reason": gate.get("reason")}
            for gate in (gates if isinstance(gates, (list, tuple)) else [])
            if isinstance(gate, Mapping)
        ],
    }


def with_certificate(view: Mapping[str, Any], certificate: Any) -> dict[str, Any]:
    """Attach the run's current certificate to an already built view."""
    return {**view, "certificate": certificate_view(certificate)}


def build_exact_financial_view(canonical: Any, certificate: Any = None) -> dict[str, Any]:
    """Build the exact financial view of ``canonical`` (model or JSON mapping)."""
    view = _build(canonical)
    view["certificate"] = certificate_view(certificate)
    return view


def _build(canonical: Any) -> dict[str, Any]:
    if canonical is None:
        return _not_evaluated([
            _reason(
                "SEM_CANONICO",
                "Não há canônico para esta versão.",
                "Execute o pipeline nesta versão.",
            )
        ])
    result = _read(canonical, "resultado")
    if result is None:
        # Skill 06 fails closed (and records no result) when the pool has no exact
        # witness: name that cause first, the missing result is its consequence.
        unwitnessed = [r for r in _contract_reasons(canonical) if r["code"] == "CONTRATO_SEM_TESTEMUNHA_P16"]
        return _not_evaluated([
            *unwitnessed,
            _reason(
                "RESULTADO_AUSENTE",
                "O resultado financeiro (Skill 06) não foi produzido nesta versão.",
                "Corrija a causa acima e execute o pipeline até a Skill 06."
                if unwitnessed
                else "Execute o pipeline até a Skill 06.",
            ),
        ])

    diagnostics = _mapping(_read(result, "pricing_diagnostics"))
    gates = _mapping(_read(result, "pricing_gates"))
    layers = _mapping(_read(result, "markup_layers"))
    if not diagnostics or diagnostics.get("status") == "UNKNOWN" or "operational_price" not in diagnostics:
        return _not_evaluated(_not_evaluated_reasons(canonical, diagnostics))

    total = _layer_amounts(layers.get("total"))
    by_category_raw = _mapping(layers.get("by_category"))
    by_category = {category: _layer_amounts(by_category_raw.get(category)) for category in CATEGORIES}
    cost = {
        "total": _exact(diagnostics.get("total_cost")),
        "direct": _exact(diagnostics.get("direct_cost")),
        "indirect": _exact(diagnostics.get("indirect_cost")),
    }
    price = _exact(diagnostics.get("operational_price"))
    malformed = sorted(
        [f"pricing_diagnostics.{key}_cost" for key, value in cost.items() if value is None]
        + (["pricing_diagnostics.operational_price"] if price is None else [])
        + (["markup_layers.total"] if total is None else [])
        + [f"markup_layers.by_category.{category}" for category, row in by_category.items() if row is None]
        + ([] if gates else ["pricing_gates"])
    )
    if malformed or total is None or price is None:
        return _not_evaluated([
            _reason(
                "EVIDENCIA_EXATA_INCOMPLETA",
                "O canônico registra um diagnóstico de preço, mas não a evidência exata completa "
                "(racionais exatos de custo e preço, camadas de markup e gates). Nada é estimado no lugar.",
                "Reexecute o pipeline nesta versão: canônicos anteriores às camadas de markup (N9) não têm "
                "decomposição exata.",
                ", ".join(malformed),
            )
        ])

    bdi_rates = {category: _exact(diagnostics.get(f"bdi_rate_{category.lower()}")) for category in CATEGORIES}
    below_floor = layers.get("bdi_below_category_floor")
    gate_reasons = gates.get("reasons")
    site_cost = diagnostics.get("site_indirects_cost")
    return {
        "schema": SCHEMA,
        "status": AVALIADO,
        "reasons": [],
        "currency": diagnostics.get("currency"),
        "cost": cost,
        "price": price,
        "layers": total,
        "by_category": by_category,
        "profit_layer_share": _exact(gates.get("profit_layer_share")),
        "minimum_profit_margin": _exact(gates.get("minimum_profit_margin")),
        "catalog_benchmark": _exact(diagnostics.get("catalog_benchmark")),
        "bdi_on_catalog": _exact(diagnostics.get("implied_bdi_on_catalog")),
        "regulatory_bdi_rate": _exact(gates.get("regulatory_bdi_rate")),
        "regulatory_bdi_floor": _exact(gates.get("regulatory_bdi_floor")),
        "bdi_rate_by_category": bdi_rates if all(bdi_rates.values()) else None,
        "bdi_floor_by_category": _exact_map(layers.get("bdi_floor_by_category")),
        "categories_below_floor": (
            sorted(str(item) for item in below_floor) if isinstance(below_floor, (list, tuple)) else None
        ),
        "site_indirects": {
            "scope_status": diagnostics.get("site_indirects_scope_status"),
            "cost": _exact(site_cost),
            "source": diagnostics.get("site_indirects_source") or diagnostics.get("site_indirects_scope_source"),
            "reference_id": (
                diagnostics.get("site_indirects_reference_id")
                or diagnostics.get("site_indirects_scope_reference_id")
            ),
        },
        "gates": {
            "status": gates.get("status"),
            "regulatory_status": gates.get("regulatory_status"),
            "profitability_status": gates.get("profitability_status"),
            "certification_intent": gates.get("certification_intent"),
            "reasons": (
                [part for part in (item.strip() for item in gate_reasons.split(";")) if part]
                if isinstance(gate_reasons, str) else []
            ),
        },
        "certificate": None,
    }


def compact_view(view: Mapping[str, Any]) -> dict[str, Any]:
    """Headline of a view for listings: status, cost, price, layers and gate states."""
    if view.get("status") != AVALIADO:
        return {"status": NAO_AVALIADO, "reasons": list(view.get("reasons") or [])}
    gates = _mapping(view.get("gates"))
    return {
        "status": AVALIADO,
        "reasons": [],
        "currency": view.get("currency"),
        "cost_total": _mapping(view.get("cost")).get("total"),
        "price": view.get("price"),
        "layers": dict(_mapping(view.get("layers"))),
        "profit_layer_share": view.get("profit_layer_share"),
        "gates": {key: gates.get(key) for key in ("status", "regulatory_status", "profitability_status")},
    }


def view_from_summary(summary: Any) -> dict[str, Any]:
    """The view stored in a run/version summary (``financeiro_exato``).

    A summary recorded before this view existed carries only legacy floats;
    those are never shown, so the result is not-evaluated with that reason.
    """
    view = _mapping(summary).get("financeiro_exato")
    if isinstance(view, Mapping) and view.get("status") in (AVALIADO, NAO_AVALIADO):
        return dict(view)
    if not _mapping(summary):
        return _not_evaluated([
            _reason(
                "SEM_RESUMO",
                "Não há resumo de execução para esta versão.",
                "Execute o pipeline nesta versão.",
            )
        ])
    return _not_evaluated([
        _reason("RESUMO_ANTERIOR_AO_FINANCEIRO_EXATO", _SUMMARY_PREDATES_VIEW, "Reexecute o pipeline nesta versão.")
    ])


def _at(view: Mapping[str, Any], path: tuple[str, ...]) -> str | None:
    node: Any = view
    for key in path:
        node = _mapping(node).get(key)
    return _exact(node)


def exact_deltas(left_view: Mapping[str, Any], right_view: Mapping[str, Any]) -> dict[str, Any]:
    """``right - left`` of each compared quantity, as exact strings.

    A quantity is compared only when both views are evaluated and record it;
    otherwise its delta is ``None`` (never a difference against zero).
    """
    comparable = left_view.get("status") == AVALIADO and right_view.get("status") == AVALIADO
    deltas: dict[str, str | None] = {}
    for name, path in DELTA_FIELDS.items():
        left, right = _at(left_view, path), _at(right_view, path)
        deltas[name] = (
            str(Fraction(right) - Fraction(left)) if comparable and left is not None and right is not None else None
        )
    return {
        "schema": DELTAS_SCHEMA,
        "status": AVALIADO if comparable else NAO_AVALIADO,
        "reasons": [] if comparable else [
            {"side": side, **reason}
            for side, view in (("left", left_view), ("right", right_view))
            if view.get("status") != AVALIADO
            for reason in (view.get("reasons") or [_reason("MOTIVO_NAO_REGISTRADO", "Motivo não registrado.")])
        ],
        "deltas": deltas,
    }


def _money(value: str | None) -> str:
    approx = display_float(value)
    if approx is None:
        return "—"
    return f"{approx:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _percent(value: str | None) -> str:
    approx = display_float(value)
    return "—" if approx is None else f"{approx * 100:.2f}%".replace(".", ",")


def format_money(value: Any) -> str:
    """Display approximation of an exact amount (pt-BR, two decimals, no currency)."""
    return _money(value if isinstance(value, str) else None)


def format_percent(value: Any) -> str:
    """Display approximation of an exact rate/share as a percentage."""
    return _percent(value if isinstance(value, str) else None)


def reason_lines(view: Mapping[str, Any]) -> list[str]:
    """One user-facing line per not-evaluated reason: message, detail and how to fix it."""
    lines: list[str] = []
    for reason in view.get("reasons") or []:
        if not isinstance(reason, Mapping):
            continue
        line = str(reason.get("message") or "Motivo não registrado.")
        if reason.get("detail"):
            line += f" [{reason['detail']}]"
        if reason.get("action"):
            line += f" Como resolver: {reason['action']}"
        lines.append(line)
    return lines


def text_lines(view: Mapping[str, Any]) -> list[str]:
    """Plain-text rendering shared by the CLI and other text surfaces.

    Amounts are display approximations of the exact strings in the view.
    """
    if view.get("status") != AVALIADO:
        return ["Financeiro exato: não avaliado", *(f"  - {line}" for line in reason_lines(view))]
    currency = str(view.get("currency") or "")
    layers = _mapping(view.get("layers"))
    cost = _mapping(view.get("cost"))
    gates = _mapping(view.get("gates"))
    lines = [
        f"Financeiro exato ({currency}, valores aproximados para exibição):",
        f"  Custo total:   {_money(cost.get('total'))} (direto {_money(cost.get('direct'))}, "
        f"indireto {_money(cost.get('indirect'))})",
        f"  Overhead:      {_money(layers.get('overhead'))}",
        f"  Lucro:         {_money(layers.get('profit'))} "
        f"({_percent(view.get('profit_layer_share'))} do preço; mínimo {_percent(view.get('minimum_profit_margin'))})",
        f"  Tributos:      {_money(layers.get('taxes'))}",
        f"  Preço:         {_money(view.get('price'))}",
        f"  BDI s/ catálogo: {_percent(view.get('bdi_on_catalog'))} "
        f"(piso ponderado {_percent(view.get('regulatory_bdi_floor'))})",
        f"  Gates de preço: {gates.get('status')} (regulatório {gates.get('regulatory_status')}, "
        f"lucro {gates.get('profitability_status')})",
    ]
    lines.extend(f"    - {reason}" for reason in gates.get("reasons") or [])
    below = view.get("categories_below_floor")
    if below:
        lines.append(f"  Categorias abaixo do piso de BDI: {', '.join(below)}")
    certificate = view.get("certificate")
    if isinstance(certificate, Mapping):
        lines.append(f"  Certificado P23: {certificate.get('decision')} ({certificate.get('status')})")
    return lines
