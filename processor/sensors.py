"""Process sensor JSONL files into daily and hourly aggregated statistics."""
from datetime import datetime, timedelta, timezone

from processor.helpers import parse_ts, date_of, hour_bucket, ts_gt
from processor.r2_client import get_jsonl_lines


def bucket_records_by_day(
    records: list[dict],
    value_field: str | None = None,  # reserved; kept for API compat with plan spec
    watermark: str = "1970-01-01T00:00:00Z",
) -> dict[str, list[dict]]:
    """Group records by date, filtering to only those > watermark."""
    buckets: dict[str, list] = {}
    for rec in records:
        ts_str = rec.get("timestamp", "")
        if not ts_str or not ts_gt(ts_str, watermark):
            continue
        day = date_of(parse_ts(ts_str))
        buckets.setdefault(day, []).append(rec)
    return buckets


def bucket_records_by_hour(
    records: list[dict],
    watermark: str = "1970-01-01T00:00:00Z",
) -> dict[str, list[dict]]:
    """Group records by hour bucket (YYYY-MM-DDTHH:00:00Z), filtering > watermark."""
    buckets: dict[str, list] = {}
    for rec in records:
        ts_str = rec.get("timestamp", "")
        if not ts_str or not ts_gt(ts_str, watermark):
            continue
        hk = hour_bucket(parse_ts(ts_str))
        buckets.setdefault(hk, []).append(rec)
    return buckets


def determine_plant_status(records: list[dict]) -> str:
    """Return the dominant plant_state for a set of plant_status records."""
    counts: dict[str, int] = {}
    for rec in records:
        state = rec.get("plant_state", "")
        if state:
            counts[state] = counts.get(state, 0) + 1
    if not counts:
        return "unknown"
    return max(counts, key=counts.__getitem__)


def _moisture_stats(records: list[dict]) -> dict:
    values = [r["value"] for r in records if "value" in r]
    if not values:
        return {"min": None, "max": None, "avg": None, "count": 0, "readings": []}
    return {
        "min": min(values),
        "max": max(values),
        "avg": round(sum(values) / len(values), 2),
        "count": len(values),
        "readings": values,
    }


def _light_stats(records: list[dict]) -> dict:
    minutes_on = sum(
        r.get("duration_minutes", 0)
        for r in records
        if r.get("event_type") == "turn_on"
    )
    events = [
        {"timestamp": r.get("timestamp", ""), "event_type": r.get("event_type", "")}
        for r in records
        if r.get("timestamp") and r.get("event_type")
    ]
    return {"minutes_on": minutes_on, "events": events}


def _water_stats(records: list[dict]) -> dict:
    total_ml = sum(r.get("ml", 0) for r in records)
    events = [
        {"timestamp": r.get("timestamp", ""), "ml": r.get("ml", 0)}
        for r in records
        if r.get("timestamp")
    ]
    return {"total_ml": total_ml, "events": events}


def _plant_status_stats(records: list[dict]) -> dict:
    counts = {"healthy": 0, "stressed": 0, "critical": 0}
    for rec in records:
        state = rec.get("plant_state", "")
        if state in counts:
            counts[state] += 1
    dominant = determine_plant_status(records)
    return {**counts, "dominant": dominant}


def _merge_moisture(existing: dict, new_records: list[dict]) -> dict:
    """Merge new moisture records into existing daily moisture stats."""
    old_readings = existing.get("readings", [])
    new_values = [r["value"] for r in new_records if "value" in r]
    all_values = old_readings + new_values
    if not all_values:
        return existing
    return {
        "min": min(all_values),
        "max": max(all_values),
        "avg": round(sum(all_values) / len(all_values), 2),
        "count": len(all_values),
        "readings": all_values,
    }


def _merge_light(existing: dict, new_records: list[dict]) -> dict:
    """Merge new light records into existing daily light stats."""
    new_stats = _light_stats(new_records)
    return {
        "minutes_on": existing.get("minutes_on", 0) + new_stats["minutes_on"],
        "events": existing.get("events", []) + new_stats["events"],
    }


def _merge_water(existing: dict, new_records: list[dict]) -> dict:
    """Merge new water records into existing daily water stats."""
    new_stats = _water_stats(new_records)
    return {
        "total_ml": existing.get("total_ml", 0) + new_stats["total_ml"],
        "events": existing.get("events", []) + new_stats["events"],
    }


