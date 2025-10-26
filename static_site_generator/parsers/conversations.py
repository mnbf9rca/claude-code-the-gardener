"""
Parser for Claude conversation JSONL files.
Extracts conversations, formats them for display, and calculates token/cost statistics.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from .stats import load_jsonl, parse_timestamp


def parse_conversation(file_path: Path) -> Optional[Dict[str, Any]]:
    """Parse a single conversation file and extract relevant data."""

    messages = load_jsonl(file_path)
    if not messages:
        return None

    # Find the session ID and metadata from first message
    session_id = messages[0].get("sessionId", file_path.stem)
    first_user_msg = next((m for m in messages if m.get("type") == "user" and not m.get("isSidechain")), None)

    if not first_user_msg:
        return None

    conversation = {
        "session_id": session_id,
        "file_path": str(file_path),
        "start_time": first_user_msg.get("timestamp"),
        "end_time": messages[-1].get("timestamp"),
        "prompt": first_user_msg.get("message", {}).get("content", ""),
        "messages": [],
        "tool_calls": [],
        "tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0},
        "message_count": 0,
        "tool_call_count": 0,
    }

    # Parse timestamps for duration calculation
    try:
        start_dt = parse_timestamp(conversation["start_time"])
        end_dt = parse_timestamp(conversation["end_time"])
        duration = end_dt - start_dt
        conversation["duration_seconds"] = int(duration.total_seconds())
        conversation["duration_human"] = format_duration(duration.total_seconds())
    except (ValueError, TypeError):
        conversation["duration_seconds"] = 0
        conversation["duration_human"] = "Unknown"

    # Process messages
    for msg in messages:
        msg_type = msg.get("type")

        # Skip warmup messages (sidechain)
        if msg.get("isSidechain"):
            continue

        if msg_type == "user":
            conversation["messages"].append({
                "role": "user",
                "timestamp": msg.get("timestamp"),
                "content": msg.get("message", {}).get("content", ""),
                "uuid": msg.get("uuid"),
            })
            conversation["message_count"] += 1

        elif msg_type == "assistant":
            assistant_msg = msg.get("message", {})
            content = assistant_msg.get("content", [])

            # Extract text and tool calls
            text_parts = []
            tool_calls = []

            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif item.get("type") == "tool_use":
                            tool_call = {
                                "id": item.get("id"),
                                "name": item.get("name"),
                                "input": item.get("input", {}),
                            }
                            tool_calls.append(tool_call)
                            conversation["tool_calls"].append(tool_call)
                            conversation["tool_call_count"] += 1

            conversation["messages"].append({
                "role": "assistant",
                "timestamp": msg.get("timestamp"),
                "content": "\n".join(text_parts) if text_parts else "",
                "tool_calls": tool_calls,
                "uuid": msg.get("uuid"),
                "model": assistant_msg.get("model"),
            })
            conversation["message_count"] += 1

            # Accumulate token usage
            usage = assistant_msg.get("usage", {})
            conversation["tokens"]["input"] += usage.get("input_tokens", 0)
            conversation["tokens"]["output"] += usage.get("output_tokens", 0)
            conversation["tokens"]["cache_read"] += usage.get("cache_read_input_tokens", 0)

            cache_creation = usage.get("cache_creation", {})
            if isinstance(cache_creation, dict):
                conversation["tokens"]["cache_creation"] += cache_creation.get("ephemeral_5m_input_tokens", 0)
                conversation["tokens"]["cache_creation"] += cache_creation.get("ephemeral_1h_input_tokens", 0)

        elif msg_type == "tool_result":
            # Add tool results to the previous assistant message
            if conversation["messages"] and conversation["messages"][-1]["role"] == "assistant":
                if "tool_results" not in conversation["messages"][-1]:
                    conversation["messages"][-1]["tool_results"] = []

                tool_result = msg.get("toolResult", {})
                conversation["messages"][-1]["tool_results"].append({
                    "tool_call_id": tool_result.get("toolUseId"),
                    "content": tool_result.get("content", []),
                    "is_error": tool_result.get("isError", False),
                })

    # Calculate cost estimate
    conversation["cost_usd"] = estimate_cost(conversation["tokens"])

    return conversation


def estimate_cost(tokens: Dict[str, int]) -> float:
    """Estimate cost in USD based on token usage (Claude 3.5 Sonnet rates)."""
    input_cost = (tokens["input"] / 1_000_000) * 3.0
    output_cost = (tokens["output"] / 1_000_000) * 15.0
    cache_write_cost = (tokens["cache_creation"] / 1_000_000) * 3.75
    cache_read_cost = (tokens["cache_read"] / 1_000_000) * 0.30

    return round(input_cost + output_cost + cache_write_cost + cache_read_cost, 4)


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m"


def get_all_conversations(data_dir: Path) -> List[Dict[str, Any]]:
    """Parse all conversation files and return sorted list."""
    claude_dir = data_dir / "claude"

    if not claude_dir.exists():
        return []

    conversations = []
    for conv_file in claude_dir.glob("*.jsonl"):
        conv = parse_conversation(conv_file)
        if conv:
            conversations.append(conv)

    # Sort by start time (newest first)
    conversations.sort(key=lambda x: x["start_time"], reverse=True)

    return conversations


def get_conversation_by_id(data_dir: Path, session_id: str) -> Optional[Dict[str, Any]]:
    """Get a single conversation by session ID."""
    claude_dir = data_dir / "claude"
    conv_file = claude_dir / f"{session_id}.jsonl"

    if not conv_file.exists():
        return None

    return parse_conversation(conv_file)


def format_tool_call_for_display(tool_call: Dict[str, Any]) -> str:
    """Format a tool call for HTML display."""
    name = tool_call.get("name", "unknown")
    input_params = tool_call.get("input", {})

    # Pretty print the input JSON
    formatted_input = json.dumps(input_params, indent=2)

    html = f'''<div class="tool-call">
  <div class="tool-name">{name}</div>
  <pre class="tool-input"><code>{formatted_input}</code></pre>
</div>'''
    return html


def get_highlights(conversations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract interesting/highlighted conversations based on various criteria."""
    highlights = []

    for conv in conversations:
        is_highlight = False
        highlight_reasons = []

        # High token usage
        total_tokens = sum(conv["tokens"].values())
        if total_tokens > 50000:
            is_highlight = True
            highlight_reasons.append(f"High token usage ({total_tokens:,} tokens)")

        # Many tool calls
        if conv["tool_call_count"] > 20:
            is_highlight = True
            highlight_reasons.append(f"Many tool calls ({conv['tool_call_count']})")

        # Long duration
        if conv["duration_seconds"] > 300:  # > 5 minutes
            is_highlight = True
            highlight_reasons.append(f"Long conversation ({conv['duration_human']})")

        # Look for interesting tool patterns
        tool_names = [tc.get("name", "") for tc in conv["tool_calls"]]

        # Water dispensed
        if any("dispense_water" in name for name in tool_names):
            is_highlight = True
            highlight_reasons.append("Water dispensed")

        # Camera used
        if any("capture_photo" in name for name in tool_names):
            is_highlight = True
            highlight_reasons.append("Photo captured")

        # Messages to human
        if any("send_message_to_human" in name for name in tool_names):
            is_highlight = True
            highlight_reasons.append("Message to human")

        if is_highlight:
            # Format highlight to match timeline highlight structure
            highlights.append({
                "type": "conversation",
                "timestamp": conv["start_time"],
                "summary": f"Conversation: {conv['tool_call_count']} tools, {conv['duration_human']}",
                "highlight_reason": ", ".join(highlight_reasons),
                "session_id": conv["session_id"],
            })

    return highlights
