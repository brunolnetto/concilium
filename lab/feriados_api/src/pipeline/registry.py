from __future__ import annotations

import importlib


def load_component(
    path: str,
):
    """
    Load dynamic component.

    Example:

    src.transformers.holidays.normalize_holidays

    """

    module_name, attr = path.rsplit(
        ".",
        1,
    )

    module = importlib.import_module(
        module_name
    )

    return getattr(
        module,
        attr,
    )