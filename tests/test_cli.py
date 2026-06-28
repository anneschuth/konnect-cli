"""Tests for konnect.cli using Click's CliRunner. Auth + client are mocked."""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from konnect.cli import cli


@contextmanager
def fake_client(stub):
    """Patch KonnectClient so `with KonnectClient() as client` yields `stub`."""
    cm = MagicMock()
    cm.__enter__.return_value = stub
    cm.__exit__.return_value = False
    with patch("konnect.cli.KonnectClient", return_value=cm):
        yield


def test_version():
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_children_table():
    stub = MagicMock()
    stub.get_children.return_value = [{"displayName": "Sofie", "id": 7}]
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["children"])
    assert result.exit_code == 0
    assert "Sofie" in result.output


def test_children_json():
    stub = MagicMock()
    stub.get_children.return_value = [{"displayName": "Sofie", "id": 7}]
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["--json", "children"])
    assert result.exit_code == 0
    assert json.loads(result.output)[0]["displayName"] == "Sofie"


def test_children_empty():
    stub = MagicMock()
    stub.get_children.return_value = []
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["children"])
    assert result.exit_code == 0
    assert "Geen kinderen" in result.output


def test_account():
    stub = MagicMock()
    stub.get_parent.return_value = {"displayName": "Ouder", "email": "o@b.nl"}
    stub.get_customer_info.return_value = {"name": "Kind en Co Ludens"}
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["account"])
    assert result.exit_code == 0
    assert "Ouder" in result.output
    assert "Kind en Co Ludens" in result.output


def test_timeline_json():
    stub = MagicMock()
    stub.get_timeline.return_value = [{"type": "photo", "text": "Leuke dag", "photos": [1, 2]}]
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["--json", "timeline", "--limit", "5"])
    assert result.exit_code == 0
    assert json.loads(result.output)[0]["text"] == "Leuke dag"


def test_notifications():
    stub = MagicMock()
    stub.get_notifications.return_value = [
        {"type": "info", "text": "Nieuw bericht", "read": False}
    ]
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["notifications"])
    assert result.exit_code == 0
    assert "Nieuw bericht" in result.output


def test_logout_when_logged_out(tmp_path):
    missing = tmp_path / "tokens.json"
    with patch("konnect.client.TOKEN_PATH", missing):
        result = CliRunner().invoke(cli, ["logout"])
    assert result.exit_code == 0
    assert "al uitgelogd" in result.output


def test_logout_removes_tokens(tmp_path):
    token_path = tmp_path / "tokens.json"
    token_path.write_text("{}")
    with patch("konnect.client.TOKEN_PATH", token_path):
        result = CliRunner().invoke(cli, ["logout"])
    assert result.exit_code == 0
    assert not token_path.exists()
    assert "Uitgelogd" in result.output


def test_login_success(tmp_path):
    with (
        patch("konnect.client.KonnectAuth.login", return_value={"token": "t"}) as mock_login,
        patch("konnect.client.TOKEN_PATH", tmp_path / "tokens.json"),
    ):
        result = CliRunner().invoke(cli, ["login", "-u", "a@b.nl", "-p", "pw"])
    assert result.exit_code == 0
    assert "Login geslaagd" in result.output
    mock_login.assert_called_once()
