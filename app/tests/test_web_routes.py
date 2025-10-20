"""
Tests for Web Routes (HTTP endpoints and UI)
"""
import pytest
from freezegun import freeze_time
from starlette.testclient import TestClient
from starlette.applications import Starlette
from web_routes import add_message_routes
from tools.human_messages import (
    messages_to_human,
    messages_from_human,
    MESSAGES_TO_HUMAN_FILE,
    MESSAGES_FROM_HUMAN_FILE
)


@pytest.fixture(autouse=True)
def clean_message_history():
    """Clean message history before and after each test"""
    # Clear in-memory state
    messages_to_human.clear()
    messages_from_human.clear()

    # Delete actual JSONL files
    if MESSAGES_TO_HUMAN_FILE.exists():
        MESSAGES_TO_HUMAN_FILE.unlink()
    if MESSAGES_FROM_HUMAN_FILE.exists():
        MESSAGES_FROM_HUMAN_FILE.unlink()

    yield

    # Cleanup after test
    messages_to_human.clear()
    messages_from_human.clear()
    if MESSAGES_TO_HUMAN_FILE.exists():
        MESSAGES_TO_HUMAN_FILE.unlink()
    if MESSAGES_FROM_HUMAN_FILE.exists():
        MESSAGES_FROM_HUMAN_FILE.unlink()


@pytest.fixture
def test_app():
    """Create a test Starlette app with message routes"""
    app = Starlette()
    add_message_routes(app)
    return app


@pytest.fixture
def client(test_app):
    """Create a test client"""
    return TestClient(test_app)


def test_get_messages_ui_empty(client, clean_message_history):
    """Test that UI loads with no messages"""
    response = client.get("/messages")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Plant Care Messages" in response.text
    assert "No messages yet" in response.text


def test_get_messages_ui_with_messages(client, clean_message_history):
    """Test that UI displays messages"""
    # Add test messages
    messages_to_human.append({
        "message_id": "msg_20251020_100000_001",
        "timestamp": "2025-10-20T10:00:00+00:00",
        "content": "Plant needs water!",
        "in_reply_to": None
    })
    messages_from_human.append({
        "message_id": "msg_20251020_110000_001",
        "timestamp": "2025-10-20T11:00:00+00:00",
        "content": "I'll water it now",
        "in_reply_to": "msg_20251020_100000_001"
    })

    response = client.get("/messages")

    assert response.status_code == 200
    assert "Plant needs water!" in response.text
    assert "I'll water it now" in response.text
    assert "msg_20251020_100000_001" in response.text
    assert "msg_20251020_110000_001" in response.text
    assert "From Agent" in response.text
    assert "From You" in response.text


def test_get_messages_ui_shows_reply_reference(client, clean_message_history):
    """Test that UI shows in_reply_to references"""
    messages_to_human.append({
        "message_id": "msg_20251020_100000_001",
        "timestamp": "2025-10-20T10:00:00+00:00",
        "content": "Question for you",
        "in_reply_to": None
    })
    messages_from_human.append({
        "message_id": "msg_20251020_110000_001",
        "timestamp": "2025-10-20T11:00:00+00:00",
        "content": "Here's the answer",
        "in_reply_to": "msg_20251020_100000_001"
    })

    response = client.get("/messages")

    assert response.status_code == 200
    assert "In reply to" in response.text
    assert "msg_20251020_100000_001" in response.text


def test_get_messages_ui_message_count(client, clean_message_history):
    """Test that UI shows correct message count"""
    # Add 3 messages
    for i in range(3):
        messages_to_human.append({
            "message_id": f"msg_test_{i}",
            "timestamp": f"2025-10-20T{10+i:02d}:00:00+00:00",
            "content": f"Message {i}",
            "in_reply_to": None
        })

    response = client.get("/messages")

    assert response.status_code == 200
    assert "3 messages" in response.text


def test_get_messages_api_empty(client, clean_message_history):
    """Test API returns empty list when no messages"""
    response = client.get("/api/messages")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["messages"] == []


def test_get_messages_api_with_messages(client, clean_message_history):
    """Test API returns messages as JSON"""
    # Add test messages
    messages_to_human.append({
        "message_id": "msg_20251020_100000_001",
        "timestamp": "2025-10-20T10:00:00+00:00",
        "content": "Agent message",
        "in_reply_to": None
    })
    messages_from_human.append({
        "message_id": "msg_20251020_110000_001",
        "timestamp": "2025-10-20T11:00:00+00:00",
        "content": "Human reply",
        "in_reply_to": "msg_20251020_100000_001"
    })

    response = client.get("/api/messages")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert len(data["messages"]) == 2

    # Check messages are sorted newest first
    assert data["messages"][0]["message_id"] == "msg_20251020_110000_001"
    assert data["messages"][1]["message_id"] == "msg_20251020_100000_001"

    # Check direction field is added
    assert data["messages"][0]["direction"] == "from_human"
    assert data["messages"][1]["direction"] == "to_human"


def test_get_messages_api_with_limit(client, clean_message_history):
    """Test API respects limit parameter"""
    # Add 5 messages
    for i in range(5):
        messages_to_human.append({
            "message_id": f"msg_test_{i}",
            "timestamp": f"2025-10-20T{10+i:02d}:00:00+00:00",
            "content": f"Message {i}",
            "in_reply_to": None
        })

    response = client.get("/api/messages?limit=3")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
    assert len(data["messages"]) == 3


