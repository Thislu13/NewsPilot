from datetime import date, datetime, time, timezone, timedelta
from typing import Optional, Union

UTC = timezone.utc
UTC_MIN = datetime.min.replace(tzinfo=UTC)
DateLike = Union[date, str]
DateTimeLike = Union[datetime, str]


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: Optional[DateTimeLike]) -> Optional[datetime]:
    if dt is None:
        return None
    if isinstance(dt, str):
        normalized = dt.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        normalized = normalized.replace(" +", "+").replace(" -", "-")
        if len(normalized) >= 5 and normalized[-5] in "+-" and normalized[-4:].isdigit():
            normalized = normalized[:-5] + normalized[-5:-2] + ":" + normalized[-2:]
        dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def utc_day_bounds(day: DateLike) -> tuple[datetime, datetime]:
    if isinstance(day, str):
        day = date.fromisoformat(day)
    start = datetime.combine(day, time.min, tzinfo=UTC)
    end = start + timedelta(days=1)
    return start, end


def format_utc_date(dt: Optional[datetime]) -> str:
    if dt is None:
        return "unknown"
    normalized = ensure_utc(dt)
    return normalized.strftime("%Y-%m-%d")
