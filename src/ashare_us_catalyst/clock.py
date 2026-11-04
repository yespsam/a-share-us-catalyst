from __future__ import annotations

from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Optional


def shanghai_tz() -> tzinfo:
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("Asia/Shanghai")
    except Exception:
        return timezone(timedelta(hours=8), name="Asia/Shanghai")


def shanghai_now(now: Optional[datetime] = None) -> datetime:
    tz = shanghai_tz()
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def shanghai_today(now: Optional[datetime] = None) -> date:
    return shanghai_now(now).date()


def parse_cn_time(value: object, tz: Optional[tzinfo] = None) -> Optional[datetime]:
    """Parse common Chinese news/quote timestamps. Returns an aware Shanghai time."""
    zone = tz or shanghai_tz()
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit() and len(text) in {10, 13}:
        num = int(text)
        if len(text) == 13:
            num = num / 1000
        try:
            return datetime.fromtimestamp(num, tz=zone)
        except (OSError, OverflowError, ValueError):
            return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=zone)
    return None
