"""
Parser for action logs and timeline generation.
Combines all events (actions, thoughts, sensor readings) into a unified timeline.
"""

from pathlib import Path
from typing import Dict, List, Any
from .stats import load_jsonl, parse_timestamp


def get_action_log(data_dir: Path) -> List[Dict[str, Any]]:
    """Get all action log entries."""
    action_file = data_dir / "action_log.jsonl"
    return load_jsonl(action_file)


def get_thinking_log(data_dir: Path) -> List[Dict[str, Any]]:
    """Get all thinking log entries."""
    thinking_file = data_dir / "thinking.jsonl"
    return load_jsonl(thinking_file)


def correlate_timeline_with_conversations(timeline: List[Dict[str, Any]], conversations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Add conversation context to timeline events by matching timestamps.

    For each timeline event, finds the conversation that was active at that time
    and adds session_id for linking.
    """
    for event in timeline:
        event_time = parse_timestamp(event["timestamp"])

        # Find conversation that contains this timestamp
        for conv in conversations:
            try:
                start_time = parse_timestamp(conv["start_time"])
                end_time = parse_timestamp(conv["end_time"])

                if start_time <= event_time <= end_time:
                    event["session_id"] = conv["session_id"]
                    break
            except (ValueError, TypeError, KeyError):
                continue

    return timeline


def get_unified_timeline(data_dir: Path) -> List[Dict[str, Any]]:
    """Create a unified timeline of all events for visualization."""

    timeline = []

    # Add actions
    actions = get_action_log(data_dir)
    for action in actions:
        try:
            timestamp = parse_timestamp(action["timestamp"])
            timeline.append({
                "type": "action",
                "subtype": action.get("type", "unknown"),
                "timestamp": action["timestamp"],
                "unix": int(timestamp.timestamp() * 1000),
                "data": action.get("details", {}),
                "summary": create_action_summary(action),
            })
        except (ValueError, TypeError, KeyError):
            continue

    # Add thoughts
    thoughts = get_thinking_log(data_dir)
    for thought in thoughts:
        try:
            timestamp = parse_timestamp(thought["timestamp"])
            timeline.append({
                "type": "thought",
                "timestamp": thought["timestamp"],
                "unix": int(timestamp.timestamp() * 1000),
                "data": thought,
                "summary": thought.get("hypothesis", "")[:100] + "..." if len(thought.get("hypothesis", "")) > 100 else thought.get("hypothesis", ""),
                "tags": thought.get("tags", []),
            })
        except (ValueError, TypeError, KeyError):
            continue

    # Add photos
    camera_file = data_dir / "camera_usage.jsonl"
    photos = load_jsonl(camera_file)
    for photo in photos:
        try:
            timestamp = parse_timestamp(photo["timestamp"])
            timeline.append({
                "type": "photo",
                "timestamp": photo["timestamp"],
                "unix": int(timestamp.timestamp() * 1000),
                "data": photo,
                "summary": "Photo captured",
            })
        except (ValueError, TypeError, KeyError):
            continue

    # Add water events
    water_file = data_dir / "water_pump_history.jsonl"
    water_events = load_jsonl(water_file)
    for event in water_events:
        try:
            timestamp = parse_timestamp(event["timestamp"])
            timeline.append({
                "type": "water",
                "timestamp": event["timestamp"],
                "unix": int(timestamp.timestamp() * 1000),
                "data": event,
                "summary": f"Dispensed {event.get('ml_dispensed', 0)}ml water",
            })
        except (ValueError, TypeError, KeyError):
            continue

    # Add light events
    light_file = data_dir / "light_history.jsonl"
    light_events = load_jsonl(light_file)
    for event in light_events:
        try:
            timestamp = parse_timestamp(event["timestamp"])
            action = event.get("action", "unknown")
            duration = event.get("duration_minutes", 0)

            timeline.append({
                "type": "light",
                "timestamp": event["timestamp"],
                "unix": int(timestamp.timestamp() * 1000),
                "data": event,
                "summary": f"Light {action} ({duration}min)" if action == "activated" else f"Light {action}",
            })
        except (ValueError, TypeError, KeyError):
            continue

    # Add messages to/from human
    messages_to = load_jsonl(data_dir / "messages_to_human.jsonl")
    for msg in messages_to:
        try:
            timestamp = parse_timestamp(msg["timestamp"])
            timeline.append({
                "type": "message",
                "subtype": "to_human",
                "timestamp": msg["timestamp"],
                "unix": int(timestamp.timestamp() * 1000),
                "data": msg,
                "summary": msg.get("message", "")[:100] + "..." if len(msg.get("message", "")) > 100 else msg.get("message", ""),
            })
        except (ValueError, TypeError, KeyError):
            continue

    messages_from = load_jsonl(data_dir / "messages_from_human.jsonl")
    for msg in messages_from:
        try:
            timestamp = parse_timestamp(msg["timestamp"])
            timeline.append({
                "type": "message",
                "subtype": "from_human",
                "timestamp": msg["timestamp"],
                "unix": int(timestamp.timestamp() * 1000),
                "data": msg,
                "summary": msg.get("content", "")[:100] + "..." if len(msg.get("content", "")) > 100 else msg.get("content", ""),
            })
        except (ValueError, TypeError, KeyError):
            continue

    # Sort by timestamp (newest first)
    timeline.sort(key=lambda x: x["unix"], reverse=True)

    return timeline


def create_action_summary(action: Dict[str, Any]) -> str:
    """Create a human-readable summary of an action."""
    action_type = action.get("type", "unknown")
    details = action.get("details", {})

    if action_type == "water":
        if isinstance(details, dict):
            ml = details.get("ml_dispensed", "unknown")
            return f"Dispensed {ml}ml water"
        return f"Water action: {details}"

    elif action_type == "light":
        if isinstance(details, dict):
            action = details.get("action", "unknown")
            duration = details.get("duration_minutes", 0)
            if action == "activated":
                return f"Light activated ({duration}min)"
            else:
                return f"Light {action}"
        return f"Light action: {details}"

    elif action_type == "observe":
        if isinstance(details, dict):
            # Extract key observation details
            moisture = details.get("moisture")
            plant_health = details.get("plant_health")
            action = details.get("action")
            next_action = details.get("next_action")

            summary_parts = []
            if action:
                summary_parts.append(f"Action: {action}")
            if plant_health:
                summary_parts.append(f"Health: {plant_health}")
            if moisture:
                summary_parts.append(f"Moisture: {moisture}")
            if next_action:
                summary_parts.append(f"Next: {next_action}")

            if summary_parts:
                return "Observation - " + ", ".join(summary_parts)

            # Fallback: try to create a readable summary from available keys
            return f"Observation recorded ({len(details)} data points)"
        return f"Observation: {details}"

    elif action_type == "alert":
        if isinstance(details, dict):
            message = details.get("message", details.get("alert", "Alert triggered"))
            return f"Alert: {message}"
        return f"Alert: {details}"

    else:
        # Generic handler for unknown action types
        if isinstance(details, dict) and details:
            # Try to extract a meaningful summary
            if "message" in details:
                return f"{action_type}: {details['message']}"
            elif len(details) <= 3:
                # Small dict - show key-value pairs
                pairs = [f"{k}={v}" for k, v in details.items()]
                return f"{action_type}: {', '.join(pairs)}"
            else:
                return f"{action_type} ({len(details)} details)"
        return f"{action_type}: {details}"


def detect_highlights(timeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect interesting moments in the timeline."""
    highlights = []

    # Look for first occurrences
    first_water = next((e for e in reversed(timeline) if e["type"] == "water"), None)
    if first_water:
        highlights.append({
            **first_water,
            "highlight_reason": "First water dispensed",
        })

    first_photo = next((e for e in reversed(timeline) if e["type"] == "photo"), None)
    if first_photo:
        highlights.append({
            **first_photo,
            "highlight_reason": "First photo captured",
        })

    # Look for messages to human (always interesting)
    messages_to_human = [e for e in timeline if e.get("type") == "message" and e.get("subtype") == "to_human"]
    for msg in messages_to_human:
        highlights.append({
            **msg,
            "highlight_reason": "Message to human",
        })

    # Look for repeated concerns in thoughts (same tags appearing frequently)
    thought_tags = {}
    for event in timeline:
        if event["type"] == "thought":
            for tag in event.get("tags", []):
                if tag not in thought_tags:
                    thought_tags[tag] = []
                thought_tags[tag].append(event)

    for tag, events in thought_tags.items():
        if len(events) >= 5:  # Tag appears 5+ times
            # Add the most recent one as a highlight
            highlights.append({
                **events[0],
                "highlight_reason": f"Repeated concern: {tag} ({len(events)} times)",
            })

    return highlights
