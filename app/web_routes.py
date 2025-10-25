"""
Web Routes for Plant Care System
Provides HTTP endpoints and HTML UI for human-agent messaging and photo gallery
"""
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.requests import Request
from datetime import datetime, timezone
from typing import Dict, Any, List
from pathlib import Path
import json
import tools.human_messages as human_messages
from tools.human_messages import _generate_message_id, MAX_MESSAGE_LENGTH
from tools.camera import capture_real_photo, CAMERA_CONFIG
from utils.logging_config import get_logger

logger = get_logger(__name__)


def _get_all_messages() -> List[Dict[str, Any]]:
    """
    Get all messages (to and from human) sorted by timestamp, newest first.

    Returns:
        List of messages with added 'direction' field ('to_human' or 'from_human')
    """
    # Reload from disk to pick up any manual edits
    human_messages.messages_to_human.load()
    human_messages.messages_from_human.load()

    # Get all messages
    to_human = human_messages.messages_to_human.get_all()
    from_human = human_messages.messages_from_human.get_all()

    # Add direction field (make copies to avoid modifying originals)
    to_human_with_dir = [{**msg, 'direction': 'to_human'} for msg in to_human]
    from_human_with_dir = [{**msg, 'direction': 'from_human'} for msg in from_human]

    # Combine and sort by timestamp (newest first)
    all_messages = to_human_with_dir + from_human_with_dir
    all_messages.sort(key=lambda x: x['timestamp'], reverse=True)

    return all_messages


def _get_photos_from_directory(limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    """
    List photos from the photos directory with pagination.

    Args:
        limit: Maximum number of photos to return
        offset: Number of photos to skip

    Returns:
        Dict with 'total', 'photos' (list), 'limit', and 'offset'
    """
    photos_dir = CAMERA_CONFIG["save_path"]

    # Get all photo files matching the pattern
    all_photos = []
    if photos_dir.exists() and photos_dir.is_dir():
        photo_files = sorted(
            photos_dir.glob("plant_*.jpg"),
            key=lambda p: p.stat().st_mtime,
            reverse=True  # Newest first
        )

        for photo_path in photo_files:
            # Extract timestamp from filename
            # Format: plant_YYYYMMDD_HHMMSS_mmm.jpg
            filename = photo_path.name
            try:
                parts = filename.replace('.jpg', '').split('_')
                if len(parts) >= 4:
                    date_part = parts[1]  # YYYYMMDD
                    time_part = parts[2]  # HHMMSS
                    ms_part = parts[3] if len(parts) > 3 else "000"

                    # Reconstruct ISO timestamp
                    timestamp = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}T{time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}.{ms_part}+00:00"
                else:
                    # Fallback to file modification time
                    timestamp = datetime.fromtimestamp(photo_path.stat().st_mtime, tz=timezone.utc).isoformat()
            except Exception:
                timestamp = datetime.fromtimestamp(photo_path.stat().st_mtime, tz=timezone.utc).isoformat()

            all_photos.append({
                "filename": filename,
                "url": f"/photos/{filename}",
                "timestamp": timestamp
            })

    # Apply pagination
    total = len(all_photos)
    paginated_photos = all_photos[offset:offset + limit]

    return {
        "total": total,
        "photos": paginated_photos,
        "limit": limit,
        "offset": offset
    }


async def get_messages_api(request: Request) -> JSONResponse:
    """
    GET /messages
    Returns all messages as JSON

    Query parameters:
        - limit: Maximum number of messages (default: 50, must be positive)
    """
    # Get and validate limit from query params
    try:
        limit = int(request.query_params.get('limit', 50))
        if limit < 0:
            return JSONResponse(
                {'error': 'Limit must be a non-negative integer'},
                status_code=400
            )
    except ValueError:
        return JSONResponse(
            {'error': 'Limit must be a valid integer'},
            status_code=400
        )

    # Get all messages
    all_messages = _get_all_messages()

    # Apply limit
    all_messages = all_messages[:limit]

    return JSONResponse({
        'count': len(all_messages),
        'messages': all_messages
    })


