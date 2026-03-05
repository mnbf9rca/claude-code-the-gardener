"""Select representative photos per day from raw/photos/."""
import re
from datetime import datetime, timezone

from processor.helpers import date_of, parse_ts
from processor.r2_client import list_objects

# Photo filename format: plant_YYYYMMDD_HHMMSS_NNN.jpg
_PHOTO_RE = re.compile(r"plant_(\d{8})_(\d{6})_\d+\.jpg$")

# 6 time slots: divide 24h into 6 equal 4-hour windows.
# Midpoints in seconds from midnight: 2h, 6h, 10h, 14h, 18h, 22h.
SLOT_MIDPOINTS_SECONDS = [2 * 3600, 6 * 3600, 10 * 3600, 14 * 3600, 18 * 3600, 22 * 3600]
NOON_SLOT = 3  # index of the slot closest to noon (14:00 midpoint ≈ solar noon)


def parse_photo_timestamp(filename: str) -> datetime | None:
    """Parse YYYYMMDD_HHMMSS from plant_YYYYMMDD_HHMMSS_NNN.jpg filename.

    Returns UTC datetime or None if filename doesn't match.
    """
    # Strip any path prefix
    name = filename.rsplit("/", 1)[-1]
    m = _PHOTO_RE.match(name)
    if not m:
        return None
    date_str, time_str = m.group(1), m.group(2)
    return datetime(
        int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]),
        int(time_str[:2]), int(time_str[2:4]), int(time_str[4:6]),
        tzinfo=timezone.utc,
    )


