"""Main entrypoint for GHA data processor.

Reads raw/ from R2, writes state/ to R2.
Cursor in state/current_state.json ensures fault-tolerant incremental processing.
"""
import os
from datetime import datetime, timezone

from processor.conversation import build_conversation
from processor.cursor import load_cursor, save_cursor
from processor.photos import process_photos
from processor.r2_client import (
    get_json,
    get_jsonl_lines,
    get_s3_client,
    put_json,
)
from processor.sensors import (
    bucket_records_by_day,
    build_hourly_stats,
    merge_daily_stats,
    read_sensor_file,
)
from processor.sessions import load_pricing, process_sessions

BUCKET = os.environ["R2_BUCKET_NAME"]
PHOTOS_BUCKET = os.environ["R2_PHOTOS_BUCKET_NAME"]
PUBLIC_URL = os.environ["R2_PHOTOS_PUBLIC_URL"]


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def main() -> None:
    s3 = get_s3_client()
    pricing = load_pricing()

    log("=== Gardener Processor Start ===")

    # ── Load cursor ─────────────────────────────────────────────────────────
    state = load_cursor(s3, BUCKET)
    wm = state["watermarks"]
    log(f"Cursor loaded. Last run: {state.get('last_run', 'never')}")

    # ── 1. Sessions → ai_stats.json ─────────────────────────────────────────
    log("Processing sessions...")
    existing_ai_stats = get_json(s3, BUCKET, "state/ai_stats.json", default={})
    new_ai_by_date, new_sessions_wm = process_sessions(
        s3, BUCKET, wm["sessions_last_modified"], pricing
    )
    # Merge new days into existing (new data overwrites same-date entries)
    merged_ai = {**existing_ai_stats, **new_ai_by_date}
    put_json(s3, BUCKET, "state/ai_stats.json", merged_ai)
    wm["sessions_last_modified"] = new_sessions_wm
    log(f"ai_stats.json written ({len(merged_ai)} days)")

    # ── 2. Sensor files → sensor_stats_daily.json + sensor_stats_hourly.json ─
    log("Processing sensor files...")
    existing_daily = get_json(s3, BUCKET, "state/sensor_stats_daily.json", default={})
    new_by_type: dict[str, dict[str, list]] = {
        "moisture": {}, "light": {}, "water": {}, "plant_status": {}
    }

    sensor_map = {
        "moisture_sensor_history.jsonl": ("moisture", "value"),
        "light_history.jsonl": ("light", None),
        "water_pump_history.jsonl": ("water", None),
        "plant_status_history.jsonl": ("plant_status", None),
    }

    for fname, (category, _value_field) in sensor_map.items():
        wm_key = fname
        records = read_sensor_file(s3, BUCKET, fname)
        bucketed = bucket_records_by_day(records, watermark=wm["sensor_files"][wm_key])
        new_by_type[category] = bucketed
        # Update watermark to latest record timestamp seen
        if records:
            latest_ts = max(
                (r.get("timestamp", "") for r in records if r.get("timestamp")),
                default="",
            )
            if latest_ts > wm["sensor_files"][wm_key]:
                wm["sensor_files"][wm_key] = latest_ts
        log(f"  {fname}: {sum(len(v) for v in bucketed.values())} new records")

    merged_daily = merge_daily_stats(existing_daily, new_by_type)
    put_json(s3, BUCKET, "state/sensor_stats_daily.json", merged_daily)

    hourly = build_hourly_stats(merged_daily, new_by_type)
    put_json(s3, BUCKET, "state/sensor_stats_hourly.json", hourly)
    log(f"sensor_stats_daily.json ({len(merged_daily)} days), hourly ({len(hourly)} hours)")

    # ── 3. Photos → plant_timeline.json + day_index.json ────────────────────
    log("Processing photos...")
    timeline, new_photos_wm = process_photos(
        s3, PHOTOS_BUCKET, wm["photos_last_modified"], PUBLIC_URL
    )
    wm["photos_last_modified"] = new_photos_wm

    # Enrich timeline entries with plant status from daily sensor stats
    for date, entry in timeline.items():
        if date in merged_daily:
            entry["status"] = merged_daily[date]["plant_status"]["dominant"]

    # Sort by date for consistent output
    timeline_sorted = dict(sorted(timeline.items()))
    put_json(s3, BUCKET, "state/plant_timeline.json", timeline_sorted)

    # Build day_index: lightweight per-day summary for grid view
    day_index = {
        date: {
            "date": date,
            "status": entry.get("status", "unknown"),
            "photo_url": entry.get("noon_photo_url"),
            "has_watering": bool(
                merged_daily.get(date, {}).get("water", {}).get("total_ml", 0)
            ),
        }
        for date, entry in timeline_sorted.items()
    }
    put_json(s3, BUCKET, "state/day_index.json", day_index)
    log(f"plant_timeline.json ({len(timeline_sorted)} days), day_index.json")

    # ── 4. Per-day detail files (state/day/YYYY-MM-DD.json) ─────────────────
    log("Building day detail files...")
    # Read moisture once (avoid one S3 GET per day)
    moisture_all = read_sensor_file(s3, BUCKET, "moisture_sensor_history.jsonl")
    moisture_by_date: dict[str, list] = {}
    for r in moisture_all:
        d = r.get("timestamp", "")[:10]
        if d:
            moisture_by_date.setdefault(d, []).append(r)

    for date in sorted(set(list(merged_daily.keys()) + list(timeline_sorted.keys()))):
        day_data = merged_daily.get(date, {})
        tl_entry = timeline_sorted.get(date, {})
        day_detail = {
            "date": date,
            "status": day_data.get("plant_status", {}).get("dominant", "unknown"),
            "photos": tl_entry.get("photos", []),
            "moisture_readings": [
                {"timestamp": r["timestamp"], "value": r["value"]}
                for r in moisture_by_date.get(date, [])
                if r.get("timestamp") and "value" in r
            ],
            "light_events": day_data.get("light", {}).get("events", []),
            "water_events": day_data.get("water", {}).get("events", []),
            "messages_to_human": [],    # filled from conversation below
            "messages_from_human": [],
            "agent_summary": None,      # reserved for future MCP tool
            "token_usage": merged_ai.get(date, {}),
            "estimated_cost_usd": merged_ai.get(date, {}).get("estimated_cost_usd", 0.0),
            "sessions": merged_ai.get(date, {}).get("sessions", 0),
        }
        put_json(s3, BUCKET, f"state/day/{date}.json", day_detail)
    log("Day detail files written")

    # ── 5. Conversation → conversation.json ──────────────────────────────────
    log("Building conversation.json...")
    to_human = get_jsonl_lines(s3, BUCKET, "raw/data/messages_to_human.jsonl")
    from_human = get_jsonl_lines(s3, BUCKET, "raw/data/messages_from_human.jsonl")
    conversation = build_conversation(to_human, from_human)
    put_json(s3, BUCKET, "state/conversation.json", conversation)
    log(f"conversation.json ({len(conversation)} messages)")

    # ── 6. current_state.json — ALWAYS LAST ─────────────────────────────────
    # Update display fields from latest data
    if timeline_sorted:
        latest_date = max(timeline_sorted.keys())
        latest_tl = timeline_sorted[latest_date]
        state["plant_status"] = latest_tl.get("status", "unknown")
        state["latest_photo_url"] = latest_tl.get("noon_photo_url")
    agent_msgs = [m for m in conversation if m.get("direction") == "to_human"]
    if agent_msgs:
        last_agent = agent_msgs[-1]
        state["last_agent_message"] = {
            "timestamp": last_agent["timestamp"],
            "content": last_agent["content"][:200],
        }

    state["watermarks"] = wm
    save_cursor(s3, BUCKET, state)
    log("=== Processing complete. Cursor saved. ===")


if __name__ == "__main__":
    main()
