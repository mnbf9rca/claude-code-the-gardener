"""
Shared formatting utilities for HTML generation.
"""

import json
from typing import Any
import markdown2


def markdown_to_html(text: str) -> str:
    """Convert markdown to HTML for display using markdown2 library."""
    if not text:
        return ""
    return markdown2.markdown(text, extras=[
        'fenced-code-blocks',     # Support ``` code blocks
        'tables',                 # Support markdown tables
        'cuddled-lists',          # Lists without blank lines before them
        'code-friendly',          # Better code rendering
        'task_list',              # Support [ ] and [x] checkboxes
        'strike',                 # Support ~~strikethrough~~
        'header-ids',             # Add IDs to headers for linking
    ])


def format_field_value(field_name: str, value: Any, is_table_context: bool = False) -> str:
    """
    Format a field value based on semantic field name conventions.

    Applies special formatting for timestamps, status fields, markdown content, etc.
    """
    if value is None or value == '':
        return '<em>N/A</em>' if is_table_context else 'N/A'

    # Timestamp fields - truncate and apply monospace styling
    if any(x in field_name.lower() for x in ['timestamp', '_time', '_at', 'bucket_start', 'bucket_end']):
        ts_str = str(value)[:19] if isinstance(value, str) else str(value)
        return f'<span class="timestamp-cell">{ts_str}</span>'

    # Status and state fields - apply color badges
    if field_name in ['status', 'state', 'plant_state']:
        return f'<span class="plant-state-{value}">{value}</span>'

    # Success/boolean fields
    if field_name == 'success':
        icon = '✓' if value else '✗'
        css_class = 'status-ok' if value else 'status-error'
        return f'<span class="{css_class}">{icon} {"Success" if value else "Failed"}</span>'

    # Action sequences and nested lists - format as compact list
    if 'action' in field_name.lower() and 'sequence' in field_name.lower():
        if isinstance(value, list):
            items = []
            for action in value:
                if isinstance(action, dict):
                    order = action.get('order', '')
                    action_type = action.get('action', 'unknown')
                    action_value = action.get('value')
                    if action_value:
                        items.append(f"{order}. {action_type} ({action_value})")
                    else:
                        items.append(f"{order}. {action_type}")
            return '<br>'.join(items) if items else '<em>None</em>'
        return str(value)

    # Content/markdown/reasoning fields - render with proper formatting
    markdown_fields = ['content', 'message', 'observation', 'hypothesis',
                       'reasoning', 'uncertainties', 'note']
    if any(field in field_name.lower() for field in markdown_fields):
        text = str(value)
        # In table context, truncate long text and add ellipsis
        if is_table_context and len(text) > 150:
            text = text[:150] + '...'
        # Check if it looks like markdown
        if '\n' in text or '#' in text or '**' in text:
            return markdown_to_html(text)
        return text

    # Type field - add icons
    if field_name == 'type':
        icons = {
            'water': '💧', 'light': '💡', 'photo': '📷',
            'message': '💬', 'thought': '🧠', 'action': '⚡'
        }
        icon = icons.get(str(value).lower(), '')
        return f'{icon} {value}' if icon else str(value)

    # URLs - make them clickable
    if field_name == 'url' or (isinstance(value, str) and value.startswith('http')):
        return f'<a href="{value}" target="_blank" class="link">View</a>'

    # Nested lists or dicts - format compactly
    if isinstance(value, (list, dict)):
        return f'<span class="nested-data">{json.dumps(value)}</span>'

    # Default - just convert to string
    return str(value)
