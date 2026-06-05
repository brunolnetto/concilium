"""API integration layer for Streamlit UI."""

from __future__ import annotations

import json
from urllib import error, parse, request

from concilium.presentation.ui.config import DEFAULT_BASE_URL  # fonte canônica em ui/config.py


def api_call(
    method: str,
    path: str,
    base_url: str = DEFAULT_BASE_URL,
    payload: dict | None = None,
    params: dict | None = None,
    actor: str = "anonymous",
) -> dict:
    """Execute HTTP request to Concilium API."""
    if not path.startswith("/"):
        path = f"/{path}"
    url = f"{base_url.rstrip('/')}{path}"
    if params:
        url = f"{url}?{parse.urlencode(params)}"

    data = None
    headers = {"Content-Type": "application/json", "X-User": actor}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = request.Request(url=url, method=method, data=data, headers=headers)
    try:
        with request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


def fetch_artifact_bytes(
    base_url: str,
    project_id: str,
    kind: str,
    filename: str,
    version: str | None,
    actor: str,
) -> bytes:
    """Download artifact bytes from API."""
    params = {"kind": kind, "filename": filename}
    if version:
        params["version"] = version
    url = f"{base_url.rstrip('/')}/api/projects/{project_id}/artifacts/download?{parse.urlencode(params)}"
    req = request.Request(url=url, method="GET", headers={"X-User": actor})
    with request.urlopen(req, timeout=120) as resp:
        return resp.read()
