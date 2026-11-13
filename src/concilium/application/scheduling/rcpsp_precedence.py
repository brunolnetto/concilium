"""Single parser for ``rcpsp_spec.precedence`` (finish-to-start overrides).

Accepted entries:
  * ``[pred, succ]`` → θ = 1.0 (classic FS)
  * ``[pred, succ, theta]`` → FS released when ``pred`` reaches θ ∈ [0, 1]
  * ``{"de": pred, "para": succ}`` with optional ``"tipo": "FS"``, ``"lag": 0``
    and ``"completion_threshold_pct": theta`` — the keys of ``ArestaActivityDag``

SS/FF relations and lags belong in ``EapItem.predecessores``; this override
list is FS-only. Anything else raises ``ValueError`` naming the offending
index, instead of crashing with ``KeyError`` or silently dropping a declared
constraint (which would schedule against a different DAG than the user's).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

_MAPPING_KEYS = frozenset({"de", "para", "tipo", "lag", "completion_threshold_pct"})
_FORMS = "use [pred, succ] or [pred, succ, theta] or {'de', 'para', 'completion_threshold_pct'}"


@dataclass(frozen=True)
class PrecedenceEdge:
    pred: str
    succ: str
    theta: float = 1.0


def _theta(value: object, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where}: theta must be a number in [0, 1]")
    theta = float(value)
    if not isfinite(theta) or not 0.0 <= theta <= 1.0:
        raise ValueError(f"{where}: theta must be in [0, 1], got {value!r}")
    return theta


def _edge(entry: object, where: str) -> PrecedenceEdge:
    if isinstance(entry, (list, tuple)):
        if len(entry) not in (2, 3):
            raise ValueError(f"{where}: expected [pred, succ] or [pred, succ, theta], got {entry!r}")
        pred, succ = entry[0], entry[1]
        theta = _theta(entry[2], where) if len(entry) == 3 else 1.0
    elif isinstance(entry, dict):
        unknown = set(entry) - _MAPPING_KEYS
        if unknown:
            raise ValueError(f"{where}: unsupported keys {sorted(unknown)}; {_FORMS}")
        tipo = entry.get("tipo", "FS")
        if tipo != "FS":
            raise ValueError(
                f"{where}: only FS overrides are accepted here; declare {tipo!r} in EapItem.predecessores"
            )
        if entry.get("lag", 0) not in (0, None):
            raise ValueError(f"{where}: lag is not supported in FS overrides; declare it in EapItem.predecessores")
        pred, succ = entry.get("de"), entry.get("para")
        theta = _theta(entry["completion_threshold_pct"], where) if "completion_threshold_pct" in entry else 1.0
    else:
        raise ValueError(f"{where}: {_FORMS}; got {type(entry).__name__}")
    if not isinstance(pred, str) or not isinstance(succ, str) or not pred.strip() or not succ.strip():
        raise ValueError(f"{where}: activity ids must be nonempty strings")
    if pred == succ:
        raise ValueError(f"{where}: an activity cannot precede itself ({pred})")
    return PrecedenceEdge(pred, succ, theta)


def parse_rcpsp_precedence(raw: object) -> tuple[PrecedenceEdge, ...]:
    """Parse and validate the whole list; raise on the first malformed entry."""
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ValueError(f"rcpsp_spec.precedence must be a list; {_FORMS}")
    edges: list[PrecedenceEdge] = []
    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(raw):
        where = f"rcpsp_spec.precedence[{index}]"
        edge = _edge(entry, where)
        if (edge.pred, edge.succ) in seen:
            raise ValueError(f"{where}: duplicate edge {edge.pred}->{edge.succ}")
        seen.add((edge.pred, edge.succ))
        edges.append(edge)
    return tuple(edges)
