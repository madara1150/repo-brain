"""Turn a LINE chat (exported .txt or pasted text) into cases with personal data hidden.

LINE's "Export chat history" writes date header lines followed by tab-separated
"time<TAB>sender<TAB>message" lines (multi-line messages continue on the next lines,
often wrapped in double quotes). Desktop, iOS and Android differ in the date format and
use 24h or AM/PM times, so parsing is deliberately loose.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

MSG = re.compile(r"^\s*(\d{1,2}[:.]\d{2}(?:\s?[AaPp]\.?[Mm]\.?)?)\t([^\t]*)\t?(.*)$")
DATE = re.compile(r"(\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}|\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})")
HEADER_NOISE = re.compile(r"^(\[LINE\]|Saved on|บันทึกเมื่อ|ประวัติการแชท|Chat history)", re.I)

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<!\d)(?:\+66[\s-]?|0)\d(?:[\s-]?\d){7,8}(?!\d)")
THAI_ID = re.compile(r"(?<!\d)\d[\s-]?\d{4}[\s-]?\d{5}[\s-]?\d{2}[\s-]?\d(?!\d)")
BANK = re.compile(r"(?<!\d)\d{3}-\d-\d{5}-\d(?!\d)")
LINE_ID = re.compile(r"(?i)\b(line\s*id|ไลน์\s*ไอดี|ไอดีไลน์)\s*[:：]?\s*@?[\w.\-]+")

GAP_MINUTES = 180  # a quiet period this long starts a new case


@dataclass
class Message:
    date: str
    time: str
    sender: str
    text: str


@dataclass
class Case:
    date: str
    messages: list = field(default_factory=list)
    text: str = ""          # redacted transcript ready for Claude

    @property
    def key(self) -> str:
        return hashlib.sha1(self.text.encode("utf-8")).hexdigest()[:16]

    @property
    def preview(self) -> str:
        """First message of the redacted transcript (never the raw chat)."""
        first = self.text.split("\n", 1)[0]
        first = re.sub(r"^\[[^\]]*\]\s*[^:]{1,40}:\s*", "", first)
        return " ".join(first.split())[:80]


def _minutes(t: str) -> int | None:
    m = re.match(r"(\d{1,2})[:.](\d{2})\s*([AaPp])?", t)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower()
    if ap == "p" and h < 12:
        h += 12
    if ap == "a" and h == 12:
        h = 0
    return h * 60 + mi


def parse(text: str) -> list[Message]:
    msgs: list[Message] = []
    date = ""
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.rstrip()
        m = MSG.match(line)
        if m:
            body = m.group(3)
            if body.startswith('"') and body.count('"') == 1:
                body = body[1:]
            msgs.append(Message(date, m.group(1), m.group(2).strip(), body))
            continue
        if not line.strip():
            continue
        if "\t" not in line and DATE.search(line) and len(line) < 60:
            date = DATE.search(line).group(1)
            continue
        if HEADER_NOISE.match(line.strip()):
            continue
        if msgs:  # continuation of a multi-line message
            piece = line[:-1] if line.endswith('"') and msgs[-1].text.count('"') == 0 else line
            msgs[-1].text += "\n" + piece
    return msgs


def redact(text: str, names: dict[str, str]) -> str:
    for name in sorted(names, key=len, reverse=True):
        if len(name) >= 2:
            text = re.sub(r"@?" + re.escape(name), names[name], text)
    text = EMAIL.sub("[อีเมล]", text)
    text = LINE_ID.sub("[LINE ID]", text)
    text = THAI_ID.sub("[เลขบัตรประชาชน]", text)
    text = BANK.sub("[เลขบัญชี]", text)
    text = PHONE.sub("[เบอร์โทร]", text)
    return text


def _labels(senders: list[str]) -> dict[str, str]:
    out = {}
    for s in senders:
        if s and s not in out:
            n = len(out)
            out[s] = "คน " + (chr(ord("A") + n) if n < 26 else str(n + 1))
    return out


def split_cases(text: str, gap_minutes: int = GAP_MINUTES) -> list[Case]:
    """Cases with redacted transcripts. Text that isn't a LINE export becomes one case."""
    msgs = parse(text)
    if not msgs:
        body = redact(text.strip(), {})
        return [Case("", [], body)] if body else []
    groups: list[list[Message]] = []
    last_date, last_min = None, None
    for m in msgs:
        mins = _minutes(m.time)
        new = not groups or m.date != last_date or (
            mins is not None and last_min is not None and mins - last_min >= gap_minutes)
        if new:
            groups.append([])
        groups[-1].append(m)
        last_date, last_min = m.date, mins if mins is not None else last_min
    cases = []
    for g in groups:
        names = _labels([m.sender for m in g])
        lines = [f"[{m.time}] {names.get(m.sender, m.sender or 'ระบบ')}: {redact(m.text, names)}" for m in g]
        cases.append(Case(g[0].date, g, "\n".join(lines)))
    return cases
