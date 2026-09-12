"""sgt helpers used by active aria timestamp contract"""
from datetime import datetime, timedelta, timezone

SGT = timezone(timedelta(hours=8), name="SGT")

def sgt_now() -> datetime:
    return datetime.now(SGT)

def as_sgt(value: datetime, *, timespec: str = "seconds") -> str:

    if not isinstance(value, datetime):
        raise TypeError("timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(SGT).isoformat(timespec=timespec)