import subprocess
from pathlib import Path

import pytest

from prep_notices.cli import DEFAULT_SPREADSHEET, PROJECT_ROOT, parse_args


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--task-list-id", ""],
        ["--task-list-id", "@default"],
        ["--task-list-id", "person@example.com"],
        ["--calendar-id", "old"],
        ["--list-task-lists", "--task-list-id", "list"],
        ["--list-task-lists", "--spreadsheet-id", "sheet"],
        ["--list-task-lists", "--sheet-title", "Items"],
    ],
)
def test_invalid_configuration(args):
    with pytest.raises(SystemExit) as exc:
        parse_args(args)
    assert exc.value.code == 2


def test_resource_overrides():
    config = parse_args(
        [
            "--task-list-id",
            "test-list",
            "--spreadsheet-id",
            "test",
            "--sheet-title",
            "Items",
        ]
    )
    assert (config.task_list_id, config.spreadsheet_id, config.sheet_title) == (
        "test-list",
        "test",
        "Items",
    )
    assert parse_args(["--task-list-id", "list"]).spreadsheet_id == DEFAULT_SPREADSHEET
    assert parse_args(["--list-task-lists"]).list_task_lists


def test_help_outside_project(tmp_path):
    executable = PROJECT_ROOT / ".venv/bin/prep-notices"
    result = subprocess.run(
        [str(executable), "--help"], cwd=tmp_path, text=True, capture_output=True
    )
    assert result.returncode == 0
    assert "--list-task-lists" in result.stdout
    assert list(tmp_path.iterdir()) == []
    assert PROJECT_ROOT == Path(__file__).resolve().parents[1]