async def post_reply(request: Request) -> JSONResponse:
    """
    POST /messages/reply
    Submit a reply from human to agent

    Request body (JSON or form):
        - content: Message content (required)
        - in_reply_to: Message ID being replied to (optional)
    """
    try:
        # Parse request body (handle both JSON and form data)
        content_type = request.headers.get('content-type', '')

        if 'application/json' in content_type:
            data = await request.json()
            content = data.get('content', '').strip()
            in_reply_to = data.get('in_reply_to')
        else:
            # Form data
            form = await request.form()
            content_field = form.get('content', '')
            # Handle both string and UploadFile (form data can be either)
            content = content_field.strip() if isinstance(content_field, str) else ''
            in_reply_to_field = form.get('in_reply_to')
            in_reply_to = in_reply_to_field if isinstance(in_reply_to_field, str) else None

        # Validate content (strip() already handled whitespace-only content)
        if not content:
            return JSONResponse(
                {'error': 'Message content is required'},
                status_code=400
            )

        if len(content) > MAX_MESSAGE_LENGTH:
            return JSONResponse(
                {'error': f'Message exceeds maximum length of {MAX_MESSAGE_LENGTH} characters'},
                status_code=400
            )

        # Generate message entry
        message_id = _generate_message_id()
        timestamp = datetime.now(timezone.utc).isoformat()

        message_entry = {
            "message_id": message_id,
            "timestamp": timestamp,
            "content": content,
            "in_reply_to": in_reply_to or None
        }

        # Store to history
        human_messages.messages_from_human.append(message_entry)

        logger.info(f"Reply from human received: {message_id}")

        return JSONResponse({
            'success': True,
            'message_id': message_id,
            'timestamp': timestamp
        })

    except (json.JSONDecodeError, ValueError) as e:
        # Handle expected errors from parsing/validation
        logger.error(f"Error processing reply: {e}")
        return JSONResponse(
            {'error': f'Invalid request: {str(e)}'},
            status_code=400
        )
    except OSError as e:
        # Handle filesystem errors when writing to history
        logger.error(f"Error storing reply: {e}")
        return JSONResponse(
            {'error': 'Failed to store message'},
            status_code=500
        )
    except Exception:
        # Log unexpected errors with full stack trace
        logger.exception("Unexpected error processing reply")
        return JSONResponse(
            {'error': 'Internal server error'},
            status_code=500
        )


async def get_photos_api(request: Request) -> JSONResponse:
    """
    GET /api/photos
    Returns list of captured photos as JSON with pagination

    Query parameters:
        - limit: Maximum number of photos to return (default: 20, max: 100)
        - offset: Number of photos to skip for pagination (default: 0)
    """
    # Get and validate query parameters
    try:
        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))

        # Validate limit (clamp between 1 and 100)
        limit = max(1, min(limit, 100))

        # Validate offset (prevent negative values)
        offset = max(offset, 0)

    except ValueError:
        return JSONResponse(
            {'error': 'Invalid limit or offset parameter'},
            status_code=400
        )

    # Get photos from directory
    result = _get_photos_from_directory(limit=limit, offset=offset)

    return JSONResponse(result)


async def post_capture_photo(request: Request) -> JSONResponse:  # noqa: ARG001
    """
    POST /api/capture
    Trigger camera to capture a new photo

    Returns:
        JSON with photo URL and timestamp on success
    """
    try:
        # Capture photo using camera tool
        photo_path, timestamp = capture_real_photo()

        # Convert file path to URL
        filename = Path(photo_path).name
        photo_url = f"/photos/{filename}"

        logger.info(f"Photo captured via web route: {filename}")

        return JSONResponse({
            'success': True,
            'url': photo_url,
            'timestamp': timestamp,
            'filename': filename
        })

    except ValueError as e:
        # Camera error (not available, capture failed, etc.)
        logger.error(f"Camera capture failed: {e}")
        return JSONResponse(
            {'success': False, 'error': str(e)},
            status_code=500
        )
    except Exception as e:
        # Unexpected error
        logger.error(f"Unexpected error during photo capture: {e}")
        return JSONResponse(
            {'success': False, 'error': 'Internal server error'},
            status_code=500
        )


