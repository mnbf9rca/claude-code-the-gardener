"""
Unit Tests for JsonlHistory Utility

Tests the reusable JSONL history manager used across multiple tools.
"""

import pytest
import json
from datetime import datetime, timedelta, timezone
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

    history.append(events[0])
    history.append(events[1])
    history.append(events[2])

    assert history.count() == 3
    assert history.get_all() == events


def test_get_recent_basic(temp_history_file):
    """Test getting recent entries"""
    history = JsonlHistory(file_path=temp_history_file)

    # Append 10 entries explicitly
    history.append({"id": 0})
    history.append({"id": 1})
    history.append({"id": 2})
    history.append({"id": 3})
    history.append({"id": 4})
    history.append({"id": 5})
    history.append({"id": 6})
    history.append({"id": 7})
    history.append({"id": 8})
    history.append({"id": 9})

    recent_5 = history.get_recent(5)
    assert len(recent_5) == 5
    assert recent_5[0]["id"] == 5
    assert recent_5[4]["id"] == 9


def test_get_recent_with_offset(temp_history_file):
    """Test pagination with offset"""
    history = JsonlHistory(file_path=temp_history_file)

    # Append 10 entries explicitly
    history.append({"id": 0})
    history.append({"id": 1})
    history.append({"id": 2})
    history.append({"id": 3})
    history.append({"id": 4})
    history.append({"id": 5})
    history.append({"id": 6})
    history.append({"id": 7})
    history.append({"id": 8})
    history.append({"id": 9})

    # Get 3 entries, skipping the 5 most recent
    result = history.get_recent(n=3, offset=5)
    assert len(result) == 3
    assert result[0]["id"] == 2
    assert result[2]["id"] == 4


def test_get_recent_more_than_available(temp_history_file):
    """Test requesting more entries than available"""
    history = JsonlHistory(file_path=temp_history_file)

    history.append({"id": 0})
    history.append({"id": 1})
    history.append({"id": 2})
    history.append({"id": 3})
    history.append({"id": 4})

    result = history.get_recent(100)
    assert len(result) == 5


def test_get_by_time_range(temp_history_file):
    """Test getting entries by time range"""
    history = JsonlHistory(file_path=temp_history_file)

    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Add events at different times - explicit instead of loop
    with freeze_time(base_time + timedelta(hours=0)):
        history.append({"id": 0, "timestamp": (base_time + timedelta(hours=0)).isoformat()})
    with freeze_time(base_time + timedelta(hours=1)):
        history.append({"id": 1, "timestamp": (base_time + timedelta(hours=1)).isoformat()})
    with freeze_time(base_time + timedelta(hours=2)):
        history.append({"id": 2, "timestamp": (base_time + timedelta(hours=2)).isoformat()})
    with freeze_time(base_time + timedelta(hours=3)):
        history.append({"id": 3, "timestamp": (base_time + timedelta(hours=3)).isoformat()})
    with freeze_time(base_time + timedelta(hours=4)):
        history.append({"id": 4, "timestamp": (base_time + timedelta(hours=4)).isoformat()})

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

    base_time = datetime.now(timezone.utc)

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


def test_search_special_characters(temp_history_file):
    """Test search with special characters in keyword"""
    history = JsonlHistory(file_path=temp_history_file)

    history.append({"note": "Fertilizer applied: N-P-K 10-10-10"})
    history.append({"note": "Checked pH level: 6.5"})
    history.append({"note": "Water dispensed @ 8:00am"})
    history.append({"note": "Light duration extended"})

    # Search for a keyword with special characters
    result = history.search("N-P-K")
    assert len(result) == 1
    assert "N-P-K" in result[0]["note"]

    result = history.search("@ 8:00am")
    assert len(result) == 1
    assert "@ 8:00am" in result[0]["note"]

    # Search for a keyword with punctuation that does not exist
    result = history.search("pH:7.0")
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
        f.write(json.dumps(events[0]) + '\n')
        f.write(json.dumps(events[1]) + '\n')
        f.write(json.dumps(events[2]) + '\n')

    # Create history and load
    history = JsonlHistory(file_path=temp_history_file)
    history.load()

    assert history.count() == 3
    assert history.get_all() == events


