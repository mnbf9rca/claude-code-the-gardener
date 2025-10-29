"""
Shared formatting utilities for HTML generation.
"""

import json
import os
import re
from typing import Any
from urllib.parse import urlparse
import markdown2


def _extract_photo_filename(url: str) -> str:
    """
    Extract filename from a photo URL, handling query parameters and fragments.

    Args:
        url: Photo URL (absolute or relative)

    Returns:
        Just the filename portion (e.g., 'plant_123.jpg')
    """
    if '/photos/' not in url:
        return url

    # Use urlparse for robust handling of query params and fragments
    parsed = urlparse(url)
    return os.path.basename(parsed.path)


def convert_photo_urls_to_relative(text: str) -> str:
    """
    Convert absolute photo URLs to relative paths for static site.

    Finds any URL containing '/photos/' (regardless of protocol, host, or port)
    and converts it to a relative path like '../photos/filename.jpg'.

    Examples:
        'http://192.168.1.100:8000/photos/plant_123.jpg' -> '../photos/plant_123.jpg'
        'http://localhost:8080/photos/plant_456.jpg' -> '../photos/plant_456.jpg'
        'http://plant-server.local:8000/photos/plant_789.jpg' -> '../photos/plant_789.jpg'

    Args:
        text: Text content that may contain absolute photo URLs

    Returns:
        Text with absolute photo URLs converted to relative paths
    """
    if '/photos/' not in text:
        return text

    # Match any URL containing /photos/ and extract the full URL
    # Pattern: http(s)://[host]:[port]/photos/[filename]
    pattern = r'https?://[^/\s]+(?::\d+)?/photos/[^\s\)\"\'<>]+'

    def replace_url(match):
        url = match.group(0)
        filename = _extract_photo_filename(url)
        return f'../photos/{filename}'

    return re.sub(pattern, replace_url, text)


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
    if field_name.lower() in ['status', 'state', 'plant_state']:
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
    # Use exact matching or suffix matching to avoid false positives (e.g., 'reasoning_score')
    markdown_field_patterns = {'content', 'message', 'observation', 'hypothesis',
                                'reasoning', 'uncertainties', 'note'}
    field_lower = field_name.lower()
    is_markdown_field = (
        field_lower in markdown_field_patterns or
        any(field_lower.endswith(f'_{pattern}') for pattern in markdown_field_patterns)
    )

    if is_markdown_field:
        text = str(value)
        # Convert photo URLs to relative paths before processing
        text = convert_photo_urls_to_relative(text)
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

    # URLs - make them clickable (convert photo URLs to relative paths)
    # Note: Intentionally broad matching to catch photo URLs in any field (notes, actions, etc.)
    if field_name == 'url' or (isinstance(value, str) and value.startswith('http')):
        url = str(value)
        # Convert absolute photo URLs to relative paths for static site (reuses helper)
        if '/photos/' in url:
            filename = _extract_photo_filename(url)
            url = f'../photos/{filename}'
        return f'<a href="{url}" target="_blank" class="link">View</a>'

    # Nested lists or dicts - format compactly
    if isinstance(value, (list, dict)):
        try:
            json_str = json.dumps(value, default=str)
        except (TypeError, ValueError):
            # Provide clearer indication of serialization failure
            type_name = type(value).__name__
            json_str = f"&lt;non-serializable {type_name}&gt;"
        return f'<span class="nested-data">{json_str}</span>'

    # Default - just convert to string
    return str(value)
