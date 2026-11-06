from unittest.mock import Mock

import httplib2
import pytest
from googleapiclient.errors import HttpError
from test_items import cells

from prep_notices.errors import ApiError, UncertainInsert
from prep_notices.google_api import Tasks
from prep_notices.items import parse_item


def response(value):
    request = Mock()
    request.execute.return_value = value
    return request


def test_discovery_all_pages_including_empty():
    api = Mock()
    api.tasklists.return_value.list.side_effect = [
        response({"nextPageToken": "next"}),
        response({"items": [{"id": "test", "title": "Expiration Notices"}]}),
    ]
    assert Tasks(api).lists() == [{"id": "test", "title": "Expiration Notices"}]
    assert api.tasklists.return_value.list.call_args.kwargs["pageToken"] == "next"
    api.tasks.assert_not_called()
    api.tasklists.return_value.insert.assert_not_called()


def test_discovery_failure_not_partial_success():
    api = Mock()
    api.tasklists.return_value.list.side_effect = [
        response(
            {"items": [{"id": "first", "title": "First"}], "nextPageToken": "next"}
        ),
        Mock(execute=Mock(side_effect=TimeoutError("secret transport"))),
    ]
    with pytest.raises(ApiError, match="Discover task lists") as exc:
        Tasks(api).lists()
    assert "secret" not in str(exc.value)


def test_selected_list_no_fallback():
    api = Mock()
    api.tasklists.return_value.get.return_value = response({"id": "test"})
    Tasks(api).validate_list("test")
    api.tasklists.return_value.get.assert_called_once_with(tasklist="test")
    api.tasklists.return_value.get.return_value = response({"id": "other"})
    with pytest.raises(ApiError, match="mismatched"):
        Tasks(api).validate_list("test")


def test_snapshot_completed_hidden_and_pagination():
    api = Mock()
    task = {
        "title": "EXPIRATION NOTICE 007: Old name",
        "due": "2026-12-05T00:00:00.000Z",
        "status": "completed",
        "hidden": True,
    }
    api.tasks.return_value.list.side_effect = [
        response({"nextPageToken": "next"}),
        response({"items": [task]}),
    ]
    snapshot = Tasks(api).snapshot("selected")
    assert snapshot.contains(parse_item(cells()))
    options = api.tasks.return_value.list.call_args.kwargs
    assert options == dict(
        tasklist="selected",
        maxResults=100,
        showCompleted=True,
        showHidden=True,
        showDeleted=False,
        showAssigned=True,
        pageToken="next",
    )
    api.tasks.return_value.insert.assert_not_called()


@pytest.mark.parametrize(
    ("task", "matches"),
    [
        ({"title": "EXPIRATION NOTICE 007: Old", "due": "2026-12-05T00:00:00Z"}, True),
        (
            {"title": "EXPIRATION NOTICE 0070: Old", "due": "2026-12-05T00:00:00Z"},
            False,
        ),
        ({"title": "expiration notice 007: Old", "due": "2026-12-05T00:00:00Z"}, False),
        ({"title": "EXPIRATION NOTICE 007: Old", "due": "2026-12-04T00:00:00Z"}, False),
        ({"title": "EXPIRATION NOTICE 007: Old"}, False),
        (
            {
                "title": "EXPIRATION NOTICE 007: Old",
                "due": "2026-12-05T00:00:00Z",
                "deleted": True,
            },
            False,
        ),
    ],
)
def test_matching_rules(task, matches):
    api = Mock()
    api.tasks.return_value.list.return_value = response({"items": [task]})
    assert (
        Tasks(api).snapshot("only-this-list").contains(parse_item(cells())) is matches
    )
    assert api.tasks.return_value.list.call_args.kwargs["tasklist"] == "only-this-list"


def test_insert_payload_and_confirmed_snapshot_update():
    api = Mock()
    api.tasks.return_value.list.return_value = response({})
    api.tasks.return_value.insert.return_value = response({"id": "created"})
    tasks = Tasks(api)
    snapshot = tasks.snapshot("selected")
    item = parse_item(cells())
    assert not snapshot.contains(item)
    tasks.insert("selected", item)
    api.tasks.return_value.insert.assert_called_once_with(
        tasklist="selected", body=item.payload()
    )
    api.tasks.return_value.insert.return_value.execute.assert_called_once_with(
        num_retries=0
    )
    snapshot.remember(item)
    assert snapshot.contains(item)


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (TimeoutError("secret response"), UncertainInsert),
        (
            HttpError(httplib2.Response({"status": "503"}), b"secret response"),
            UncertainInsert,
        ),
        (HttpError(httplib2.Response({"status": "403"}), b"secret response"), ApiError),
    ],
)
def test_insert_failures_not_retried(failure, expected):
    api = Mock()
    api.tasks.return_value.insert.return_value.execute.side_effect = failure
    with pytest.raises(expected) as exc:
        Tasks(api).insert("selected", parse_item(cells()))
    assert "secret response" not in str(exc.value)
    api.tasks.return_value.insert.return_value.execute.assert_called_once_with(
        num_retries=0
    )


def test_snapshot_page_failure_and_malformed_date():
    api = Mock()
    api.tasks.return_value.list.side_effect = [
        response({"nextPageToken": "next"}),
        Mock(execute=Mock(side_effect=TimeoutError("private"))),
    ]
    with pytest.raises(ApiError):
        Tasks(api).snapshot("selected")
    api.tasks.return_value.insert.assert_not_called()
    api.tasks.return_value.list.side_effect = None
    api.tasks.return_value.list.return_value = response(
        {"items": [{"title": "Notice", "due": "2026-12-99T00:00:00Z"}]}
    )
    with pytest.raises(ApiError, match="invalid scheduled date"):
        Tasks(api).snapshot("selected")
