"""Reusable helpers for Konnect ouderportaal data structures.

Pure stdlib, no external dependencies.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def fmt_date(iso: str | None) -> str:
    """Format an ISO datetime to a short readable Dutch-style string."""
    if not iso:
        return ""
    try:
        # Tolerate a trailing Z (UTC) which fromisoformat rejects on <3.11 paths.
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%d %b %H:%M")
    except (ValueError, TypeError):
        return iso[:16]


def child_name(child: dict[str, Any]) -> str:
    """Extract a display name from a child object.

    Tries common Konnect name fields, falling back to first + last name.
    Returns "Onbekend" when nothing usable is present.
    """
    for key in ("displayName", "fullName", "name"):
        val = child.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    first = str(child.get("firstName", "") or "")
    prefix = str(child.get("namePrefix", child.get("surnamePrefix", "")) or "")
    last = str(child.get("lastName", child.get("surname", "")) or "")
    parts = [first, prefix, last] if prefix else [first, last]
    name = " ".join(p for p in parts if p)
    return name or "Onbekend"


def first_str(item: dict[str, Any], *keys: str, default: str = "") -> str:
    """Return the first non-empty string value among the given keys."""
    for key in keys:
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return default
