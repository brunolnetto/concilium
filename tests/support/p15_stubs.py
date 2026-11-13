"""Typed P15 boundary stub for Skill04 tests that isolate the physical resolver.

Uses the real ``Skill04PhysicalResolution`` so a contract change (e.g. the
P23 witness fields ``audit_status``/``complete_search``/``violation_details``)
breaks the double at construction, not as an AttributeError inside Skill04.
"""

from __future__ import annotations

from sys import modules
from typing import Any

from concilium.application.skills import run_cronograma


def install_p15_pass_stub(monkeypatch: Any, reason: str) -> None:
    resolver = run_cronograma.__globals__["resolve_skill04_physical_schedule"]
    resolution_type = modules[resolver.__module__].Skill04PhysicalResolution

    def pass_physical_resolution(**kwargs: Any) -> Any:
        return resolution_type(
            status="PASS",
            schedule_selected=kwargs["schedule_selected"],
            distribution_by_item=kwargs["distribution_by_item"],
            fallback_item_ids=kwargs["fallback_item_ids"],
            attempts=1,
            reason=reason,
            audit_status="PASS",
            # An isolated boundary proves nothing about search completeness;
            # P23 must still treat V6 as UNKNOWN for these runs.
            complete_search=None,
        )

    monkeypatch.setitem(run_cronograma.__globals__, "resolve_skill04_physical_schedule", pass_physical_resolution)
