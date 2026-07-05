"""Atomic design atoms - Basic UI elements (buttons, inputs, cards, etc)."""

from __future__ import annotations

from typing import Any, Literal

import streamlit as st

_DeltaColor = Literal[
    "normal", "inverse", "off", "red", "orange", "yellow", "green", "blue", "violet", "gray", "grey", "primary"
]


def render_primary_button(
    label: str,
    key: str,
    on_click=None,
    use_container_width: bool = False,
    disabled: bool = False,
) -> bool:
    """Render primary action button."""
    return st.button(
        label,
        key=key,
        on_click=on_click,
        use_container_width=use_container_width,
        disabled=disabled,
        type="primary",
    )


def render_secondary_button(
    label: str,
    key: str,
    on_click=None,
    use_container_width: bool = False,
    disabled: bool = False,
) -> bool:
    """Render secondary action button."""
    return st.button(
        label,
        key=key,
        on_click=on_click,
        use_container_width=use_container_width,
        disabled=disabled,
        type="secondary",
    )


def render_metric(
    label: str, value: str | int | float, delta: str | None = None, delta_color: _DeltaColor = "normal"
) -> None:
    """Render a metric card."""
    st.metric(label, value, delta=delta, delta_color=delta_color)


def render_badge(text: str, color: str = "blue") -> None:
    """Render a badge/label."""
    st.markdown(f"**{text}**")


def render_divider() -> None:
    """Render a divider."""
    st.divider()


def render_info(message: str) -> None:
    """Render info message."""
    st.info(message)


def render_success(message: str) -> None:
    """Render success message."""
    st.success(message)


def render_error(message: str) -> None:
    """Render error message."""
    st.error(message)


def render_warning(message: str) -> None:
    """Render warning message."""
    st.warning(message)


def render_caption(text: str) -> None:
    """Render caption text."""
    st.caption(text)


def render_subheader(text: str) -> None:
    """Render subheader."""
    st.subheader(text)


def render_header(text: str) -> None:
    """Render header."""
    st.header(text)


def render_text_input(
    label: str,
    key: str,
    value: str = "",
    placeholder: str = "",
) -> str:
    """Render text input."""
    return st.text_input(label, value=value, placeholder=placeholder, key=key)


def render_number_input(
    label: str,
    key: str,
    value: float = 0.0,
    min_value: float | None = None,
    max_value: float | None = None,
    step: float = 0.01,
) -> float:
    """Render number input."""
    return st.number_input(
        label,
        value=value,
        min_value=min_value,
        max_value=max_value,
        step=step,
        key=key,
    )


def render_selectbox(
    label: str,
    options: list,
    key: str,
    index: int = 0,
) -> Any:
    """Render selectbox."""
    return st.selectbox(label, options=options, index=index, key=key)


def render_checkbox(
    label: str,
    key: str,
    value: bool = False,
) -> bool:
    """Render checkbox."""
    return st.checkbox(label, value=value, key=key)


def render_text_area(
    label: str,
    key: str,
    value: str = "",
    height: int = 150,
) -> str:
    """Render text area."""
    return st.text_area(label, value=value, height=height, key=key)
