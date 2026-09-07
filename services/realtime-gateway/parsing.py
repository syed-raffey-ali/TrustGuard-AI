"""Conversation parsers — Build Bible Sections 7 (paste-a-conversation).

Supported inputs:
  * WhatsApp export, bracketed timestamp: [DD/MM/YY, HH:MM:SS] Sender: text
      - 24h and 12h (AM/PM) variants, optional seconds, square brackets optional,
        comma after date optional, iOS MM/DD order auto-detected
  * No-timestamp variant:  Sender: text
  * Continuation lines (no colon) append to the previous message
  * System lines are dropped (encryption notices, "created group", LRM marks stripped)
  * plain paste: free-form text — sender-prefixed if possible, else one blob
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


SYSTEM_LINE_MARKERS = (
    "messages and calls are end-to-end encrypted",
    "this chat is end-to-end encrypted",
    "created group",
    "changed the subject",
    "changed this group's icon",
    "added you",
    "left the group",
    "removed ",
    "joined using this group",
    "security code changed",
    "missed voice call",
    "missed video call",
    "deleted this message",
    "<media omitted>",
    "image omitted",
    "video omitted",
    "sticker omitted",
    "document omitted",
    "audio omitted",
)

# [12/08/25, 14:03:11] Sender: text   |   [8/12/25, 2:03:11 PM] Sender: text
RE_BRACKETED = re.compile(
    r"""^\s*\[?
        (?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{2,4}),?\s+
        (?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?\s*
        (?P<ampm>[AaPp]\.?[Mm]\.?)?\s*
        \]?\s*
        (?P<sender>[^:\]]{1,64}?):\s
        (?P<text>.*)$
    """,
    re.VERBOSE,
)
# 12/08/25 - 14:03 - Sender: text  (dash variant seen on some Android exports)
RE_DASHED = re.compile(
    r"""^\s*
        (?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{2,4})\s*-\s*
        (?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?\s*
        (?P<ampm>[AaPp]\.?[Mm]\.?)?\s*-\s*
        (?P<sender>[^:\]]{1,64}?):\s
        (?P<text>.*)$
    """,
    re.VERBOSE,
)
# Sender: text
RE_SENDER_ONLY = re.compile(r"^(?P<sender>[^:\n]{1,64}?):\s(?P<text>.+)$")

RE_TIMESTAMP_PREFIX = re.compile(r"^\s*(?:\[|\d{1,2}/\d{1,2}/\d{2,4})")


@dataclass
class ParsedMessage:
    message_id: str
    speaker: str
    text: str
    timestamp: str | None = None
    meta: dict = field(default_factory=dict)


def _clean(text: str) -> str:
    """Strip unicode directional marks WhatsApp injects around sender names."""
    text = unicodedata.normalize("NFC", text)
    for ch in ("\u200e", "\u200f", "\u202a", "\u202b", "\u202c", "\ufeff"):
        text = text.replace(ch, "")
    return text.strip()


def _is_system(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in SYSTEM_LINE_MARKERS)


def _parse_timestamp(m: re.Match) -> tuple[str | None, str]:
    month = int(m.group("month"))
    day = int(m.group("day"))
    year = int(m.group("year"))
    year += 2000 if year < 100 else 0
    hour = int(m.group("hour"))
    minute = int(m.group("minute"))
    second = int(m.group("second") or 0)
    ampm = (m.group("ampm") or "").replace(".", "").upper()

    # Auto-detect day/month order: a value > 12 must be the day.
    if day > 12 and month <= 12:
        day_order_month, day_order_day = month, day  # MM/DD (iOS)
    elif month > 12 and day <= 12:
        day_order_month, day_order_day = day, month  # DD/MM (Android)
    else:
        # ambiguous — default to Android DD/MM ordering, flag it
        day_order_day, day_order_month = day, month
        m.meta_ambiguous = True  # type: ignore[attr-defined]

    if ampm == "PM" and hour < 12:
        hour += 12
    elif ampm == "AM" and hour == 12:
        hour = 0
    iso = f"{year:04d}-{day_order_month:02d}-{day_order_day:02d}T{hour:02d}:{minute:02d}:{second:02d}"
    ambiguous = getattr(m, "meta_ambiguous", False)
    return iso, ("date_order_assumed_dd_mm" if not ambiguous else "")


def parse_whatsapp_export(raw: str) -> list[ParsedMessage]:
    messages: list[ParsedMessage] = []
    idx = 0
    for line in raw.splitlines():
        line = _clean(line)
        if not line or _is_system(line):
            continue
        m = RE_BRACKETED.match(line) or RE_DASHED.match(line)
        if m:
            ts, _flag = _parse_timestamp(m)
            messages.append(ParsedMessage(
                message_id=f"m_{idx + 1}",
                speaker=_clean(m.group("sender")),
                text=m.group("text").strip(),
                timestamp=ts,
            ))
            idx += 1
            continue
        if RE_TIMESTAMP_PREFIX.match(line):
            # timestamped line we failed to fully parse — keep the tail text
            continue
        msender = RE_SENDER_ONLY.match(line)
        if msender and messages:
            messages.append(ParsedMessage(
                message_id=f"m_{idx + 1}",
                speaker=_clean(msender.group("sender")),
                text=msender.group("text").strip(),
                timestamp=None,
            ))
            idx += 1
            continue
        if msender:  # very first line already sender-prefixed
            messages.append(ParsedMessage(
                message_id=f"m_{idx + 1}",
                speaker=_clean(msender.group("sender")),
                text=msender.group("text").strip(),
            ))
            idx += 1
            continue
        # continuation of previous message
        if messages:
            messages[-1].text += "\n" + line
        else:
            messages.append(ParsedMessage(message_id="m_1", speaker="unknown", text=line))
            idx = 1
    return messages


def parse_plain_paste(raw: str) -> list[ParsedMessage]:
    """Free-form paste: use 'Sender:' prefixes when present, else one blob."""
    lines = [_clean(l) for l in raw.splitlines() if _clean(l)]
    sender_lines = sum(1 for l in lines if RE_SENDER_ONLY.match(l))
    if len(lines) >= 2 and sender_lines >= max(1, len(lines) // 2):
        return parse_whatsapp_export("\n".join(lines))
    if lines:
        return [ParsedMessage(message_id="m_1", speaker="them", text="\n".join(lines))]
    return []


def parse_auto(raw: str, fmt: str = "plain") -> list[ParsedMessage]:
    if fmt == "whatsapp_export":
        parsed = parse_whatsapp_export(raw)
        return parsed if parsed else parse_plain_paste(raw)
    parsed = parse_plain_paste(raw)
    return parsed if parsed else parse_whatsapp_export(raw)