def test_lazy_loading(temp_history_file):
    """Test that loading is lazy"""
    # Pre-populate file
    temp_history_file.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_history_file, 'w') as f:
        f.write(json.dumps({"id": 0}) + '\n')
        f.write(json.dumps({"id": 1}) + '\n')
        f.write(json.dumps({"id": 2}) + '\n')
        f.write(json.dumps({"id": 3}) + '\n')
        f.write(json.dumps({"id": 4}) + '\n')

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

    # Add 10 events explicitly
    history.append({"id": 0})
    history.append({"id": 1})
    history.append({"id": 2})
    history.append({"id": 3})
    history.append({"id": 4})
    history.append({"id": 5})
    history.append({"id": 6})
    history.append({"id": 7})
    history.append({"id": 8})
    history.append({"id": 9})

    # Should only keep 5 most recent in memory
    assert history.count() == 5
    assert history.get_all()[0]["id"] == 5
    assert history.get_all()[4]["id"] == 9


def test_load_respects_max_memory(temp_history_file):
    """Test that loading from disk respects max_memory_entries"""
    # Pre-populate file with 15 events (reduced from 100 to make explicit writing feasible)
    temp_history_file.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_history_file, 'w') as f:
        # Write 15 entries
        f.write(json.dumps({"id": 0}) + '\n')
        f.write(json.dumps({"id": 1}) + '\n')
        f.write(json.dumps({"id": 2}) + '\n')
        f.write(json.dumps({"id": 3}) + '\n')
        f.write(json.dumps({"id": 4}) + '\n')
        f.write(json.dumps({"id": 5}) + '\n')
        f.write(json.dumps({"id": 6}) + '\n')
        f.write(json.dumps({"id": 7}) + '\n')
        f.write(json.dumps({"id": 8}) + '\n')
        f.write(json.dumps({"id": 9}) + '\n')
        f.write(json.dumps({"id": 10}) + '\n')
        f.write(json.dumps({"id": 11}) + '\n')
        f.write(json.dumps({"id": 12}) + '\n')
        f.write(json.dumps({"id": 13}) + '\n')
        f.write(json.dumps({"id": 14}) + '\n')

    # Load with max 10
    history = JsonlHistory(file_path=temp_history_file, max_memory_entries=10)
    history.load()

    # Should only have loaded the last 10
    assert history.count() == 10
    assert history.get_all()[0]["id"] == 5
    assert history.get_all()[9]["id"] == 14


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

    history.append({"id": 0})
    history.append({"id": 1})
    history.append({"id": 2})
    history.append({"id": 3})
    history.append({"id": 4})

    assert history.count() == 5

    history.clear()
    assert history.count() == 0
    assert not history._loaded


def test_clear_persistence(temp_history_file):
    """Test that clear() does not modify or remove data from the underlying JSONL file"""
    history = JsonlHistory(file_path=temp_history_file)
    history.append({"id": 0})
    history.append({"id": 1})
    history.append({"id": 2})
    history.append({"id": 3})
    history.append({"id": 4})

    history.clear()
    # Reload from file to check persistence
    new_history = JsonlHistory(file_path=temp_history_file)
    new_history.load()
    assert new_history.count() == 5
    assert [e["id"] for e in new_history.get_all()] == [0, 1, 2, 3, 4]


def test_len_operator(temp_history_file):
    """Test len() operator support"""
    history = JsonlHistory(file_path=temp_history_file)

    history.append({"id": 0})
    history.append({"id": 1})
    history.append({"id": 2})
    history.append({"id": 3})
    history.append({"id": 4})

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
    history1.append({"id": 0})
    history1.append({"id": 1})
    history1.append({"id": 2})
    history1.append({"id": 3})
    history1.append({"id": 4})

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


