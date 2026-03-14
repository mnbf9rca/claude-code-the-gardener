from processor.conversation import build_conversation


def test_build_conversation_merges_and_sorts():
    """Conversation = human + agent messages sorted by timestamp."""
    to_human = [
        {"message_id": "a1", "timestamp": "2026-02-24T10:00:00+00:00", "content": "Hi human"},
    ]
    from_human = [
        {"message_id": "b1", "timestamp": "2026-02-24T09:00:00+00:00", "content": "Hey!"},
    ]
    result = build_conversation(to_human, from_human)
    assert len(result) == 2
    assert result[0]["direction"] == "from_human"  # earlier
    assert result[1]["direction"] == "to_human"


def test_build_conversation_empty_inputs():
    result = build_conversation([], [])
    assert result == []


def test_build_conversation_preserves_content():
    to_human = [
        {"message_id": "a1", "timestamp": "2026-02-24T10:00:00+00:00",
         "content": "Status report", "in_reply_to": None},
    ]
    result = build_conversation(to_human, [])
    assert result[0]["content"] == "Status report"
    assert result[0]["message_id"] == "a1"
