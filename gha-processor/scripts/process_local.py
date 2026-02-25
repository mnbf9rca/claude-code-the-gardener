#!/usr/bin/env python3
"""Local filesystem runner for the gardener data processor.

Reads raw data from a local tmp/ directory (no S3/R2 required) and writes
derived state JSON files to state/ for local inspection.

Intentionally absent outputs (require a photos bucket not present locally):
    state/plant_timeline.json
    state/day_index.json

Usage:
    uv run python scripts/process_local.py
    uv run python scripts/process_local.py --tmp-dir ./tmp --state-dir ./state
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

# ── Logging ─────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


# ── Filesystem I/O helpers ──────────────────────────────────────────────────

def read_jsonl(path: Path) -> list[dict]:
    """Read and parse a JSONL file. Skips blank/malformed lines."""
    if not path.exists():
        log(f"  (skip) {path} not found")
        return []
    lines = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                lines.append(json.loads(raw))
            except json.JSONDecodeError:
                log(f"  WARNING: skipping malformed line in {path}: {raw[:80]!r}")
    return lines


def write_json(path: Path, data) -> None:
    """Write data as pretty-printed JSON, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    log(f"  wrote {path} ({path.stat().st_size:,} bytes)")


# ── Local session processing ─────────────────────────────────────────────────

