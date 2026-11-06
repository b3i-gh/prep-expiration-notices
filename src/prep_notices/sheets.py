from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from googleapiclient.discovery import Resource

from prep_notices.errors import ApiError, NoticeError
from prep_notices.google_api import execute
from prep_notices.items import Cell, Row


@dataclass(frozen=True)
class SheetData:
    zone: ZoneInfo
    rows: list[Row]


class Sheets:
    def __init__(self, api: Resource):
        self.api = api

    def read(self, spreadsheet_id: str, title: str | None = None) -> SheetData:
        resource = self.api.spreadsheets()
        metadata = execute(
            resource.get(
                spreadsheetId=spreadsheet_id,
                fields="properties(timeZone),sheets(properties(title,sheetId))",
            ),
            "Read spreadsheet metadata",
        )
        zone_name = metadata.get("properties", {}).get("timeZone")
        try:
            if not isinstance(zone_name, str) or not zone_name:
                raise ValueError("missing spreadsheet time zone")
            zone = ZoneInfo(zone_name)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise NoticeError(
                "Spreadsheet time zone is missing or invalid; fix the Sheet settings."
            ) from exc
        sheets = metadata.get("sheets", [])
        if title is None:
            if len(sheets) != 1:
                raise NoticeError(
                    "Select an exact --sheet-title when the file has multiple sheets."
                )
            title = sheets[0].get("properties", {}).get("title")
        if not isinstance(title, str) or not any(
            sheet.get("properties", {}).get("title") == title for sheet in sheets
        ):
            raise NoticeError("Selected sheet title does not exist in the spreadsheet.")
        quoted = "'" + title.replace("'", "''") + "'"
        result = execute(
            resource.get(
                spreadsheetId=spreadsheet_id,
                ranges=[f"{quoted}!A2:F"],
                fields=(
                    "sheets(data(startRow,startColumn,rowData(values("
                    "effectiveValue,formattedValue,effectiveFormat(numberFormat(type))))))"
                ),
            ),
            "Read item rows",
        )
        rows = []
        for sheet in result.get("sheets", []):
            for block in sheet.get("data", []):
                start = block.get("startRow", 0)
                column = block.get("startColumn", 0)
                for offset, raw_row in enumerate(block.get("rowData", [])):
                    if start + offset == 0:
                        continue
                    cells = [Cell() for _ in range(column)]
                    for raw_cell in raw_row.get("values", []):
                        value = raw_cell.get("effectiveValue", {})
                        cells.append(
                            Cell(
                                display=raw_cell.get("formattedValue", ""),
                                value=next(iter(value.values()), None),
                                format_type=raw_cell.get("effectiveFormat", {})
                                .get("numberFormat", {})
                                .get("type"),
                                error="errorValue" in value,
                            )
                        )
                    rows.append(Row(start + offset + 1, tuple(cells[:6])))
        if len({row.number for row in rows}) != len(rows):
            raise ApiError(
                "Read item rows: overlapping grid data; no writes performed."
            )
        return SheetData(zone, rows)
