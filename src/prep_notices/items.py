import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Cell:
    display: str = ""
    value: object = None
    format_type: str | None = None
    error: bool = False


@dataclass(frozen=True)
class Row:
    number: int
    cells: tuple[Cell, ...]


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    quantity: str
    expiration: date
    notice_days: int
    notice_date: date

    @property
    def prefix(self) -> str:
        return f"EXPIRATION NOTICE {self.id}:"

    @property
    def title(self) -> str:
        return f"{self.prefix} {self.name}"

    @property
    def notes(self) -> str:
        return (
            f"{self.name} (quantity: {self.quantity}) will expire on "
            f"{self.expiration.isoformat()}."
        )

    def payload(self) -> dict[str, str]:
        return {
            "title": self.title,
            "notes": self.notes,
            "due": f"{self.notice_date.isoformat()}T00:00:00.000Z",
            "status": "needsAction",
        }


@dataclass(frozen=True)
class Outcome:
    rows: tuple[int, ...]
    status: str
    detail: str


@dataclass(frozen=True)
class Candidate:
    item: Item
    rows: tuple[int, ...]


@dataclass
class Plan:
    candidates: list[Candidate] = field(default_factory=list)
    outcomes: list[Outcome] = field(default_factory=list)


def integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite integer number")
    if isinstance(value, float) and (
        not math.isfinite(value) or not value.is_integer()
    ):
        raise ValueError(f"{label} must be a finite integer number")
    return int(value)


def parse_item(cells: tuple[Cell, ...]) -> Item:
    padded = (*cells[:6], *(Cell() for _ in range(max(0, 6 - len(cells)))))
    identity, name, quantity, _, expiration, days = padded
    for label, cell in (
        ("ID", identity),
        ("name", name),
        ("quantity", quantity),
        ("expiration date", expiration),
        ("notice days", days),
    ):
        if cell.error:
            raise ValueError(f"{label} contains a Sheets error")
    if not name.display.strip() or not quantity.display.strip():
        raise ValueError("name and quantity are required")
    if expiration.format_type not in {"DATE", "DATE_TIME"}:
        raise ValueError("expiration must be a native Sheets date cell")
    serial = integer(expiration.value, "expiration date")
    notice_days = integer(days.value, "notice days")
    if notice_days < 0:
        raise ValueError("notice days must not be negative")
    try:
        expires = date(1899, 12, 30) + timedelta(days=serial)
        notice_date = expires - timedelta(days=notice_days)
    except OverflowError as exc:
        raise ValueError("expiration/notice date arithmetic is out of range") from exc
    item = Item(
        identity.display.strip(),
        name.display.strip(),
        quantity.display.strip(),
        expires,
        notice_days,
        notice_date,
    )
    if len(item.title) > 1024 or len(item.notes) > 8192:
        raise ValueError("generated task exceeds title (1024) or notes (8192) limit")
    return item


def prepare(rows: list[Row], today: date) -> Plan:
    plan = Plan()
    groups: dict[str, list[Row]] = {}
    for row in rows:
        identity = row.cells[0] if row.cells else Cell()
        if identity.error:
            plan.outcomes.append(
                Outcome((row.number,), "invalid", "ID contains a Sheets error")
            )
        elif not identity.display.strip():
            plan.outcomes.append(Outcome((row.number,), "blank", "blank ID ignored"))
        else:
            groups.setdefault(identity.display.strip(), []).append(row)
    for identity, group in groups.items():
        numbers = tuple(row.number for row in group)
        items = []
        errors = []
        for row in group:
            try:
                items.append(parse_item(row.cells))
            except ValueError as exc:
                errors.append(f"row {row.number}: {exc}")
        if errors:
            plan.outcomes.append(
                Outcome(
                    numbers,
                    "invalid",
                    f"ID {identity!r} excluded: " + "; ".join(errors),
                )
            )
            continue
        if any(item != items[0] for item in items[1:]):
            plan.outcomes.append(
                Outcome(
                    numbers, "invalid", f"conflicting notice data for ID {identity!r}"
                )
            )
            continue
        item = items[0]
        if len(group) > 1:
            plan.outcomes.append(
                Outcome(numbers[1:], "consolidated", f"identical to row {numbers[0]}")
            )
        if item.notice_date < today:
            plan.outcomes.append(
                Outcome(
                    numbers,
                    "past",
                    f"ID {identity!r}: {item.notice_date} is in the past",
                )
            )
        else:
            plan.candidates.append(Candidate(item, numbers))
    return plan


def local_today(now: datetime, zone: ZoneInfo) -> date:
    if now.tzinfo is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return now.astimezone(zone).date()
