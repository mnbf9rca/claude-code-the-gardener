import json
import pytest
from processor.sensors import (
    bucket_records_by_day,
    bucket_records_by_hour,
    merge_daily_stats,
    determine_plant_status,
    build_hourly_stats,
)


MOISTURE_RECORDS = [
    {"value": 2100, "timestamp": "2026-02-24T06:00:00Z"},
    {"value": 2050, "timestamp": "2026-02-24T12:00:00Z"},
    {"value": 2000, "timestamp": "2026-02-23T12:00:00Z"},
]
LIGHT_RECORDS = [
    {"timestamp": "2026-02-24T08:00:00+00:00", "event_type": "turn_on", "duration_minutes": 120},
    {"timestamp": "2026-02-24T10:00:00+00:00", "event_type": "turn_off_scheduled"},
]
WATER_RECORDS = [
    {"timestamp": "2026-02-24T04:00:00+00:00", "ml": 20, "seconds": 22},
]
PLANT_STATUS_RECORDS = [
    {"timestamp": "2026-02-24T06:00:00+00:00", "plant_state": "healthy", "sensor_reading": 2100},
    {"timestamp": "2026-02-24T12:00:00+00:00", "plant_state": "healthy", "sensor_reading": 2050},
    {"timestamp": "2026-02-24T18:00:00+00:00", "plant_state": "stressed", "sensor_reading": 1900},
]


def test_bucket_records_by_day_groups_correctly():
    result = bucket_records_by_day(MOISTURE_RECORDS, "value")
    assert "2026-02-24" in result
    assert "2026-02-23" in result
    assert len(result["2026-02-24"]) == 2
    assert len(result["2026-02-23"]) == 1


def test_bucket_records_by_day_filters_by_watermark():
    result = bucket_records_by_day(
        MOISTURE_RECORDS, "value", watermark="2026-02-23T23:59:59Z"
    )
    assert "2026-02-24" in result
    assert "2026-02-23" not in result  # filtered out


def test_determine_plant_status_returns_mode():
    """Status = whichever plant_state has the most records that day."""
    # 2 healthy, 1 stressed → healthy wins
    status = determine_plant_status(PLANT_STATUS_RECORDS)
    assert status == "healthy"


def test_determine_plant_status_empty_returns_unknown():
    assert determine_plant_status([]) == "unknown"


def test_merge_daily_stats_accumulates():
    """merge_daily_stats adds new-day buckets into existing stats."""
    existing = {
        "2026-02-23": {
            "moisture": {"min": 2000, "max": 2000, "avg": 2000, "count": 1, "readings": [2000]},
            "light": {"minutes_on": 0, "events": []},
            "water": {"total_ml": 0, "events": []},
            "plant_status": {"healthy": 1, "stressed": 0, "critical": 0, "dominant": "healthy"},
        }
    }
    new_records = {
        "moisture": {"2026-02-24": [{"value": 2100}, {"value": 2050}]},
        "light": {"2026-02-24": LIGHT_RECORDS},
        "water": {"2026-02-24": WATER_RECORDS},
        "plant_status": {"2026-02-24": PLANT_STATUS_RECORDS},
    }
    result = merge_daily_stats(existing, new_records)
    assert "2026-02-23" in result  # old day preserved
    assert "2026-02-24" in result  # new day added
    assert result["2026-02-24"]["moisture"]["count"] == 2
    assert result["2026-02-24"]["moisture"]["avg"] == pytest.approx(2075.0)
    assert result["2026-02-24"]["water"]["total_ml"] == 20


def test_merge_daily_stats_merges_existing_date():
    """New records for an already-existing date are merged, not replaced."""
    existing = {
        "2026-02-24": {
            "moisture": {"min": 2100, "max": 2100, "avg": 2100.0, "count": 1, "readings": [2100]},
            "light": {"minutes_on": 60, "events": [
                {"timestamp": "2026-02-24T06:00:00+00:00", "event_type": "turn_on"}
            ]},
            "water": {"total_ml": 10, "events": [
                {"timestamp": "2026-02-24T06:00:00+00:00", "ml": 10}
            ]},
            "plant_status": {"healthy": 1, "stressed": 0, "critical": 0, "dominant": "healthy"},
        }
    }
    # Second run: afternoon records for the same date
    new_records = {
        "moisture": {"2026-02-24": [{"value": 1900, "timestamp": "2026-02-24T18:00:00Z"}]},
        "light": {"2026-02-24": [
            {"timestamp": "2026-02-24T18:00:00+00:00", "event_type": "turn_on", "duration_minutes": 120}
        ]},
        "water": {"2026-02-24": [
            {"timestamp": "2026-02-24T18:00:00+00:00", "ml": 15}
        ]},
        "plant_status": {"2026-02-24": [
            {"timestamp": "2026-02-24T18:00:00+00:00", "plant_state": "stressed"}
        ]},
    }
    result = merge_daily_stats(existing, new_records)
    day = result["2026-02-24"]
    # Moisture: old reading [2100] merged with new [1900] → count=2, avg=2000
    assert day["moisture"]["count"] == 2
    assert day["moisture"]["avg"] == pytest.approx(2000.0)
    # Light: 60 + 120 = 180 minutes, 2 events
    assert day["light"]["minutes_on"] == 180
    assert len(day["light"]["events"]) == 2
    # Water: 10 + 15 = 25 ml
    assert day["water"]["total_ml"] == 25
    # Plant status: healthy=1, stressed=1 → merged counts
    assert day["plant_status"]["healthy"] == 1
    assert day["plant_status"]["stressed"] == 1


def test_build_hourly_stats_populates_moisture_light_water():
    """build_hourly_stats should populate moisture, light_on, and water_ml per hour."""
    records_by_type = {
        "moisture": {"2026-02-24": [
            {"value": 2100, "timestamp": "2026-02-24T08:30:00Z"},
            {"value": 2050, "timestamp": "2026-02-24T08:45:00Z"},
        ]},
        "light": {"2026-02-24": [
            {"timestamp": "2026-02-24T08:00:00+00:00", "event_type": "turn_on", "duration_minutes": 120},
        ]},
        "water": {"2026-02-24": [
            {"timestamp": "2026-02-24T08:10:00+00:00", "ml": 20},
        ]},
    }
    # Use cutoff_days=400 to avoid filtering out test data
    result = build_hourly_stats({}, records_by_type, cutoff_days=400)
    assert "2026-02-24T08:00:00Z" in result
    hour = result["2026-02-24T08:00:00Z"]
    assert hour["moisture"]["count"] == 2
    assert hour["moisture"]["avg"] == pytest.approx(2075.0)
    assert hour["light_on"] is True
    assert hour["water_ml"] == 20
