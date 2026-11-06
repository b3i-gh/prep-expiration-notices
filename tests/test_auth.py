import json
import stat
from unittest.mock import Mock, patch

import pytest
from google.auth.exceptions import RefreshError

from prep_notices.auth import SCOPES, authenticate
from prep_notices.errors import NoticeError


@pytest.fixture
def client(tmp_path):
    directory = tmp_path / ".secrets"
    directory.mkdir()
    (directory / "credentials.json").write_text("{}")
    return directory


def credential(valid=True):
    result = Mock()
    result.valid = valid
    result.granted_scopes = list(SCOPES)
    result.to_json.return_value = json.dumps({"scopes": SCOPES, "token": "synthetic"})
    return result


def test_first_consent_and_private_persistence(tmp_path, client):
    credentials = credential()
    with patch("prep_notices.auth.InstalledAppFlow") as flow:
        flow.from_client_secrets_file.return_value.run_local_server.return_value = (
            credentials
        )
        assert authenticate(tmp_path) is credentials
        options = (
            flow.from_client_secrets_file.return_value.run_local_server.call_args.kwargs
        )
        assert options["bind_addr"] == "127.0.0.1"
        assert not options["open_browser"]
        assert flow.from_client_secrets_file.call_args.args[1] == SCOPES
    assert stat.S_IMODE(client.stat().st_mode) == 0o700
    for path in client.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("valid", [True, False])
def test_reuse_and_refresh(tmp_path, client, valid):
    (client / "token.json").write_text(json.dumps({"scopes": SCOPES}))
    credentials = credential(valid)
    credentials.refresh.side_effect = lambda _: setattr(credentials, "valid", True)
    with (
        patch(
            "prep_notices.auth.Credentials.from_authorized_user_info",
            return_value=credentials,
        ),
        patch("prep_notices.auth.InstalledAppFlow") as flow,
    ):
        assert authenticate(tmp_path) is credentials
        assert credentials.refresh.call_count == (0 if valid else 1)
        flow.assert_not_called()
    assert json.loads((client / "token.json").read_text())["token"] == "synthetic"


@pytest.mark.parametrize(
    "content",
    [
        "not-json-secret",
        json.dumps({"scopes": ["https://www.googleapis.com/auth/calendar"]}),
    ],
)
def test_corrupt_or_legacy_scope_token(tmp_path, client, content):
    token = client / "token.json"
    token.write_text(content)
    with pytest.raises(NoticeError) as exc:
        authenticate(tmp_path)
    assert content not in str(exc.value)
    assert token.read_text() == content


def test_missing_client(tmp_path):
    with pytest.raises(NoticeError, match="credentials.json"):
        authenticate(tmp_path)


def test_rejected_refresh_preserves_token(tmp_path, client):
    token = client / "token.json"
    token.write_text(json.dumps({"scopes": SCOPES}))
    before = token.read_text()
    credentials = credential(False)
    credentials.refresh.side_effect = RefreshError("sensitive provider response")
    with (
        patch(
            "prep_notices.auth.Credentials.from_authorized_user_info",
            return_value=credentials,
        ),
        pytest.raises(NoticeError) as exc,
    ):
        authenticate(tmp_path)
    assert "sensitive" not in str(exc.value)
    assert token.read_text() == before


def test_safe_storage_failure(tmp_path, client):
    (client / "token.json").write_text(json.dumps({"scopes": SCOPES}))
    before = (client / "token.json").read_text()
    with (
        patch(
            "prep_notices.auth.Credentials.from_authorized_user_info",
            return_value=credential(),
        ),
        patch("prep_notices.auth.os.replace", side_effect=OSError("secret content")),
        pytest.raises(NoticeError) as exc,
    ):
        authenticate(tmp_path)
    assert "secret content" not in str(exc.value)
    assert (client / "token.json").read_text() == before
    assert sorted(p.name for p in client.iterdir()) == [
        "credentials.json",
        "token.json",
    ]


def test_denied_consent_and_missing_refresh_token(tmp_path, client):
    credentials = credential(False)
    credentials.refresh_token = None
    (client / "token.json").write_text(json.dumps({"scopes": SCOPES}))
    with (
        patch(
            "prep_notices.auth.Credentials.from_authorized_user_info",
            return_value=credentials,
        ),
        pytest.raises(NoticeError, match="cannot be refreshed"),
    ):
        authenticate(tmp_path)


def test_symlink_credentials_rejected(tmp_path, client):
    target = tmp_path / "outside.json"
    target.write_text("synthetic-secret")
    (client / "credentials.json").unlink()
    (client / "credentials.json").symlink_to(target)
    with pytest.raises(NoticeError, match="symlinks"):
        authenticate(tmp_path)


def test_insufficient_consent(tmp_path, client):
    credentials = credential()
    credentials.granted_scopes = [SCOPES[0]]
    with patch("prep_notices.auth.InstalledAppFlow") as flow:
        flow.from_client_secrets_file.return_value.run_local_server.return_value = (
            credentials
        )
        with pytest.raises(NoticeError, match="did not grant"):
            authenticate(tmp_path)
    assert not (client / "token.json").exists()
