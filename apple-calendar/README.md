# apple-calendar-mcp

An [MCP](https://modelcontextprotocol.io) server that drives **Apple Calendar (Calendar.app)** on macOS through AppleScript.

Read your agenda and **create, update and delete events** in your own named calendars (e.g. `Health`, `Business`, `Deadlines`). Pairs nicely with [`apple-mail`](../apple-mail) to turn an email into a calendar entry.

## Tools

| Tool | Description |
|------|-------------|
| `list_calendars` | List calendars and whether each is writable |
| `list_events(calendar?, start?, end?, limit?)` | List events in a date window (default: today) |
| `get_event(handle)` | Full details of an event (times, location, notes, url) |
| `create_event(calendar, title, start, end?, all_day?, location?, notes?, url?)` | Create an event |
| `update_event(handle, …fields…)` | Update only the fields you pass |
| `delete_event(handle)` | Delete one specific event (returns what was deleted) |

**Handles.** Read tools return a stable `handle` per event in the form
`calendar|||uid`. The UID is persistent, so action tools re-locate events reliably.

**Dates.** ISO-like strings: `"2026-06-03 18:00"` (24h, local time), or
`"2026-06-03"` for all-day. Components are injected numerically, so behaviour
does not depend on your system locale.

## Linking a mail to an event

`create_event` accepts a `url`. Pass a Mail message's `message://…` URL (exposed
by `apple-mail`'s `read_message`) and the event opens the original email in one
click. Claude orchestrates the two servers — there is no hard coupling.

## Requirements & install

macOS with Calendar.app, plus [uv](https://docs.astral.sh/uv/) (or Python 3.10+).

```bash
# Run straight from GitHub (no clone, no PyPI):
uvx --from "git+https://github.com/CarolaneLFBV/apple-mcp#subdirectory=apple-calendar" apple-calendar-mcp
```

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` **while the
app is fully quit** (it rewrites this file on exit), then relaunch:

```json
{
  "mcpServers": {
    "apple-calendar": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/CarolaneLFBV/apple-mcp#subdirectory=apple-calendar",
        "apple-calendar-mcp"
      ]
    }
  }
}
```

### Claude Code

```bash
claude mcp add apple-calendar -- uvx --from "git+https://github.com/CarolaneLFBV/apple-mcp#subdirectory=apple-calendar" apple-calendar-mcp
```

## macOS Automation permission

On first use, macOS asks whether the app running the server may control
**Calendar**. Allow it (System Settings → Privacy & Security → Automation).

## Notes & limits

- Reading events over **wide date ranges is slow** via AppleScript — prefer a
  specific calendar and a short window (a day, a week).
- `update_event` changes fields in place; it does **not** move an event to a
  different calendar (AppleScript can't do this reliably). Delete and re-create
  to move between calendars.

## Development

```bash
cd apple-calendar
uv sync
uv run pytest          # unit tests (no Calendar.app interaction)
uv run apple-calendar-mcp
```

## License

[MIT](../LICENSE) © Carolane Lefebvre
