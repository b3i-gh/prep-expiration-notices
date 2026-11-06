import copy
import json
from datetime import UTC, datetime
from io import StringIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import httplib2
import pytest
from googleapiclient.discovery import build
from test_items import cells

from prep_notices.cli import Config
from prep_notices.operation import run


class GoogleBackend:
    credentials = None

    def __init__(self):
        self.calls = []
        self.rows = [cells(), cells("1"), cells("1")]
        self.tasks = [
            {
                "id": "manual",
                "title": "EXPIRATION NOTICE 007: Previous name",
                "due": "2026-12-05T00:00:00.000Z",
                "status": "needsAction",
            },
            {
                "id": "unrelated",
                "title": "EXPIRATION NOTICE 10: Other item",
                "due": "2026-12-05T00:00:00.000Z",
                "status": "completed",
            },
        ]
        self.inserted = []
        self.fail_page = False

    def request(self, uri, method="GET", body=None, headers=None, **kwargs):
        parsed = urlparse(uri)
        query = parse_qs(parsed.query)
        self.calls.append((parsed.netloc, parsed.path, method, query))
        status = 200
        if parsed.netloc == "sheets.googleapis.com":
            assert method == "GET"
            mask = query["fields"][0]
            depth = 0
            for char in mask:
                depth += (char == "(") - (char == ")")
                assert depth >= 0, "Invalid Google partial-response field mask"
            assert depth == 0, "Unbalanced Google partial-response field mask"
            if "ranges" not in query:
                result = {
                    "properties": {"timeZone": "Europe/Rome"},
                    "sheets": [{"properties": {"title": "Items", "sheetId": 0}}],
                }
            else:
                assert query["ranges"] == ["'Items'!A2:F"]
                rows = []
                for values in self.rows:
                    raw = []
                    for cell in values:
                        effective = {}
                        if cell.value is not None:
                            key = (
                                "numberValue"
                                if isinstance(cell.value, (float, int))
                                else "stringValue"
                            )
                            effective[key] = cell.value
                        raw.append(
                            {
                                "formattedValue": cell.display,
                                "effectiveValue": effective,
                                "effectiveFormat": {
                                    "numberFormat": {"type": cell.format_type or "TEXT"}
                                },
                            }
                        )
                    rows.append({"values": raw})
                result = {"sheets": [{"data": [{"startRow": 1, "rowData": rows}]}]}
        else:
            assert parsed.netloc == "tasks.googleapis.com"
            if parsed.path == "/tasks/v1/users/@me/lists":
                assert method == "GET"
                result = {"items": [{"id": "selected", "title": "Notices"}]}
            elif parsed.path == "/tasks/v1/users/@me/lists/selected":
                assert method == "GET"
                result = {"id": "selected", "title": "Notices"}
            else:
                assert parsed.path == "/tasks/v1/lists/selected/tasks"
                if method == "GET":
                    assert query["showCompleted"] == ["true"]
                    assert query["showHidden"] == ["true"]
                    assert query["showAssigned"] == ["true"]
                    assert query["showDeleted"] == ["false"]
                    if "pageToken" not in query:
                        result = {"nextPageToken": "last"}
                    elif self.fail_page:
                        status, result = (
                            403,
                            {"error": {"message": "synthetic-private"}},
                        )
                    else:
                        assert query["pageToken"] == ["last"]
                        result = {"items": copy.deepcopy(self.tasks)}
                else:
                    assert method == "POST"
                    payload = json.loads(body)
                    assert set(payload) == {"title", "notes", "status", "due"}
                    result = {**payload, "id": f"insert-{len(self.inserted)}"}
                    self.tasks.append(copy.deepcopy(result))
                    self.inserted.append(copy.deepcopy(result))
        return (
            httplib2.Response(
                {"status": str(status), "content-type": "application/json"}
            ),
            json.dumps(result).encode(),
        )

    def service(self, name, version, credentials):
        assert name in {"sheets", "tasks"}, "Calendar must not be accessed"
        return build(
            name, version, http=self, cache_discovery=False, static_discovery=True
        )


def invoke(backend, config=None):
    if config is None:
        config = Config("selected")
    output = StringIO()
    with (
        patch("prep_notices.operation.authenticate"),
        patch("prep_notices.operation.service", side_effect=backend.service),
    ):
        code = run(
            config,
            output=output,
            clock=lambda: datetime(2026, 11, 3, 10, tzinfo=UTC),
        )
    return code, output.getvalue()


def test_real_clients_rerun_before_and_after_completion():
    backend = GoogleBackend()
    before = copy.deepcopy(backend.tasks)
    code, text = invoke(backend)
    assert code == 0
    assert "created=1 existing=1" in text
    assert "consolidated_rows=1" in text
    assert backend.inserted[0]["title"] == "EXPIRATION NOTICE 1: Rice"
    assert backend.inserted[0]["due"] == "2026-12-05T00:00:00.000Z"
    assert backend.tasks[:2] == before
    code, text = invoke(backend)
    assert code == 0 and "created=0 existing=2" in text
    backend.tasks[-1].update(status="completed", hidden=True)
    completed = copy.deepcopy(backend.tasks[-1])
    code, text = invoke(backend)
    assert code == 0 and "created=0 existing=2" in text
    assert len(backend.inserted) == 1
    assert backend.tasks[-1] == completed
    assert backend.tasks[:2] == before


def test_changed_and_removed_rows_preserve_old_tasks():
    backend = GoogleBackend()
    assert invoke(backend)[0] == 0
    old = copy.deepcopy(backend.tasks)
    backend.rows = [cells("1", days=4)]
    assert invoke(backend)[0] == 0
    assert backend.tasks[:-1] == old
    assert backend.tasks[-1]["due"] == "2026-12-06T00:00:00.000Z"
    before = copy.deepcopy(backend.tasks)
    backend.rows = []
    assert invoke(backend)[0] == 0
    assert backend.tasks == before


def test_second_page_failure_blocks_writes_with_nonzero_exit():
    backend = GoogleBackend()
    backend.fail_page = True
    code, text = invoke(backend)
    assert code == 1
    assert backend.inserted == []
    assert "HTTP 403" in text
    assert "synthetic-private" not in text
    assert "api_errors=1" in text


def test_real_client_discovery_makes_no_sheet_or_write_requests():
    backend = GoogleBackend()
    assert invoke(backend, Config(None, list_task_lists=True))[0] == 0
    assert len(backend.calls) == 1
    assert backend.calls[0][:3] == (
        "tasks.googleapis.com",
        "/tasks/v1/users/@me/lists",
        "GET",
    )


@pytest.mark.parametrize("reason", [TimeoutError("private"), ValueError("private")])
def test_real_client_uncertain_insert_stops_without_retry(reason):
    backend = GoogleBackend()
    request = backend.request

    def fail_insert(uri, method="GET", **kwargs):
        if method == "POST":
            backend.inserted.append({"uncertain": True})
            raise reason
        return request(uri, method=method, **kwargs)

    backend.request = fail_insert
    code, text = invoke(backend)
    assert code == 1
    assert len(backend.inserted) == 1
    assert "uncertain_notices=1" in text
    assert "created=0" in text
    assert "private" not in text
