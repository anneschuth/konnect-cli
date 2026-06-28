"""Tests for konnect.helpers."""

from __future__ import annotations

from konnect.helpers import child_name, first_str, fmt_date


class TestChildName:
    def test_display_name(self):
        assert child_name({"displayName": "Jan Jansen"}) == "Jan Jansen"

    def test_full_name(self):
        assert child_name({"fullName": "Jan Jansen"}) == "Jan Jansen"

    def test_first_last(self):
        assert child_name({"firstName": "Jan", "lastName": "Jansen"}) == "Jan Jansen"

    def test_first_prefix_last(self):
        result = child_name({"firstName": "Jan", "namePrefix": "van", "lastName": "Dijk"})
        assert result == "Jan van Dijk"

    def test_surname_fallback(self):
        result = child_name({"firstName": "Jan", "surnamePrefix": "de", "surname": "Vries"})
        assert result == "Jan de Vries"

    def test_empty_returns_onbekend(self):
        assert child_name({}) == "Onbekend"

    def test_display_name_takes_priority(self):
        result = child_name({"displayName": "Display", "firstName": "First", "lastName": "Last"})
        assert result == "Display"


class TestFirstStr:
    def test_first_present(self):
        assert first_str({"a": "x", "b": "y"}, "a", "b") == "x"

    def test_skips_empty(self):
        assert first_str({"a": "", "b": "y"}, "a", "b") == "y"

    def test_skips_non_string(self):
        assert first_str({"a": 5, "b": "y"}, "a", "b") == "y"

    def test_default(self):
        assert first_str({}, "a", default="fallback") == "fallback"


class TestFmtDate:
    def test_basic(self):
        assert fmt_date("2026-06-22T14:30:00") == "22 Jun 14:30"

    def test_zulu(self):
        assert fmt_date("2026-06-22T14:30:00Z") == "22 Jun 14:30"

    def test_empty(self):
        assert fmt_date("") == ""
        assert fmt_date(None) == ""

    def test_garbage_truncated(self):
        assert fmt_date("not-a-date-string") == "not-a-date-strin"
