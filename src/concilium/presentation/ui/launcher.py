from __future__ import annotations

import os
import subprocess
from pathlib import Path

from concilium.presentation.ui.config import resolve_ui_bind_host, resolve_ui_bind_port


def _default_ui_entrypoint() -> Path:
    return Path(__file__).resolve().parent / "prototype_streamlit.py"


def resolve_ui_entrypoint() -> Path:
    custom = (os.environ.get("CONCILIUM_UI_ENTRYPOINT") or "").strip()
    if custom:
        return Path(custom)
    return _default_ui_entrypoint()


def build_streamlit_command(entrypoint: Path | None = None) -> list[str]:
    script = entrypoint or resolve_ui_entrypoint()
    host = resolve_ui_bind_host()
    port = resolve_ui_bind_port()
    return [
        "streamlit",
        "run",
        str(script),
        "--server.address",
        host,
        "--server.port",
        str(port),
    ]


def main() -> None:
    cmd = build_streamlit_command()
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
