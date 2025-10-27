"""
Tool input/result formatter registry.

This module provides a registry-based approach to formatting tool inputs and results
for HTML display, improving maintainability and testability.
"""

import json
from typing import Dict, Any, Callable, Optional
from .conversations import markdown_to_html, format_field_value


# Type alias for formatter functions
ToolInputFormatter = Callable[[str, Dict[str, Any]], str]


class ToolFormatterRegistry:
    """Registry for tool-specific input formatters."""

    def __init__(self):
        self._formatters: Dict[str, ToolInputFormatter] = {}

    def register(self, pattern: str, formatter: ToolInputFormatter) -> None:
        """Register a formatter for tools matching the given pattern."""
        self._formatters[pattern] = formatter

    def format(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Format tool input using registered formatters or default."""
        # Try to find a matching formatter
        for pattern, formatter in self._formatters.items():
            if pattern in tool_name:
                return formatter(tool_name, tool_input)

        # Fall back to default formatter
        return self._default_format(tool_input)

    def _default_format(self, tool_input: Dict[str, Any]) -> str:
        """Default formatter for tools without specific formatting."""
        if not tool_input:
            return '<span class="tool-no-params">No parameters</span>'

        params = []
        for key, value in tool_input.items():
            if isinstance(value, (list, dict)):
                # Format complex structures as pretty JSON
                value_html = f'<pre class="tool-result-json"><code>{json.dumps(value, indent=2)}</code></pre>'
                params.append(f'<div><span class="tool-param-key">{key}:</span><br>{value_html}</div>')
            else:
                params.append(f'<span class="tool-param-key">{key}:</span> <span class="tool-param-value">{value}</span>')
        return '<br>'.join(params)


# Create global registry
_input_registry = ToolFormatterRegistry()


def _format_moisture_tool(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Format moisture sensor tool inputs."""
    if 'hours' in tool_input:
        return f'<span class="tool-param">Last {tool_input["hours"]} hours, {tool_input.get("samples_per_hour", 1)} samples/hour</span>'
    return _input_registry._default_format(tool_input)


def _format_recent_data_tool(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Format recent thoughts/actions tool inputs."""
    if 'n' in tool_input:
        return f'<span class="tool-param">Last {tool_input["n"]} items</span>'
    return _input_registry._default_format(tool_input)


def _format_light_tool(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Format light activation tool inputs."""
    if 'duration_minutes' in tool_input:
        return f'<span class="tool-param">Duration: {tool_input["duration_minutes"]} minutes</span>'
    return _input_registry._default_format(tool_input)


def _format_water_tool(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Format water dispensing tool inputs."""
    if 'ml' in tool_input:
        return f'<span class="tool-param">Amount: {tool_input["ml"]}ml</span>'
    return _input_registry._default_format(tool_input)


def _format_save_notes_tool(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Format save_notes tool inputs."""
    mode = tool_input.get('mode', 'update')
    content = tool_input.get('content', '')

    result = f'<div><strong>Mode:</strong> <span class="tool-param-value">{mode}</span></div>'

    if isinstance(content, str) and content:
        formatted_content = markdown_to_html(content)
        result += f'<div class="tool-result-notes-box">{formatted_content}</div>'

    return result


def _format_plant_status_tool(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Format write_plant_status tool inputs."""
    params = []

    if 'plant_state' in tool_input:
        params.append(
            f'<span class="tool-param-key">State:</span> '
            f'<span class="plant-state-{tool_input["plant_state"]}">{tool_input["plant_state"]}</span>'
        )

    if 'reasoning' in tool_input:
        params.append(f'<span class="tool-param-key">Reasoning:</span> {tool_input["reasoning"]}')

    if 'next_action_sequence' in tool_input:
        actions = tool_input['next_action_sequence']
        if isinstance(actions, list):
            actions_html = format_field_value('next_action_sequence', actions)
            params.append(f'<span class="tool-param-key">Next actions:</span><br>{actions_html}')

    return '<br>'.join(params) if params else '<span class="tool-param">Plant status update</span>'


def _format_log_thought_tool(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Format log_thought tool inputs."""
    parts = []

    # Main fields as 2-column table
    table_rows = [
        f'<tr><td class="tool-param-key">{key}</td><td>{tool_input[key]}</td></tr>'
        for key in ['observation', 'hypothesis', 'reasoning', 'uncertainties']
        if key in tool_input
    ]

    if table_rows:
        parts.append(f'<table class="data-table">{"".join(table_rows)}</table>')

    # Candidate actions as list of tables
    if 'candidate_actions' in tool_input and isinstance(tool_input['candidate_actions'], list):
        actions_html = ['<div class="tool-param-key">Candidate Actions:</div>']
        for idx, action in enumerate(tool_input['candidate_actions'], 1):
            if isinstance(action, dict):
                action_rows = [
                    f'<tr><td class="tool-param-key">{k}</td><td>{v}</td></tr>'
                    for k, v in action.items()
                ]
                actions_html.append(
                    f'<div style="margin-left: 1rem; margin-bottom: 0.5rem;">'
                    f'<strong>Action {idx}:</strong>'
                    f'<table class="data-table">{"".join(action_rows)}</table></div>'
                )
        parts.append(''.join(actions_html))

    # Tags as inline list
    if 'tags' in tool_input and isinstance(tool_input['tags'], list):
        tags_html = ' '.join(f'<span class="tag">{tag}</span>' for tag in tool_input['tags'])
        parts.append(f'<div><span class="tool-param-key">Tags:</span> {tags_html}</div>')

    return ''.join(parts) if parts else '<span class="tool-param">Thought logged</span>'


def _format_log_action_tool(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Format log_action tool inputs."""
    parts = []

    # Show type first if present
    if 'type' in tool_input:
        parts.append(
            f'<div style="margin-bottom: 0.5rem;">'
            f'<span class="tool-param-key">Type:</span> '
            f'<span class="tool-param-value">{tool_input["type"]}</span></div>'
        )

    # Show details as a nested 2-column table
    if 'details' in tool_input and isinstance(tool_input['details'], dict):
        details = tool_input['details']
        detail_rows = [
            f'<tr><td class="tool-param-key">{key}</td><td>{value}</td></tr>'
            for key, value in details.items()
        ]

        if detail_rows:
            parts.append(f'<div style="margin-top: 0.5rem;"><strong>Details:</strong></div>')
            parts.append(f'<table class="data-table">{"".join(detail_rows)}</table>')

    return ''.join(parts) if parts else '<span class="tool-param">Action logged</span>'


# Register all formatters
_input_registry.register('moisture', _format_moisture_tool)
_input_registry.register('recent_thoughts', _format_recent_data_tool)
_input_registry.register('recent_actions', _format_recent_data_tool)
_input_registry.register('light', _format_light_tool)
_input_registry.register('dispense_water', _format_water_tool)
_input_registry.register('save_notes', _format_save_notes_tool)
_input_registry.register('write_plant_status', _format_plant_status_tool)
_input_registry.register('log_thought', _format_log_thought_tool)
_input_registry.register('log_action', _format_log_action_tool)


def format_tool_input(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """
    Format tool input parameters in a human-readable way using the formatter registry.

    This is the main entry point for tool input formatting.
    """
    return _input_registry.format(tool_name, tool_input)
