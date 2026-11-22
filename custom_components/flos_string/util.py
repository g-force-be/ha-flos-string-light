"""Helpers for the names and the options of a Flos String Light."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .const import (
    CONF_CONNECT_TWICE,
    CONF_SECOND_CONNECTION,
    DEFAULT_SECOND_CONNECTION,
    SECOND_ALWAYS,
    SECOND_NEVER,
)


def clean_name(name: str | None) -> str:
    """Return the name without NUL characters and surrounding whitespace.

    The lamp pads its Bluetooth name with NULs, and Home Assistant passes them on
    in the discovery.
    """
    return (name or "").replace("\x00", "").strip()


def second_connection(options: Mapping[str, Any]) -> str:
    """Return the choice for the second connection in the options of a lamp.

    Options saved with 2026.47.9 hold that version's on/off setting instead: on
    is always, off is never.
    """
    if CONF_SECOND_CONNECTION in options:
        return options[CONF_SECOND_CONNECTION]
    if CONF_CONNECT_TWICE in options:
        return SECOND_ALWAYS if options[CONF_CONNECT_TWICE] else SECOND_NEVER
    return DEFAULT_SECOND_CONNECTION