# Time-bucketed sampling tests
@freeze_time("2025-01-24 12:00:00")
def test_time_bucketed_sample_uniform_distribution(temp_history_file):
    """Test time-bucketed sampling with uniformly distributed data"""
    history = JsonlHistory(file_path=temp_history_file)

    # Add 60 entries, one per minute for 1 hour
    base_time = datetime(2025, 1, 24, 11, 0, 0, tzinfo=timezone.utc)
    for i in range(60):
        entry_time = base_time + timedelta(minutes=i)
        history.append({
            "timestamp": entry_time.isoformat(),
            "value": 1000 + i
        })

    # Request 1 hour with 6 samples/hour
    result = history.get_time_bucketed_sample(hours=1, samples_per_hour=6)

    # Should return 6 samples (one per 10-min bucket)
    assert len(result) == 6

    # Each sample should be ~10 minutes apart
    for i in range(len(result) - 1):
        t1 = datetime.fromisoformat(result[i]["timestamp"])
        t2 = datetime.fromisoformat(result[i + 1]["timestamp"])
        gap = (t2 - t1).total_seconds() / 60  # Convert to minutes
        assert 9 <= gap <= 11  # Allow 1-minute tolerance


@freeze_time("2025-01-24 12:00:00")
def test_time_bucketed_sample_with_gaps(temp_history_file):
    """Test time-bucketed sampling with missing data (gaps)"""
    history = JsonlHistory(file_path=temp_history_file)

    base_time = datetime(2025, 1, 24, 11, 0, 0, tzinfo=timezone.utc)

    # Add data only for first 10 minutes and last 10 minutes (40-min gap)
    for i in range(10):
        history.append({
            "timestamp": (base_time + timedelta(minutes=i)).isoformat(),
            "value": 1000 + i
        })

    for i in range(50, 60):
        history.append({
            "timestamp": (base_time + timedelta(minutes=i)).isoformat(),
            "value": 1000 + i
        })

    # Request 1 hour with 6 samples/hour
    result = history.get_time_bucketed_sample(hours=1, samples_per_hour=6)

    # Should only return samples from buckets with data (likely 2)
    assert len(result) <= 6
    assert len(result) >= 2  # At least one from each filled bucket


@freeze_time("2025-01-24 12:00:00")
def test_time_bucketed_sample_dense_data(temp_history_file):
    """Test time-bucketed sampling with multiple entries per bucket"""
    history = JsonlHistory(file_path=temp_history_file)

    base_time = datetime(2025, 1, 24, 11, 0, 0, tzinfo=timezone.utc)

    # Add 10 entries per minute for first 10 minutes (100 total)
    for minute in range(10):
        for second in range(0, 60, 6):  # Every 6 seconds
            entry_time = base_time + timedelta(minutes=minute, seconds=second)
            history.append({
                "timestamp": entry_time.isoformat(),
                "value": 1000 + minute * 10 + second
            })

    # Request 1 hour with 6 samples/hour
    result = history.get_time_bucketed_sample(hours=1, samples_per_hour=6)

    # Should return samples, at most one per bucket
    assert len(result) <= 6
    assert len(result) >= 1  # At least one bucket should have data


@freeze_time("2025-01-24 12:00:00")
def test_time_bucketed_sample_empty_window(temp_history_file):
    """Test time-bucketed sampling with no data in time window"""
    history = JsonlHistory(file_path=temp_history_file)

    # Add data from 5 hours ago (outside 1-hour window)
    old_time = datetime(2025, 1, 24, 7, 0, 0, tzinfo=timezone.utc)
    history.append({
        "timestamp": old_time.isoformat(),
        "value": 1000
    })

    # Request last 1 hour
    result = history.get_time_bucketed_sample(hours=1, samples_per_hour=6)

    assert result == []


@freeze_time("2025-01-24 12:00:00")
def test_time_bucketed_sample_aggregation_first(temp_history_file):
    """Test 'first' aggregation strategy"""
    history = JsonlHistory(file_path=temp_history_file)

    base_time = datetime(2025, 1, 24, 11, 0, 0, tzinfo=timezone.utc)

    # Add 3 entries in first 10-minute bucket
    history.append({"timestamp": (base_time + timedelta(minutes=0)).isoformat(), "value": 100})
    history.append({"timestamp": (base_time + timedelta(minutes=5)).isoformat(), "value": 200})
    history.append({"timestamp": (base_time + timedelta(minutes=9)).isoformat(), "value": 300})

    result = history.get_time_bucketed_sample(hours=1, samples_per_hour=6, aggregation="first")

    # Should return first entry (value=100)
    assert len(result) == 1
    assert result[0]["value"] == 100


