"""Unit tests for the pure helpers (no Calendar.app interaction)."""

import pytest

from apple_calendar_mcp.server import (
    FIELD,
    HANDLE,
    RECORD,
    esc,
    parse_dt,
    parse_events,
    split_handle,
    _format_events,
)


def _record(uid, title, start, end, all_day, location, calendar):
    return FIELD.join([uid, title, start, end, all_day, location, calendar])


def test_esc():
    assert esc('a "b" \\c') == 'a \\"b\\" \\\\c'


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026-06-03 18:00", (2026, 6, 3, 18, 0)),
        ("2026-06-03", (2026, 6, 3, 0, 0)),
        ("2026-06-03T09:05", (2026, 6, 3, 9, 5)),
        ("2026-12-31 23:59", (2026, 12, 31, 23, 59)),
    ],
)
def test_parse_dt(value, expected):
    assert parse_dt(value) == expected


def test_split_handle_roundtrip():
    assert split_handle(f"Health{HANDLE}ABC-123") == ("Health", "ABC-123")


@pytest.mark.parametrize("bad", ["", "Health", "a|||b|||c"])
def test_split_handle_invalid(bad):
    with pytest.raises(ValueError):
        split_handle(bad)


def test_parse_events_single():
    raw = _record("UID1", "Gym", "2026-06-03 18:00", "2026-06-03 19:00", "false", "Studio", "Health") + RECORD
    events = parse_events(raw)
    assert len(events) == 1
    e = events[0]
    assert e["title"] == "Gym"
    assert e["start"] == "2026-06-03 18:00"
    assert e["all_day"] is False
    assert e["location"] == "Studio"
    assert e["calendar"] == "Health"
    assert e["handle"] == f"Health{HANDLE}UID1"


def test_parse_events_all_day_and_skip_short():
    good = _record("U2", "Trip", "2026-06-04 00:00", "2026-06-05 00:00", "true", "", "Personal")
    short = "U3" + FIELD + "incomplete"
    raw = RECORD.join([good, short]) + RECORD
    events = parse_events(raw)
    assert len(events) == 1
    assert events[0]["all_day"] is True


def test_parse_events_empty():
    assert parse_events("") == []


def test_format_events_empty():
    out = _format_events([], "2026-06-03 00:00", "2026-06-03 23:59")
    assert "No events" in out


def test_format_events_renders_handle():
    raw = _record("U1", "Standup", "2026-06-03 09:00", "2026-06-03 09:15", "false", "", "Business") + RECORD
    out = _format_events(parse_events(raw), "2026-06-03 00:00", "2026-06-03 23:59")
    assert "Standup" in out
    assert f"Business{HANDLE}U1" in out
