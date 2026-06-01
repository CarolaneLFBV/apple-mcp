"""Unit tests for the pure helpers (no Mail.app interaction)."""

import pytest

from apple_mail_mcp.server import (
    FIELD,
    HANDLE,
    RECORD,
    esc,
    parse_messages,
    split_handle,
    _format_list,
)


def _record(msg_id, subject, sender, date, read, mailbox, account):
    return FIELD.join([msg_id, subject, sender, date, read, mailbox, account])


def test_esc_escapes_quotes_and_backslashes():
    assert esc('he said "hi"') == 'he said \\"hi\\"'
    assert esc("a\\b") == "a\\\\b"
    assert esc("plain") == "plain"


def test_parse_messages_empty():
    assert parse_messages("") == []
    assert parse_messages("   ") == []


def test_parse_messages_single():
    raw = _record("42", "Hello", "a@b.com", "Mon 1 Jan", "false", "INBOX", "iCloud") + RECORD
    msgs = parse_messages(raw)
    assert len(msgs) == 1
    m = msgs[0]
    assert m["subject"] == "Hello"
    assert m["from"] == "a@b.com"
    assert m["unread"] is True  # read flag "false" => unread
    assert m["mailbox"] == "INBOX"
    assert m["account"] == "iCloud"
    assert m["handle"] == f"iCloud{HANDLE}INBOX{HANDLE}42"


def test_parse_messages_read_flag():
    raw = _record("1", "S", "x", "d", "true", "INBOX", "iCloud") + RECORD
    assert parse_messages(raw)[0]["unread"] is False


def test_parse_messages_multiple_and_skips_short_records():
    good = _record("1", "A", "x", "d", "true", "INBOX", "iCloud")
    short = "1" + FIELD + "incomplete"
    raw = RECORD.join([good, short]) + RECORD
    msgs = parse_messages(raw)
    assert len(msgs) == 1
    assert msgs[0]["subject"] == "A"


def test_split_handle_roundtrip():
    handle = f"iCloud{HANDLE}INBOX{HANDLE}42"
    assert split_handle(handle) == ("iCloud", "INBOX", "42")


@pytest.mark.parametrize("bad", ["", "iCloud", "iCloud|||INBOX", "a|||b|||c|||d"])
def test_split_handle_invalid_raises(bad):
    with pytest.raises(ValueError):
        split_handle(bad)


def test_format_list_empty():
    assert _format_list([]) == "No matching message."


def test_format_list_renders_handle_and_marker():
    raw = _record("7", "Subj", "s@x.com", "Today", "false", "INBOX", "iCloud") + RECORD
    out = _format_list(parse_messages(raw))
    assert "Subj" in out
    assert "iCloud|||INBOX|||7" in out
    assert "●" in out  # unread marker
