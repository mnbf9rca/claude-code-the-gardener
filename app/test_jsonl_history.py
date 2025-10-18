"""
Unit Tests for JsonlHistory Utility

Tests the reusable JSONL history manager used across multiple tools.
"""

import pytest
import json
from datetime import datetime, timedelta
from freezegun import freeze_time
from pathlib import Path
from utils.jsonl_history import JsonlHistory


@pytest.fixture
def temp_history_file(tmp_path):
    """Create a temporary history file path"""
    return tmp_path / "test_history.jsonl"


def test_initialization(temp_history_file):
    """Test basic initialization"""
    history = JsonlHistory(file_path=temp_history_file)

    assert history.file_path == temp_history_file
    assert history.max_memory_entries == 1000
    assert not history._loaded
    assert len(history._history) == 0


def test_auto_create_file(temp_history_file):
    """Test that file is auto-created on first use"""
    history = JsonlHistory(file_path=temp_history_file)

    # File shouldn't exist yet
    assert not temp_history_file.exists()

    # First append should create it
    history.append({"test": "data"})

    assert temp_history_file.exists()


def test_append_single_event(temp_history_file):
    """Test appending a single event"""
    history = JsonlHistory(file_path=temp_history_file)

    event = {"timestamp": "2024-01-01T12:00:00", "data": "test"}
    history.append(event)

    assert history.count() == 1
    assert history.get_all()[0] == event

    # Verify it's on disk
    with open(temp_history_file) as f:
        lines = f.readlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == event


def test_append_multiple_events(temp_history_file):
    """Test appending multiple events"""
    history = JsonlHistory(file_path=temp_history_file)

    events = [
        {"id": 1, "data": "first"},
        {"id": 2, "data": "second"},
        {"id": 3, "data": "third"}
    ]

    for event in events:
        history.append(event)

    assert history.count() == 3
    assert history.get_all() == events


def test_get_recent_basic(temp_history_file):
    """Test getting recent entries"""
    history = JsonlHistory(file_path=temp_history_file)

    for i in range(10):
        history.append({"id": i})

    recent_5 = history.get_recent(5)
    assert len(recent_5) == 5
    assert recent_5[0]["id"] == 5
    assert recent_5[4]["id"] == 9


def test_get_recent_with_offset(temp_history_file):
    """Test pagination with offset"""
    history = JsonlHistory(file_path=temp_history_file)

    for i in range(10):
        history.append({"id": i})

    # Get 3 entries, skipping the 5 most recent
    result = history.get_recent(n=3, offset=5)
    assert len(result) == 3
    assert result[0]["id"] == 2
    assert result[2]["id"] == 4


def test_get_recent_more_than_available(temp_history_file):
    """Test requesting more entries than available"""
    history = JsonlHistory(file_path=temp_history_file)

    for i in range(5):
        history.append({"id": i})

    result = history.get_recent(100)
    assert len(result) == 5


def test_get_by_time_range(temp_history_file):
    """Test getting entries by time range"""
    history = JsonlHistory(file_path=temp_history_file)

    base_time = datetime(2024, 1, 1, 12, 0, 0)

    # Add events at different times
    for i in range(5):
        with freeze_time(base_time + timedelta(hours=i)):
            history.append({
                "id": i,
                "timestamp": (base_time + timedelta(hours=i)).isoformat()
            })

    # Query for hours 1-3
    start = base_time + timedelta(hours=1)
    end = base_time + timedelta(hours=3)

    result = history.get_by_time_range(start, end)
    assert len(result) == 3
    assert result[0]["id"] == 1
    assert result[2]["id"] == 3


def test_get_by_time_window(temp_history_file):
    """Test getting entries from last N hours"""
    history = JsonlHistory(file_path=temp_history_file)

    base_time = datetime.now()

    # Add event 30 hours ago
    with freeze_time(base_time - timedelta(hours=30)):
        history.append({
            "id": 1,
            "timestamp": (base_time - timedelta(hours=30)).isoformat()
        })

    # Add event 10 hours ago
    with freeze_time(base_time - timedelta(hours=10)):
        history.append({
            "id": 2,
            "timestamp": (base_time - timedelta(hours=10)).isoformat()
        })

    # Query last 24 hours
    with freeze_time(base_time):
        result = history.get_by_time_window(hours=24)

    assert len(result) == 1
    assert result[0]["id"] == 2


def test_search_basic(temp_history_file):
    """Test basic keyword search"""
    history = JsonlHistory(file_path=temp_history_file)

    history.append({"note": "Plant needs water"})
    history.append({"note": "Light duration extended"})
    history.append({"note": "Water dispensed successfully"})

    result = history.search("water")
    assert len(result) == 2


def test_search_case_insensitive(temp_history_file):
    """Test case-insensitive search"""
    history = JsonlHistory(file_path=temp_history_file)

    history.append({"note": "WATER NEEDED"})

    result = history.search("water", case_sensitive=False)
    assert len(result) == 1

    result = history.search("water", case_sensitive=True)
    assert len(result) == 0


