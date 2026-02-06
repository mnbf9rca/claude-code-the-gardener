"""
Parser for sensor data (moisture, light, water pump).
Prepares time-series data for charting.
"""

import json
from pathlib import Path
from typing import Dict, List, Any
from .stats import load_jsonl, parse_timestamp


def get_moisture_data(data_dir: Path) -> List[Dict[str, Any]]:
    """Get moisture sensor readings formatted for charting."""
    moisture_file = data_dir / "moisture_sensor_history.jsonl"
    readings = load_jsonl(moisture_file)

    # Format for Chart.js
    chart_data = []
    for reading in readings:
        try:
            timestamp = parse_timestamp(reading["timestamp"])
            chart_data.append({
                "timestamp": timestamp.isoformat(),
                "value": reading["value"],
                "unix": int(timestamp.timestamp() * 1000),  # milliseconds for JS
            })
        except (ValueError, TypeError, KeyError):
            continue

    return sorted(chart_data, key=lambda x: x["unix"])


def get_light_data(data_dir: Path) -> List[Dict[str, Any]]:
    """Get light activation history formatted for charting."""
    light_file = data_dir / "light_history.jsonl"
    events = load_jsonl(light_file)

    chart_data = []
    for event in events:
        try:
            duration_minutes = event.get("duration_minutes", 0)
            # Only include events with actual duration (filter out turn_off, recovery events)
            if duration_minutes <= 0:
                continue

            timestamp = parse_timestamp(event["timestamp"])
            chart_data.append({
                "timestamp": timestamp.isoformat(),
                "duration_minutes": duration_minutes,
                "unix": int(timestamp.timestamp() * 1000),
                "action": event.get("action", "unknown"),
            })
        except (ValueError, TypeError, KeyError):
            continue

    return sorted(chart_data, key=lambda x: x["unix"])


def get_water_data(data_dir: Path) -> List[Dict[str, Any]]:
    """Get water pump history formatted for charting."""
    water_file = data_dir / "water_pump_history.jsonl"
    events = load_jsonl(water_file)

    chart_data = []
    cumulative_ml = 0

    for event in events:
        try:
            timestamp = parse_timestamp(event["timestamp"])
            ml_dispensed = event.get("ml", 0)
            cumulative_ml += ml_dispensed

            chart_data.append({
                "timestamp": timestamp.isoformat(),
                "ml_dispensed": ml_dispensed,
                "cumulative_ml": cumulative_ml,
                "unix": int(timestamp.timestamp() * 1000),
            })
        except (ValueError, TypeError, KeyError):
            continue

    return sorted(chart_data, key=lambda x: x["unix"])