def _merge_plant_status(existing: dict, new_records: list[dict]) -> dict:
    """Merge new plant_status records into existing daily plant_status stats."""
    new_stats = _plant_status_stats(new_records)
    merged = {
        "healthy": existing.get("healthy", 0) + new_stats["healthy"],
        "stressed": existing.get("stressed", 0) + new_stats["stressed"],
        "critical": existing.get("critical", 0) + new_stats["critical"],
    }
    # Recalculate dominant from merged counts
    dominant = max(merged, key=merged.__getitem__) if any(merged.values()) else "unknown"
    return {**merged, "dominant": dominant}


def merge_daily_stats(
    existing: dict[str, dict],
    new_by_type: dict[str, dict[str, list]],
) -> dict[str, dict]:
    """Merge new per-day records into existing daily stats dict.

    For dates that already exist in `existing`, stats are merged (not replaced)
    so that consecutive GHA runs both contribute records for the same calendar day.

    Args:
        existing: current sensor_stats_daily.json content
        new_by_type: {sensor_type: {date: [records]}} for new records only
    """
    result = dict(existing)

    all_dates = set()
    for records_by_date in new_by_type.values():
        all_dates.update(records_by_date.keys())

    for date in sorted(all_dates):
        day = result.setdefault(date, {
            "moisture": {"min": None, "max": None, "avg": None, "count": 0, "readings": []},
            "light": {"minutes_on": 0, "events": []},
            "water": {"total_ml": 0, "events": []},
            "plant_status": {"healthy": 0, "stressed": 0, "critical": 0, "dominant": "unknown"},
        })

        if date in new_by_type.get("moisture", {}):
            day["moisture"] = _merge_moisture(day["moisture"], new_by_type["moisture"][date])

        if date in new_by_type.get("light", {}):
            day["light"] = _merge_light(day["light"], new_by_type["light"][date])

        if date in new_by_type.get("water", {}):
            day["water"] = _merge_water(day["water"], new_by_type["water"][date])

        if date in new_by_type.get("plant_status", {}):
            day["plant_status"] = _merge_plant_status(
                day["plant_status"], new_by_type["plant_status"][date]
            )

    return result


def build_hourly_stats(
    daily_stats: dict[str, dict],
    records_by_type: dict[str, dict[str, list]],
    cutoff_days: int = 7,
) -> dict[str, dict]:
    """Build hourly sensor_stats_hourly.json (last N days only).

    Records older than cutoff_days are excluded from the hourly file.
    (They're still in sensor_stats_daily.json.)
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=cutoff_days)
    hourly: dict[str, dict] = {}

    def _get_or_init(hk: str) -> dict:
        return hourly.setdefault(hk, {"moisture": [], "light_on": False, "water_ml": 0})

    # Moisture
    for _date, by_date in records_by_type.get("moisture", {}).items():
        for rec in by_date:
            ts = parse_ts(rec.get("timestamp", "1970-01-01T00:00:00Z"))
            if ts < cutoff:
                continue
            h = _get_or_init(hour_bucket(ts))
            h["moisture"].append(rec.get("value", 0))

    # Light — mark hour as light_on if a turn_on event falls in it
    for _date, by_date in records_by_type.get("light", {}).items():
        for rec in by_date:
            ts_str = rec.get("timestamp", "")
            if not ts_str:
                continue
            ts = parse_ts(ts_str)
            if ts < cutoff:
                continue
            if rec.get("event_type") == "turn_on":
                h = _get_or_init(hour_bucket(ts))
                h["light_on"] = True

    # Water — accumulate ml per hour
    for _date, by_date in records_by_type.get("water", {}).items():
        for rec in by_date:
            ts_str = rec.get("timestamp", "")
            if not ts_str:
                continue
            ts = parse_ts(ts_str)
            if ts < cutoff:
                continue
            h = _get_or_init(hour_bucket(ts))
            h["water_ml"] = h.get("water_ml", 0) + rec.get("ml", 0)

    # Summarise moisture lists → stats
    for hk, h in hourly.items():
        vals = h.pop("moisture", [])
        h["moisture"] = {
            "avg": round(sum(vals) / len(vals), 2) if vals else None,
            "count": len(vals),
        }

    return hourly


def read_sensor_file(s3, bucket: str, filename: str) -> list[dict]:
    """Download a sensor JSONL file from raw/data/."""
    return get_jsonl_lines(s3, bucket, f"raw/data/{filename}")