@freeze_time("2025-01-24 12:00:00")
def test_time_bucketed_sample_aggregation_last(temp_history_file):
    """Test 'last' aggregation strategy"""
    history = JsonlHistory(file_path=temp_history_file)

    base_time = datetime(2025, 1, 24, 11, 0, 0, tzinfo=timezone.utc)

    # Add 3 entries in first 10-minute bucket
    history.append({"timestamp": (base_time + timedelta(minutes=0)).isoformat(), "value": 100})
    history.append({"timestamp": (base_time + timedelta(minutes=5)).isoformat(), "value": 200})
    history.append({"timestamp": (base_time + timedelta(minutes=9)).isoformat(), "value": 300})

    result = history.get_time_bucketed_sample(hours=1, samples_per_hour=6, aggregation="last")

    # Should return last entry (value=300)
    assert len(result) == 1
    assert result[0]["value"] == 300


@freeze_time("2025-01-24 12:00:00")
def test_time_bucketed_sample_aggregation_middle(temp_history_file):
    """Test 'middle' aggregation strategy"""
    history = JsonlHistory(file_path=temp_history_file)

    base_time = datetime(2025, 1, 24, 11, 0, 0, tzinfo=timezone.utc)

    # Add 3 entries in first 10-minute bucket
    # Bucket is 11:00-11:10, midpoint is 11:05
    history.append({"timestamp": (base_time + timedelta(minutes=0)).isoformat(), "value": 100})
    history.append({"timestamp": (base_time + timedelta(minutes=5)).isoformat(), "value": 200})  # Closest to midpoint
    history.append({"timestamp": (base_time + timedelta(minutes=9)).isoformat(), "value": 300})

    result = history.get_time_bucketed_sample(hours=1, samples_per_hour=6, aggregation="middle")

    # Should return entry closest to bucket midpoint (value=200 at 11:05)
    assert len(result) == 1
    assert result[0]["value"] == 200


@freeze_time("2025-01-24 12:00:00")
def test_time_bucketed_sample_single_entry(temp_history_file):
    """Test time-bucketed sampling with only one entry"""
    history = JsonlHistory(file_path=temp_history_file)

    # Add single entry in last hour
    recent_time = datetime(2025, 1, 24, 11, 30, 0, tzinfo=timezone.utc)
    history.append({
        "timestamp": recent_time.isoformat(),
        "value": 1000
    })

    result = history.get_time_bucketed_sample(hours=1, samples_per_hour=6)

    # Should return the one entry
    assert len(result) == 1
    assert result[0]["value"] == 1000


@freeze_time("2025-01-24 12:00:00")
def test_time_bucketed_sample_custom_samples_per_hour(temp_history_file):
    """Test time-bucketed sampling with different samples_per_hour"""
    history = JsonlHistory(file_path=temp_history_file)

    base_time = datetime(2025, 1, 24, 11, 0, 0, tzinfo=timezone.utc)

    # Add 60 entries (one per minute)
    for i in range(60):
        history.append({
            "timestamp": (base_time + timedelta(minutes=i)).isoformat(),
            "value": 1000 + i
        })

    # Request 1 hour with 12 samples/hour (5-minute buckets)
    result = history.get_time_bucketed_sample(hours=1, samples_per_hour=12)

    # Should return 12 samples
    assert len(result) == 12


@freeze_time("2025-01-24 12:00:00")
def test_time_bucketed_sample_returns_chronological(temp_history_file):
    """Test that results are returned in chronological order"""
    history = JsonlHistory(file_path=temp_history_file)

    base_time = datetime(2025, 1, 24, 11, 0, 0, tzinfo=timezone.utc)

    # Add entries in random order
    for i in [30, 10, 50, 20, 40, 0]:
        history.append({
            "timestamp": (base_time + timedelta(minutes=i)).isoformat(),
            "value": 1000 + i
        })

    result = history.get_time_bucketed_sample(hours=1, samples_per_hour=6)

    # Verify chronological order
    for i in range(len(result) - 1):
        t1 = datetime.fromisoformat(result[i]["timestamp"])
        t2 = datetime.fromisoformat(result[i + 1]["timestamp"])
        assert t1 < t2  # Should be strictly increasing


