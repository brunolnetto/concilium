"""Routes for system health."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["system"])


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/swagger")


@router.get("/health", summary="Health check")
def health() -> dict[str, str]:
    return {"status": "ok"}
