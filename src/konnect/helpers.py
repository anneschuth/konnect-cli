"""Reusable helpers for Konnect ouderportaal data structures.

Pure stdlib, no external dependencies.
"""

from __future__ import annotations

import re
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any

# Tags that should introduce a line break when flattening HTML to text.
_BLOCK_TAGS = {"br", "p", "div", "tr", "li", "table"}


class _TextExtractor(HTMLParser):
    """Collapse HTML to plain text, breaking lines on block-level tags."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(value: str | None) -> str:
    """Flatten an HTML fragment to readable plain text.

    Block-level tags become line breaks; runs of whitespace are collapsed.
    Returns the input unchanged when it contains no markup.
    """
    if not value:
        return ""
    if "<" not in value:
        return value.strip()
    parser = _TextExtractor()
    parser.feed(value)
    text = unescape("".join(parser.parts))
    # Collapse intra-line whitespace, then trim blank lines.
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def fmt_date(value: str | int | float | None) -> str:
    """Format a timestamp to a short readable Dutch-style string.

    Accepts an ISO datetime string or an epoch number (the Konnect API uses
    epoch milliseconds; seconds are tolerated too). Returns "" for empty input.
    """
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        # Konnect timestamps are epoch milliseconds (13 digits).
        seconds = value / 1000 if value > 1e11 else value
        try:
            return datetime.fromtimestamp(seconds).strftime("%d %b %H:%M")
        except (ValueError, OSError, OverflowError):
            return str(value)
    try:
        # Tolerate a trailing Z (UTC) which fromisoformat rejects on <3.11 paths.
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%d %b %H:%M")
    except (ValueError, TypeError):
        return value[:16]


def child_name(child: dict[str, Any]) -> str:
    """Extract a display name from a child object.

    Tries common Konnect name fields, falling back to first + last name.
    Returns "Onbekend" when nothing usable is present.
    """
    for key in ("fullname", "fullName", "displayName", "name"):
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
