"""
Parser for sensor data (moisture, light, water pump).
Prepares time-series data for charting.
"""

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
            timestamp = parse_timestamp(event["timestamp"])
            chart_data.append({
                "timestamp": timestamp.isoformat(),
                "duration_minutes": event.get("duration_minutes", 0),
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
            ml_dispensed = event.get("ml_dispensed", 0)
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


def get_combined_sensor_data(data_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Get all sensor data in one call for efficiency."""
    return {
        "moisture": get_moisture_data(data_dir),
        "light": get_light_data(data_dir),
        "water": get_water_data(data_dir),
    }


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
