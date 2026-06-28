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
    from konnect.cli import __version__

    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_children_table():
    stub = MagicMock()
    stub.get_children.return_value = [{"fullname": "Sofie", "id": "7"}]
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["children"])
    assert result.exit_code == 0
    assert "Sofie" in result.output


def test_children_json():
    stub = MagicMock()
    stub.get_children.return_value = [{"fullname": "Sofie", "id": "7"}]
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["--json", "children"])
    assert result.exit_code == 0
    assert json.loads(result.output)[0]["fullname"] == "Sofie"


def test_children_all_flag_includes_inactive():
    stub = MagicMock()
    stub.get_children.return_value = []
    with fake_client(stub):
        CliRunner().invoke(cli, ["children", "--all"])
    stub.get_children.assert_called_once_with(include_inactive=True)


def test_children_empty():
    stub = MagicMock()
    stub.get_children.return_value = []
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["children"])
    assert result.exit_code == 0
    assert "Geen kinderen" in result.output


def test_account():
    stub = MagicMock()
    stub.get_parent.return_value = {"fullname": "Ouder", "emailAddress": "o@b.nl"}
    stub.get_customer_info.return_value = {"customerName": "Kind en Co Ludens"}
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["account"])
    assert result.exit_code == 0
    assert "Ouder" in result.output
    assert "Kind en Co Ludens" in result.output


def test_timeline_renders_journal_text():
    stub = MagicMock()
    stub.get_timeline.return_value = [
        {
            "type": "journal",
            "date": 1782079200000,
            "children": [{"fullname": "Sofie"}],
            "journal": {"content": "Leuke dag gehad", "writtenByName": "Juf"},
        }
    ]
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["timeline"])
    assert result.exit_code == 0
    assert "Leuke dag gehad" in result.output
    assert "Sofie" in result.output


def test_notifications_counts():
    stub = MagicMock()
    stub.get_notifications.return_value = {
        "nrOfNewMessages": 2,
        "nrOfNewNewsItems": 0,
        "nrOfNewNewsletters": 1,
    }
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["notifications"])
    assert result.exit_code == 0
    assert "Berichten" in result.output
    assert "2" in result.output


def test_notifications_all_zero():
    stub = MagicMock()
    stub.get_notifications.return_value = {"nrOfNewMessages": 0, "nrOfNewNewsletters": 0}
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["notifications"])
    assert result.exit_code == 0
    assert "Niets ongelezen" in result.output


MESSAGES = [
    {
        "subject": "Reminder afscheid",
        "lastWritten": "Juf",
        "date": 1782392507927,
        "message": "<p>Beste ouders, volgende maand...</p>",
        "unread": True,
    },
    {
        "subject": "Uitje",
        "lastWritten": "Sneeuwwit",
        "date": 1782000000000,
        "message": "<div>We gaan naar het bos</div>",
        "unread": False,
    },
]


def test_messages_list():
    stub = MagicMock()
    stub.get_messages.return_value = list(MESSAGES)
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["messages"])
    assert result.exit_code == 0
    assert "Reminder afscheid" in result.output
    assert "Uitje" in result.output


def test_messages_unread_filter():
    stub = MagicMock()
    stub.get_messages.return_value = list(MESSAGES)
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["messages", "--unread"])
    assert result.exit_code == 0
    assert "Reminder afscheid" in result.output
    assert "Uitje" not in result.output


def test_messages_detail_strips_html():
    stub = MagicMock()
    stub.get_messages.return_value = list(MESSAGES)
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["messages", "1"])
    assert result.exit_code == 0
    assert "Beste ouders" in result.output
    assert "<p>" not in result.output


def test_messages_detail_out_of_range():
    stub = MagicMock()
    stub.get_messages.return_value = list(MESSAGES)
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["messages", "99"])
    assert result.exit_code == 1
    assert "bestaat niet" in result.output


def test_messages_empty():
    stub = MagicMock()
    stub.get_messages.return_value = []
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["messages"])
    assert result.exit_code == 0
    assert "Geen berichten" in result.output


def test_newsletters_list():
    stub = MagicMock()
    stub.get_newsletters.return_value = [
        {"mailSubject": "Juni-update", "sendDate": 1782000000000, "unread": True}
    ]
    with fake_client(stub):
        result = CliRunner().invoke(cli, ["newsletters"])
    assert result.exit_code == 0
    assert "Juni-update" in result.output


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
