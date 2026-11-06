from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from prep_notices.items import Cell, Row, local_today, parse_item, prepare


def cells(
    identity="007", name="Rice", quantity="3", expires=date(2026, 12, 10), days=5
):
    return (
        Cell(identity, identity),
        Cell(name, name),
        Cell(quantity, quantity),
        Cell(),
        Cell(expires.isoformat(), (expires - date(1899, 12, 30)).days, "DATE"),
        Cell(str(days), days),
    )


def change(values, index, value):
    result = list(values)
    result[index] = value
    return tuple(result)


def test_native_date_and_exact_task_payload():
    item = parse_item(cells())
    assert item.payload() == {
        "title": "EXPIRATION NOTICE 007: Rice",
        "notes": "Rice (quantity: 3) will expire on 2026-12-10.",
        "due": "2026-12-05T00:00:00.000Z",
        "status": "needsAction",
    }


@pytest.mark.parametrize("days", [-1, 1.5, True, "5", float("inf"), float("nan")])
def test_invalid_notice_days(days):
    with pytest.raises(ValueError, match="notice days"):
        parse_item(cells(days=days))


@pytest.mark.parametrize(
    "cell",
    [
        Cell("10/12/2026", "10/12/2026"),
        Cell("date", 46000.5, "DATE_TIME"),
        Cell("date", True, "DATE"),
        Cell("date", 10**30, "DATE"),
        Cell("date", float("nan"), "DATE"),
        Cell("#ERROR!", error=True),
        Cell(),
    ],
)
def test_invalid_dates(cell):
    with pytest.raises(ValueError):
        parse_item(change(cells(), 4, cell))


@pytest.mark.parametrize("index", [1, 2, 4, 5])
def test_missing_required_cells(index):
    with pytest.raises(ValueError):
        parse_item(change(cells(), index, Cell()))


def test_missing_trailing_cells():
    with pytest.raises(ValueError):
        parse_item(cells()[:3])


def test_blank_zero_and_leading_zero_identity():
    rows = [
        Row(i + 2, cells(identity=value))
        for i, value in enumerate([" ", "0", "001", "1"])
    ]
    plan = prepare(rows, date(2026, 11, 3))
    assert [c.item.id for c in plan.candidates] == ["0", "001", "1"]
    assert plan.outcomes[0].status == "blank"


def test_displayed_values_and_informational_acquisition():
    values = cells(identity=" 001 ", name=" Rice ", quantity=" 1,5 kg ")
    values = change(values, 3, Cell("#ERROR!", error=True))
    item = parse_item(values)
    assert (item.id, item.name, item.quantity) == ("001", "Rice", "1,5 kg")


def test_consolidation_conflicts_and_invalid_group():
    rows = [
        Row(2, cells("same")),
        Row(3, change(cells("same"), 3, Cell("different acquisition"))),
        Row(4, cells("conflict", quantity="1")),
        Row(5, cells("conflict", quantity="2")),
        Row(6, cells("invalid")),
        Row(7, cells("invalid", days=-1)),
        Row(8, cells("valid")),
    ]
    plan = prepare(rows, date(2026, 11, 3))
    assert [candidate.item.id for candidate in plan.candidates] == ["same", "valid"]
    assert [(o.rows, o.status) for o in plan.outcomes] == [
        ((3,), "consolidated"),
        ((4, 5), "invalid"),
        ((6, 7), "invalid"),
    ]


@pytest.mark.parametrize(
    ("expires", "days", "expected"),
    [
        (date(2027, 1, 3), 5, date(2026, 12, 29)),
        (date(2028, 3, 1), 1, date(2028, 2, 29)),
        (date(2026, 12, 10), 0, date(2026, 12, 10)),
    ],
)
def test_date_arithmetic(expires, days, expected):
    assert parse_item(cells(expires=expires, days=days)).notice_date == expected


def test_arithmetic_underflow():
    with pytest.raises(ValueError, match="out of range"):
        parse_item(cells(expires=date.min, days=1))


def test_past_today_and_spreadsheet_zone():
    now = datetime(2026, 11, 3, 0, 30, tzinfo=UTC)
    today = local_today(now, ZoneInfo("America/Los_Angeles"))
    assert today == date(2026, 11, 2)
    rows = [
        Row(2, cells("past", expires=date(2026, 11, 1), days=0)),
        Row(3, cells("today", expires=today, days=0)),
    ]
    plan = prepare(rows, today)
    assert [c.item.id for c in plan.candidates] == ["today"]
    assert plan.outcomes[0].status == "past"


@pytest.mark.parametrize(("field", "limit"), [("name", 1024), ("quantity", 8192)])
def test_text_limits(field, limit):
    baseline = cells()
    index = 1 if field == "name" else 2
    item = parse_item(baseline)
    current = len(item.title if field == "name" else item.notes)
    text = "x" * (limit - current + len(baseline[index].display))
    values = change(baseline, index, Cell(text, text))
    parse_item(values)
    with pytest.raises(ValueError, match="limit"):
        parse_item(change(values, index, Cell(text + "x", text + "x")))
