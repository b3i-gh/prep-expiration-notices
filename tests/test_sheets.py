from unittest.mock import Mock

import pytest
from test_google_api import response

from prep_notices.errors import NoticeError
from prep_notices.sheets import Sheets


def metadata(titles=("Items",), zone="Europe/Rome"):
    return {
        "properties": {"timeZone": zone},
        "sheets": [{"properties": {"title": title}} for title in titles],
    }


def test_grid_offsets_quoted_title_and_omitted_trailing_cells():
    api = Mock()
    api.spreadsheets.return_value.get.side_effect = [
        response(metadata(("Bob's Items",))),
        response(
            {
                "sheets": [
                    {
                        "data": [
                            {
                                "startRow": 3,
                                "rowData": [
                                    {
                                        "values": [
                                            {
                                                "effectiveValue": {"numberValue": 1},
                                                "formattedValue": "001",
                                            }
                                        ]
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ),
    ]
    data = Sheets(api).read("test")
    assert data.zone.key == "Europe/Rome"
    assert data.rows[0].number == 4
    assert data.rows[0].cells[0].display == "001"
    assert api.spreadsheets.return_value.get.call_args.kwargs["ranges"] == [
        "'Bob''s Items'!A2:F"
    ]


@pytest.mark.parametrize(
    ("meta", "title"),
    [
        (metadata(("One", "Two")), None),
        (metadata(), "Missing"),
        (metadata(zone=None), None),
        (metadata(zone="invalid-zone"), None),
    ],
)
def test_selection_and_timezone_errors(meta, title):
    api = Mock()
    api.spreadsheets.return_value.get.return_value = response(meta)
    with pytest.raises(NoticeError):
        Sheets(api).read("test", title)
    assert api.spreadsheets.return_value.get.call_count == 1


def test_explicit_title_among_multiple_and_empty_sheet():
    api = Mock()
    api.spreadsheets.return_value.get.side_effect = [
        response(metadata(("One", "Two"))),
        response({"sheets": [{}]}),
    ]
    assert Sheets(api).read("test", "Two").rows == []
