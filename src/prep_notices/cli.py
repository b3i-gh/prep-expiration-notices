import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPREADSHEET = "1kWkRswlbvOWXcmwqWnyssDSIvwoIIKo3J3ZXwX8bnqI"


@dataclass(frozen=True)
class Config:
    task_list_id: str | None
    spreadsheet_id: str = DEFAULT_SPREADSHEET
    sheet_title: str | None = None
    list_task_lists: bool = False


def nonblank(value: str) -> str:
    if not value.strip():
        raise argparse.ArgumentTypeError("must not be blank")
    return value.strip()


def task_list_id(value: str) -> str:
    value = nonblank(value)
    if value == "@default" or "://" in value or "@" in value:
        raise argparse.ArgumentTypeError(
            "use an explicit task-list ID from --list-task-lists, not a calendar ID/URL"
        )
    return value


def parse_args(argv: Sequence[str] | None = None) -> Config:
    parser = argparse.ArgumentParser(
        description=(
            "Create missing date-only Google Tasks from expiration rows. "
            "This does not configure or guarantee alerts."
        )
    )
    parser.add_argument("--task-list-id", type=task_list_id)
    parser.add_argument("--spreadsheet-id", type=nonblank)
    parser.add_argument("--sheet-title", type=nonblank)
    parser.add_argument(
        "--list-task-lists",
        action="store_true",
        help="list existing titles/IDs; no writes",
    )
    args = parser.parse_args(argv)
    if args.list_task_lists:
        if any((args.task_list_id, args.spreadsheet_id, args.sheet_title)):
            parser.error("--list-task-lists cannot be combined with resource options")
    elif not args.task_list_id:
        parser.error("--task-list-id is required; discover IDs with --list-task-lists")
    return Config(
        args.task_list_id,
        args.spreadsheet_id or DEFAULT_SPREADSHEET,
        args.sheet_title,
        args.list_task_lists,
    )


def main(argv: Sequence[str] | None = None) -> int:
    config = parse_args(argv)
    from prep_notices.operation import run

    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
