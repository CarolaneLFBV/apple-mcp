"""
Apple Mail MCP server — read / search + organize.

Drives Mail.app through AppleScript (osascript). No send capability:
deliberately limited to reading, searching and organizing mail.

Message handles
---------------
Each message is referenced by a stable "handle" encoding the account,
the mailbox and Mail's internal id:  account|||mailbox|||id
The action tools accept this handle (returned by the search tools).
"""

from __future__ import annotations

import subprocess
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("apple-mail")

# Unlikely separators used to parse AppleScript output.
FIELD = "\x1f"   # between fields of one message
RECORD = "\x1e"  # between messages
HANDLE = "|||"   # between handle components


# --------------------------------------------------------------------------
# AppleScript helpers
# --------------------------------------------------------------------------

def run_applescript(script: str) -> str:
    """Run an AppleScript snippet and return stdout (trailing newline stripped)."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "Mail did not respond within 60 s. The mailbox may be too large "
            "— narrow the search (account, mailbox, or lower the limit)."
        )
    if result.returncode != 0:
        err = result.stderr.strip()
        if "Not authorized" in err or "-1743" in err:
            raise RuntimeError(
                "Authorization denied. Open System Settings → Privacy & Security "
                "→ Automation and allow the app running Claude (Terminal/iTerm/"
                "Claude) to control “Mail”."
            )
        if "-600" in err or "isn't running" in err:
            raise RuntimeError("Mail.app is not running. Open Mail and try again.")
        raise RuntimeError(f"AppleScript error: {err}")
    return result.stdout.rstrip("\n")


def esc(value: str) -> str:
    """Escape a string for insertion into an AppleScript string literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def parse_messages(raw: str) -> list[dict]:
    """Parse the tab-delimited output of a listing script into dicts."""
    if not raw:
        return []
    out = []
    for record in raw.split(RECORD):
        if not record.strip():
            continue
        parts = record.split(FIELD)
        if len(parts) < 7:
            continue
        msg_id, subject, sender, date_str, read, mailbox, account = parts[:7]
        out.append(
            {
                "handle": f"{account}{HANDLE}{mailbox}{HANDLE}{msg_id}",
                "subject": subject,
                "from": sender,
                "date": date_str,
                "unread": read == "false",
                "mailbox": mailbox,
                "account": account,
            }
        )
    return out


def split_handle(handle: str) -> tuple[str, str, str]:
    """Split a handle into (account, mailbox, id) or raise ValueError."""
    parts = handle.split(HANDLE)
    if len(parts) != 3:
        raise ValueError(
            f"Invalid handle: {handle!r}. Use a handle returned by "
            "search_messages / list_unread."
        )
    return parts[0], parts[1], parts[2]  # account, mailbox, id


# AppleScript fragment: serialize a `msgList` variable into tab-delimited text.
# No line-continuation char (¬) to avoid parsing pitfalls.
SERIALIZE = f"""
set AppleScript's text item delimiters to ""
set outText to ""
repeat with m in msgList
    set acctName to ""
    try
        set acctName to name of (account of (mailbox of m))
    end try
    set theBox to ""
    try
        set theBox to name of (mailbox of m)
    end try
    set readFlag to "true"
    try
        if read status of m is false then set readFlag to "false"
    end try
    set outText to outText & (id of m as string) & "{FIELD}"
    set outText to outText & (subject of m) & "{FIELD}"
    set outText to outText & (sender of m) & "{FIELD}"
    set outText to outText & ((date received of m) as string) & "{FIELD}"
    set outText to outText & readFlag & "{FIELD}"
    set outText to outText & theBox & "{FIELD}"
    set outText to outText & acctName & "{RECORD}"
end repeat
return outText
"""


def locator(account: str, mailbox: str, msg_id: str) -> str:
    """Return an AppleScript fragment defining `theMessage`."""
    return f"""
    set theAccount to first account whose name is "{esc(account)}"
    set theMailbox to first mailbox of theAccount whose name is "{esc(mailbox)}"
    set theMessage to first message of theMailbox whose id is {int(msg_id)}
    """


