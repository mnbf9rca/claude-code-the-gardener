"""
Tests for Human Messages Tool
"""
import pytest
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock
from freezegun import freeze_time
from tools.human_messages import (
    setup_human_messages_tools,
    _generate_message_id,
    _send_email_notification,
    MAX_MESSAGE_LENGTH
)
import tools.human_messages as human_messages_module
from fastmcp import FastMCP


@pytest.fixture(autouse=True)
def clean_message_history(tmp_path):
    """Reset message history state before each test"""
    # Use temp directory for state files (don't touch production state!)
    from utils.jsonl_history import JsonlHistory

    # Save original histories
    original_to_human = human_messages_module.messages_to_human
    original_from_human = human_messages_module.messages_from_human

    # Create new history instances with temp files
    human_messages_module.messages_to_human = JsonlHistory(
        file_path=tmp_path / "messages_to_human.jsonl",
        max_memory_entries=1000
    )
    human_messages_module.messages_from_human = JsonlHistory(
        file_path=tmp_path / "messages_from_human.jsonl",
        max_memory_entries=1000
    )

    yield

    # Restore original histories
    human_messages_module.messages_to_human = original_to_human
    human_messages_module.messages_from_human = original_from_human


@pytest.fixture
def test_mcp():
    """Create a test MCP server with message tools"""
    mcp = FastMCP("test")
    setup_human_messages_tools(mcp)
    return mcp


def test_generate_message_id():
    """Test message ID generation"""
    # Test with frozen time
    with freeze_time("2025-10-20 14:30:45.123456"):
        msg_id = _generate_message_id()

        # Check format: msg_YYYYMMDD_HHMMSS_mmm
        assert msg_id == "msg_20251020_143045_123"
        assert msg_id.startswith("msg_")
        parts = msg_id.split("_")
        assert len(parts) == 4  # msg, date, time, milliseconds

        # Check date part is 8 digits
        assert len(parts[1]) == 8
        assert parts[1].isdigit()

        # Check time part is 6 digits
        assert len(parts[2]) == 6
        assert parts[2].isdigit()

        # Check milliseconds part is 3 digits
        assert len(parts[3]) == 3
        assert parts[3].isdigit()

    # Generate with different time to ensure they're different
    with freeze_time("2025-10-20 14:30:45.789012"):
        msg_id2 = _generate_message_id()
        assert msg_id2 == "msg_20251020_143045_789"
        assert msg_id != msg_id2


@pytest.mark.asyncio
async def test_send_message_to_human_basic(test_mcp, clean_message_history):
    """Test basic message sending"""

    # Get the tool
    tool = test_mcp._tool_manager._tools["send_message_to_human"]

    # Send a message
    tool_result = await tool.run(arguments={"message": "Hello human, the plant needs water!"})
    result_dict = json.loads(tool_result.content[0].text)

    # Check response
    assert result_dict["message_id"].startswith("msg_")
    assert isinstance(result_dict["timestamp"], str)

    # Verify timestamp is valid ISO8601
    dt = datetime.fromisoformat(result_dict["timestamp"])
    assert dt.tzinfo is not None

    # Check message was stored
    messages = human_messages_module.messages_to_human.get_all()
    assert len(messages) == 1
    assert messages[0]["content"] == "Hello human, the plant needs water!"
    assert messages[0]["message_id"] == result_dict["message_id"]
    assert messages[0]["in_reply_to"] is None


@pytest.mark.asyncio
async def test_send_message_with_reply_to(test_mcp, clean_message_history):
    """Test sending a message in reply to a human message"""

    # First, simulate a message from human to agent
    human_msg_id = "msg_20251020_120000_001"
    human_messages_module.messages_from_human.append({
        "message_id": human_msg_id,
        "timestamp": "2025-10-20T12:00:00+00:00",
        "content": "Should I water the plant today?",
        "in_reply_to": None
    })

    tool = test_mcp._tool_manager._tools["send_message_to_human"]

    # Agent replies to the human's question
    tool_result = await tool.run(arguments={
        "message": "Regarding your question about watering... Yes, the soil moisture is low.",
        "in_reply_to": human_msg_id
    })
    result_dict = json.loads(tool_result.content[0].text)

    # Check message was stored with reply reference to the human's message
    messages = human_messages_module.messages_to_human.get_all()
    assert len(messages) == 1
    assert messages[0]["in_reply_to"] == human_msg_id
    assert messages[0]["content"] == "Regarding your question about watering... Yes, the soil moisture is low."

    # Verify we can trace the conversation thread
    human_messages = human_messages_module.messages_from_human.get_all()
    assert len(human_messages) == 1
    assert human_messages[0]["message_id"] == human_msg_id


