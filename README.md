# apple-mcp

A growing suite of **Model Context Protocol (MCP) servers for Apple apps on macOS** — bring your local Apple ecosystem to Claude (and any MCP client).

Each server is a standalone Python package that talks to a native macOS app through AppleScript. No cloud, no API keys: everything runs locally against the apps you already use.

## Servers

| Server | Status | What it does |
|--------|--------|--------------|
| [`apple-mail`](./apple-mail) | ✅ Available | Read, search and organize Mail.app (no send) |
| `apple-calendar` | 🔜 Planned | Read and manage Calendar.app events |
| `apple-health` | 🔜 Planned | Read Apple Health data |

Each server lives in its own directory and is installed independently — pick only the ones you want.

## Quick start

See each server's README for installation and configuration. For Apple Mail:

➡️ **[apple-mail/README.md](./apple-mail/README.md)**

## Why separate servers?

- **Least privilege** — grant Claude access only to the apps you choose.
- **Independent installs** — `uvx apple-mail-mcp` pulls in only what that server needs.
- **Independent releases** — each server versions on its own.

## Requirements

- macOS (these servers rely on AppleScript automation of native apps)
- [uv](https://docs.astral.sh/uv/) (recommended) or Python 3.10+
- macOS Automation permission for the app running your MCP client (prompted on first use)

## License

[MIT](./LICENSE) © Carolane Lefebvre
