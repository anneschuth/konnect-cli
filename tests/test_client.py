"""Tests for konnect.client. Network calls are mocked, no real HTTP."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
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


class TestItems:
    def test_items_from_list(self):
        c = KonnectClient(token="x")
        with patch.object(c, "_get", return_value=[{"a": 1}]):
            assert c.get_children() == [{"a": 1}]

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


class TestLogin:
    def _resp(self, status, json_body=None, headers=None):
        r = MagicMock(spec=httpx.Response)
        r.status_code = status
        r.headers = headers or {}
        r.json.return_value = json_body if json_body is not None else {}
        r.raise_for_status.return_value = None
        return r

    def test_login_json_body_success(self, tmp_path):
        token_path = tmp_path / "tokens.json"
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.put.return_value = self._resp(
            200, {"result": True, "payload": {"token": "tok123"}}
        )
        with (
            patch.object(client_mod.httpx, "Client", return_value=mock_client),
            patch.object(client_mod, "TOKEN_PATH", token_path),
        ):
            tokens = KonnectAuth.login(username="a@b.nl", password="pw", portal="someorg")
        assert tokens["token"] == "tok123"
        assert tokens["portal"] == "someorg"
        assert token_path.exists()

    def test_login_falls_back_to_basic(self, tmp_path):
        token_path = tmp_path / "tokens.json"
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        # First PUT (JSON) → 415, second (Basic) → 200
        mock_client.put.side_effect = [
            self._resp(415),
            self._resp(200, {"token": "viabasic"}),
        ]
        with (
            patch.object(client_mod.httpx, "Client", return_value=mock_client),
            patch.object(client_mod, "TOKEN_PATH", token_path),
        ):
            tokens = KonnectAuth.login(username="a@b.nl", password="pw")
        assert tokens["token"] == "viabasic"

    def test_login_bad_credentials(self, tmp_path):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.put.return_value = self._resp(401)
        with (
            patch.object(client_mod.httpx, "Client", return_value=mock_client),
            patch.object(client_mod, "TOKEN_PATH", tmp_path / "t.json"),
            pytest.raises(RuntimeError, match="onjuist"),
        ):
            KonnectAuth.login(username="a@b.nl", password="wrong")
