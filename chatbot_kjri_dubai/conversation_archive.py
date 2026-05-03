"""Conversation closure detection and transcript archiving for KJRI Dubai chatbot."""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import psycopg2

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Closure detection
# ---------------------------------------------------------------------------

_GRATITUDE_PATTERNS = re.compile(
    r"terima\s*kasih|makasih|thank\s*you|thanks|"
    r"sampai\s*jumpa|selamat\s*tinggal|bye|goodbye|dadah|"
    r"sudah\s*(?:cukup|selesai)",
    re.IGNORECASE,
)

# If any of these signals are present alongside a gratitude keyword,
# treat the message as a continuation rather than a closure.
_CONTINUATION_SIGNALS = re.compile(
    r"\?|tapi|tetapi|namun|satu\s*lagi|mau\s*tanya|ada\s*lagi|"
    r"bagaimana|gimana|berapa|apakah|bisa\s*tolong",
    re.IGNORECASE,
)


def detect_gratitude_closure(text: str) -> Optional[str]:
    """Return 'gratitude' if text is a clean farewell/thank-you, else None.

    Anti-false-positive heuristic: if continuation signals (question mark,
    'tapi', 'mau tanya', interrogative words) are present alongside a
    gratitude keyword, return None (user is continuing the conversation).
    """
    if not _GRATITUDE_PATTERNS.search(text):
        return None
    if _CONTINUATION_SIGNALS.search(text):
        return None
    return "gratitude"
