"""Shared helpers used across processor modules."""
from datetime import datetime, timezone


def parse_ts(s: str) -> datetime:
    """Parse ISO 8601 timestamp, handling both Z and +00:00 suffixes."""
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def ts_gt(timestamp_str: str, watermark_str: str) -> bool:
    """Return True if timestamp > watermark (both ISO 8601 strings)."""
    return parse_ts(timestamp_str) > parse_ts(watermark_str)


def date_of(ts: datetime) -> str:
    """Return YYYY-MM-DD string for a UTC datetime."""
    return ts.strftime("%Y-%m-%d")


def hour_bucket(ts: datetime) -> str:
    """Return YYYY-MM-DDTHH:00:00Z string for a UTC datetime."""
    return ts.strftime("%Y-%m-%dT%H:00:00Z")