def test_search_specific_fields(temp_history_file):
    """Test searching in specific fields"""
    history = JsonlHistory(file_path=temp_history_file)

    history.append({"observation": "moisture low", "action": "nothing"})
    history.append({"observation": "all good", "action": "moisture check"})

    # Search only in observation field
    result = history.search("moisture", search_fields=["observation"])
    assert len(result) == 1
    assert result[0]["observation"] == "moisture low"


def test_load_from_existing_file(temp_history_file):
    """Test loading from an existing file"""
    # Write some data to file manually
    events = [
        {"id": 1, "data": "first"},
        {"id": 2, "data": "second"},
        {"id": 3, "data": "third"}
    ]

    temp_history_file.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_history_file, 'w') as f:
        for event in events:
            f.write(json.dumps(event) + '\n')

    # Create history and load
    history = JsonlHistory(file_path=temp_history_file)
    history.load()

    assert history.count() == 3
    assert history.get_all() == events


def test_lazy_loading(temp_history_file):
    """Test that loading is lazy"""
    # Pre-populate file
    events = [{"id": i} for i in range(5)]
    temp_history_file.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_history_file, 'w') as f:
        for event in events:
            f.write(json.dumps(event) + '\n')

    history = JsonlHistory(file_path=temp_history_file)

    # Should not be loaded yet
    assert not history._loaded

    # First access should trigger load
    history.ensure_loaded()
    assert history._loaded
    assert history.count() == 5


def test_memory_pruning(temp_history_file):
    """Test that memory is pruned when exceeding max"""
    history = JsonlHistory(file_path=temp_history_file, max_memory_entries=5)

    # Add 10 events
    for i in range(10):
        history.append({"id": i})

    # Should only keep 5 most recent in memory
    assert history.count() == 5
    assert history.get_all()[0]["id"] == 5
    assert history.get_all()[4]["id"] == 9


def test_load_respects_max_memory(temp_history_file):
    """Test that loading from disk respects max_memory_entries"""
    # Pre-populate file with 100 events
    temp_history_file.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_history_file, 'w') as f:
        for i in range(100):
            f.write(json.dumps({"id": i}) + '\n')

    # Load with max 10
    history = JsonlHistory(file_path=temp_history_file, max_memory_entries=10)
    history.load()

    # Should only have loaded the last 10
    assert history.count() == 10
    assert history.get_all()[0]["id"] == 90
    assert history.get_all()[9]["id"] == 99


def test_malformed_lines_skipped(temp_history_file):
    """Test that malformed JSON lines are skipped"""
    # Write mix of good and bad data
    temp_history_file.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_history_file, 'w') as f:
        f.write(json.dumps({"id": 1}) + '\n')
        f.write('not valid json\n')
        f.write(json.dumps({"id": 2}) + '\n')
        f.write('\n')  # Empty line
        f.write(json.dumps({"id": 3}) + '\n')

    history = JsonlHistory(file_path=temp_history_file)
    history.load()

    assert history.count() == 3
    assert [e["id"] for e in history.get_all()] == [1, 2, 3]


def test_clear(temp_history_file):
    """Test clearing the history"""
    history = JsonlHistory(file_path=temp_history_file)

    for i in range(5):
        history.append({"id": i})

    assert history.count() == 5

    history.clear()
    assert history.count() == 0
    assert not history._loaded


def test_len_operator(temp_history_file):
    """Test len() operator support"""
    history = JsonlHistory(file_path=temp_history_file)

    for i in range(5):
        history.append({"id": i})

    assert len(history) == 5


def test_repr(temp_history_file):
    """Test string representation"""
    history = JsonlHistory(file_path=temp_history_file)
    history.append({"test": "data"})

    repr_str = repr(history)
    assert "JsonlHistory" in repr_str
    assert str(temp_history_file) in repr_str
    assert "entries=1" in repr_str


def test_persistence_across_instances(temp_history_file):
    """Test that data persists across different instances"""
    # First instance - write data
    history1 = JsonlHistory(file_path=temp_history_file)
    for i in range(5):
        history1.append({"id": i})

    # Second instance - read data
    history2 = JsonlHistory(file_path=temp_history_file)
    history2.load()

    assert history2.count() == 5
    assert history2.get_all() == history1.get_all()


def test_empty_file(temp_history_file):
    """Test handling of empty file"""
    # Create empty file
    temp_history_file.parent.mkdir(parents=True, exist_ok=True)
    temp_history_file.touch()

    history = JsonlHistory(file_path=temp_history_file)
    history.load()

    assert history.count() == 0
    assert history.get_all() == []


def test_get_recent_empty(temp_history_file):
    """Test get_recent on empty history"""
    history = JsonlHistory(file_path=temp_history_file)

    result = history.get_recent(10)
    assert result == []


def test_search_empty(temp_history_file):
    """Test search on empty history"""
    history = JsonlHistory(file_path=temp_history_file)

    result = history.search("anything")
    assert result == []
