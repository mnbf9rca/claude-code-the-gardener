"""Tests for day_index building and current_state currency fields in main.py."""


def _make_merged_daily(dates_statuses: dict[str, str]) -> dict:
    """Helper: build a merged_daily dict with minimal structure."""
    return {
        date: {
            "plant_status": {"dominant": status, "healthy": 1, "stressed": 0, "critical": 0},
            "water": {"total_ml": 20 if date == "2026-03-04" else 0, "events": []},
            "moisture": {"min": 2000, "max": 2200, "avg": 2100, "count": 2, "readings": []},
            "light": {"minutes_on": 0, "events": []},
        }
        for date, status in dates_statuses.items()
    }


def _make_timeline(dates_with_photos: list[str]) -> dict:
    """Helper: build a timeline_sorted dict with noon_photo_url for listed dates."""
    return {
        date: {
            "date": date,
            "status": "healthy",
            "photos": [f"https://photos.example.com/{date}/plant_1.jpg"],
            "noon_photo_url": f"https://photos.example.com/{date}/plant_1.jpg",
            "has_watering": False,
        }
        for date in dates_with_photos
    }


# ── day_index tests ──────────────────────────────────────────────────────────

def test_day_index_includes_sensor_only_dates():
    """Days with sensor data but no photo must appear in day_index."""
    from processor.main import build_day_index

    merged_daily = _make_merged_daily({
        "2026-03-03": "healthy",  # sensor only
        "2026-03-04": "healthy",  # has photo
        "2026-03-05": "healthy",  # sensor only
    })
    timeline = _make_timeline(["2026-03-04"])

    result = build_day_index(merged_daily, timeline)

    assert "2026-03-03" in result
    assert "2026-03-05" in result
    assert "2026-03-04" in result


def test_day_index_photo_url_null_for_sensor_only_date():
    """Sensor-only dates get photo_url: null."""
    from processor.main import build_day_index

    merged_daily = _make_merged_daily({"2026-03-03": "healthy", "2026-03-04": "healthy"})
    timeline = _make_timeline(["2026-03-04"])

    result = build_day_index(merged_daily, timeline)

    assert result["2026-03-03"]["photo_url"] is None
    assert result["2026-03-04"]["photo_url"] is not None


def test_day_index_status_from_merged_daily():
    """Status must come from merged_daily plant_status.dominant, not timeline."""
    from processor.main import build_day_index

    merged_daily = _make_merged_daily({"2026-03-04": "stressed"})
    timeline = _make_timeline(["2026-03-04"])  # timeline would say "healthy"

    result = build_day_index(merged_daily, timeline)

    assert result["2026-03-04"]["status"] == "stressed"


def test_day_index_includes_photo_only_dates():
    """Days with a photo but no sensor data must appear with unknown status and no watering."""
    from processor.main import build_day_index

    merged_daily = _make_merged_daily({"2026-03-04": "healthy"})
    timeline = _make_timeline(["2026-03-04", "2026-03-05"])  # 2026-03-05 is photo-only

    result = build_day_index(merged_daily, timeline)

    assert "2026-03-05" in result
    assert result["2026-03-05"]["status"] == "unknown"
    assert result["2026-03-05"]["has_watering"] is False
    assert result["2026-03-05"]["photo_url"] is not None


def test_day_index_has_watering_from_merged_daily():
    """has_watering reflects water.total_ml from merged_daily."""
    from processor.main import build_day_index

    merged_daily = _make_merged_daily({"2026-03-04": "healthy", "2026-03-05": "healthy"})
    # 2026-03-04 has 20ml water (set in _make_merged_daily); 2026-03-05 has 0ml
    timeline = _make_timeline([])

    result = build_day_index(merged_daily, timeline)

    assert result["2026-03-04"]["has_watering"] is True
    assert result["2026-03-05"]["has_watering"] is False


# ── current_state currency tests ─────────────────────────────────────────────

def test_current_state_latest_data_date_is_max_sensor_date():
    """latest_data_date must be the most recent date in merged_daily."""
    from processor.main import build_current_state_updates

    merged_daily = _make_merged_daily({
        "2026-03-05": "healthy",
        "2026-03-07": "healthy",
        "2026-03-06": "healthy",
    })
    timeline = _make_timeline(["2026-03-05"])  # latest photo is older than latest data

    updates = build_current_state_updates(merged_daily, timeline)

    assert updates["latest_data_date"] == "2026-03-07"


def test_current_state_plant_status_from_latest_sensor_date():
    """plant_status must come from merged_daily latest date, not timeline."""
    from processor.main import build_current_state_updates

    merged_daily = _make_merged_daily({
        "2026-03-06": "stressed",
        "2026-03-07": "healthy",
    })
    timeline = _make_timeline(["2026-03-06"])

    updates = build_current_state_updates(merged_daily, timeline)

    assert updates["plant_status"] == "healthy"  # from 2026-03-07, not timeline


def test_current_state_latest_photo_date_from_timeline():
    """latest_photo_date must be the most recent date in timeline."""
    from processor.main import build_current_state_updates

    merged_daily = _make_merged_daily({"2026-03-06": "healthy", "2026-03-07": "healthy"})
    timeline = _make_timeline(["2026-03-06"])  # no photo for 2026-03-07

    updates = build_current_state_updates(merged_daily, timeline)

    assert updates["latest_photo_date"] == "2026-03-06"
    assert "2026-03-06" in updates["latest_photo_url"]


def test_current_state_no_timeline_photo_fields_absent():
    """If timeline is empty, photo fields must not be set."""
    from processor.main import build_current_state_updates

    merged_daily = _make_merged_daily({"2026-03-07": "healthy"})
    updates = build_current_state_updates(merged_daily, {})

    assert "latest_photo_url" not in updates
    assert "latest_photo_date" not in updates