def _parse_ts(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def filter_lit_filenames(
    filenames: list[str],
    light_events: list[dict],
) -> list[str]:
    """Return only filenames taken while the light was on.

    light_events is a list of dicts with 'timestamp', 'event_type', and
    optionally 'scheduled_off' (present on turn_on events from new data).

    Strategy:
    - Primary: interval-based using [turn_on.timestamp, turn_on.scheduled_off].
      This is the most reliable approach — scheduled_off is authoritative.
    - Fallback: event-pair state tracking for older data that lacks scheduled_off.
      Only turn_off_scheduled / turn_off_manual / recovery_turn_off end a lit
      window; recovery_reschedule and other intermediate events are ignored.

    Returns an empty list if no light data is available or no photos are lit.
    Callers must show a 'no photos' placeholder rather than falling back to
    unfiltered (potentially dark) photos.
    """
    if not light_events:
        return []

    # ── Primary: interval-based ───────────────────────────────────────────────
    intervals = [
        (_parse_ts(evt["timestamp"]), _parse_ts(evt["scheduled_off"]))
        for evt in light_events
        if evt.get("event_type") == "turn_on" and evt.get("scheduled_off")
    ]
    if intervals:
        lit = []
        for fname in filenames:
            dt = parse_photo_timestamp(fname)
            if dt is None:
                continue
            pts = dt.timestamp()
            if any(on <= pts <= off for on, off in intervals):
                lit.append(fname)
        return lit

    # ── Fallback: event-pair state tracking (old data without scheduled_off) ──
    _OFF_TYPES = {"turn_off_scheduled", "turn_off_manual", "recovery_turn_off"}
    sorted_events = sorted(light_events, key=lambda e: _parse_ts(e["timestamp"]))

    lit = []
    for fname in filenames:
        dt = parse_photo_timestamp(fname)
        if dt is None:
            continue
        photo_ts = dt.timestamp()
        light_on = False
        for evt in sorted_events:
            if _parse_ts(evt["timestamp"]) <= photo_ts:
                etype = evt["event_type"]
                if etype == "turn_on":
                    light_on = True
                elif etype in _OFF_TYPES:
                    light_on = False
                # recovery_reschedule and other intermediates: leave state unchanged
            else:
                break
        if light_on:
            lit.append(fname)

    return lit


def select_photos_for_day(
    filenames: list[str],
    light_events: list[dict] | None = None,
) -> list[str]:
    """Return lit photos for a day, spread across time if there are many.

    Filters to light-on photos only. If ≤6 lit photos, returns all of them.
    If >6, divides into 6 equal time slots and picks the nearest to each
    slot midpoint. Returns [] if no lit photos are found.
    """
    if not filenames:
        return []

    candidates = filter_lit_filenames(filenames, light_events or [])

    # Parse timestamps for valid filenames
    parsed: list[tuple[str, int]] = []  # (filename, seconds_from_midnight)
    for fname in candidates:
        dt = parse_photo_timestamp(fname)
        if dt is None:
            continue
        seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
        parsed.append((fname, seconds))

    if not parsed:
        return []

    # With ≤6 candidates slot selection can only lose photos — return all.
    if len(parsed) <= len(SLOT_MIDPOINTS_SECONDS):
        return [fname for fname, _ in parsed]

    selected = []
    for midpoint in SLOT_MIDPOINTS_SECONDS:
        nearest = min(parsed, key=lambda p: abs(p[1] - midpoint), default=None)
        if nearest and nearest[0] not in selected:
            selected.append(nearest[0])

    return selected


def get_noon_photo(
    filenames: list[str],
    light_events: list[dict] | None = None,
) -> str | None:
    """Return the lit photo nearest 14:00 UTC, or None if no lit photos exist."""
    if not filenames:
        return None

    candidates = filter_lit_filenames(filenames, light_events or [])

    parsed: list[tuple[str, int]] = []
    for fname in candidates:
        dt = parse_photo_timestamp(fname)
        if dt is None:
            continue
        seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
        parsed.append((fname, seconds))

    if not parsed:
        return None

    target = SLOT_MIDPOINTS_SECONDS[NOON_SLOT]
    return min(parsed, key=lambda p: abs(p[1] - target))[0]


def build_photo_url(r2_key: str, public_bucket_url: str) -> str:
    """Build the public URL for a photo given its R2 key (YYYY/MM/DD/filename)."""
    base = public_bucket_url.rstrip("/")
    return f"{base}/{r2_key}"


def process_photos(
    s3,
    photos_bucket: str,
    watermark: str,
    public_bucket_url: str,
    light_events_by_date: dict[str, list[dict]] | None = None,
) -> tuple[dict, str]:
    """Build plant_timeline.json and day_index.json entries from the photos bucket.

    Photos are stored in gardener-photos at YYYY/MM/DD/filename.jpg.

    Returns:
        (timeline_by_date, new_watermark)
        timeline_by_date: {date: {status: "unknown", photos: [...urls...], noon_photo: url}}
        new_watermark: ISO 8601 string of most recent photo LastModified
    """
    all_objects = list_objects(s3, photos_bucket, "")
    wm_dt = parse_ts(watermark)

    # Group full R2 keys by day (key format: YYYY/MM/DD/filename.jpg)
    by_day: dict[str, list[str]] = {}  # date → list of full R2 keys
    new_watermark = watermark

    for obj in all_objects:
        key = obj["Key"]
        filename = key.rsplit("/", 1)[-1]
        dt = parse_photo_timestamp(filename)
        if dt is None:
            continue
        day = date_of(dt)
        by_day.setdefault(day, []).append(key)

        last_mod = obj["LastModified"].astimezone(timezone.utc)
        if last_mod > wm_dt:
            obj_ts = last_mod.strftime("%Y-%m-%dT%H:%M:%SZ")
            if last_mod > parse_ts(new_watermark):
                new_watermark = obj_ts

    # Build timeline entries for all days (full rebuild per day — idempotent)
    timeline: dict[str, dict] = {}
    light_events_by_date = light_events_by_date or {}
    for day, keys in by_day.items():
        filenames = [k.rsplit("/", 1)[-1] for k in keys]
        day_light_events = light_events_by_date.get(day, [])
        selected_fnames = select_photos_for_day(filenames, day_light_events)
        fname_to_key = {k.rsplit("/", 1)[-1]: k for k in keys}
        selected_keys = [fname_to_key[f] for f in selected_fnames]
        noon_fname = get_noon_photo(filenames, day_light_events)
        noon_key = fname_to_key.get(noon_fname) if noon_fname else None
        timeline[day] = {
            "date": day,
            "status": "unknown",  # filled in by sensors processor
            "photos": [build_photo_url(k, public_bucket_url) for k in selected_keys],
            "noon_photo_url": build_photo_url(noon_key, public_bucket_url) if noon_key else None,
        }

    return timeline, new_watermark
