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
                    # Extract text parts from list
                    text_parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
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


def markdown_to_html(text: str) -> str:
    """Convert markdown to HTML for display."""
    if not text:
        return ""

    # Code blocks
    text = re.sub(r'```(\w+)?\n(.*?)```', r'<pre class="code-block"><code>\2</code></pre>', text, flags=re.DOTALL)

    # Bold
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)

    # Headers
    text = re.sub(r'^### (.*?)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.*?)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.*?)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)

    # Lists
    lines = text.split('\n')
    in_list = False
    result = []
    for line in lines:
        if line.strip().startswith('- '):
            if not in_list:
                result.append('<ul class="markdown-list">')
                in_list = True
            result.append(f'<li>{line.strip()[2:]}</li>')
        else:
            if in_list:
                result.append('</ul>')
                in_list = False
            result.append(line)
    if in_list:
        result.append('</ul>')

    return '\n'.join(result)


def format_tool_input(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Format tool input parameters in a human-readable way."""
    if not tool_input:
        return '<span class="tool-no-params">No parameters</span>'

    # Plant-specific tools - make them more readable
    if 'moisture' in tool_name.lower():
        if 'hours' in tool_input:
            return f'<span class="tool-param">Last {tool_input["hours"]} hours, {tool_input.get("samples_per_hour", 1)} samples/hour</span>'

    elif 'recent_thoughts' in tool_name or 'recent_actions' in tool_name:
        if 'n' in tool_input:
            return f'<span class="tool-param">Last {tool_input["n"]} items</span>'

    elif 'light' in tool_name.lower() and 'activate' in tool_name:
        if 'duration_minutes' in tool_input:
            return f'<span class="tool-param">Duration: {tool_input["duration_minutes"]} minutes</span>'

    elif 'dispense_water' in tool_name:
        if 'ml' in tool_input:
            return f'<span class="tool-param">Amount: {tool_input["ml"]}ml</span>'

    # For other tools, show params as key-value pairs
    params = []
    for key, value in tool_input.items():
        params.append(f'<span class="tool-param-key">{key}:</span> <span class="tool-param-value">{value}</span>')
    return '<br>'.join(params)


def format_tool_result(tool_name: str, result_content: Any) -> str:
    """Format tool result based on tool type for better readability."""
    if isinstance(result_content, str):
        try:
            result_content = json.loads(result_content)
        except (json.JSONDecodeError, TypeError):
            # If it's markdown or plain text, render it
            if '\n' in result_content or '#' in result_content:
                return f'<div class="tool-result-markdown">{markdown_to_html(result_content)}</div>'
            return f'<div class="tool-result-text">{result_content}</div>'

    if not isinstance(result_content, dict):
        return f'<pre class="tool-result-raw"><code>{json.dumps(result_content, indent=2)}</code></pre>'

    # Plant tool results
    if 'read_moisture' in tool_name:
        value = result_content.get('value', 'N/A')
        status = result_content.get('status', 'unknown')
        timestamp = result_content.get('timestamp', '')
        return f'''<div class="tool-result-structured">
            <div class="result-item"><span class="label">Moisture:</span> <span class="value moisture-value">{value}</span></div>
            <div class="result-item"><span class="label">Status:</span> <span class="status-{status}">{status}</span></div>
            <div class="result-item small"><span class="label">Time:</span> {timestamp}</div>
        </div>'''

    elif 'water_usage' in tool_name:
        used = result_content.get('used_ml', 0)
        remaining = result_content.get('remaining_ml', 0)
        events = result_content.get('events', 0)
        return f'''<div class="tool-result-structured">
            <div class="result-item"><span class="label">Used (24h):</span> <span class="value">{used}ml</span></div>
            <div class="result-item"><span class="label">Remaining:</span> <span class="value">{remaining}ml</span></div>
            <div class="result-item"><span class="label">Events:</span> {events}</div>
        </div>'''

    elif 'light_status' in tool_name:
        status = result_content.get('status', 'unknown')
        can_activate = result_content.get('can_activate', False)
        minutes = result_content.get('minutes_until_available', 0)
        return f'''<div class="tool-result-structured">
            <div class="result-item"><span class="label">Status:</span> <span class="status-{status}">{status}</span></div>
            <div class="result-item"><span class="label">Can activate:</span> {can_activate}</div>
            {f'<div class="result-item"><span class="label">Available in:</span> {minutes} minutes</div>' if minutes > 0 else ''}
        </div>'''

    elif 'capture_photo' in tool_name or 'camera' in tool_name:
        url = result_content.get('url', '')
        timestamp = result_content.get('timestamp', '')
        if url:
            return f'''<div class="tool-result-structured">
                <div class="result-item"><span class="label">Photo captured:</span> {timestamp}</div>
                <div class="result-item"><a href="{url}" target="_blank" class="photo-link">View Photo</a></div>
            </div>'''

    elif 'get_current_time' in tool_name:
        timestamp = result_content.get('timestamp', result_content)
        return f'<div class="tool-result-structured"><div class="result-item"><span class="value">{timestamp}</span></div></div>'

    elif 'moisture_history' in tool_name and 'result' in result_content:
        readings = result_content.get('result', [])
        if readings:
            rows = []
            for timestamp, value in readings:
                rows.append(f'<tr><td>{timestamp}</td><td class="moisture-value">{value}</td></tr>')
            return f'''<div class="tool-result-table">
                <table class="moisture-history">
                    <thead><tr><th>Time</th><th>Value</th></tr></thead>
                    <tbody>{''.join(rows)}</tbody>
                </table>
            </div>'''

    elif 'fetch_notes' in tool_name and 'content' in result_content:
        content = result_content.get('content', '')
        return f'<div class="tool-result-notes">{markdown_to_html(content)}</div>'

    # list_messages_from_human - structured message list
    elif 'list_messages' in tool_name and 'messages' in result_content:
        messages = result_content.get('messages', [])
        if messages:
            items = []
            for msg in messages:
                msg_id = msg.get('message_id', 'N/A')
                timestamp = msg.get('timestamp', '')[:19]  # Trim to readable length
                content = msg.get('content', '')
                in_reply_to = msg.get('in_reply_to')

                # Render content as markdown if it looks like formatted text
                content_html = markdown_to_html(content) if content else '<em>No content</em>'
                reply_badge = f'<span class="reply-badge">↩ Reply to {in_reply_to}</span>' if in_reply_to else ''

                items.append(f'''<div class="message-item">
                    <div class="message-meta">
                        <strong>{msg_id}</strong> · {timestamp} {reply_badge}
                    </div>
                    <div class="message-body">{content_html}</div>
                </div>''')

            return f'''<div class="tool-result-messages">
                <div class="message-count">{len(messages)} message(s)</div>
                {''.join(items)}
            </div>'''

    # get_recent_thoughts - structured thought cards
    elif 'thoughts' in tool_name and 'thoughts' in result_content:
        thoughts = result_content.get('thoughts', [])
        if thoughts:
            cards = []
            for i, thought in enumerate(thoughts, 1):
                timestamp = thought.get('timestamp', '')[:19]
                observation = markdown_to_html(thought.get('observation', ''))
                hypothesis = markdown_to_html(thought.get('hypothesis', ''))
                reasoning = markdown_to_html(thought.get('reasoning', ''))
                uncertainties = markdown_to_html(thought.get('uncertainties', ''))
                actions = thought.get('candidate_actions', [])
                tags = thought.get('tags', [])

                # Format actions as a list
                if actions:
                    action_items = [f"<li>{act.get('action', 'unknown')}" +
                                  (f" ({act.get('value')})" if act.get('value') else "") +
                                  "</li>" for act in actions]
                    actions_html = f"<ul class='action-list'>{''.join(action_items)}</ul>"
                else:
                    actions_html = "<em>No actions</em>"

                # Format tags
                tags_html = ' '.join([f'<span class="tag">{tag}</span>' for tag in tags]) if tags else ''

                cards.append(f'''<div class="thought-card">
                    <div class="thought-header">
                        <span class="thought-number">#{i}</span>
                        <span class="thought-time">{timestamp}</span>
                    </div>
                    {f'<div class="thought-tags">{tags_html}</div>' if tags_html else ''}
                    <div class="thought-section">
                        <div class="section-label">Observation</div>
                        <div class="section-content">{observation}</div>
                    </div>
                    <div class="thought-section">
                        <div class="section-label">Hypothesis</div>
                        <div class="section-content">{hypothesis}</div>
                    </div>
                    <div class="thought-section">
                        <div class="section-label">Candidate Actions</div>
                        <div class="section-content">{actions_html}</div>
                    </div>
                    <div class="thought-section">
                        <div class="section-label">Reasoning</div>
                        <div class="section-content">{reasoning}</div>
                    </div>
                    {f'<div class="thought-section"><div class="section-label">Uncertainties</div><div class="section-content">{uncertainties}</div></div>' if uncertainties else ''}
                </div>''')

            return f'<div class="tool-result-thoughts">{chr(10).join(cards)}</div>'

    # History tools - handle dict with 'result' wrapper (moisture_history, light_history, etc.)
    elif isinstance(result_content, dict) and 'result' in result_content:
        result_list = result_content['result']
        if isinstance(result_list, list) and result_list:
            first_item = result_list[0]

            # Bucketed data with aggregation (dicts with bucket_start/bucket_end)
            if isinstance(first_item, dict) and 'bucket_start' in first_item:
                rows = []
                for bucket in result_list:
                    start = bucket.get('bucket_start', '')[:19]
                    end = bucket.get('bucket_end', '')[:19]
                    value = bucket.get('value', 0)
                    count = bucket.get('count', 0)
                    rows.append(f'<tr><td>{start}</td><td>{end}</td><td class="value-cell">{value}</td><td>{count}</td></tr>')

                return f'''<div class="tool-result-table">
                    <table class="history-table">
                        <thead><tr><th>Bucket Start</th><th>Bucket End</th><th>Value</th><th>Count</th></tr></thead>
                        <tbody>{''.join(rows)}</tbody>
                    </table>
                </div>'''

            # Time series data [[timestamp, value], ...]
            elif isinstance(first_item, list) and len(first_item) == 2:
                rows = []
                for timestamp, value in result_list:
                    ts_short = timestamp[:19] if isinstance(timestamp, str) else timestamp
                    rows.append(f'<tr><td>{ts_short}</td><td class="value-cell">{value}</td></tr>')

                return f'''<div class="tool-result-table">
                    <table class="history-table">
                        <thead><tr><th>Time</th><th>Value</th></tr></thead>
                        <tbody>{''.join(rows)}</tbody>
                    </table>
                </div>'''

    # History tools - check if it's a list of [timestamp, value] or bucketed data (no wrapper)
    elif isinstance(result_content, list) and result_content:
        first_item = result_content[0]

        # Bucketed data with aggregation (dicts with bucket_start/bucket_end)
        if isinstance(first_item, dict) and 'bucket_start' in first_item:
            rows = []
            for bucket in result_content:
                start = bucket.get('bucket_start', '')[:19]
                end = bucket.get('bucket_end', '')[:19]
                value = bucket.get('value', 0)
                count = bucket.get('count', 0)
                rows.append(f'<tr><td>{start}</td><td>{end}</td><td class="value-cell">{value}</td><td>{count}</td></tr>')

            return f'''<div class="tool-result-table">
                <table class="history-table">
                    <thead><tr><th>Bucket Start</th><th>Bucket End</th><th>Value</th><th>Count</th></tr></thead>
                    <tbody>{''.join(rows)}</tbody>
                </table>
            </div>'''

        # Time series data [[timestamp, value], ...]
        elif isinstance(first_item, list) and len(first_item) == 2:
            rows = []
            for timestamp, value in result_content:
                ts_short = timestamp[:19] if isinstance(timestamp, str) else timestamp
                rows.append(f'<tr><td>{ts_short}</td><td class="value-cell">{value}</td></tr>')

            return f'''<div class="tool-result-table">
                <table class="history-table">
                    <thead><tr><th>Time</th><th>Value</th></tr></thead>
                    <tbody>{''.join(rows)}</tbody>
                </table>
            </div>'''

    # Default: JSON pretty print
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