def get_conversation_analytics(conversations: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Generate time-series data from conversations for analytics charts."""

    # Sort conversations by start time
    sorted_convs = sorted(conversations, key=lambda c: c.get("start_time", ""))

    cost_data = []
    tokens_data = []
    thoughts_data = []
    actions_data = []
    cumulative_cost = 0
    cumulative_thoughts = 0
    cumulative_actions = 0

    for conv in sorted_convs:
        try:
            timestamp = parse_timestamp(conv["start_time"])
            unix_ms = int(timestamp.timestamp() * 1000)

            # Cost accumulation
            cost = conv.get("cost_usd", 0)
            cumulative_cost += cost
            cost_data.append({
                "timestamp": timestamp.isoformat(),
                "cost": cost,
                "cumulative_cost": cumulative_cost,
                "unix": unix_ms,
            })

            # Tokens by type
            tokens = conv.get("tokens", {})
            tokens_data.append({
                "timestamp": timestamp.isoformat(),
                "input": tokens.get("input", 0),
                "output": tokens.get("output", 0),
                "cache_read": tokens.get("cache_read", 0),
                "cache_creation": tokens.get("cache_creation", 0),
                "unix": unix_ms,
            })

            # Count thoughts and actions from messages
            thought_count = 0
            action_count = 0

            for msg in conv.get("messages", []):
                for tool_call in msg.get("tool_calls", []):
                    tool_name = tool_call.get("name", "")
                    if "log_thought" in tool_name:
                        thought_count += 1
                    elif "log_action" in tool_name:
                        action_count += 1

            cumulative_thoughts += thought_count
            cumulative_actions += action_count

            thoughts_data.append({
                "timestamp": timestamp.isoformat(),
                "count": thought_count,
                "cumulative": cumulative_thoughts,
                "unix": unix_ms,
            })

            actions_data.append({
                "timestamp": timestamp.isoformat(),
                "count": action_count,
                "cumulative": cumulative_actions,
                "unix": unix_ms,
            })

        except (ValueError, TypeError, KeyError):
            continue

    return {
        "cost": cost_data,
        "tokens": tokens_data,
        "thoughts": thoughts_data,
        "actions": actions_data,
    }


def get_combined_sensor_data(data_dir: Path, conversations: List[Dict[str, Any]] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Get all sensor and conversation analytics data in one call for efficiency."""
    data = {
        "moisture": get_moisture_data(data_dir),
        "light": get_light_data(data_dir),
        "water": get_water_data(data_dir),
    }

    # Add conversation analytics if provided
    if conversations:
        analytics = get_conversation_analytics(conversations)
        data.update(analytics)

    return data


def get_sensor_summary(data_dir: Path) -> Dict[str, Any]:
    """Get current sensor status and recent trends."""

    moisture = get_moisture_data(data_dir)
    light = get_light_data(data_dir)
    water = get_water_data(data_dir)

    summary = {
        "moisture": {
            "current": moisture[-1]["value"] if moisture else None,
            "trend": calculate_trend([r["value"] for r in moisture[-10:]]) if len(moisture) >= 10 else "unknown",
            "last_reading": moisture[-1]["timestamp"] if moisture else None,
        },
        "light": {
            "last_activation": light[-1]["timestamp"] if light else None,
            "last_duration": light[-1]["duration_minutes"] if light else 0,
            "total_sessions": len(light),
        },
        "water": {
            "last_watering": water[-1]["timestamp"] if water else None,
            "last_amount": water[-1]["ml_dispensed"] if water else 0,
            "total_ml": water[-1]["cumulative_ml"] if water else 0,
            "total_events": len(water),
        }
    }

    return summary


def calculate_trend(values: List[float]) -> str:
    """Calculate simple trend direction from a list of values."""
    if len(values) < 2:
        return "unknown"

    # Compare first half average to second half average
    mid = len(values) // 2
    first_half_avg = sum(values[:mid]) / mid
    second_half_avg = sum(values[mid:]) / (len(values) - mid)

    diff = second_half_avg - first_half_avg
    percent_change = (diff / first_half_avg) * 100

    if percent_change > 5:
        return "increasing"
    elif percent_change < -5:
        return "decreasing"
    else:
        return "stable"


def parse_sensors(data_dir: Path) -> dict:
    """
    Parse sensor data and return for Chart.js consumption.

    Args:
        data_dir: Path to data directory

    Returns:
        dict with keys: moisture, light, water
    """
    sensors = {
        "moisture": [],
        "light": [],
        "water": []
    }

    # Parse moisture sensor
    moisture_file = data_dir / "moisture_sensor_history.jsonl"
    if moisture_file.exists():
        with open(moisture_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    sensors["moisture"].append({
                        "timestamp": event.get("timestamp"),
                        "value": event.get("raw_value", 0)
                    })
                except json.JSONDecodeError as e:
                    import sys
                    print(f"Warning: Skipping malformed JSON in {moisture_file}: {e}", file=sys.stderr)
                    continue

    # Parse light history
    light_file = data_dir / "light_history.jsonl"
    if light_file.exists():
        with open(light_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    sensors["light"].append({
                        "timestamp": event.get("timestamp"),
                        "action": event.get("action", "unknown"),
                        "duration_minutes": event.get("duration_minutes", 0)
                    })
                except json.JSONDecodeError as e:
                    import sys
                    print(f"Warning: Skipping malformed JSON in {light_file}: {e}", file=sys.stderr)
                    continue

    # Parse water pump
    water_file = data_dir / "water_pump_history.jsonl"
    if water_file.exists():
        with open(water_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    sensors["water"].append({
                        "timestamp": event.get("timestamp"),
                        "ml_dispensed": event.get("ml", 0)
                    })
                except json.JSONDecodeError as e:
                    import sys
                    print(f"Warning: Skipping malformed JSON in {water_file}: {e}", file=sys.stderr)
                    continue

    return sensors
