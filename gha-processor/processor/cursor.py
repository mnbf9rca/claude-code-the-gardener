"""Load and save the processing cursor (state/current_state.json).

The cursor holds per-file watermarks. If current_state.json is missing,
all watermarks default to epoch, triggering full reprocessing of all data.
The cursor is always written LAST so a failed run replays from the previous watermark.
"""
from datetime import datetime, timezone

from processor.r2_client import get_json, put_json

EPOCH = "1970-01-01T00:00:00Z"

SENSOR_FILES = [
    "action_log.jsonl",
    "camera_usage.jsonl",
    "light_history.jsonl",
    "messages_from_human.jsonl",
    "messages_to_human.jsonl",
    "moisture_sensor_history.jsonl",
    "plant_status_history.jsonl",
    "thinking.jsonl",
    "water_pump_history.jsonl",
]


def load_cursor(s3, bucket: str) -> dict:
    """Load current_state.json, filling any missing watermarks with EPOCH."""
    state = get_json(s3, bucket, "state/current_state.json", default={})
    wm = state.setdefault("watermarks", {})

    wm.setdefault("sessions_last_modified", EPOCH)
    wm.setdefault("photos_last_modified", EPOCH)
    wm.setdefault("notes_last_modified", EPOCH)

    sensor_wm = wm.setdefault("sensor_files", {})
    for fname in SENSOR_FILES:
        sensor_wm.setdefault(fname, EPOCH)

    return state


def save_cursor(s3, bucket: str, state: dict) -> None:
    """Write updated cursor. Call this LAST — it commits the processing run."""
    state["last_run"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    put_json(s3, bucket, "state/current_state.json", state)
