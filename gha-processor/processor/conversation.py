"""Merge human↔agent messages into chronological conversation thread."""
from processor.helpers import parse_ts


def build_conversation(
    to_human: list[dict],
    from_human: list[dict],
) -> list[dict]:
    """Merge and sort messages from both directions into a single timeline.

    Each entry: {message_id, timestamp, direction, content, in_reply_to}
    Always rebuilt from scratch (no watermark needed — files are small).
    """
    entries = []

    for msg in to_human:
        entries.append({
            "message_id": msg.get("message_id", ""),
            "timestamp": msg.get("timestamp", ""),
            "direction": "to_human",
            "content": msg.get("content", ""),
            "in_reply_to": msg.get("in_reply_to"),
        })

    for msg in from_human:
        entries.append({
            "message_id": msg.get("message_id", ""),
            "timestamp": msg.get("timestamp", ""),
            "direction": "from_human",
            "content": msg.get("content", ""),
            "in_reply_to": msg.get("in_reply_to"),
        })

    # Sort chronologically; skip entries with missing timestamps
    return sorted(
        [e for e in entries if e["timestamp"]],
        key=lambda e: parse_ts(e["timestamp"]),
    )
