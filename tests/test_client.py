"""Tests for konnect.client. Network calls are mocked, no real HTTP."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from konnect import client as client_mod
from konnect.client import (
    KonnectAuth,
    KonnectClient,
    _extract_token,
    _unwrap,
    base_url,
    resolve_portal,
)


class TestPortal:
    def test_resolve_default(self):
        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("KONNECT_PORTAL", None)
            assert resolve_portal() == "kindencoludens"

    def test_resolve_explicit(self):
        assert resolve_portal("someorg") == "someorg"

    def test_resolve_env(self):
        with patch.dict("os.environ", {"KONNECT_PORTAL": "envorg"}):
            assert resolve_portal() == "envorg"

    def test_explicit_beats_env(self):
        with patch.dict("os.environ", {"KONNECT_PORTAL": "envorg"}):
            assert resolve_portal("explicit") == "explicit"

    def test_base_url(self):
        assert base_url("someorg") == "https://someorg.ouderportaal.nl"


class TestUnwrap:
    def test_unwraps_envelope(self):
        assert _unwrap({"result": True, "payload": {"a": 1}, "messages": None}) == {"a": 1}

    def test_unwraps_partial_envelope(self):
        assert _unwrap({"result": True, "payload": "kindencoludens"}) == "kindencoludens"

    def test_passes_through_plain_dict(self):
        data = {"a": 1, "b": 2}
        assert _unwrap(data) == data

    def test_passes_through_dict_with_extra_keys(self):
        # Has payload but also other keys → not the envelope, leave as-is.
        data = {"payload": 1, "other": 2}
        assert _unwrap(data) == data

    def test_passes_through_list(self):
        assert _unwrap([1, 2, 3]) == [1, 2, 3]


class TestExtractToken:
    def test_string_payload(self):
        assert _extract_token("abc.def.ghi") == "abc.def.ghi"

    def test_auth_token_key(self):
        # The real Konnect success body uses `authToken`.
        assert _extract_token({"authToken": "jwt.value.here"}) == "jwt.value.here"

    def test_auth_token_takes_priority(self):
        assert _extract_token({"authToken": "a", "token": "b"}) == "a"

    def test_token_key(self):
        assert _extract_token({"token": "t1"}) == "t1"

    def test_access_token_key(self):
        assert _extract_token({"accessToken": "t2"}) == "t2"

    def test_snake_case_key(self):
        assert _extract_token({"access_token": "t3"}) == "t3"

    def test_none_when_absent(self):
        assert _extract_token({"foo": "bar"}) is None

    def test_none_for_empty_string(self):
        assert _extract_token("") is None


class TestChildrenAndNotifications:
    def test_children_active_only(self):
        c = KonnectClient(token="x")
        data = {"activeChildren": [{"id": "1"}], "inactiveChildren": [{"id": "2"}]}
        with patch.object(c, "_get", return_value=data):
            assert c.get_children() == [{"id": "1"}]

    def test_children_include_inactive(self):
        c = KonnectClient(token="x")
        data = {"activeChildren": [{"id": "1"}], "inactiveChildren": [{"id": "2"}]}
        with patch.object(c, "_get", return_value=data):
            assert c.get_children(include_inactive=True) == [{"id": "1"}, {"id": "2"}]

    def test_notifications_returns_dict(self):
        c = KonnectClient(token="x")
        with patch.object(c, "_get", return_value={"nrOfNewMessages": 3}):
            assert c.get_notifications() == {"nrOfNewMessages": 3}

    def test_messages_returns_list(self):
        c = KonnectClient(token="x")
        with patch.object(c, "_get", return_value=[{"subject": "Hoi"}]) as g:
            assert c.get_messages("20260101", "20260201") == [{"subject": "Hoi"}]
        g.assert_called_once_with("/logbook/overview", **{"from": "20260101", "to": "20260201"})

    def test_messages_non_list_is_empty(self):
        c = KonnectClient(token="x")
        with patch.object(c, "_get", return_value={"oops": 1}):
            assert c.get_messages("20260101", "20260201") == []

    def test_newsletters_unwraps_items(self):
        c = KonnectClient(token="x")
        data = {"moreItems": False, "newsletterItems": [{"mailSubject": "Juni"}]}
        with patch.object(c, "_get", return_value=data):
            assert c.get_newsletters() == [{"mailSubject": "Juni"}]


class TestItems:
    def test_items_from_list(self):
        c = KonnectClient(token="x")
        with patch.object(c, "_get", return_value=[{"a": 1}]):
            assert c.get_timeline() == [{"a": 1}]

    def test_items_from_items_key(self):
        c = KonnectClient(token="x")
        with patch.object(c, "_get", return_value={"items": [{"a": 1}]}):
            assert c._items("/x") == [{"a": 1}]

    def test_items_from_cards_key(self):
        c = KonnectClient(token="x")
        with patch.object(c, "_get", return_value={"cards": [{"c": 1}]}):
            assert c._items("/x") == [{"c": 1}]

    def test_items_empty_dict(self):
        c = KonnectClient(token="x")
        with patch.object(c, "_get", return_value={"unrelated": 1}):
            assert c._items("/x") == []


class TestClientEnter:
    def test_requires_token(self):
        with (
            patch.object(KonnectAuth, "get_token", return_value=None),
            pytest.raises(RuntimeError, match="Niet ingelogd"),
            KonnectClient(),
        ):
            pass

    def test_uses_explicit_token(self):
        c = KonnectClient(token="explicit", portal="someorg")
        with c as entered:
            assert entered.token == "explicit"
            assert c._client is not None
            assert str(c._client.base_url).startswith("https://someorg.ouderportaal.nl")

    def test_uses_token_and_portal_from_auth(self):
        c = KonnectClient()
        with (
            patch.object(KonnectAuth, "get_token", return_value=("tok", "fromauth")),
            c as entered,
        ):
            assert entered.token == "tok"
            assert entered.portal == "fromauth"


# Real GET /auth-api/token success body shape.
MINT_BODY = {
    "authToken": "jwt.token.value",
    "refreshToken": "refresh.value",
    "expiration": "2026-06-28T13:00:00Z",
    "domainServerName": "kindencoludens",
}


class TestLogin:
    def test_login_success(self, tmp_path):
        token_path = tmp_path / "tokens.json"
        with (
            patch.object(client_mod, "_mint", return_value=MINT_BODY) as mint,
            patch.object(client_mod, "TOKEN_PATH", token_path),
        ):
            tokens = KonnectAuth.login(username="a@b.nl", password="pw", portal="someorg")
        assert tokens["token"] == "jwt.token.value"
        assert tokens["portal"] == "someorg"
        assert tokens["refreshToken"] == "refresh.value"
        assert token_path.exists()
        # Credentials and portal are forwarded to the browser layer.
        _, kwargs = mint.call_args
        assert kwargs["username"] == "a@b.nl"
        assert kwargs["password"] == "pw"

    def test_login_no_session_raises(self, tmp_path):
        with (
            patch.object(client_mod, "_mint", return_value=None),
            patch.object(client_mod, "TOKEN_PATH", tmp_path / "t.json"),
            pytest.raises(RuntimeError, match="kon geen sessie"),
        ):
            KonnectAuth.login(username="a@b.nl", password="wrong")

    def test_refresh_headless_success(self, tmp_path):
        token_path = tmp_path / "tokens.json"
        with (
            patch.object(client_mod, "_mint", return_value=MINT_BODY) as mint,
            patch.object(client_mod, "TOKEN_PATH", token_path),
        ):
            tokens = KonnectAuth.refresh(portal="someorg")
        assert tokens is not None
        assert tokens["token"] == "jwt.token.value"
        # Refresh must not open a window.
        _, kwargs = mint.call_args
        assert kwargs["interactive"] is False

    def test_refresh_expired_returns_none(self, tmp_path):
        with (
            patch.object(client_mod, "_mint", return_value=None),
            patch.object(client_mod, "TOKEN_PATH", tmp_path / "t.json"),
        ):
            assert KonnectAuth.refresh(portal="someorg") is None
