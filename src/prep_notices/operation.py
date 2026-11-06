import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from prep_notices.auth import authenticate
from prep_notices.cli import PROJECT_ROOT, Config
from prep_notices.errors import ApiError, NoticeError, UncertainInsert
from prep_notices.google_api import Tasks, service
from prep_notices.items import Outcome, local_today, prepare
from prep_notices.sheets import Sheets


@dataclass
class Report:
    output: TextIO
    outcomes: list[Outcome] = field(default_factory=list)
    created: int = 0
    existing: int = 0
    api_errors: int = 0
    errors: int = 0
    uncertain: int = 0
    not_processed: int = 0

    def row(self, outcome: Outcome) -> None:
        self.outcomes.append(outcome)
        print(
            f"{outcome.status}: rows {','.join(map(str, outcome.rows))}: "
            f"{outcome.detail}",
            file=self.output,
        )

    def summary(self) -> None:
        def row_count(status: str) -> int:
            return sum(len(o.rows) for o in self.outcomes if o.status == status)

        past = sum(o.status == "past" for o in self.outcomes)
        print(
            f"Summary: created={self.created} existing={self.existing} "
            f"past_notices={past} blank_id_rows={row_count('blank')} "
            f"consolidated_rows={row_count('consolidated')} "
            f"invalid_rows={row_count('invalid')} api_errors={self.api_errors} "
            f"errors={self.errors} uncertain_notices={self.uncertain} "
            f"not_processed_notices={self.not_processed}",
            file=self.output,
        )


def process(
    config: Config,
    tasks: Tasks,
    sheets: Sheets | None,
    report: Report,
    clock: Callable[[], datetime],
) -> int:
    if config.list_task_lists:
        lists = tasks.lists()
        for task_list in lists:
            print(
                f"{json.dumps(task_list['title'])}\t{json.dumps(task_list['id'])}",
                file=report.output,
            )
        print(f"Task lists: {len(lists)} (read-only discovery)", file=report.output)
        return 0
    if sheets is None or config.task_list_id is None:
        raise NoticeError("Notice creation requires Sheets access and a task-list ID.")
    data = sheets.read(config.spreadsheet_id, config.sheet_title)
    today = local_today(clock(), data.zone)
    print(
        f"Today: {today} (spreadsheet time zone: {data.zone.key})", file=report.output
    )
    plan = prepare(data.rows, today)
    for outcome in plan.outcomes:
        report.row(outcome)
    report.errors += sum(o.status == "invalid" for o in plan.outcomes)
    report.not_processed = len(plan.candidates)
    tasks.validate_list(config.task_list_id)
    if plan.candidates:
        snapshot = tasks.snapshot(config.task_list_id)
        for candidate in plan.candidates:
            item = candidate.item
            detail = f"ID {item.id!r} on {item.notice_date}"
            if snapshot.contains(item):
                report.existing += 1
                report.row(Outcome(candidate.rows, "existing", detail))
            else:
                try:
                    tasks.insert(config.task_list_id, item)
                except UncertainInsert:
                    report.uncertain += 1
                    report.not_processed -= 1
                    print(
                        f"UNCERTAIN: {detail}; do not blindly retry insertion. "
                        "A manual rerun will recheck the selected task list.",
                        file=report.output,
                    )
                    raise
                except ApiError:
                    print(
                        f"FAILED: rows {candidate.rows}: {detail}; "
                        "later writes stopped.",
                        file=report.output,
                    )
                    raise
                report.created += 1
                snapshot.remember(item)
                report.row(Outcome(candidate.rows, "created", detail))
            report.not_processed -= 1
    return 1 if report.errors else 0


def run(
    config: Config,
    *,
    root: Path = PROJECT_ROOT,
    output: TextIO | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    report = Report(output if output is not None else sys.stdout)
    try:
        credentials = authenticate(root)
        tasks = Tasks(service("tasks", "v1", credentials))
        sheets = (
            None
            if config.list_task_lists
            else Sheets(service("sheets", "v4", credentials))
        )
        return process(config, tasks, sheets, report, clock)
    except NoticeError as exc:
        report.errors += 1
        report.api_errors += isinstance(exc, ApiError)
        print(f"ERROR: {exc}", file=report.output)
        return 1
    finally:
        if not config.list_task_lists:
            report.summary()
