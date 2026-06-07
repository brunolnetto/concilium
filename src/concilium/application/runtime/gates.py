"""Política de skills GATE do Runtime."""

from __future__ import annotations

from concilium.application.skills import MANIFEST_META

# ADR-022: skills GATE cujas falhas contaminam (taint) o canônico.
_GATE_SKILLS: frozenset[str] = frozenset(sid for sid, meta in MANIFEST_META.items() if meta.get("gate", False))
