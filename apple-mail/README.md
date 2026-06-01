# apple-mail-mcp

An [MCP](https://modelcontextprotocol.io) server that drives **Apple Mail (Mail.app)** on macOS through AppleScript.

**Scope: read, search and organize — no send.** This server deliberately cannot send email or create drafts, so an agent can help you triage your inbox without ever sending anything on your behalf.

## Tools

### Read / search
| Tool | Description |
|------|-------------|
| `list_accounts` | List configured mail accounts |
| `list_mailboxes(account?)` | List mailboxes (optionally for one account) |
| `search_messages(query?, sender?, account?, mailbox="INBOX", unread_only=False, limit=20)` | Search messages |
| `list_unread(account?, mailbox="INBOX", limit=20)` | Shortcut for unread messages |
| `read_message(handle)` | Read a message's full content |

### Organize
| Tool | Description |
|------|-------------|
| `mark_read(handle, read=True)` | Mark read / unread |
| `flag_message(handle, flagged=True)` | Add / remove a flag |
| `move_message(handle, target_mailbox, target_account?)` | Move to another mailbox |
| `delete_message(handle)` | Move to trash (reversible) |

**Handles.** Search tools return a stable `handle` for each message in the form
`account|||mailbox|||id`. Pass it to the action tools.

## Requirements

- macOS with Mail.app configured
- [uv](https://docs.astral.sh/uv/) (recommended) or Python 3.10+

## Installation

### Option 1 — Run from GitHub with uvx (no clone, no PyPI needed)

```bash
uvx --from "git+https://github.com/CarolaneLFBV/apple-mcp#subdirectory=apple-mail" apple-mail-mcp
```

### Option 2 — Clone and run with uv

```bash
git clone https://github.com/CarolaneLFBV/apple-mcp
cd apple-mcp/apple-mail
uv run apple-mail-mcp
```

### Option 3 — From PyPI (once published)

```bash
uvx apple-mail-mcp
```

## Client configuration

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "apple-mail": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/CarolaneLFBV/apple-mcp#subdirectory=apple-mail",
        "apple-mail-mcp"
      ]
    }
  }
}
```

Then **fully quit and relaunch** Claude Desktop (⌘Q).

> If `uvx` is not on your `PATH` as seen by the app, use its absolute path
> (find it with `which uvx`, e.g. `/opt/homebrew/bin/uvx`).

### Claude Code

```bash
claude mcp add apple-mail -- uvx --from "git+https://github.com/CarolaneLFBV/apple-mcp#subdirectory=apple-mail" apple-mail-mcp
```

## macOS Automation permission

The first time the server talks to Mail, macOS asks whether the app running it
(Terminal, iTerm, or Claude) may control **Mail**. Allow it. You can review this
later under **System Settings → Privacy & Security → Automation**.

## Development

```bash
cd apple-mail
uv sync
uv run pytest          # unit tests (no Mail.app interaction)
uv run apple-mail-mcp  # run the server
```

## How it works

Tools generate small AppleScript snippets executed via `osascript`. Output is
serialized with unlikely control-character delimiters and parsed in Python.
Messages are addressed by a `account|||mailbox|||id` handle so action tools can
re-locate a message reliably across calls.

## License

[MIT](../LICENSE) © Carolane Lefebvre
