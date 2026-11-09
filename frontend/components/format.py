"""Small display formatters shared by the UI."""
from datetime import datetime, timezone


def fmt_seconds(secs: float | None) -> str:
    """Seconds -> 'm:ss' (or 'h:mm:ss' past an hour). None -> '–:––'."""
    if secs is None:
        return "–:––"
    s = int(secs)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def fmt_range(start: float | None, end: float | None) -> str:
    return f"{fmt_seconds(start)}–{fmt_seconds(end)}"


def _parse(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def fmt_date(iso: str | None) -> str:
    """'Nov 8, 2026' in the viewer's local time."""
    dt = _parse(iso)
    return f"{dt.strftime('%b')} {dt.day}, {dt.year}" if dt else ""


def fmt_datetime(iso: str | None) -> str:
    """'Nov 8, 14:32' in the viewer's local time ('Today, 14:32' for today)."""
    dt = _parse(iso)
    if not dt:
        return ""
    clock = dt.strftime("%H:%M")
    if dt.date() == datetime.now(timezone.utc).astimezone().date():
        return f"Today, {clock}"
    return f"{dt.strftime('%b')} {dt.day}, {clock}"


_MD_SPECIAL = "\\`*_{}[]()#+-.!|>~$<"


def md_escape(text: str | None) -> str:
    """Make untrusted text (video titles, channel names) render literally inside st.markdown."""
    return "".join("\\" + c if c in _MD_SPECIAL else c for c in (text or ""))


def truncate(text: str | None, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
