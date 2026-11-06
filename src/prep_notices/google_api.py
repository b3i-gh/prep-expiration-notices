import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime

import httplib2
from google.auth.exceptions import GoogleAuthError
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from googleapiclient.http import HttpRequest

from prep_notices.errors import ApiError, UncertainInsert
from prep_notices.items import Item


def service(api: str, version: str, credentials: Credentials) -> Resource:
    return build(
        api,
        version,
        http=AuthorizedHttp(
            credentials,
            http=httplib2.Http(timeout=30),
            max_refresh_attempts=0,
        ),
        cache_discovery=False,
        static_discovery=True,
    )


def execute(request: HttpRequest, operation: str, *, insert: bool = False) -> dict:
    try:
        result = request.execute(num_retries=0)
    except HttpError as exc:
        status = exc.resp.status
        error = (
            UncertainInsert if insert and (status >= 500 or status == 408) else ApiError
        )
        raise error(
            f"{operation}: HTTP {status}. Check API enablement, account access, "
            "resource ID, and quota; rerun manually after resolving the error."
        ) from exc
    except (OSError, httplib2.HttpLib2Error, GoogleAuthError) as exc:
        error = UncertainInsert if insert else ApiError
        raise error(
            f"{operation}: transport/authentication failure. Check connectivity "
            "and OAuth access; rerun manually to recheck remote state."
        ) from exc
    except ValueError as exc:
        error = UncertainInsert if insert else ApiError
        raise error(
            f"{operation}: invalid response; rerun to recheck remote state."
        ) from exc
    if not isinstance(result, dict):
        error = UncertainInsert if insert else ApiError
        raise error(f"{operation}: unexpected API response; rerun to recheck state.")
    return result


def pages(resource: Resource, operation: str, **kwargs) -> Iterator[dict]:
    token = None
    seen = set()
    while True:
        response = execute(resource.list(**kwargs, pageToken=token), operation)
        items = response.get("items", [])
        if not isinstance(items, list) or not all(
            isinstance(item, dict) for item in items
        ):
            raise ApiError(f"{operation}: invalid items in API response.")
        yield from items
        token = response.get("nextPageToken")
        if not token:
            return
        if not isinstance(token, str) or token in seen:
            raise ApiError(f"{operation}: invalid or repeated pagination token.")
        seen.add(token)


class Tasks:
    def __init__(self, api: Resource):
        self.api = api

    def lists(self) -> list[dict]:
        result = list(
            pages(self.api.tasklists(), "Discover task lists", maxResults=1000)
        )
        if any(
            not item.get("id") or not isinstance(item.get("title"), str)
            for item in result
        ):
            raise ApiError("Discover task lists: incomplete list metadata.")
        return result

    def validate_list(self, list_id: str) -> None:
        result = execute(
            self.api.tasklists().get(tasklist=list_id), "Read selected task list"
        )
        if result.get("id") != list_id:
            raise ApiError(
                "Read selected task list: mismatched list ID; no fallback allowed."
            )

    def snapshot(self, list_id: str) -> "Snapshot":
        snapshot = Snapshot()
        for task in pages(
            self.api.tasks(),
            "Read existing tasks",
            tasklist=list_id,
            maxResults=100,
            showCompleted=True,
            showHidden=True,
            showDeleted=False,
            showAssigned=True,
        ):
            if task.get("deleted"):
                continue
            title = task.get("title", "")
            due = task.get("due")
            if not isinstance(title, str):
                raise ApiError("Read existing tasks: invalid title.")
            if due is None:
                continue
            if not isinstance(due, str) or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
                due,
            ):
                raise ApiError("Read existing tasks: invalid scheduled date.")
            try:
                day = datetime.fromisoformat(due.replace("Z", "+00:00")).date()
            except ValueError as exc:
                raise ApiError("Read existing tasks: invalid scheduled date.") from exc
            snapshot.titles.setdefault(day, []).append(title)
        return snapshot

    def insert(self, list_id: str, item: Item) -> None:
        result = execute(
            self.api.tasks().insert(tasklist=list_id, body=item.payload()),
            "Insert notice task",
            insert=True,
        )
        if not result.get("id"):
            raise UncertainInsert(
                "Insert notice task: no confirmation ID; "
                "rerun manually to recheck state."
            )


@dataclass
class Snapshot:
    titles: dict[date, list[str]] = field(default_factory=dict)

    def contains(self, item: Item) -> bool:
        return any(
            title.startswith(item.prefix)
            for title in self.titles.get(item.notice_date, [])
        )

    def remember(self, item: Item) -> None:
        self.titles.setdefault(item.notice_date, []).append(item.title)