@pytest.mark.asyncio
async def test_send_message_too_long(test_mcp, clean_message_history):
    """Test that overly long messages are rejected"""
    tool = test_mcp._tool_manager._tools["send_message_to_human"]

    # Create a message that exceeds max length
    long_message = "x" * (MAX_MESSAGE_LENGTH + 1)

    # Should raise ValueError
    with pytest.raises(Exception, match="exceeds maximum length"):
        await tool.run(arguments={"message": long_message})

    # Verify no message was stored
    assert len(human_messages_module.messages_to_human.get_all()) == 0


@pytest.mark.asyncio
async def test_send_message_empty_content(test_mcp, clean_message_history):
    """Test that empty messages are rejected"""
    tool = test_mcp._tool_manager._tools["send_message_to_human"]

    # Should raise ValueError for empty message
    with pytest.raises(ValueError, match="Message content is required"):
        await tool.run(arguments={"message": ""})

    # Verify no message was stored
    assert len(human_messages_module.messages_to_human.get_all()) == 0


@pytest.mark.asyncio
async def test_send_message_whitespace_only(test_mcp, clean_message_history):
    """Test that whitespace-only messages are rejected"""
    tool = test_mcp._tool_manager._tools["send_message_to_human"]

    # Should raise ValueError for whitespace-only message
    with pytest.raises(ValueError, match="whitespace-only"):
        await tool.run(arguments={"message": "   \n\t  "})

    # Verify no message was stored
    assert len(human_messages_module.messages_to_human.get_all()) == 0


@pytest.mark.asyncio
async def test_send_email_notification_not_configured(caplog):
    """Test that email notification fails gracefully when not configured"""

    with caplog.at_level(logging.DEBUG):
        with patch.dict('os.environ', {}, clear=True):
            # Call with missing SMTP config
            _send_email_notification("msg_test_001", "Test message")

            # Should log debug message about missing config
            assert "SMTP not configured" in caplog.text


@pytest.mark.asyncio
async def test_send_email_notification_configured():
    """Test email notification when SMTP is configured"""
    env_vars = {
        'SMTP_HOST': 'smtp.example.com',
        'SMTP_PORT': '587',
        'SMTP_USER': 'test@example.com',
        'SMTP_PASSWORD': 'password',
        'SMTP_FROM': 'test@example.com',
        'SMTP_TO': 'user@example.com',
        'MCP_HOST': 'localhost',
        'MCP_PORT': '8000'
    }

    with patch.dict('os.environ', env_vars):
        with patch('smtplib.SMTP') as mock_smtp:
            # Configure mock
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            # Send notification
            _send_email_notification("msg_test_001", "Test message content")

            # Verify SMTP was called with timeout
            mock_smtp.assert_called_once_with('smtp.example.com', 587, timeout=10)
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with('test@example.com', 'password')
            mock_server.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_send_email_notification_failure(caplog):
    """Test that email failures don't break message sending"""
    env_vars = {
        'SMTP_HOST': 'smtp.example.com',
        'SMTP_PORT': '587',
        'SMTP_USER': 'test@example.com',
        'SMTP_PASSWORD': 'password',
        'SMTP_FROM': 'test@example.com',
        'SMTP_TO': 'user@example.com'
    }

    with patch.dict('os.environ', env_vars):
        with patch('smtplib.SMTP', side_effect=Exception("SMTP error")):
            # Should not raise exception
            _send_email_notification("msg_test_001", "Test message")

            # Should log warning
            assert "Failed to send email notification" in caplog.text


@pytest.mark.asyncio
async def test_send_email_notification_without_auth():
    """Test email notification without authentication (unauthenticated SMTP on port 25)"""
    env_vars = {
        'SMTP_HOST': 'localhost',
        'SMTP_PORT': '25',
        'SMTP_FROM': 'plant-care@localhost',
        'SMTP_TO': 'user@example.com',
        'MCP_HOST': 'localhost',
        'MCP_PORT': '8000'
    }

    with patch.dict('os.environ', env_vars):
        with patch('smtplib.SMTP') as mock_smtp:
            # Configure mock
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            # Send notification
            _send_email_notification("msg_test_001", "Test message content")

            # Verify SMTP was called with timeout
            mock_smtp.assert_called_once_with('localhost', 25, timeout=10)
            # Port 25 defaults to no TLS, so starttls should NOT be called
            mock_server.starttls.assert_not_called()
            # Should NOT call login when no auth credentials provided
            mock_server.login.assert_not_called()
            mock_server.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_send_email_notification_port_25_with_tls_enabled():
    """Test email notification on port 25 with TLS explicitly enabled"""
    env_vars = {
        'SMTP_HOST': 'localhost',
        'SMTP_PORT': '25',
        'SMTP_FROM': 'plant-care@localhost',
        'SMTP_TO': 'user@example.com',
        'SMTP_USE_TLS': 'true',  # Explicitly enable TLS on port 25
        'MCP_HOST': 'localhost',
        'MCP_PORT': '8000'
    }

    with patch.dict('os.environ', env_vars):
        with patch('smtplib.SMTP') as mock_smtp:
            # Configure mock
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            # Send notification
            _send_email_notification("msg_test_001", "Test message content")

            # Verify SMTP was called with timeout
            mock_smtp.assert_called_once_with('localhost', 25, timeout=10)
            # TLS explicitly enabled, so starttls SHOULD be called
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_not_called()
            mock_server.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_list_messages_from_human_empty(test_mcp, clean_message_history):
    """Test listing messages when none exist"""

    tool = test_mcp._tool_manager._tools["list_messages_from_human"]

    tool_result = await tool.run(arguments={})
    result_dict = json.loads(tool_result.content[0].text)

    assert result_dict["count"] == 0
    assert len(result_dict["messages"]) == 0


