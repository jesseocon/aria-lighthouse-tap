"""Rates compset export helpers."""

from __future__ import annotations

from tap_lighthouse.rates_export import (
    build_rates_records,
    build_rates_wide_rows,
    column_action,
    competitor_names,
    table_column_key,
    enrich_rates_records,
    parse_rate_hover,
)
from tap_lighthouse.rates_navigation import resolve_rate_types, resolve_rates_url


def test_table_column_key_is_a_bigquery_column_name() -> None:
    assert table_column_key("Hyatt House Boston/Burlington") == "hyatt_house_boston_burlington"
    assert table_column_key("Hilton Garden Inn Boston-Burlington") == "hilton_garden_inn_boston_burlington"
    assert table_column_key("  123 Inn!! ") == "_123_inn"
    assert table_column_key("A / B") == "a_b"


def test_resolve_rates_url_encodes_channel_and_rate_type() -> None:
    best_flex = resolve_rates_url(
        "202158",
        month="2026-10",
        ota_id="bookingdotcom",
        rate_param=None,
    )
    assert "otaId=bookingdotcom" in best_flex
    assert "rateParam" not in best_flex
    assert best_flex.endswith("view=table")

    third_party = resolve_rates_url(
        "202158",
        month="2026-10",
        ota_id="branddotcom",
        rate_param="thirdparty",
    )
    assert "otaId=branddotcom" in third_party
    assert "rateParam=thirdparty" in third_party


def test_resolve_rate_types_defaults_to_best_flex() -> None:
    default = resolve_rate_types(None)
    assert [item[0] for item in default] == ["best_flex"]
    assert resolve_rate_types("  ")[0][0] == "best_flex"

    selected = resolve_rate_types("best_flex, lowest, third_party")
    assert [item[0] for item in selected] == ["best_flex", "lowest", "third_party"]
    assert selected[1][2] == "lowest"
    assert selected[2][2] == "thirdparty"


def test_column_action_drops_pencil_and_blank_trailing_cell() -> None:
    assert column_action("column_0", "") == "drop"
    assert column_action("column_10", "") == "drop"
    assert column_action("column_1", "Sat 03/10") == "date"
    assert column_action("My OTB", "92%") == "keep"


def test_parse_rate_hover_keeps_updated_line() -> None:
    parsed = parse_rate_hover(
        "Rate\tRoom name\tUpdated\n$ 269\tKing Room - Evolution\t\n18 hours ago",
    )
    assert parsed["hover_rate"] == "$ 269"
    assert parsed["hover_room_name"] == "King Room - Evolution"
    assert parsed["hover_updated"] == "18 hours ago"


def test_build_rates_wide_rows_keeps_hotels_as_columns() -> None:
    rows = build_rates_wide_rows(
        [
            {
                "date_label": "Sat 03/10",
                "my_otb": "92%",
                "my_otb_hover": "Current 92%",
                "market_demand": "99%",
                "events_hover": "Events",
                "competitors": [
                    {
                        "label": "Hilton Garden Inn Boston-Burlington",
                        "rate": "$ 269",
                        "href": "/redirect?ota=bookingdotcom",
                        "hover": "Rate\tRoom name\tUpdated\n$ 269\tKing Room\t\n18 hours ago",
                    },
                    {
                        "label": "Hyatt House Boston/Burlington",
                        "rate": "$ 339",
                        "href": "",
                        "hover": "",
                    },
                ],
            },
        ],
        month="2026-10",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["date"] == "Sat 03/10"
    assert row["hilton_garden_inn_boston_burlington"] == "$ 269"
    assert row["hilton_garden_inn_boston_burlington_hover_room_name"] == "King Room"
    assert row["hyatt_house_boston_burlington"] == "$ 339"
    assert "competitor" not in row
    assert competitor_names(
        [
            {
                "competitors": [
                    {"label": "Hilton Garden Inn Boston-Burlington"},
                    {"label": "Hyatt House Boston/Burlington"},
                ],
            },
        ],
    ) == {
        "hilton_garden_inn_boston_burlington": "Hilton Garden Inn Boston-Burlington",
        "hyatt_house_boston_burlington": "Hyatt House Boston/Burlington",
    }


def test_build_rates_records_stores_settings_and_skips_market_demand_hover() -> None:
    rows = [
        {
            "date_label": "Sat 03/10",
            "my_otb": "92%",
            "my_otb_hover": "Current 92%",
            "market_demand": "99%",
            "events_hover": "Events Boston Data and AI",
            "competitors": [
                {
                    "label": "Hilton Garden Inn Boston-Burlington",
                    "key": "hilton_garden_inn_boston_burlington",
                    "rate": "$ 269",
                    "href": "/redirect?ota=bookingdotcom",
                    "hover": "Rate\tRoom name\tUpdated\n$ 269\tKing Room\t\n18 hours ago",
                },
            ],
        },
    ]
    records = build_rates_records(
        rows,
        month="2026-10",
        channel="Booking.com",
        channel_key="booking_com",
        rate_type="Best flex",
        rate_type_key="best_flex",
    )
    assert len(records) == 1
    record = records[0]
    assert record["stay_date"] == "2026-10-03"
    assert record["channel"] == "Booking.com"
    assert record["rate_type"] == "Best flex"
    assert record["market_demand"] == "99%"
    assert record["competitor"] == "Hilton Garden Inn Boston-Burlington"
    assert record["competitor_key"] == "hilton_garden_inn_boston_burlington"
    assert record["hover_room_name"] == "King Room"
    assert record["events_hover"] == "Events Boston Data and AI"
    assert "market_demand_hover" not in record

    enriched = enrich_rates_records(
        records,
        run_id="run-1",
        run_timestamp="2026-10-03T00:00:00",
        refreshed_at="2026-10-04T19:53:00-07:00",
        refresh_label="Updated a few seconds ago",
        sync_params={"channel": "Booking.com", "rate_type": "Best flex"},
        hotel_id="202158",
    )
    assert enriched[0]["hotel_id"] == "202158"
    assert enriched[0]["refreshed_at"] == "2026-10-04T19:53:00-07:00"
    assert enriched[0]["refresh_label"] == "Updated a few seconds ago"
    assert enriched[0]["record_hash"]
    assert "Booking.com" in enriched[0]["sync_params"]

    later = enrich_rates_records(
        records,
        run_id="run-1",
        run_timestamp="2026-10-03T00:00:00",
        refreshed_at="2026-10-05T08:00:00-07:00",
        refresh_label="Updated a few seconds ago",
        sync_params={"channel": "Booking.com", "rate_type": "Best flex"},
        hotel_id="202158",
    )
    assert later[0]["record_hash"] != enriched[0]["record_hash"]
