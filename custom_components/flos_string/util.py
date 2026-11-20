"""Helpers for the names of a Flos String Light."""

from __future__ import annotations


def clean_name(name: str | None) -> str:
    """Return the name without NUL characters and surrounding whitespace.

    The lamp pads its Bluetooth name with NULs, and Home Assistant passes them on
    in the discovery.
    """
    return (name or "").replace("\x00", "").strip()