@pytest.mark.asyncio
async def test_list_messages_from_human_basic(test_mcp, clean_message_history):
    """Test listing messages from human"""

    # Add some test messages
    human_messages_module.messages_from_human.append({
        "message_id": "msg_20251020_100000_001",
        "timestamp": "2025-10-20T10:00:00+00:00",
        "content": "First message",
        "in_reply_to": None
    })
    human_messages_module.messages_from_human.append({
        "message_id": "msg_20251020_110000_001",
        "timestamp": "2025-10-20T11:00:00+00:00",
        "content": "Second message",
        "in_reply_to": "msg_20251020_095500_001"
    })

    tool = test_mcp._tool_manager._tools["list_messages_from_human"]

    tool_result = await tool.run(arguments={})
    result_dict = json.loads(tool_result.content[0].text)

    # Should return newest first
    assert result_dict["count"] == 2
    assert result_dict["messages"][0]["message_id"] == "msg_20251020_110000_001"
    assert result_dict["messages"][1]["message_id"] == "msg_20251020_100000_001"
    assert result_dict["messages"][0]["content"] == "Second message"
    assert result_dict["messages"][0]["in_reply_to"] == "msg_20251020_095500_001"


@pytest.mark.asyncio
async def test_list_messages_pagination(test_mcp, clean_message_history):
    """Test message pagination"""

    # Add 5 test messages
    for i in range(5):
        human_messages_module.messages_from_human.append({
            "message_id": f"msg_20251020_{10 + i:02d}0000_001",
            "timestamp": f"2025-10-20T{10 + i:02d}:00:00+00:00",
            "content": f"Message {i+1}",
            "in_reply_to": None
        })

    tool = test_mcp._tool_manager._tools["list_messages_from_human"]

    # Get first 3
    tool_result = await tool.run(arguments={"limit": 3, "offset": 0})
    result_dict = json.loads(tool_result.content[0].text)
    assert result_dict["count"] == 3
    assert result_dict["messages"][0]["content"] == "Message 5"  # Newest first
    assert result_dict["messages"][2]["content"] == "Message 3"

    # Get next 2
    tool_result = await tool.run(arguments={"limit": 2, "offset": 3})
    result_dict = json.loads(tool_result.content[0].text)
    assert result_dict["count"] == 2
    assert result_dict["messages"][0]["content"] == "Message 2"
    assert result_dict["messages"][1]["content"] == "Message 1"


@pytest.mark.asyncio
async def test_list_messages_without_content(test_mcp, clean_message_history):
    """Test listing messages without content"""

    human_messages_module.messages_from_human.append({
        "message_id": "msg_20251020_100000_001",
        "timestamp": "2025-10-20T10:00:00+00:00",
        "content": "Secret message",
        "in_reply_to": None
    })

    tool = test_mcp._tool_manager._tools["list_messages_from_human"]

    tool_result = await tool.run(arguments={"include_content": False})
    result_dict = json.loads(tool_result.content[0].text)

    assert result_dict["count"] == 1
    assert result_dict["messages"][0]["message_id"] == "msg_20251020_100000_001"
    assert result_dict["messages"][0]["content"] == ""  # Content not included


def test_message_persistence(tmp_path, clean_message_history):
    """Test that messages persist to disk"""
    # Create temp file path
    test_file = tmp_path / "test_messages.jsonl"

    # Create new history with temp file
    from utils.jsonl_history import JsonlHistory
    test_history = JsonlHistory(file_path=test_file, max_memory_entries=100)

    # Add message
    test_history.append({
        "message_id": "msg_20251020_100000_001",
        "timestamp": "2025-10-20T10:00:00+00:00",
        "content": "Test message",
        "in_reply_to": None
    })

    # Verify file was created
    assert test_file.exists()

    # Create new history instance and load
    test_history2 = JsonlHistory(file_path=test_file, max_memory_entries=100)
    test_history2.load()

    # Verify message was loaded
    messages = test_history2.get_all()
    assert len(messages) == 1
    assert messages[0]["message_id"] == "msg_20251020_100000_001"