# --------------------------------------------------------------------------
# Tools — read / search
# --------------------------------------------------------------------------

@mcp.tool()
def list_accounts() -> str:
    """List the mail accounts configured in Mail.app."""
    script = f'''
    tell application "Mail" to set theNames to name of every account
    set AppleScript's text item delimiters to "{RECORD}"
    return theNames as string
    '''
    raw = run_applescript(script)
    accounts = [a.strip() for a in raw.split(RECORD) if a.strip()] if raw else []
    if not accounts:
        return "No account found."
    return "Accounts:\n" + "\n".join(f"- {a}" for a in accounts)


@mcp.tool()
def list_mailboxes(account: Optional[str] = None) -> str:
    """List mailboxes. Filter by account if `account` is provided."""
    if account:
        script = f'''
        tell application "Mail"
            set theAccount to first account whose name is "{esc(account)}"
            set theNames to name of every mailbox of theAccount
        end tell
        set AppleScript's text item delimiters to "{RECORD}"
        return theNames as string
        '''
    else:
        script = f'''
        tell application "Mail" to set theNames to name of every mailbox
        set AppleScript's text item delimiters to "{RECORD}"
        return theNames as string
        '''
    raw = run_applescript(script)
    boxes = [b.strip() for b in raw.split(RECORD) if b.strip()] if raw else []
    if not boxes:
        return "No mailbox found."
    header = f"Mailboxes ({account}):" if account else "Mailboxes:"
    return header + "\n" + "\n".join(f"- {b}" for b in boxes)


@mcp.tool()
def search_messages(
    query: Optional[str] = None,
    sender: Optional[str] = None,
    account: Optional[str] = None,
    mailbox: str = "INBOX",
    unread_only: bool = False,
    limit: int = 20,
) -> str:
    """Search for messages in a mailbox.

    - query: text searched in the subject (case-insensitive)
    - sender: filter on the sender (contains)
    - account: account name (otherwise, any mailbox named `mailbox`)
    - mailbox: mailbox name (default INBOX)
    - unread_only: only return unread messages
    - limit: max number of messages returned (most recent first)
    """
    conditions = []
    if unread_only:
        conditions.append("read status is false")
    if query:
        conditions.append(f'subject contains "{esc(query)}"')
    if sender:
        conditions.append(f'sender contains "{esc(sender)}"')
    whose = (" whose " + " and ".join(conditions)) if conditions else ""

    if account:
        box_ref = (
            f'(first mailbox of (first account whose name is "{esc(account)}") '
            f'whose name is "{esc(mailbox)}")'
        )
    else:
        box_ref = f'(first mailbox whose name is "{esc(mailbox)}")'

    script = f'''
    tell application "Mail"
        set srcMessages to (messages of {box_ref}{whose})
        set msgList to {{}}
        set n to count of srcMessages
        set lim to {int(limit)}
        if n < lim then set lim to n
        repeat with i from 1 to lim
            set end of msgList to item i of srcMessages
        end repeat
        {SERIALIZE}
    end tell
    '''
    messages = parse_messages(run_applescript(script))
    return _format_list(messages)


@mcp.tool()
def list_unread(account: Optional[str] = None, mailbox: str = "INBOX", limit: int = 20) -> str:
    """Shortcut: list unread messages in a mailbox (default INBOX)."""
    return search_messages(
        account=account, mailbox=mailbox, unread_only=True, limit=limit
    )


