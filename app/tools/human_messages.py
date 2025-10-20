"""
Human Messages Tool - Bidirectional communication between agent and human

Allows Claude to send messages to the human caretaker for alerts, questions,
or updates. Human can reply via web interface.
"""
from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from utils.jsonl_history import JsonlHistory
from utils.paths import get_app_dir
from utils.logging_config import get_logger
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = get_logger(__name__)

# Constants
DEFAULT_LIST_LIMIT = 10
MAX_LIST_LIMIT = 50
MAX_MESSAGE_LENGTH = 50_000
MAX_MEMORY_ENTRIES = 1000

# State files
MESSAGES_TO_HUMAN_FILE = get_app_dir("data") / "messages_to_human.jsonl"
MESSAGES_FROM_HUMAN_FILE = get_app_dir("data") / "messages_from_human.jsonl"

# History managers
messages_to_human = JsonlHistory(file_path=MESSAGES_TO_HUMAN_FILE, max_memory_entries=MAX_MEMORY_ENTRIES)
messages_from_human = JsonlHistory(file_path=MESSAGES_FROM_HUMAN_FILE, max_memory_entries=MAX_MEMORY_ENTRIES)

# Load existing messages from disk
messages_to_human.load()
messages_from_human.load()


def _generate_message_id() -> str:
    """
    Generate a unique message ID based on timestamp.

    Returns:
        Message ID in format: msg_YYYYMMDD_HHMMSS_mmm
    """
    now = datetime.now(timezone.utc)
    # Include microseconds for uniqueness
    return now.strftime("msg_%Y%m%d_%H%M%S_") + f"{now.microsecond // 1000:03d}"


def _send_email_notification(message_id: str, content: str, in_reply_to: Optional[str] = None) -> bool:
    """
    Send email notification to human when agent sends a message.
    Gracefully degrades if SMTP is not configured.

    Args:
        message_id: The message ID
        content: The message content
        in_reply_to: Optional message ID this is in reply to

    Returns:
        True if email was sent successfully, False otherwise
    """
    # Check if SMTP is configured (host, from, and recipient are required)
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_to = os.getenv("SMTP_TO")
    smtp_from = os.getenv("SMTP_FROM")  # Required - must be explicitly set

    # TLS configuration - default based on port
    # Port 587: STARTTLS (default true)
    # Port 25: Plain SMTP (default false)
    # Port 465: Would need SMTP_SSL (not currently supported)
    smtp_port_int = int(smtp_port)
    smtp_use_tls_default = "true" if smtp_port_int == 587 else "false"
    smtp_use_tls = os.getenv("SMTP_USE_TLS", smtp_use_tls_default).lower() in ("true", "1", "yes")

    if not smtp_host or not smtp_to or not smtp_from:
        logger.debug("SMTP not configured (missing host, from, or recipient), skipping email notification")
        return False

    # Type checker: these are guaranteed to be strings after the check above
    assert smtp_host is not None
    assert smtp_to is not None
    assert smtp_from is not None

    # Authentication is optional - both user and password must be present for auth
    smtp_auth_enabled = bool(smtp_user and smtp_password)

    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"🌱 Plant Care Message: {message_id}"
        msg['From'] = smtp_from
        msg['To'] = smtp_to

        # Create plain text and HTML versions
        text_content = f"""Plant Care System Message

Message ID: {message_id}
Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
{f'In Reply To: {in_reply_to}' if in_reply_to else ''}

Message:
{content}

---
View and reply at: http://{os.getenv('MCP_HOST', 'localhost')}:{os.getenv('MCP_PORT', '8000')}/messages
"""

        html_content = f"""<html>
<head></head>
<body>
<h2>🌱 Plant Care System Message</h2>
<p><strong>Message ID:</strong> {message_id}<br>
<strong>Time:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}<br>
{f'<strong>In Reply To:</strong> {in_reply_to}<br>' if in_reply_to else ''}
</p>
<div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #4CAF50; margin: 20px 0;">
<pre style="white-space: pre-wrap; font-family: sans-serif;">{content}</pre>
</div>
<p><a href="http://{os.getenv('MCP_HOST', 'localhost')}:{os.getenv('MCP_PORT', '8000')}/messages">View and Reply</a></p>
</body>
</html>"""

        # Attach parts
        part1 = MIMEText(text_content, 'plain')
        part2 = MIMEText(html_content, 'html')
        msg.attach(part1)
        msg.attach(part2)

        # Send email with timeout to avoid hanging
        smtp_timeout = 10  # seconds
        with smtplib.SMTP(smtp_host, smtp_port_int, timeout=smtp_timeout) as server:
            # Only use STARTTLS if configured
            if smtp_use_tls:
                server.starttls()
            # Only authenticate if credentials are provided
            if smtp_auth_enabled:
                server.login(smtp_user, smtp_password)  # type: ignore
            server.send_message(msg)

        logger.info(f"Email notification sent for message {message_id}")
        return True

    except Exception as e:
        # Don't fail the message sending if email fails
        logger.warning(f"Failed to send email notification: {e}")
        return False


