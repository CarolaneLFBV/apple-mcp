"""
Apple Calendar MCP server — read / create / update / delete events.

Drives Calendar.app through AppleScript (osascript). Targets your named
calendars (e.g. "Health", "Business", "Deadlines").

Event handles
-------------
Each event is referenced by a stable handle encoding the calendar name and
the event's UID:  calendar|||uid
The UID is persistent across launches, so action tools can re-locate an event
reliably. Handles are returned by the read tools.

Dates
-----
Tools accept/return ISO-like strings "YYYY-MM-DD HH:MM" (24h, local time), or
"YYYY-MM-DD" for all-day events. Date components are injected into AppleScript
numerically, so behaviour does not depend on the system locale.

Note: reading events via AppleScript is slow over large date ranges. Keep
windows short (a day, a week) and prefer targeting a specific calendar.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("apple-calendar")

FIELD = "\x1f"   # between fields of one event
RECORD = "\x1e"  # between events
HANDLE = "|||"   # between handle components


# --------------------------------------------------------------------------
# AppleScript helpers (date handlers shared by every script that needs them)
# --------------------------------------------------------------------------

# Reusable AppleScript handlers: makeDate (build a date from components),
# isoDate (format a date as "YYYY-MM-DD HH:MM"), pad (zero-pad an integer).
AS_HELPERS = """
on makeDate(y, mo, d, hh, mm)
    set theDate to current date
    set day of theDate to 1
    set year of theDate to y
    set month of theDate to mo
    set day of theDate to d
    set hours of theDate to hh
    set minutes of theDate to mm
    set seconds of theDate to 0
    return theDate
end makeDate

on pad(n, w)
    set s to (n as integer) as string
    repeat while (count of s) < w
        set s to "0" & s
    end repeat
    return s
end pad

on isoDate(theDate)
    set y to year of theDate
    set mo to ((month of theDate) as integer)
    set d to day of theDate
    set hh to hours of theDate
    set mm to minutes of theDate
    return (my pad(y, 4)) & "-" & (my pad(mo, 2)) & "-" & (my pad(d, 2)) & " " & (my pad(hh, 2)) & ":" & (my pad(mm, 2))
end isoDate
"""


def run_applescript(script: str, timeout: int = 90) -> str:
    """Run an AppleScript snippet and return stdout (trailing newline stripped)."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "Calendar did not respond in time. Narrow the date range or target a "
            "single calendar — reading events over wide ranges is slow."
        )
    if result.returncode != 0:
        err = result.stderr.strip()
        if "Not authorized" in err or "-1743" in err:
            raise RuntimeError(
                "Authorization denied. Open System Settings → Privacy & Security "
                "→ Automation and allow the app running Claude (Terminal/iTerm/"
                "Claude) to control “Calendar”."
            )
        if "-600" in err or "isn't running" in err:
            raise RuntimeError("Calendar.app is not running. Open Calendar and try again.")
        raise RuntimeError(f"AppleScript error: {err}")
    return result.stdout.rstrip("\n")


