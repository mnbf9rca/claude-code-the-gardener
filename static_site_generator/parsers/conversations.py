"""
Parser for Claude conversation JSONL files.
Extracts conversations, formats them for display, and calculates token/cost statistics.
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from .stats import load_jsonl, parse_timestamp
from .formatting_utils import markdown_to_html, format_field_value
from .tool_formatters import format_tool_input as format_tool_input_registry


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
            # Check if this is a tool result (has toolUseResult key)
            if "toolUseResult" in msg:
                tool_result = msg.get("toolUseResult")
                if isinstance(tool_result, str):
                    # Parse JSON string
                    try:
                        tool_result = json.loads(tool_result)
                    except Exception:
                        pass

                # Get tool use ID from the message content
                tool_use_id = None
                message_content = msg.get("message", {}).get("content", [])
                if isinstance(message_content, list):
                    for item in message_content:
                        if isinstance(item, dict) and item.get("type") == "tool_result":
                            tool_use_id = item.get("tool_use_id")
                            break

                if tool_use_id:
                    # Search backwards through ALL assistant messages to find the matching tool call
                    found = False
                    for assistant_msg in reversed(conversation["messages"]):
                        if assistant_msg["role"] == "assistant" and not found:
                            for tool_call in assistant_msg.get("tool_calls", []):
                                if tool_call.get("id") == tool_use_id:
                                    content = tool_result if isinstance(tool_result, (dict, list, str)) else str(tool_result)
                                    tool_call["result"] = {
                                        "content": content,
                                        "content_html": format_tool_result(tool_call["name"], content),
                                        "is_error": False,
                                    }
                                    found = True
                                    break
            else:
                # Regular user message (not a tool result)
                content = msg.get("message", {}).get("content", "")

                # Content can be a string or a list (like assistant messages)
                if isinstance(content, list):
                    text_parts = [
                        item.get("text", "")
                        for item in content
                        if isinstance(item, dict)
                        and item.get("type") == "text"
                    ]
                    content_text = "\n".join(text_parts) if text_parts else ""
                else:
                    # It's already a string
                    content_text = content

                conversation["messages"].append({
                    "role": "user",
                    "timestamp": msg.get("timestamp"),
                    "content": content_text,
                    "content_html": markdown_to_html(content_text) if content_text else "",
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

            content_text = "\n".join(text_parts) if text_parts else ""

            # Add formatted HTML for tool calls
            for tool_call in tool_calls:
                tool_call["input_html"] = format_tool_input(tool_call["name"], tool_call["input"])

            conversation["messages"].append({
                "role": "assistant",
                "timestamp": msg.get("timestamp"),
                "content": content_text,
                "content_html": markdown_to_html(content_text) if content_text else "",
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

    # Calculate cost estimate
    conversation["cost_usd"] = estimate_cost(conversation["tokens"])

    # Extract last assistant message for snippet
    last_assistant_text = ""
    for msg in reversed(conversation["messages"]):
        if msg["role"] == "assistant" and msg.get("content"):
            last_assistant_text = msg["content"]
            break
    conversation["last_assistant_message"] = last_assistant_text
    conversation["last_assistant_message_html"] = markdown_to_html(last_assistant_text) if last_assistant_text else ""

    # Count tool calls by type (strip mcp prefix)
    tool_counts = {}
    for tool_call in conversation["tool_calls"]:
        tool_name = tool_call.get("name", "unknown")
        # Strip MCP prefixes like mcp__plant-tools__
        tool_name = tool_name.replace("mcp__plant-tools__", "")
        tool_name = tool_name.replace("mcp__", "")
        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
    conversation["tool_counts"] = tool_counts

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


def get_all_conversations(conversations_dir: Path) -> List[Dict[str, Any]]:
    """Parse all conversation files and return sorted list."""
    if not conversations_dir.exists():
        return []

    conversations = []
    for conv_file in conversations_dir.glob("*.jsonl"):
        if conv := parse_conversation(conv_file):
            conversations.append(conv)

    # Sort by start time (newest first)
    conversations.sort(key=lambda x: x["start_time"], reverse=True)

    return conversations


def get_conversation_by_id(data_dir: Path, session_id: str) -> Optional[Dict[str, Any]]:
    """Get a single conversation by session ID."""
    claude_dir = data_dir / "claude"
    conv_file = claude_dir / f"{session_id}.jsonl"

    return None if not conv_file.exists() else parse_conversation(conv_file)


def format_tool_call_for_display(tool_call: Dict[str, Any]) -> str:
    """Format a tool call for HTML display."""
    name = tool_call.get("name", "unknown")
    input_params = tool_call.get("input", {})

    # Pretty print the input JSON
    formatted_input = json.dumps(input_params, indent=2)

    return f'''<div class="tool-call">
  <div class="tool-name">{name}</div>
  <pre class="tool-input"><code>{formatted_input}</code></pre>
</div>'''


def format_tool_input(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """
    Format tool input parameters in a human-readable way.

    This is a thin wrapper around the registry-based formatter to maintain
    backwards compatibility with existing code.
    """
    return format_tool_input_registry(tool_name, tool_input)


def detect_result_pattern(data: Any) -> str:
    """
    Detect the structural pattern of tool result data.

    Returns one of: wrapped_result | counted_collection | uniform_list |
                    simple_dict | time_series | text | primitive
    """
    if isinstance(data, str):
        return 'text'

    if isinstance(data, dict):
        # Check for wrapper pattern: {"result": ...}
        if 'result' in data and len(data) == 1:
            return 'wrapped_result'

        # Check for counted collection: {count: N, items/messages/actions/thoughts: [...]}
        collection_keys = ['items', 'messages', 'actions', 'thoughts']
        if 'count' in data and any(key in data for key in collection_keys):
            return 'counted_collection'

        # Simple dictionary
        return 'simple_dict'

    if isinstance(data, list):
        if not data:
            return 'uniform_list'  # Empty list

        first_item = data[0]

        # Time series: [[timestamp, value], ...]
        if isinstance(first_item, list) and len(first_item) == 2:
            return 'time_series'

        # Uniform list of objects: [{...}, {...}]
        if isinstance(first_item, dict):
            return 'uniform_list'

        return 'uniform_list'

    return 'primitive'


def render_vertical_table(data: dict) -> str:
    """Render a simple dictionary as a vertical key-value table."""
    if not data:
        return '<div class="tool-result-empty">Empty result</div>'

    rows = []
    for key, value in data.items():
        formatted_value = format_field_value(key, value, is_table_context=True)
        # Make key human-readable
        label = key.replace('_', ' ').title()
        rows.append(f'<tr><td><strong>{label}</strong></td><td>{formatted_value}</td></tr>')

    return f'''<table class="data-table">
        <tbody>{''.join(rows)}</tbody>
    </table>'''


def render_horizontal_table(data: list) -> str:
    """Render a uniform list of dictionaries as a horizontal table or cards."""
    if not data:
        return '<div class="tool-result-empty">No results</div>'

    # Get all unique keys from all items
    all_keys = []
    for item in data:
        if isinstance(item, dict):
            for key in item.keys():
                if key not in all_keys:
                    all_keys.append(key)

    if not all_keys:
        return '<div class="tool-result-empty">No data</div>'

    # Check if this looks like plant status history (has reasoning, next_action_sequence)
    has_complex_fields = any('reasoning' in key.lower() or 'action' in key.lower() and 'sequence' in key.lower() for key in all_keys)

    # If it has complex fields, render as status cards
    if has_complex_fields:
        return render_status_cards(data, all_keys)

    # Otherwise, render as standard horizontal table
    # Build header
    headers = [key.replace('_', ' ').title() for key in all_keys]
    header_html = ''.join([f'<th>{h}</th>' for h in headers])

    # Build rows
    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue

        cells = []
        for key in all_keys:
            value = item.get(key, '')
            formatted_value = format_field_value(key, value, is_table_context=True)
            cells.append(f'<td>{formatted_value}</td>')

        rows.append(f'<tr>{"".join(cells)}</tr>')

    return f'''<table class="data-table">
        <thead><tr>{header_html}</tr></thead>
        <tbody>{''.join(rows)}</tbody>
    </table>'''


def render_status_cards(data: list, keys: list) -> str:
    """Render status history as cards with better formatting for complex fields."""
    cards = []

    for idx, item in enumerate(data, 1):
        if not isinstance(item, dict):
            continue

        # Extract key fields
        timestamp = item.get('timestamp', '')
        sensor_reading = item.get('sensor_reading', 'N/A')
        water_24h = item.get('water_24h', 0)
        light_today = item.get('light_today', 0)
        plant_state = item.get('plant_state', 'unknown')
        reasoning = item.get('reasoning', '')
        next_actions = item.get('next_action_sequence', [])

        # Format plant state with color
        state_html = f'<span class="plant-state-{plant_state}">{plant_state}</span>'

        # Format next actions as a list
        actions_html = ''
        if next_actions and isinstance(next_actions, list):
            action_items = []
            for action in next_actions:
                if isinstance(action, dict):
                    order = action.get('order', '')
                    action_type = action.get('action', 'unknown')
                    action_value = action.get('value')
                    if action_value:
                        action_items.append(f'<li>{order}. {action_type} ({action_value})</li>')
                    else:
                        action_items.append(f'<li>{order}. {action_type}</li>')
            if action_items:
                actions_html = f'<ul class="action-list">{"".join(action_items)}</ul>'

        # Format reasoning
        reasoning_html = ''
        if reasoning:
            reasoning_html = f'<div class="status-reasoning">{reasoning}</div>'

        card = f'''<div class="status-card">
            <div class="status-header">#{idx} {timestamp[:19] if timestamp else 'N/A'}</div>
            <div class="status-metrics">
                <span class="metric"><strong>State:</strong> {state_html}</span>
                <span class="metric"><strong>Moisture:</strong> {sensor_reading}</span>
                <span class="metric"><strong>Water 24h:</strong> {water_24h}ml</span>
                <span class="metric"><strong>Light today:</strong> {light_today}min</span>
            </div>
            {reasoning_html}
            {f'<div class="status-next-actions"><strong>Next actions:</strong>{actions_html}</div>' if actions_html else ''}
        </div>'''
        cards.append(card)

    return f'<div class="tool-result-status-history">{"".join(cards)}</div>'


def render_time_series(data: list) -> str:
    """Render time series data [[timestamp, value], ...] as a table."""
    if not data:
        return '<div class="tool-result-empty">No data</div>'

    rows = []
    for item in data:
        if isinstance(item, list) and len(item) == 2:
            timestamp, value = item
            ts_str = timestamp[:19] if isinstance(timestamp, str) else str(timestamp)
            rows.append(f'<tr><td class="timestamp-cell">{ts_str}</td><td>{value}</td></tr>')

    return f'''<table class="data-table">
        <thead><tr><th>Time</th><th>Value</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
    </table>'''


def render_counted_collection(data: dict) -> str:
    """Render counted collection {count: N, items: [...]} with header and table."""
    count = data.get('count', 0)

    # Find the collection key
    collection_keys = ['items', 'messages', 'actions', 'thoughts']
    collection = []
    collection_name = 'items'

    for key in collection_keys:
        if key in data:
            collection = data[key]
            collection_name = key
            break

    if not collection:
        return f'<div class="tool-result-empty">{count} {collection_name}</div>'

    # Render the collection as a horizontal table
    table_html = render_horizontal_table(collection)

    return f'''<div class="tool-result-collection">
        <div class="collection-count">{count} {collection_name}</div>
        {table_html}
    </div>'''


def render_text(text: str) -> str:
    """Render text content, applying markdown if detected."""
    if not text:
        return '<div class="tool-result-empty">Empty</div>'

    # Check if it looks like markdown
    if '\n' in text or '#' in text or '**' in text or '```' in text:
        return f'<div class="tool-result-markdown">{markdown_to_html(text)}</div>'

    return f'<div class="tool-result-text">{text}</div>'


def format_tool_result(tool_name: str, result_content: Any) -> str:
    """
    Format tool result using generic pattern-based rendering.

    Detects structural patterns and applies semantic field formatting
    instead of tool-specific logic.
    """
    # Step 1: Parse JSON strings
    if isinstance(result_content, str):
        try:
            result_content = json.loads(result_content)
        except (json.JSONDecodeError, TypeError):
            return render_text(result_content)

    # Step 2: Tool-specific overrides for special cases
    # get_recent_actions returns {count: N, actions: [{timestamp, type, details}, ...]}
    if 'get_recent_actions' in tool_name and isinstance(result_content, dict) and 'actions' in result_content:
        actions = result_content.get('actions', [])
        count = result_content.get('count', len(actions))

        if not actions:
            return '<div class="tool-result-empty">No recent actions</div>'

        action_blocks = [f'<div class="collection-count">{count} actions</div>']
        for action in actions:
            if isinstance(action, dict):
                timestamp = action.get('timestamp', 'N/A')
                action_type = action.get('type', 'unknown')
                details = action.get('details', {})

                # Format timestamp
                ts_str = timestamp[:19] if isinstance(timestamp, str) else str(timestamp)

                # Build action block
                block = f'<div style="margin-bottom: 1.5rem; padding: 1rem; background: var(--color-bg); border-radius: 4px;">'
                block += f'<div style="margin-bottom: 0.5rem;"><span class="tool-param-key">Time:</span> <span class="timestamp-cell">{ts_str}</span></div>'
                block += f'<div style="margin-bottom: 0.5rem;"><span class="tool-param-key">Type:</span> <span class="tool-param-value">{action_type}</span></div>'

                # Render details as table if it's a dict
                if isinstance(details, dict) and details:
                    detail_rows = []
                    for key, value in details.items():
                        detail_rows.append(f'<tr><td class="tool-param-key">{key}</td><td>{value}</td></tr>')
                    block += f'<div style="margin-top: 0.5rem;"><strong>Details:</strong></div>'
                    block += f'<table class="data-table">{"".join(detail_rows)}</table>'

                block += '</div>'
                action_blocks.append(block)

        return ''.join(action_blocks)

    # log_action returns {timestamp: str, success: bool}
    if 'log_action' in tool_name and isinstance(result_content, dict):
        timestamp = result_content.get('timestamp', 'N/A')
        success = result_content.get('success', False)

        ts_str = timestamp[:19] if isinstance(timestamp, str) else str(timestamp)
        status_class = 'status-ok' if success else 'status-error'
        status_text = '✅ Logged' if success else '❌ Failed'

        return f'''<div class="tool-result-text">
            <div class="{status_class}"><strong>{status_text}</strong></div>
            <div class="timestamp-cell">{ts_str}</div>
        </div>'''

    # fetch_notes returns {content: "markdown text"}
    if 'fetch_notes' in tool_name and isinstance(result_content, dict) and 'content' in result_content:
        content = result_content.get('content', '')
        if isinstance(content, str):
            return f'<div class="tool-result-notes-box">{markdown_to_html(content)}</div>'
        return '<div class="tool-result-empty">No content</div>'

    # save_notes returns {success: bool, timestamp: str, note_length_chars: int}
    if 'save_notes' in tool_name and isinstance(result_content, dict) and 'success' in result_content:
        success = result_content.get('success', False)
        timestamp = result_content.get('timestamp', '')
        length = result_content.get('note_length_chars', 0)

        status_class = 'status-ok' if success else 'status-error'
        status_text = '✅ Success' if success else '❌ Failed'
        ts_str = timestamp[:19] if timestamp else 'N/A'

        return f'''<div class="tool-result-text">
            <div class="{status_class}"><strong>{status_text}</strong></div>
            <div>Saved {length:,} characters</div>
            <div class="timestamp-cell">{ts_str}</div>
        </div>'''

    # Step 3: Detect pattern
    pattern = detect_result_pattern(result_content)

    # Step 4: Handle wrapped results by unwrapping and re-detecting
    if pattern == 'wrapped_result':
        result_content = result_content['result']
        pattern = detect_result_pattern(result_content)

    # Step 5: Apply pattern-specific renderer
    if pattern == 'simple_dict':
        return render_vertical_table(result_content)

    elif pattern == 'uniform_list':
        return render_horizontal_table(result_content)

    elif pattern == 'time_series':
        return render_time_series(result_content)

    elif pattern == 'counted_collection':
        return render_counted_collection(result_content)

    elif pattern == 'text':
        return render_text(result_content)

    elif pattern == 'primitive':
        return f'<div class="tool-result-text">{str(result_content)}</div>'

    # Fallback: JSON pretty print
    return f'<pre class="tool-result-json"><code>{json.dumps(result_content, indent=2)}</code></pre>'


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