class SendMessageResponse(BaseModel):
    """Response from sending a message to human"""
    timestamp: str = Field(..., description="When message was sent")
    message_id: str = Field(..., description="Unique message ID")


class MessageEntry(BaseModel):
    """A message entry"""
    message_id: str
    timestamp: str
    content: str
    in_reply_to: Optional[str] = None


class ListMessagesResponse(BaseModel):
    """Response from listing messages"""
    count: int = Field(..., description="Number of messages returned")
    messages: List[MessageEntry] = Field(..., description="List of messages")


def setup_human_messages_tools(mcp: FastMCP):
    """Set up human messaging tools on the MCP server"""

    @mcp.tool()
    async def send_message_to_human(
        message: str = Field(..., description=f"The message content (max {MAX_MESSAGE_LENGTH} characters)"),
        in_reply_to: Optional[str] = Field(None, description="Optional message ID this is in reply to")
    ) -> SendMessageResponse:
        """
        Send a message to the human caretaker for review, alerts, or requests for input.

        The human will receive an email notification and can reply.

        Args:
            message: The message content (markdown supported, max 50,000 characters)
            in_reply_to: Optional message ID if this is a reply to a previous (human or agent) message (not validated)

        Returns:
            Response with timestamp and unique message_id
        """
        # Validate message content
        if not message or not message.strip():
            raise ValueError("Message content is required and cannot be empty or whitespace-only")
        if len(message) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Message exceeds maximum length of {MAX_MESSAGE_LENGTH} characters")

        # Generate unique message ID
        message_id = _generate_message_id()
        timestamp = datetime.now(timezone.utc).isoformat()

        # Create message entry
        message_entry = {
            "message_id": message_id,
            "timestamp": timestamp,
            "content": message,
            "in_reply_to": in_reply_to
        }

        # Store to history
        messages_to_human.append(message_entry)

        # Send email notification (gracefully degrades if not configured)
        _send_email_notification(message_id, message, in_reply_to)

        logger.info(f"Message sent to human: {message_id}")

        return SendMessageResponse(
            timestamp=timestamp,
            message_id=message_id
        )

    @mcp.tool()
    async def list_messages_from_human(
        limit: int = Field(default=DEFAULT_LIST_LIMIT, description=f"Maximum number of messages to return (max {MAX_LIST_LIMIT})", ge=1, le=MAX_LIST_LIMIT),
        offset: int = Field(default=0, description="Number of messages to skip for pagination", ge=0),
        include_content: bool = Field(default=True, description="Whether to include message content in response")
    ) -> ListMessagesResponse:
        """
        List messages sent from the human caretaker to the agent.

        Messages are returned in reverse chronological order (newest first).
        Use pagination with limit and offset for large message histories.

        Args:
            limit: Maximum number of messages to return (default 10, max 50)
            offset: Number of messages to skip from the newest (default 0)
            include_content: Whether to include full message content (default true)

        Returns:
            List of messages with metadata and optionally content
        """
        # Get recent messages (reversed to get newest first)
        all_messages = messages_from_human.get_all()[::-1]  # Newest first

        # Apply pagination
        paginated = all_messages[offset:offset + limit]

        # Create message entries
        message_entries = []
        for msg in paginated:
            entry_data = {
                "message_id": msg["message_id"],
                "timestamp": msg["timestamp"],
                "content": msg["content"] if include_content else "",
                "in_reply_to": msg.get("in_reply_to")
            }
            message_entries.append(MessageEntry(**entry_data))

        logger.debug(f"Listed {len(message_entries)} messages from human (limit={limit}, offset={offset})")

        return ListMessagesResponse(
            count=len(message_entries),
            messages=message_entries
        )