async def get_messages_ui(request: Request) -> HTMLResponse:  # noqa: ARG001
    """
    GET /messages
    Serve simple HTML UI for viewing and replying to messages
    """
    # Get all messages
    all_messages = _get_all_messages()

    # Build HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🌱 Plant Care Messages</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }}

        header {{
            background: linear-gradient(135deg, #4CAF50, #45a049);
            color: white;
            padding: 30px;
            text-align: center;
        }}

        header h1 {{
            font-size: 2rem;
            margin-bottom: 10px;
        }}

        header p {{
            opacity: 0.9;
            font-size: 0.95rem;
        }}

        .content {{
            padding: 30px;
        }}

        .reply-form {{
            background: #f8f9fa;
            border: 2px solid #e9ecef;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 30px;
        }}

        .reply-form h2 {{
            font-size: 1.3rem;
            margin-bottom: 15px;
            color: #495057;
        }}

        .form-group {{
            margin-bottom: 15px;
        }}

        .form-group label {{
            display: block;
            margin-bottom: 5px;
            font-weight: 500;
            color: #495057;
        }}

        .form-group textarea {{
            width: 100%;
            padding: 12px;
            border: 1px solid #ced4da;
            border-radius: 6px;
            font-family: inherit;
            font-size: 1rem;
            resize: vertical;
            min-height: 100px;
        }}

        .form-group textarea:focus {{
            outline: none;
            border-color: #4CAF50;
            box-shadow: 0 0 0 3px rgba(76, 175, 80, 0.1);
        }}

        .form-group input {{
            width: 100%;
            padding: 12px;
            border: 1px solid #ced4da;
            border-radius: 6px;
            font-family: inherit;
            font-size: 1rem;
        }}

        .form-group input:focus {{
            outline: none;
            border-color: #4CAF50;
            box-shadow: 0 0 0 3px rgba(76, 175, 80, 0.1);
        }}

        .reply-to-box {{
            background: #e7f3ff;
            border-left: 4px solid #667eea;
            padding: 12px;
            margin-bottom: 15px;
            border-radius: 4px;
            display: none;
        }}

        .reply-to-box.active {{
            display: block;
        }}

        .reply-to-text {{
            font-size: 0.9rem;
            color: #495057;
            margin-bottom: 5px;
        }}

        .reply-to-text strong {{
            color: #667eea;
        }}

        .cancel-reply {{
            background: #6c757d;
            color: white;
            padding: 4px 12px;
            border: none;
            border-radius: 4px;
            font-size: 0.85rem;
            cursor: pointer;
            margin-left: 10px;
        }}

        .cancel-reply:hover {{
            background: #5a6268;
        }}

        button {{
            background: #4CAF50;
            color: white;
            padding: 12px 24px;
            border: none;
            border-radius: 6px;
            font-size: 1rem;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.2s;
        }}

        button:hover {{
            background: #45a049;
        }}

        button:active {{
            transform: scale(0.98);
        }}

        .refresh-btn {{
            background: #667eea;
            margin-left: 10px;
        }}

        .refresh-btn:hover {{
            background: #5568d3;
        }}

        .reply-btn {{
            background: #667eea;
            padding: 6px 12px;
            font-size: 0.85rem;
            margin-top: 8px;
        }}

        .reply-btn:hover {{
            background: #5568d3;
        }}

        .messages {{
            margin-top: 30px;
        }}

        .messages h2 {{
            font-size: 1.3rem;
            margin-bottom: 20px;
            color: #495057;
        }}

        .message {{
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 15px;
            transition: box-shadow 0.2s;
        }}

        .message:hover {{
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}

        .message.from-agent {{
            border-left: 4px solid #4CAF50;
            background: #f1f8f4;
        }}

        .message.from-human {{
            border-left: 4px solid #667eea;
            background: #f5f6fa;
        }}

        .message-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            flex-wrap: wrap;
            gap: 10px;
        }}

        .message-label {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85rem;
            font-weight: 500;
        }}

        .message.from-agent .message-label {{
            background: #4CAF50;
            color: white;
        }}

        .message.from-human .message-label {{
            background: #667eea;
            color: white;
        }}

        .message-meta {{
            font-size: 0.85rem;
            color: #6c757d;
        }}

        .message-content {{
            white-space: pre-wrap;
            word-wrap: break-word;
            line-height: 1.6;
        }}

        .reply-indicator {{
            background: #fff3cd;
            border-left: 3px solid #ffc107;
            padding: 8px 12px;
            margin: 10px 0;
            font-size: 0.9rem;
            color: #856404;
            border-radius: 4px;
        }}

        .reply-indicator code {{
            background: #fff;
            padding: 2px 6px;
            border-radius: 3px;
            color: #667eea;
            font-family: 'Courier New', monospace;
            font-size: 0.85rem;
        }}

        .message-footer {{
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px solid #e9ecef;
            font-size: 0.85rem;
            color: #6c757d;
        }}

        .message-footer code {{
            background: #f8f9fa;
            padding: 2px 6px;
            border-radius: 3px;
            color: #495057;
            font-family: 'Courier New', monospace;
            font-size: 0.85rem;
        }}

        .reply-link {{
            color: #667eea;
            text-decoration: none;
            font-weight: 500;
        }}

        .reply-link:hover {{
            text-decoration: underline;
        }}

        .no-messages {{
            text-align: center;
            padding: 40px;
            color: #6c757d;
        }}

        .success-message {{
            background: #d4edda;
            border: 1px solid #c3e6cb;
            color: #155724;
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 15px;
            display: none;
        }}

        .error-message {{
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 15px;
            display: none;
        }}

        @media (max-width: 600px) {{
            body {{
                padding: 10px;
            }}

            header {{
                padding: 20px;
            }}

            header h1 {{
                font-size: 1.5rem;
            }}

            .content {{
                padding: 15px;
            }}

            .message-header {{
                flex-direction: column;
                align-items: flex-start;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🌱 Plant Care Messages</h1>
            <p>Communication between you and your plant care agent</p>
        </header>

        <div class="nav-links" style="background: #f8f9fa; padding: 15px 30px; border-bottom: 2px solid #e9ecef;">
            <a href="/gallery" style="color: #667eea; text-decoration: none; font-weight: 500;">View Photos →</a>
        </div>

        <div class="content">
            <div class="reply-form">
                <h2>Send Message to Agent</h2>
                <div id="successMessage" class="success-message"></div>
                <div id="errorMessage" class="error-message"></div>

                <div id="replyToBox" class="reply-to-box">
                    <div class="reply-to-text">
                        <strong>Replying to:</strong> <span id="replyToPreview"></span>
                    </div>
                    <button type="button" class="cancel-reply" onclick="cancelReply()">Cancel Reply</button>
                </div>

                <form id="replyForm">
                    <input type="hidden" id="inReplyTo" name="in_reply_to" value="">
                    <div class="form-group">
                        <label for="content">Message:</label>
                        <textarea id="content" name="content" required placeholder="Type your message here..."></textarea>
                    </div>
                    <div class="form-group">
                        <label for="manualReplyTo">Or manually enter message ID to reply to (optional):</label>
                        <input type="text" id="manualReplyTo" name="manual_reply_to" placeholder="msg_20251020_123456_789">
                    </div>
                    <button type="submit">Send Message</button>
                    <button type="button" class="refresh-btn" onclick="window.location.reload()">Refresh Page</button>
                </form>
            </div>

            <div class="messages">
                <h2>Message History ({len(all_messages)} messages)</h2>"""

    if not all_messages:
        html += """
                <div class="no-messages">
                    <p>No messages yet. The agent will send messages here when it needs your attention.</p>
                </div>"""
    else:
        for msg in all_messages:
            direction_class = 'from-agent' if msg['direction'] == 'to_human' else 'from-human'
            direction_label = '🌱 From Agent' if msg['direction'] == 'to_human' else '👤 From You'

            # Format timestamp
            try:
                dt = datetime.fromisoformat(msg['timestamp'])
                timestamp_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            except (ValueError, KeyError):
                timestamp_str = msg['timestamp']

            # Build message HTML
            # Create safe preview for JavaScript (truncate and use JSON.dumps for proper escaping)
            msg_content_preview = msg['content'][:50]
            if len(msg['content']) > 50:
                msg_content_preview += "..."

            # JSON-encode values for safe JavaScript embedding
            msg_id_json = json.dumps(msg['message_id'])
            msg_preview_json = json.dumps(msg_content_preview)

            # Add reply indicator if this message is replying to another
            reply_indicator = ""
            if msg.get('in_reply_to'):
                reply_indicator = f"""
                    <div class="reply-indicator">
                        ↩️ In reply to: <code>{msg['in_reply_to']}</code>
                    </div>"""

            html += f"""
                <div class="message {direction_class}">
                    <div class="message-header">
                        <span class="message-label">{direction_label}</span>
                        <span class="message-meta">{timestamp_str}</span>
                    </div>{reply_indicator}
                    <div class="message-content">{msg['content']}</div>
                    <div class="message-footer">
                        <strong>ID:</strong> <code>{msg['message_id']}</code><br>
                        <button type="button" class="reply-btn" onclick="setReplyTo({msg_id_json}, {msg_preview_json})">Reply to this message</button>
                    </div>
                </div>"""

    html += """
            </div>
        </div>
    </div>

    <script>
        // Set reply-to when clicking a reply button
        function setReplyTo(messageId, messagePreview) {
            const replyToBox = document.getElementById('replyToBox');
            const replyToPreview = document.getElementById('replyToPreview');
            const inReplyToField = document.getElementById('inReplyTo');

            replyToBox.classList.add('active');
            replyToPreview.textContent = messageId + ' - "' + messagePreview + '"';
            inReplyToField.value = messageId;

            // Clear manual input if present
            document.getElementById('manualReplyTo').value = '';

            // Scroll to form and focus
            document.getElementById('content').focus();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        // Cancel reply
        function cancelReply() {
            const replyToBox = document.getElementById('replyToBox');
            const inReplyToField = document.getElementById('inReplyTo');

            replyToBox.classList.remove('active');
            inReplyToField.value = '';
        }

        // Handle form submission
        document.getElementById('replyForm').addEventListener('submit', async (e) => {
            e.preventDefault();

            const content = document.getElementById('content').value.trim();
            const successMsg = document.getElementById('successMessage');
            const errorMsg = document.getElementById('errorMessage');

            // Get in_reply_to value (prioritize hidden field from Reply button, then manual input)
            const inReplyTo = document.getElementById('inReplyTo').value || document.getElementById('manualReplyTo').value.trim() || null;

            // Hide previous messages
            successMsg.style.display = 'none';
            errorMsg.style.display = 'none';

            if (!content) {
                errorMsg.textContent = 'Please enter a message';
                errorMsg.style.display = 'block';
                return;
            }

            try {
                const payload = { content };
                if (inReplyTo) {
                    payload.in_reply_to = inReplyTo;
                }

                const response = await fetch('/api/messages/reply', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    successMsg.textContent = 'Message sent successfully! Refreshing...';
                    successMsg.style.display = 'block';
                    document.getElementById('content').value = '';
                    document.getElementById('manualReplyTo').value = '';
                    cancelReply();

                    // Refresh page after 1 second
                    setTimeout(() => {
                        window.location.reload();
                    }, 1000);
                } else {
                    errorMsg.textContent = data.error || 'Failed to send message';
                    errorMsg.style.display = 'block';
                }
            } catch (error) {
                errorMsg.textContent = 'Network error: ' + error.message;
                errorMsg.style.display = 'block';
            }
        });
    </script>
</body>
</html>"""

    return HTMLResponse(content=html)


async def get_gallery_ui(request: Request) -> HTMLResponse:
    """
    GET /gallery
    Serve simple HTML UI for viewing and capturing photos
    """
    # Get photos with pagination
    limit = 20
    offset = int(request.query_params.get('offset', 0))

    # Validate offset (prevent negative values)
    offset = max(offset, 0)

    photos_data = _get_photos_from_directory(limit=limit, offset=offset)

    photos = photos_data['photos']
    total = photos_data['total']
    has_more = (offset + limit) < total

    # Build HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📷 Plant Photos</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }}

        header {{
            background: linear-gradient(135deg, #4CAF50, #45a049);
            color: white;
            padding: 30px;
            text-align: center;
        }}

        header h1 {{
            font-size: 2rem;
            margin-bottom: 10px;
        }}

        header p {{
            opacity: 0.9;
            font-size: 0.95rem;
        }}

        .nav-links {{
            background: #f8f9fa;
            padding: 15px 30px;
            border-bottom: 2px solid #e9ecef;
        }}

        .nav-links a {{
            color: #667eea;
            text-decoration: none;
            font-weight: 500;
            margin-right: 20px;
        }}

        .nav-links a:hover {{
            text-decoration: underline;
        }}

        .content {{
            padding: 30px;
        }}

        .capture-section {{
            background: #f8f9fa;
            border: 2px solid #e9ecef;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 30px;
            text-align: center;
        }}

        .capture-btn {{
            background: #4CAF50;
            color: white;
            padding: 12px 24px;
            border: none;
            border-radius: 6px;
            font-size: 1rem;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.2s;
        }}

        .capture-btn:hover {{
            background: #45a049;
        }}

        .capture-btn:disabled {{
            background: #ccc;
            cursor: not-allowed;
        }}

        .status-message {{
            margin-top: 15px;
            padding: 12px;
            border-radius: 6px;
            display: none;
        }}

        .status-message.success {{
            background: #d4edda;
            border: 1px solid #c3e6cb;
            color: #155724;
            display: block;
        }}

        .status-message.error {{
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
            display: block;
        }}

        .gallery {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .photo-card {{
            background: white;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            overflow: hidden;
            transition: box-shadow 0.2s, transform 0.2s;
        }}

        .photo-card:hover {{
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            transform: translateY(-2px);
        }}

        .photo-card img {{
            width: 100%;
            height: 200px;
            object-fit: cover;
            display: block;
        }}

        .photo-info {{
            padding: 15px;
        }}

        .photo-timestamp {{
            font-size: 0.9rem;
            color: #6c757d;
            margin-bottom: 8px;
        }}

        .photo-filename {{
            font-size: 0.85rem;
            color: #495057;
            font-family: 'Courier New', monospace;
            word-break: break-all;
        }}

        .no-photos {{
            text-align: center;
            padding: 60px 20px;
            color: #6c757d;
        }}

        .no-photos p {{
            font-size: 1.1rem;
            margin-bottom: 10px;
        }}

        .load-more {{
            text-align: center;
            padding: 20px;
        }}

        .load-more-btn {{
            background: #667eea;
            color: white;
            padding: 12px 24px;
            border: none;
            border-radius: 6px;
            font-size: 1rem;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.2s;
            text-decoration: none;
            display: inline-block;
        }}

        .load-more-btn:hover {{
            background: #5568d3;
        }}

        .photo-count {{
            text-align: center;
            color: #6c757d;
            margin-bottom: 20px;
            font-size: 0.95rem;
        }}

        @media (max-width: 600px) {{
            body {{
                padding: 10px;
            }}

            header {{
                padding: 20px;
            }}

            header h1 {{
                font-size: 1.5rem;
            }}

            .content {{
                padding: 15px;
            }}

            .gallery {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📷 Plant Photos</h1>
            <p>Photo gallery and camera controls</p>
        </header>

        <div class="nav-links">
            <a href="/messages">← Back to Messages</a>
        </div>

        <div class="content">
            <div class="capture-section">
                <h2>Capture New Photo</h2>
                <button id="captureBtn" class="capture-btn">📸 Take Photo</button>
                <div id="statusMessage" class="status-message"></div>
            </div>

            <div class="photo-count">
                Showing {len(photos)} of {total} photos
            </div>

            <div class="gallery" id="gallery">"""

    if not photos:
        html += """
                <div class="no-photos" style="grid-column: 1 / -1;">
                    <p>📷 No photos yet</p>
                    <p style="font-size: 0.9rem;">Click "Take Photo" above to capture your first plant photo!</p>
                </div>"""
    else:
        for photo in photos:
            # Format timestamp
            try:
                dt = datetime.fromisoformat(photo['timestamp'])
                timestamp_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            except (ValueError, KeyError):
                timestamp_str = photo['timestamp']

            html += f"""
                <div class="photo-card">
                    <a href="{photo['url']}" target="_blank">
                        <img src="{photo['url']}" alt="{photo['filename']}" loading="lazy">
                    </a>
                    <div class="photo-info">
                        <div class="photo-timestamp">📅 {timestamp_str}</div>
                        <div class="photo-filename">{photo['filename']}</div>
                    </div>
                </div>"""

    html += """
            </div>"""

    # Add "Load More" button if there are more photos
    if has_more:
        next_offset = offset + limit
        html += f"""
            <div class="load-more">
                <a href="/gallery?offset={next_offset}" class="load-more-btn">Load More Photos</a>
            </div>"""

    html += """
        </div>
    </div>

    <script>
        // Handle photo capture
        document.getElementById('captureBtn').addEventListener('click', async () => {
            const btn = document.getElementById('captureBtn');
            const statusMsg = document.getElementById('statusMessage');

            // Disable button and show loading
            btn.disabled = true;
            btn.textContent = '📸 Capturing...';
            statusMsg.style.display = 'none';
            statusMsg.className = 'status-message';

            try {
                const response = await fetch('/api/capture', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });

                const data = await response.json();

                if (response.ok && data.success) {
                    statusMsg.textContent = '✓ Photo captured successfully! Refreshing page...';
                    statusMsg.classList.add('success');

                    // Refresh page after 1 second to show new photo
                    setTimeout(() => {
                        window.location.reload();
                    }, 1000);
                } else {
                    statusMsg.textContent = '✗ Error: ' + (data.error || 'Failed to capture photo');
                    statusMsg.classList.add('error');
                    btn.disabled = false;
                    btn.textContent = '📸 Take Photo';
                }
            } catch (error) {
                statusMsg.textContent = '✗ Network error: ' + error.message;
                statusMsg.classList.add('error');
                btn.disabled = false;
                btn.textContent = '📸 Take Photo';
            }
        });
    </script>
</body>
</html>"""

    return HTMLResponse(content=html)


def add_message_routes(app: Starlette):
    """
    Add message and photo routes to the Starlette app.

    Note: This function should only be called once during app initialization
    to avoid duplicate routes.

    Args:
        app: The Starlette application instance
    """
    # Define routes to add
    # Human-facing UI at /messages and /gallery
    # API endpoints under /api/ for programmatic access
    routes_to_add = [
        # Message routes
        ('/messages', get_messages_ui, ['GET']),
        ('/api/messages', get_messages_api, ['GET']),
        ('/api/messages/reply', post_reply, ['POST']),
        # Photo routes
        ('/gallery', get_gallery_ui, ['GET']),
        ('/api/photos', get_photos_api, ['GET']),
        ('/api/capture', post_capture_photo, ['POST']),
    ]

    # Add routes using Starlette's built-in route management
    routes_added = 0
    for path, endpoint, methods in routes_to_add:
        try:
            # Starlette's add_route handles deduplication and route compilation
            app.add_route(path, endpoint, methods=methods)
            routes_added += 1
            logger.debug(f"Added route: {methods} {path}")
        except Exception as exc:
            # Route may already exist or other registration issue
            logger.warning(f"Could not add route {methods} {path}: {exc}")

    logger.info(f"Added {routes_added} message and photo routes to Starlette app")