@mcp.tool()
def read_message(handle: str) -> str:
    """Read a message's full content (headers + body).

    `handle` comes from search_messages / list_unread.
    """
    account, mailbox, msg_id = split_handle(handle)
    script = f'''
    tell application "Mail"
        {locator(account, mailbox, msg_id)}
        set theSubject to subject of theMessage
        set theSender to sender of theMessage
        set theDate to (date received of theMessage) as string
        set theBody to content of theMessage
        set theReplyTo to ""
        try
            set theReplyTo to reply to of theMessage
        end try
        set outText to theSubject & "{FIELD}" & theSender & "{FIELD}"
        set outText to outText & theDate & "{FIELD}" & theReplyTo & "{FIELD}"
        set outText to outText & theBody
        return outText
    end tell
    '''
    raw = run_applescript(script)
    parts = raw.split(FIELD)
    if len(parts) < 5:
        return "Message not found or unreadable."
    subject, sender, date_str, reply_to = parts[0], parts[1], parts[2], parts[3]
    body = FIELD.join(parts[4:])
    header = [
        f"Subject  : {subject}",
        f"From     : {sender}",
        f"Date     : {date_str}",
    ]
    if reply_to:
        header.append(f"Reply-To : {reply_to}")
    return "\n".join(header) + "\n\n" + body


# --------------------------------------------------------------------------
# Tools — organize
# --------------------------------------------------------------------------

@mcp.tool()
def mark_read(handle: str, read: bool = True) -> str:
    """Mark a message as read (read=True) or unread (read=False)."""
    account, mailbox, msg_id = split_handle(handle)
    status = "true" if read else "false"
    script = f'''
    tell application "Mail"
        {locator(account, mailbox, msg_id)}
        set read status of theMessage to {status}
        return "ok"
    end tell
    '''
    run_applescript(script)
    return f"Message marked {'read' if read else 'unread'}."


@mcp.tool()
def flag_message(handle: str, flagged: bool = True) -> str:
    """Add (flagged=True) or remove (flagged=False) a flag on a message."""
    account, mailbox, msg_id = split_handle(handle)
    status = "true" if flagged else "false"
    script = f'''
    tell application "Mail"
        {locator(account, mailbox, msg_id)}
        set flagged status of theMessage to {status}
        return "ok"
    end tell
    '''
    run_applescript(script)
    return f"Flag {'added' if flagged else 'removed'}."


@mcp.tool()
def move_message(handle: str, target_mailbox: str, target_account: Optional[str] = None) -> str:
    """Move a message to another mailbox.

    target_account: destination account (default = source account).
    """
    account, mailbox, msg_id = split_handle(handle)
    dest_account = target_account or account
    script = f'''
    tell application "Mail"
        {locator(account, mailbox, msg_id)}
        set destBox to first mailbox of (first account whose name is "{esc(dest_account)}") whose name is "{esc(target_mailbox)}"
        move theMessage to destBox
        return "ok"
    end tell
    '''
    run_applescript(script)
    return f"Message moved to “{target_mailbox}” ({dest_account})."


@mcp.tool()
def delete_message(handle: str) -> str:
    """Move a message to the trash (reversible deletion)."""
    account, mailbox, msg_id = split_handle(handle)
    script = f'''
    tell application "Mail"
        {locator(account, mailbox, msg_id)}
        set mailbox of theMessage to trash mailbox
        return "ok"
    end tell
    '''
    try:
        run_applescript(script)
    except RuntimeError:
        # Some versions don't expose `trash mailbox`; fall back to delete.
        fallback = f'''
        tell application "Mail"
            {locator(account, mailbox, msg_id)}
            delete theMessage
            return "ok"
        end tell
        '''
        run_applescript(fallback)
    return "Message moved to trash."


# --------------------------------------------------------------------------

def _format_list(messages: list[dict]) -> str:
    if not messages:
        return "No matching message."
    lines = [f"{len(messages)} message(s):\n"]
    for m in messages:
        mark = "● " if m["unread"] else "  "
        lines.append(
            f"{mark}{m['subject']}\n"
            f"   From  : {m['from']}\n"
            f"   Date  : {m['date']}\n"
            f"   Mailbox: {m['mailbox']} ({m['account']})\n"
            f"   handle: {m['handle']}\n"
        )
    return "\n".join(lines)


def main() -> None:
    """Console-script entry point."""
    mcp.run()


if __name__ == "__main__":
    main()
