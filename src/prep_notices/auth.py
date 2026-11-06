import json
import os
import stat
import tempfile
import webbrowser
from pathlib import Path

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from oauthlib.oauth2 import OAuth2Error
from requests.exceptions import RequestException

from prep_notices.errors import NoticeError

SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/tasks",
)
RECOVERY = (
    "Check .secrets/credentials.json (Desktop OAuth client), consent/test-user "
    "settings, and network access. For corrupt/revoked/old-scope tokens, revoke "
    "the old grant if needed, manually remove .secrets/token.json, and authorize again."
)


def private_file(path: Path) -> None:
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise NoticeError("Credential paths must be regular files, not symlinks.")
    path.chmod(0o600)


def save_token(path: Path, credentials: Credentials) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            os.fchmod(stream.fileno(), 0o600)
            stream.write(credentials.to_json())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def authenticate(root: Path) -> Credentials:
    directory = root / ".secrets"
    client = directory / "credentials.json"
    token = directory / "token.json"
    try:
        if directory.is_symlink():
            raise NoticeError(".secrets must be a local directory, not a symlink.")
        directory.mkdir(mode=0o700, exist_ok=True)
        directory.chmod(0o700)
        private_file(client)
        credentials = None
        if token.exists() or token.is_symlink():
            private_file(token)
            info = json.loads(token.read_text(encoding="utf-8"))
            if not isinstance(info, dict) or set(info.get("scopes", [])) != set(SCOPES):
                raise NoticeError("OAuth scope mismatch. " + RECOVERY)
            credentials = Credentials.from_authorized_user_info(info)
        if credentials is None:
            flow = InstalledAppFlow.from_client_secrets_file(str(client), SCOPES)
            credentials = flow.run_local_server(
                host="localhost",
                bind_addr="127.0.0.1",
                port=0,
                open_browser=False,
                timeout_seconds=180,
                authorization_prompt_message=(
                    "Open this Google authorization URL in your browser "
                    "(Windows browser is OK in WSL):\n{url}"
                ),
                success_message="Authorization received. You can close this tab.",
                access_type="offline",
                prompt="consent",
            )
        elif not credentials.valid:
            if not credentials.refresh_token:
                raise NoticeError("Saved OAuth token cannot be refreshed. " + RECOVERY)
            credentials.refresh(Request())
        granted = credentials.granted_scopes or credentials.scopes
        if not credentials.valid or set(granted or ()) != set(SCOPES):
            raise NoticeError(
                "OAuth consent did not grant the required scopes. " + RECOVERY
            )
        save_token(token, credentials)
        return credentials
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        GoogleAuthError,
        OAuth2Error,
        webbrowser.Error,
        RequestException,
    ) as exc:
        raise NoticeError(
            "OAuth setup, refresh, or safe token storage failed. " + RECOVERY
        ) from exc