def esc(value: str) -> str:
    """Escape a string for insertion into an AppleScript string literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def parse_dt(value: str) -> tuple[int, int, int, int, int]:
    """Parse "YYYY-MM-DD[ HH:MM]" (or ISO 'T') into (year, month, day, hour, min)."""
    s = value.strip().replace("T", " ")
    if " " in s:
        date_part, time_part = s.split(" ", 1)
    else:
        date_part, time_part = s, "00:00"
    y, mo, d = (int(x) for x in date_part.split("-"))
    hh, mm = (int(x) for x in time_part.split(":")[:2])
    return y, mo, d, hh, mm


def split_handle(handle: str) -> tuple[str, str]:
    """Split a handle into (calendar, uid) or raise ValueError."""
    parts = handle.split(HANDLE)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid handle: {handle!r}. Use a handle returned by list_events / "
            "get_event (form: calendar|||uid)."
        )
    return parts[0], parts[1]


def _make_date_expr(var: str, value: str) -> str:
    """AppleScript line assigning `var` from an ISO date string via makeDate()."""
    y, mo, d, hh, mm = parse_dt(value)
    return f"set {var} to makeDate({y}, {mo}, {d}, {hh}, {mm})"


def locator(calendar: str, uid: str) -> str:
    """AppleScript fragment defining `theEvent` (inside a Calendar tell block)."""
    return f"""
        set theCal to first calendar whose name is "{esc(calendar)}"
        set theEvent to first event of theCal whose uid is "{esc(uid)}"
    """


# --------------------------------------------------------------------------
# Serializer for a list of events held in AppleScript var `evts` of `calName`
# --------------------------------------------------------------------------

def _serialize_events(cal_name_var: str = "calName") -> str:
    return f"""
        repeat with e in evts
            set theLoc to ""
            try
                set theLoc to location of e
            end try
            set allDayFlag to "false"
            try
                if allday event of e then set allDayFlag to "true"
            end try
            set outText to outText & (uid of e) & "{FIELD}"
            set outText to outText & (summary of e) & "{FIELD}"
            set outText to outText & (my isoDate(start date of e)) & "{FIELD}"
            set outText to outText & (my isoDate(end date of e)) & "{FIELD}"
            set outText to outText & allDayFlag & "{FIELD}"
            set outText to outText & theLoc & "{FIELD}"
            set outText to outText & {cal_name_var} & "{RECORD}"
        end repeat
    """


def parse_events(raw: str) -> list[dict]:
    """Parse serialized event records into dicts."""
    if not raw:
        return []
    out = []
    for record in raw.split(RECORD):
        if not record.strip():
            continue
        parts = record.split(FIELD)
        if len(parts) < 7:
            continue
        uid, summary, start, end, all_day, location, calendar = parts[:7]
        out.append(
            {
                "handle": f"{calendar}{HANDLE}{uid}",
                "title": summary,
                "start": start,
                "end": end,
                "all_day": all_day == "true",
                "location": location,
                "calendar": calendar,
            }
        )
    return out


# --------------------------------------------------------------------------
# Tools — read
# --------------------------------------------------------------------------

@mcp.tool()
def list_calendars() -> str:
    """List the calendars in Calendar.app, with whether each is writable."""
    script = f"""
    set outText to ""
    tell application "Calendar"
        repeat with c in calendars
            set w to "read-only"
            try
                if writable of c then set w to "writable"
            end try
            set outText to outText & (name of c) & "{FIELD}" & w & "{RECORD}"
        end repeat
    end tell
    return outText
    """
    raw = run_applescript(script)
    rows = []
    for rec in raw.split(RECORD):
        if not rec.strip():
            continue
        parts = rec.split(FIELD)
        if len(parts) >= 2:
            rows.append((parts[0], parts[1]))
    if not rows:
        return "No calendar found."
    return "Calendars:\n" + "\n".join(f"- {name} ({w})" for name, w in rows)


@mcp.tool()
def list_events(
    calendar: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 50,
) -> str:
    """List events in a date window.

    - calendar: restrict to one calendar by name (recommended; faster).
                If omitted, scans all calendars (slower).
    - start / end: ISO datetimes "YYYY-MM-DD HH:MM". Default: today 00:00–23:59.
    - limit: max events returned.
    """
    now = datetime.now()
    if not start:
        start = now.strftime("%Y-%m-%d 00:00")
    if not end:
        # default end = end of the start day
        sy, smo, sd, _, _ = parse_dt(start)
        end = f"{sy:04d}-{smo:02d}-{sd:02d} 23:59"

    if calendar:
        cal_selector = f'set targetCals to {{first calendar whose name is "{esc(calendar)}"}}'
    else:
        cal_selector = "set targetCals to every calendar"

    script = f"""
    {AS_HELPERS}
    {_make_date_expr("d1", start)}
    {_make_date_expr("d2", end)}
    set outText to ""
    set shown to 0
    set lim to {int(limit)}
    tell application "Calendar"
        {cal_selector}
        repeat with cal in targetCals
            if shown < lim then
                set calName to name of cal
                set evts to (every event of cal whose start date >= d1 and start date <= d2)
                {_serialize_events()}
                set shown to shown + (count of evts)
            end if
        end repeat
    end tell
    return outText
    """
    events = parse_events(run_applescript(script))
    events.sort(key=lambda e: e["start"])
    return _format_events(events[:limit], start, end)


@mcp.tool()
def get_event(handle: str) -> str:
    """Read an event's full details (title, times, location, notes, url)."""
    calendar, uid = split_handle(handle)
    script = f"""
    {AS_HELPERS}
    tell application "Calendar"
        {locator(calendar, uid)}
        set theTitle to summary of theEvent
        set theStart to my isoDate(start date of theEvent)
        set theEnd to my isoDate(end date of theEvent)
        set allDayFlag to "false"
        try
            if allday event of theEvent then set allDayFlag to "true"
        end try
        set theLoc to ""
        try
            set theLoc to location of theEvent
        end try
        set theNotes to ""
        try
            set theNotes to description of theEvent
        end try
        set theUrl to ""
        try
            set theUrl to url of theEvent
        end try
        set outText to theTitle & "{FIELD}" & theStart & "{FIELD}" & theEnd & "{FIELD}"
        set outText to outText & allDayFlag & "{FIELD}" & theLoc & "{FIELD}" & theUrl & "{FIELD}"
        set outText to outText & theNotes
        return outText
    end tell
    """
    raw = run_applescript(script)
    parts = raw.split(FIELD)
    if len(parts) < 7:
        return "Event not found or unreadable."
    title, start, end, all_day, location, url = parts[:6]
    notes = FIELD.join(parts[6:])
    lines = [
        f"Title    : {title}",
        f"Calendar : {calendar}",
        f"Start    : {start}",
        f"End      : {end}",
        f"All-day  : {'yes' if all_day == 'true' else 'no'}",
    ]
    if location:
        lines.append(f"Location : {location}")
    if url:
        lines.append(f"URL      : {url}")
    if notes:
        lines.append(f"\nNotes:\n{notes}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Tools — write
# --------------------------------------------------------------------------

@mcp.tool()
def create_event(
    calendar: str,
    title: str,
    start: str,
    end: Optional[str] = None,
    all_day: bool = False,
    location: Optional[str] = None,
    notes: Optional[str] = None,
    url: Optional[str] = None,
) -> str:
    """Create an event in the named calendar.

    - start / end: ISO "YYYY-MM-DD HH:MM". For all_day, "YYYY-MM-DD" is enough;
      if end is omitted, a 1-hour event (or single all-day) is created.
    - url: optional link. To link a Mail message, pass its message:// URL here
      (see apple-mail's read_message) so the event opens the mail in one click.
    """
    if not end:
        if all_day:
            end = start
        else:
            sy, smo, sd, shh, smm = parse_dt(start)
            base = datetime(sy, smo, sd, shh, smm) + timedelta(hours=1)
            end = base.strftime("%Y-%m-%d %H:%M")

    extra = []
    if location:
        extra.append(f'set location of newEvent to "{esc(location)}"')
    if notes:
        extra.append(f'set description of newEvent to "{esc(notes)}"')
    if url:
        extra.append(f'set url of newEvent to "{esc(url)}"')
    all_day_prop = ", allday event:true" if all_day else ""

    script = f"""
    {AS_HELPERS}
    {_make_date_expr("d1", start)}
    {_make_date_expr("d2", end)}
    tell application "Calendar"
        set theCal to first calendar whose name is "{esc(calendar)}"
        tell theCal
            set newEvent to make new event with properties {{summary:"{esc(title)}", start date:d1, end date:d2{all_day_prop}}}
        end tell
        {chr(10).join("        " + line for line in extra)}
        return uid of newEvent
    end tell
    """
    new_uid = run_applescript(script)
    handle = f"{calendar}{HANDLE}{new_uid}"
    return f"Event created in “{calendar}”: {title} ({start} → {end})\nhandle: {handle}"


@mcp.tool()
def update_event(
    handle: str,
    title: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    location: Optional[str] = None,
    notes: Optional[str] = None,
    url: Optional[str] = None,
) -> str:
    """Update fields of an existing event. Only the provided fields change.

    Note: moving an event to a different calendar is not supported here
    (AppleScript can't reliably move events) — delete and re-create instead.
    """
    calendar, uid = split_handle(handle)
    sets = []
    date_exprs = []
    if title is not None:
        sets.append(f'set summary of theEvent to "{esc(title)}"')
    if start is not None:
        date_exprs.append(_make_date_expr("ns", start))
        sets.append("set start date of theEvent to ns")
    if end is not None:
        date_exprs.append(_make_date_expr("ne", end))
        sets.append("set end date of theEvent to ne")
    if location is not None:
        sets.append(f'set location of theEvent to "{esc(location)}"')
    if notes is not None:
        sets.append(f'set description of theEvent to "{esc(notes)}"')
    if url is not None:
        sets.append(f'set url of theEvent to "{esc(url)}"')

    if not sets:
        return "Nothing to update: provide at least one field to change."

    script = f"""
    {AS_HELPERS}
    {chr(10).join(date_exprs)}
    tell application "Calendar"
        {locator(calendar, uid)}
        {chr(10).join("        " + line for line in sets)}
        return "ok"
    end tell
    """
    run_applescript(script)
    return f"Event updated in “{calendar}”."


@mcp.tool()
def delete_event(handle: str) -> str:
    """Delete a single, specific event (identified by handle). Irreversible.

    Returns the title and start of the deleted event for confirmation.
    """
    calendar, uid = split_handle(handle)
    script = f"""
    {AS_HELPERS}
    tell application "Calendar"
        {locator(calendar, uid)}
        set theTitle to summary of theEvent
        set theStart to my isoDate(start date of theEvent)
        delete theEvent
        return theTitle & "{FIELD}" & theStart
    end tell
    """
    raw = run_applescript(script)
    parts = raw.split(FIELD)
    title = parts[0] if parts else "(unknown)"
    start = parts[1] if len(parts) > 1 else ""
    return f"Deleted from “{calendar}”: {title} ({start})"


# --------------------------------------------------------------------------

def _format_events(events: list[dict], start: str, end: str) -> str:
    if not events:
        return f"No events between {start} and {end}."
    lines = [f"{len(events)} event(s) between {start} and {end}:\n"]
    for e in events:
        when = e["start"] if not e["all_day"] else f"{e['start'][:10]} (all-day)"
        line = f"• {when} — {e['title']}  [{e['calendar']}]"
        if e["location"]:
            line += f"\n    @ {e['location']}"
        line += f"\n    handle: {e['handle']}"
        lines.append(line)
    return "\n".join(lines)


def main() -> None:
    """Console-script entry point."""
    mcp.run()


if __name__ == "__main__":
    main()