def test_post_reply_success_json(client, clean_message_history):
    """Test posting a reply via JSON"""
    response = client.post(
        "/api/messages/reply",
        json={
            "content": "This is my reply",
            "in_reply_to": "msg_20251020_100000_001"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "message_id" in data
    assert "timestamp" in data
    assert data["message_id"].startswith("msg_")

    # Verify message was stored
    messages = messages_from_human.get_all()
    assert len(messages) == 1
    assert messages[0]["content"] == "This is my reply"
    assert messages[0]["in_reply_to"] == "msg_20251020_100000_001"


def test_post_reply_success_form(client, clean_message_history):
    """Test posting a reply via form data"""
    response = client.post(
        "/api/messages/reply",
        data={
            "content": "Form reply",
            "in_reply_to": ""
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    # Verify message was stored
    messages = messages_from_human.get_all()
    assert len(messages) == 1
    assert messages[0]["content"] == "Form reply"
    assert messages[0]["in_reply_to"] is None  # Empty string converted to None


def test_post_reply_without_in_reply_to(client, clean_message_history):
    """Test posting a reply without in_reply_to (new message)"""
    response = client.post(
        "/api/messages/reply",
        json={"content": "New message from human"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    # Verify message was stored
    messages = messages_from_human.get_all()
    assert len(messages) == 1
    assert messages[0]["in_reply_to"] is None


def test_post_reply_empty_content(client, clean_message_history):
    """Test that empty content is rejected"""
    response = client.post(
        "/api/messages/reply",
        json={"content": ""}
    )

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "required" in data["error"].lower()

    # Verify no message was stored
    assert len(messages_from_human.get_all()) == 0


def test_post_reply_whitespace_only(client, clean_message_history):
    """Test that whitespace-only content is rejected"""
    response = client.post(
        "/api/messages/reply",
        json={"content": "   \n\t  "}
    )

    assert response.status_code == 400
    data = response.json()
    assert "error" in data

    # Verify no message was stored
    assert len(messages_from_human.get_all()) == 0


def test_post_reply_too_long(client, clean_message_history):
    """Test that overly long messages are rejected"""
    long_content = "x" * 50001  # Exceeds MAX_MESSAGE_LENGTH

    response = client.post(
        "/api/messages/reply",
        json={"content": long_content}
    )

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "exceeds maximum length" in data["error"]

    # Verify no message was stored
    assert len(messages_from_human.get_all()) == 0


def test_post_reply_multiple_messages(client, clean_message_history):
    """Test posting multiple replies"""
    # Post first reply at a specific time
    with freeze_time("2025-10-20 15:00:00.100"):
        response1 = client.post(
            "/api/messages/reply",
            json={"content": "First reply"}
        )
        assert response1.status_code == 200

    # Post second reply at a different time
    with freeze_time("2025-10-20 15:00:00.200"):
        response2 = client.post(
            "/api/messages/reply",
            json={"content": "Second reply"}
        )
        assert response2.status_code == 200

    # Verify both were stored
    messages = messages_from_human.get_all()
    assert len(messages) == 2
    assert messages[0]["content"] == "First reply"
    assert messages[1]["content"] == "Second reply"

    # Verify they have unique IDs
    assert messages[0]["message_id"] != messages[1]["message_id"]
    assert messages[0]["message_id"] == "msg_20251020_150000_100"
    assert messages[1]["message_id"] == "msg_20251020_150000_200"


def test_ui_contains_form(client, clean_message_history):
    """Test that UI contains reply form"""
    response = client.get("/messages")

    assert response.status_code == 200
    assert "<form" in response.text
    assert 'id="replyForm"' in response.text
    assert "<textarea" in response.text
    assert 'name="content"' in response.text or 'id="content"' in response.text
    assert "Send Message" in response.text


def test_ui_contains_javascript(client, clean_message_history):
    """Test that UI contains JavaScript for form handling"""
    response = client.get("/messages")

    assert response.status_code == 200
    assert "<script>" in response.text
    assert "fetch" in response.text  # JavaScript fetch API
    assert "/api/messages/reply" in response.text


def test_messages_sorted_newest_first(client, clean_message_history):
    """Test that messages are always sorted newest first"""
    # Add messages in random order
    messages_to_human.append({
        "message_id": "msg_20251020_100000_001",
        "timestamp": "2025-10-20T10:00:00+00:00",
        "content": "First",
        "in_reply_to": None
    })
    messages_to_human.append({
        "message_id": "msg_20251020_120000_001",
        "timestamp": "2025-10-20T12:00:00+00:00",
        "content": "Third",
        "in_reply_to": None
    })
    messages_to_human.append({
        "message_id": "msg_20251020_110000_001",
        "timestamp": "2025-10-20T11:00:00+00:00",
        "content": "Second",
        "in_reply_to": None
    })

    # Test API
    response = client.get("/api/messages")
    data = response.json()
    assert data["messages"][0]["content"] == "Third"
    assert data["messages"][1]["content"] == "Second"
    assert data["messages"][2]["content"] == "First"

    # Test UI
    response_ui = client.get("/messages")
    # Find positions of messages in HTML
    pos_third = response_ui.text.find("Third")
    pos_second = response_ui.text.find("Second")
    pos_first = response_ui.text.find("First")
    assert pos_third < pos_second < pos_first  # Newest first in HTML
