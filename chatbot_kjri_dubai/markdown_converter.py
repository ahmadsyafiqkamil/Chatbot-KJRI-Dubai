"""Convert agent Markdown output to Telegram-safe HTML."""

import re
from html import escape


def md_to_html(text: str) -> str:
    """Convert common Markdown patterns to Telegram HTML.

    Telegram supports: <b>, <i>, <code>, <pre>, <a href="">.
    Anything else must be escaped. Falls back gracefully — if something
    looks wrong the caller should resend as plain text.
    """
    # Escape HTML entities first
    text = escape(text)

    # Code blocks: ```...```
    text = re.sub(
        r"```(?:\w+)?\n(.*?)```",
        r"<pre>\1</pre>",
        text,
        flags=re.DOTALL,
    )

    # Inline code: `...`
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # Bold: **text**
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    # Italic: *text* (but not inside bold tags)
    text = re.sub(r"(?<!</b>)\*(.+?)\*(?!<)", r"<i>\1</i>", text)

    # Headings: ### text → bold (Telegram has no heading tag)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    return text
