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


def select_photos_for_day(filenames: list[str]) -> list[str]:
    """Select up to 6 photos evenly spaced across the day.

    Algorithm: Divide 24h into 6 equal slots. For each slot, pick the photo
    whose timestamp is closest to the slot's midpoint. Slots with no photos
    are omitted. Input filenames must all be from the same calendar day.
    """
    if not filenames:
        return []

    # Parse timestamps for valid filenames
    parsed: list[tuple[str, int]] = []  # (filename, seconds_from_midnight)
    for fname in filenames:
        dt = parse_photo_timestamp(fname)
        if dt is None:
            continue
        seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
        parsed.append((fname, seconds))

    if not parsed:
        return []

    selected = []
    for midpoint in SLOT_MIDPOINTS_SECONDS:
        nearest = min(parsed, key=lambda p: abs(p[1] - midpoint), default=None)
        if nearest and nearest[0] not in selected:
            selected.append(nearest[0])

    return selected


def get_noon_photo(filenames: list[str]) -> str | None:
    """Return the photo nearest to solar noon (slot 3 midpoint = 14:00)."""
    selected = select_photos_for_day(filenames)
    if not selected:
        return None
    # The slot-3 photo (index 3 in the 6-slot list) is the noon anchor.
    # If fewer than 4 photos are selected, return the last one.
    return selected[min(NOON_SLOT, len(selected) - 1)]


def build_photo_url(r2_key: str, public_bucket_url: str) -> str:
    """Build the public URL for a photo given its R2 key (YYYY/MM/DD/filename)."""
    base = public_bucket_url.rstrip("/")
    return f"{base}/{r2_key}"


def process_photos(
    s3, photos_bucket: str, watermark: str, public_bucket_url: str
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
    for day, keys in by_day.items():
        filenames = [k.rsplit("/", 1)[-1] for k in keys]
        selected_fnames = select_photos_for_day(filenames)
        fname_to_key = {k.rsplit("/", 1)[-1]: k for k in keys}
        selected_keys = [fname_to_key[f] for f in selected_fnames]
        noon_fname = get_noon_photo(filenames)
        noon_key = fname_to_key.get(noon_fname) if noon_fname else None
        timeline[day] = {
            "date": day,
            "status": "unknown",  # filled in by sensors processor
            "photos": [build_photo_url(k, public_bucket_url) for k in selected_keys],
            "noon_photo_url": build_photo_url(noon_key, public_bucket_url) if noon_key else None,
        }

    return timeline, new_watermark
