"""Tests for konnect.helpers."""

from __future__ import annotations

from konnect.helpers import child_name, first_str, fmt_date, html_to_text


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

    def test_lowercase_fullname(self):
        # The real Konnect API uses lowercase `fullname`.
        assert child_name({"fullname": "Sofie de Vries"}) == "Sofie de Vries"

    def test_display_name_takes_priority(self):
        result = child_name({"fullname": "Display", "firstName": "First", "lastName": "Last"})
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

    def test_epoch_millis(self):
        # Konnect timeline dates are epoch milliseconds. Compare against the
        # same instant built locally so the assertion is timezone-independent.
        import time
        from datetime import datetime

        ms = 1782079200000
        expected = datetime.fromtimestamp(ms / 1000).strftime("%d %b %H:%M")
        assert fmt_date(ms) == expected
        # Seconds are tolerated too.
        assert fmt_date(int(time.time())) != ""

    def test_epoch_seconds_vs_millis_same_instant(self):
        # 13-digit ms and the equivalent 10-digit seconds render identically.
        assert fmt_date(1782079200000) == fmt_date(1782079200)

    def test_empty(self):
        assert fmt_date("") == ""
        assert fmt_date(None) == ""

    def test_garbage_truncated(self):
        assert fmt_date("not-a-date-string") == "not-a-date-strin"


class TestHtmlToText:
    def test_plain_passthrough(self):
        assert html_to_text("gewoon tekst") == "gewoon tekst"

    def test_strips_tags_and_breaks_blocks(self):
        html = (
            "<div class='moment-title'>09:00 Fruit eten</div>"
            "<div class='moment-entry-description'>1 Fruit</div>"
        )
        result = html_to_text(html)
        assert "09:00 Fruit eten" in result
        assert "1 Fruit" in result
        assert "<" not in result

    def test_unescapes_entities(self):
        assert html_to_text("<p>thee &amp; koek</p>") == "thee & koek"

    def test_empty(self):
        assert html_to_text("") == ""
        assert html_to_text(None) == ""
