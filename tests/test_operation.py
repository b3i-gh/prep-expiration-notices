from datetime import UTC, date, datetime
from io import StringIO
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pytest
from test_items import cells

from prep_notices.cli import Config, main
from prep_notices.errors import ApiError, NoticeError, UncertainInsert
from prep_notices.google_api import Snapshot
from prep_notices.items import Row
from prep_notices.operation import Report, process, run
from prep_notices.sheets import SheetData


def test_discovery_does_not_read_sheets_or_write():
    tasks, sheets = Mock(), Mock()
    tasks.lists.return_value = [{"id": "test", "title": "Expiration Notices"}]
    output = StringIO()
    assert (
        process(
            Config(None, list_task_lists=True), tasks, sheets, Report(output), Mock()
        )
        == 0
    )
    assert '"Expiration Notices"\t"test"' in output.getvalue()
    sheets.read.assert_not_called()
    tasks.validate_list.assert_not_called()
    tasks.snapshot.assert_not_called()
    tasks.insert.assert_not_called()


def test_run_discovery_does_not_build_sheets_service():
    output = StringIO()
    with (
        patch("prep_notices.operation.authenticate"),
        patch("prep_notices.operation.service") as service,
        patch("prep_notices.operation.Tasks") as tasks,
    ):
        tasks.return_value.lists.return_value = []
        assert run(Config(None, list_task_lists=True), output=output) == 0
    assert service.call_args.args[:2] == ("tasks", "v1")
    assert service.call_count == 1


def setup_process(rows):
    tasks, sheets = Mock(), Mock()
    sheets.read.return_value = SheetData(ZoneInfo("Europe/Rome"), rows)
    tasks.snapshot.return_value = Snapshot()
    report = Report(StringIO())
    clock = Mock(return_value=datetime(2026, 11, 3, 10, tzinfo=UTC))
    return tasks, sheets, report, clock


def test_valid_rows_continue_after_invalid_and_summary():
    rows = [
        Row(2, cells()),
        Row(3, cells("bad", days=-1)),
        Row(4, cells("")),
        Row(5, cells()),
        Row(6, cells("past", expires=datetime(2026, 1, 1).date(), days=0)),
    ]
    tasks, sheets, report, clock = setup_process(rows)
    assert process(Config("selected"), tasks, sheets, report, clock) == 1
    assert tasks.insert.call_count == 1
    assert report.created == 1
    clock.assert_called_once_with()
    report.summary()
    text = report.output.getvalue()
    assert "invalid: rows 3" in text
    assert "created=1 existing=0" in text
    assert "blank_id_rows=1 consolidated_rows=1 invalid_rows=1" in text
    assert "past_notices=1" in text


@pytest.mark.parametrize(
    "failure", [ApiError("permission denied"), UncertainInsert("timeout")]
)
def test_partial_writes_stop_and_preserve_counts(failure):
    tasks, sheets, report, clock = setup_process(
        [Row(i + 2, cells(str(i))) for i in range(3)]
    )
    tasks.insert.side_effect = [None, failure]
    with pytest.raises(type(failure)):
        process(Config("selected"), tasks, sheets, report, clock)
    assert tasks.insert.call_count == 2
    assert report.created == 1
    assert report.uncertain == isinstance(failure, UncertainInsert)
    assert report.not_processed == (1 if isinstance(failure, UncertainInsert) else 2)


def test_lookup_failure_prevents_all_writes():
    tasks, sheets, report, clock = setup_process([Row(2, cells())])
    tasks.snapshot.side_effect = ApiError("page failed")
    with pytest.raises(ApiError):
        process(Config("selected"), tasks, sheets, report, clock)
    tasks.insert.assert_not_called()


@pytest.mark.parametrize("rows", [[], [Row(2, cells(""))]])
def test_empty_or_blank_only_succeeds(rows):
    tasks, sheets, report, clock = setup_process(rows)
    assert process(Config("selected"), tasks, sheets, report, clock) == 0
    tasks.insert.assert_not_called()


def test_errors_safe_exit_status_and_summary():
    output = StringIO()
    with patch(
        "prep_notices.operation.authenticate", side_effect=NoticeError("Fix OAuth")
    ):
        assert run(Config("selected"), output=output) == 1
    assert "ERROR: Fix OAuth" in output.getvalue()
    assert "created=0" in output.getvalue()


def test_cli_dispatches_config_and_failure_status():
    with patch("prep_notices.operation.run", return_value=1) as run_mock:
        assert main(["--task-list-id", "selected"]) == 1
    assert run_mock.call_args.args[0].task_list_id == "selected"


def test_existing_past_and_conflicting_outcome_counts():
    tasks, sheets, report, clock = setup_process(
        [
            Row(2, cells()),
            Row(3, cells("past", expires=date(2026, 1, 1), days=0)),
            Row(4, cells("conflict", quantity="1")),
            Row(5, cells("conflict", quantity="2")),
        ]
    )
    tasks.snapshot.return_value.titles[date(2026, 12, 5)] = [
        "EXPIRATION NOTICE 007: old name"
    ]
    assert process(Config("selected"), tasks, sheets, report, clock) == 1
    tasks.insert.assert_not_called()
    report.summary()
    text = report.output.getvalue()
    assert "created=0 existing=1 past_notices=1" in text
    assert "invalid_rows=2" in text
    assert "invalid: rows 4,5" in text


def test_runtime_paths_do_not_follow_cwd(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    caller = tmp_path / "caller"
    caller.mkdir()
    monkeypatch.chdir(caller)
    assert run(Config("selected"), root=root, output=StringIO()) == 1
    assert (root / ".secrets").is_dir()
    assert list(caller.iterdir()) == []


def test_run_api_failure_status_and_uncertain_reporting():
    output = StringIO()
    tasks, sheets, _, clock = setup_process([Row(2, cells())])
    tasks.insert.side_effect = UncertainInsert("transport failed")
    with (
        patch("prep_notices.operation.authenticate"),
        patch("prep_notices.operation.service"),
        patch("prep_notices.operation.Tasks", return_value=tasks),
        patch("prep_notices.operation.Sheets", return_value=sheets),
    ):
        assert run(Config("selected"), output=output, clock=clock) == 1
    text = output.getvalue()
    assert "ID '007' on 2026-12-05" in text
    assert "api_errors=1" in text
    assert "uncertain_notices=1" in text
    assert "created=0" in text