def process_sessions_local(session_dir: Path, pricing: dict) -> dict:
    """Process all session JSONL files from a flat directory.

    Uses each file's mtime as its session date, mirroring the R2 processor's
    use of S3 LastModified for date bucketing.

    Note: if files were bulk-synced via rclone without --update, all mtimes may
    be identical, causing all sessions to bucket into a single day. The data is
    still correct; only the per-day breakdown is affected.

    Returns: {date_str: {sessions, input_tokens, output_tokens, ...}}
    """
    from processor.sessions import parse_session_stats

    ai_stats: dict[str, dict] = {}

    if not session_dir.exists():
        log(f"  Session dir {session_dir} not found — skipping")
        return ai_stats

    files = sorted(session_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    log(f"  Found {len(files)} session files")

    skipped = 0
    for path in files:
        lines = read_jsonl(path)
        if not lines:
            skipped += 1
            continue

        # Use file mtime as session date (mirrors R2 processor's LastModified)
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        date = mtime.strftime("%Y-%m-%d")

        stats = parse_session_stats(lines, pricing)
        day = ai_stats.setdefault(date, {
            "sessions": 0, "input_tokens": 0, "output_tokens": 0,
            "cache_read_tokens": 0, "cache_write_tokens": 0,
            "estimated_cost_usd": 0.0, "tool_calls": {},
        })
        day["sessions"] += 1
        day["input_tokens"]       += stats["input_tokens"]
        day["output_tokens"]      += stats["output_tokens"]
        day["cache_read_tokens"]  += stats["cache_read_tokens"]
        day["cache_write_tokens"] += stats["cache_write_tokens"]
        day["estimated_cost_usd"] = round(
            day["estimated_cost_usd"] + stats["cost_usd"], 6
        )
        for tool, count in stats["tool_calls"].items():
            day["tool_calls"][tool] = day["tool_calls"].get(tool, 0) + count

    if skipped:
        log(f"  Skipped {skipped} empty/malformed session files")

    return ai_stats


# ── Main ─────────────────────────────────────────────────────────────────────

def main(tmp_dir: Path, state_dir: Path) -> None:
    from processor.conversation import build_conversation
    from processor.sensors import (
        bucket_records_by_day,
        build_hourly_stats,
        merge_daily_stats,
    )
    from processor.sessions import load_pricing

    data_dir = tmp_dir / "data"
    session_dir = tmp_dir / "projects" / "-home-gardener-workspace"

    log("=== Gardener Local Processor Start ===")
    log(f"  Data dir:    {data_dir}")
    log(f"  Session dir: {session_dir}")
    log(f"  Output dir:  {state_dir}")

    pricing = load_pricing()

    # ── 1. Sessions → ai_stats.json ─────────────────────────────────────────
    log("Processing sessions...")
    ai_by_date = process_sessions_local(session_dir, pricing)
    write_json(state_dir / "ai_stats.json", ai_by_date)
    log(f"ai_stats.json: {len(ai_by_date)} days")

    # ── 2. Sensor files → sensor_stats_daily.json + sensor_stats_hourly.json ─
    log("Processing sensor files...")
    # Matches main.py sensor_map structure; _value_field unused but kept for alignment.
    sensor_map = {
        "moisture_sensor_history.jsonl": ("moisture", "value"),
        "light_history.jsonl": ("light", None),
        "water_pump_history.jsonl": ("water", None),
        "plant_status_history.jsonl": ("plant_status", None),
    }
    new_by_type: dict[str, dict[str, list]] = {
        "moisture": {}, "light": {}, "water": {}, "plant_status": {}
    }

    for fname, (category, _value_field) in sensor_map.items():
        records = read_jsonl(data_dir / fname)
        # No watermark: local run always processes full history (no incremental state).
        bucketed = bucket_records_by_day(records)
        new_by_type[category] = bucketed
        n_records = sum(len(v) for v in bucketed.values())
        log(f"  {fname}: {n_records} records across {len(bucketed)} days")

    merged_daily = merge_daily_stats({}, new_by_type)
    write_json(state_dir / "sensor_stats_daily.json", merged_daily)

    # cutoff_days=9999 so all historical records are included in the hourly file
    # (production uses 7 days to keep the file small; no such constraint locally).
    hourly = build_hourly_stats(merged_daily, new_by_type, cutoff_days=9999)
    write_json(state_dir / "sensor_stats_hourly.json", hourly)
    log(f"sensor_stats_daily.json: {len(merged_daily)} days, hourly: {len(hourly)} hours")

    # ── 3. Conversation → conversation.json ──────────────────────────────────
    log("Building conversation.json...")
    to_human = read_jsonl(data_dir / "messages_to_human.jsonl")
    from_human = read_jsonl(data_dir / "messages_from_human.jsonl")
    conversation = build_conversation(to_human, from_human)
    write_json(state_dir / "conversation.json", conversation)
    log(f"conversation.json: {len(conversation)} messages")

    # ── 4. Per-day detail files (state/day/YYYY-MM-DD.json) ─────────────────
    log("Building day detail files...")
    # Read moisture once to avoid re-scanning the file per day.
    moisture_all = read_jsonl(data_dir / "moisture_sensor_history.jsonl")
    moisture_by_date: dict[str, list] = {}
    for r in moisture_all:
        d = r.get("timestamp", "")[:10]
        if d:
            moisture_by_date.setdefault(d, []).append(r)

    for date in sorted(merged_daily.keys()):
        day_data = merged_daily[date]
        day_detail = {
            "date": date,
            "status": day_data.get("plant_status", {}).get("dominant", "unknown"),
            "photos": [],           # no photos bucket in local tmp/
            "moisture_readings": [
                {"timestamp": r["timestamp"], "value": r["value"]}
                for r in moisture_by_date.get(date, [])
                if r.get("timestamp") and "value" in r
            ],
            "light_events": day_data.get("light", {}).get("events", []),
            "water_events": day_data.get("water", {}).get("events", []),
            "messages_to_human": [],
            "messages_from_human": [],
            "agent_summary": None,
            "token_usage": ai_by_date.get(date, {}),
            "estimated_cost_usd": ai_by_date.get(date, {}).get("estimated_cost_usd", 0.0),
            "sessions": ai_by_date.get(date, {}).get("sessions", 0),
        }
        write_json(state_dir / "day" / f"{date}.json", day_detail)

    log(f"Day detail files: {len(merged_daily)}")
    log("=== Local processing complete ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local gardener data processor (no S3)")
    parser.add_argument(
        "--tmp-dir", type=Path, default=Path("tmp"),
        help="Path to local data directory (default: ./tmp)",
    )
    parser.add_argument(
        "--state-dir", type=Path, default=Path("state"),
        help="Output directory for state JSON files (default: ./state)",
    )
    args = parser.parse_args()
    main(args.tmp_dir, args.state_dir)