def test_time_bucketed_sample_with_custom_end_time(temp_history_file):
    """Test time-bucketed sampling with custom end_time (historical data)"""
    history = JsonlHistory(file_path=temp_history_file)

    # Add data spanning multiple days
    base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    for day in range(5):
        for hour in range(24):
            entry_time = base_time + timedelta(days=day, hours=hour)
            history.append({
                "timestamp": entry_time.isoformat(),
                "value": 1000 + day * 100 + hour
            })

    # Sample from Jan 2, 00:00 to Jan 3, 00:00 (24 hours on day 2)
    end_time = datetime(2025, 1, 3, 0, 0, 0, tzinfo=timezone.utc)
    result = history.get_time_bucketed_sample(
        hours=24,
        samples_per_hour=1,
        end_time=end_time
    )

    # Should get samples from day 2 only (values 1100-1123)
    assert len(result) > 0
    for entry in result:
        value = entry["value"]
        assert 1100 <= value < 1200, f"Expected values 1100-1199 (day 2), got {value}"


def test_time_bucketed_sample_end_time_defaults_to_now(temp_history_file):
    """Test that end_time=None behaves same as explicit now"""
    history = JsonlHistory(file_path=temp_history_file)

    # Add recent data
    with freeze_time("2025-01-24 12:00:00"):
        base_time = datetime(2025, 1, 24, 11, 0, 0, tzinfo=timezone.utc)
        for i in range(60):
            history.append({
                "timestamp": (base_time + timedelta(minutes=i)).isoformat(),
                "value": 1000 + i
            })

        # Both calls should return same results
        result_default = history.get_time_bucketed_sample(hours=1, samples_per_hour=6)
        result_explicit = history.get_time_bucketed_sample(
            hours=1,
            samples_per_hour=6,
            end_time=datetime.now(timezone.utc)
        )

        assert len(result_default) == len(result_explicit)
        # Timestamps should match
        for default_entry, explicit_entry in zip(result_default, result_explicit):
            assert default_entry["timestamp"] == explicit_entry["timestamp"]


@freeze_time("2025-01-24 12:00:00")
def test_time_bucketed_sample_invalid_aggregation(temp_history_file):
    """Test that invalid aggregation strategy raises ValueError"""
    history = JsonlHistory(file_path=temp_history_file)

    # Add some data
    base_time = datetime(2025, 1, 24, 11, 0, 0, tzinfo=timezone.utc)
    for i in range(10):
        history.append({
            "timestamp": (base_time + timedelta(minutes=i)).isoformat(),
            "value": 1000 + i
        })

    # Invalid aggregation should raise ValueError
    with pytest.raises(ValueError, match="Unknown aggregation strategy"):
        history.get_time_bucketed_sample(
            hours=1,
            samples_per_hour=6,
            aggregation="invalid"
        )


@freeze_time("2025-01-24 12:00:00")
def test_time_bucketed_sample_with_malformed_timestamps(temp_history_file):
    """Test that malformed timestamps are skipped with logging"""
    history = JsonlHistory(file_path=temp_history_file)

    # Add good data
    base_time = datetime(2025, 1, 24, 11, 0, 0, tzinfo=timezone.utc)
    for i in range(5):
        history.append({
            "timestamp": (base_time + timedelta(minutes=i * 10)).isoformat(),
            "value": 1000 + i
        })

    # Manually add malformed entry to the history
    history._history.append({"timestamp": "not-a-timestamp", "value": 9999})
    history._history.append({"bad_key": "no timestamp", "value": 8888})

    # Should skip malformed entries and return only valid ones
    result = history.get_time_bucketed_sample(hours=1, samples_per_hour=6)

    # Verify all returned entries have valid values (not the malformed ones)
    for entry in result:
        assert entry["value"] != 9999, "Malformed timestamp entry should be skipped"
        assert entry["value"] != 8888, "Missing timestamp entry should be skipped"

    # Should have results from valid entries
    assert len(result) > 0
