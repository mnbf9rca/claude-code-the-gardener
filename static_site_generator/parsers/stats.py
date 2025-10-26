"""
Overall statistics calculator for the Claude Gardener project.
Provides high-level metrics across all data sources.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any
from collections import defaultdict


def load_jsonl(file_path: Path) -> List[Dict[str, Any]]:
    """Load a JSONL file and return list of JSON objects."""
    if not file_path.exists():
        return []

    records = []
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"Warning: Could not parse line in {file_path}: {e}")
    return records


def parse_timestamp(ts_str: str) -> datetime:
    """Parse various timestamp formats into datetime object."""
    # Handle different formats: ISO8601 with/without microseconds and timezone
    formats = [
        "%Y-%m-%dT%H:%M:%S.%f%z",  # 2025-10-22T23:10:51.276073+00:00
        "%Y-%m-%dT%H:%M:%S%z",      # 2025-10-22T23:10:51+00:00
        "%Y-%m-%dT%H:%M:%SZ",       # 2025-10-22T22:23:51Z
        "%Y-%m-%dT%H:%M:%S.%fZ",    # 2025-10-22T22:23:51.123Z
    ]

    for fmt in formats:
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue

    # Fallback: try isoformat
    try:
        return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError(f"Could not parse timestamp: {ts_str}")


def calculate_overall_stats(data_dir: Path) -> Dict[str, Any]:
    """Calculate overall project statistics."""

    stats = {
        "conversations": {},
        "sensors": {},
        "actions": {},
        "thoughts": {},
        "photos": {},
        "water": {},
        "light": {},
        "messages": {},
        "project": {},
    }

    # Conversation stats
    claude_dir = data_dir / "claude"
    if claude_dir.exists():
        conversation_files = list(claude_dir.glob("*.jsonl"))
        stats["conversations"]["total_count"] = len(conversation_files)

        total_tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
        total_messages = 0
        tool_calls = defaultdict(int)

        for conv_file in conversation_files:
            messages = load_jsonl(conv_file)
            for msg in messages:
                if msg.get("type") == "assistant" and "message" in msg:
                    total_messages += 1
                    usage = msg.get("message", {}).get("usage", {})
                    total_tokens["input"] += usage.get("input_tokens", 0)
                    total_tokens["output"] += usage.get("output_tokens", 0)
                    total_tokens["cache_read"] += usage.get("cache_read_input_tokens", 0)

                    cache_creation = usage.get("cache_creation", {})
                    if isinstance(cache_creation, dict):
                        total_tokens["cache_creation"] += cache_creation.get("ephemeral_5m_input_tokens", 0)
                        total_tokens["cache_creation"] += cache_creation.get("ephemeral_1h_input_tokens", 0)

                    # Count tool calls
                    content = msg.get("message", {}).get("content", [])
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "tool_use":
                                tool_name = item.get("name", "unknown")
                                tool_calls[tool_name] += 1

        stats["conversations"]["total_tokens"] = total_tokens
        stats["conversations"]["total_messages"] = total_messages
        stats["conversations"]["tool_calls"] = dict(tool_calls)

        # Cost estimation (approximate rates for Claude 3.5 Sonnet)
        # Input: $3/MTok, Output: $15/MTok, Cache write: $3.75/MTok, Cache read: $0.30/MTok
        input_cost = (total_tokens["input"] / 1_000_000) * 3.0
        output_cost = (total_tokens["output"] / 1_000_000) * 15.0
        cache_write_cost = (total_tokens["cache_creation"] / 1_000_000) * 3.75
        cache_read_cost = (total_tokens["cache_read"] / 1_000_000) * 0.30

        stats["conversations"]["estimated_cost_usd"] = {
            "input": round(input_cost, 2),
            "output": round(output_cost, 2),
            "cache_write": round(cache_write_cost, 2),
            "cache_read": round(cache_read_cost, 2),
            "total": round(input_cost + output_cost + cache_write_cost + cache_read_cost, 2)
        }

    # Moisture sensor stats
    moisture_file = data_dir / "moisture_sensor_history.jsonl"
    moisture_readings = load_jsonl(moisture_file)
    if moisture_readings:
        values = [r.get("value", 0) for r in moisture_readings]
        stats["sensors"]["moisture"] = {
            "total_readings": len(moisture_readings),
            "min": min(values) if values else 0,
            "max": max(values) if values else 0,
            "avg": round(sum(values) / len(values), 1) if values else 0,
            "current": values[-1] if values else 0,
        }

    # Action log stats
    action_log_file = data_dir / "action_log.jsonl"
    actions = load_jsonl(action_log_file)
    action_types = defaultdict(int)
    for action in actions:
        action_types[action.get("type", "unknown")] += 1
    stats["actions"]["by_type"] = dict(action_types)
    stats["actions"]["total"] = len(actions)

    # Thinking stats
    thinking_file = data_dir / "thinking.jsonl"
    thoughts = load_jsonl(thinking_file)
    stats["thoughts"]["total"] = len(thoughts)

    if thoughts:
        # Count unique tags
        all_tags = []
        for thought in thoughts:
            all_tags.extend(thought.get("tags", []))
        tag_counts = defaultdict(int)
        for tag in all_tags:
            tag_counts[tag] += 1
        stats["thoughts"]["top_tags"] = dict(sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10])

    # Camera stats
    camera_file = data_dir / "camera_usage.jsonl"
    photos = load_jsonl(camera_file)
    stats["photos"]["total"] = len(photos)

    # Water pump stats
    water_file = data_dir / "water_pump_history.jsonl"
    water_events = load_jsonl(water_file)
    total_ml = sum(e.get("ml_dispensed", 0) for e in water_events)
    stats["water"]["total_ml_dispensed"] = total_ml
    stats["water"]["total_events"] = len(water_events)

    # Light stats
    light_file = data_dir / "light_history.jsonl"
    light_events = load_jsonl(light_file)
    total_minutes = sum(e.get("duration_minutes", 0) for e in light_events)
    stats["light"]["total_minutes"] = total_minutes
    stats["light"]["total_hours"] = round(total_minutes / 60, 1)
    stats["light"]["total_sessions"] = len(light_events)

    # Messages from/to human
    messages_from = load_jsonl(data_dir / "messages_from_human.jsonl")
    messages_to = load_jsonl(data_dir / "messages_to_human.jsonl")
    stats["messages"]["from_human"] = len(messages_from)
    stats["messages"]["to_human"] = len(messages_to)

    # Project timeline
    all_timestamps = []

    for record_list in [moisture_readings, actions, thoughts, photos, water_events, light_events]:
        for record in record_list:
            ts_str = record.get("timestamp")
            if ts_str:
                try:
                    all_timestamps.append(parse_timestamp(ts_str))
                except (ValueError, TypeError):
                    pass

    if all_timestamps:
        all_timestamps.sort()
        stats["project"]["start_date"] = all_timestamps[0].isoformat()
        stats["project"]["end_date"] = all_timestamps[-1].isoformat()
        duration = all_timestamps[-1] - all_timestamps[0]
        stats["project"]["duration_days"] = duration.days
        stats["project"]["duration_hours"] = round(duration.total_seconds() / 3600, 1)

    return stats


def get_daily_summary(data_dir: Path) -> List[Dict[str, Any]]:
    """Get a day-by-day summary of activity."""

    daily_data = defaultdict(lambda: {
        "date": None,
        "moisture_readings": 0,
        "actions": 0,
        "thoughts": 0,
        "photos": 0,
        "water_ml": 0,
        "light_minutes": 0,
        "conversations": 0,
    })

    # Helper to extract date from timestamp
    def get_date(ts_str):
        try:
            dt = parse_timestamp(ts_str)
            return dt.date().isoformat()
        except (ValueError, TypeError):
            return None

    # Process moisture readings
    moisture_file = data_dir / "moisture_sensor_history.jsonl"
    for record in load_jsonl(moisture_file):
        date = get_date(record.get("timestamp"))
        if date:
            daily_data[date]["date"] = date
            daily_data[date]["moisture_readings"] += 1

    # Process actions
    action_file = data_dir / "action_log.jsonl"
    for record in load_jsonl(action_file):
        date = get_date(record.get("timestamp"))
        if date:
            daily_data[date]["date"] = date
            daily_data[date]["actions"] += 1

    # Process thoughts
    thinking_file = data_dir / "thinking.jsonl"
    for record in load_jsonl(thinking_file):
        date = get_date(record.get("timestamp"))
        if date:
            daily_data[date]["date"] = date
            daily_data[date]["thoughts"] += 1

    # Process photos
    camera_file = data_dir / "camera_usage.jsonl"
    for record in load_jsonl(camera_file):
        date = get_date(record.get("timestamp"))
        if date:
            daily_data[date]["date"] = date
            daily_data[date]["photos"] += 1

    # Process water
    water_file = data_dir / "water_pump_history.jsonl"
    for record in load_jsonl(water_file):
        date = get_date(record.get("timestamp"))
        if date:
            daily_data[date]["date"] = date
            daily_data[date]["water_ml"] += record.get("ml_dispensed", 0)

    # Process light
    light_file = data_dir / "light_history.jsonl"
    for record in load_jsonl(light_file):
        date = get_date(record.get("timestamp"))
        if date:
            daily_data[date]["date"] = date
            daily_data[date]["light_minutes"] += record.get("duration_minutes", 0)

    # Process conversations (count unique session IDs per day)
    claude_dir = data_dir / "claude"
    if claude_dir.exists():
        for conv_file in claude_dir.glob("*.jsonl"):
            messages = load_jsonl(conv_file)
            for msg in messages:
                # Look for the first user message (non-sidechain) to determine conversation date
                if msg.get("type") == "user" and not msg.get("isSidechain"):
                    date = get_date(msg.get("timestamp"))
                    if date:
                        daily_data[date]["date"] = date
                        daily_data[date]["conversations"] += 1
                    break

    # Convert to sorted list
    return sorted(daily_data.values(), key=lambda x: x["date"] if x["date"] else "")
