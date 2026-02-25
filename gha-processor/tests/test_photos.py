from processor.photos import (
    build_photo_url,
    parse_photo_timestamp,
    select_photos_for_day,
)


def test_parse_photo_timestamp_valid():
    """plant_YYYYMMDD_HHMMSS_NNN.jpg → datetime."""
    dt = parse_photo_timestamp("plant_20260224_120000_001.jpg")
    assert dt.year == 2026
    assert dt.month == 2
    assert dt.day == 24
    assert dt.hour == 12
    assert dt.minute == 0


def test_parse_photo_timestamp_invalid_returns_none():
    dt = parse_photo_timestamp("not_a_photo.jpg")
    assert dt is None


def test_select_photos_for_day_selects_up_to_6():
    """6 evenly-spaced slots across 24h; one photo nearest each slot midpoint."""
    # Photos every 2 hours
    filenames = [f"plant_20260224_{h:02d}0000_001.jpg" for h in range(0, 24, 2)]
    selected = select_photos_for_day(filenames)
    assert len(selected) == 6


def test_select_photos_for_day_returns_nearest_to_slot_midpoints():
    """Slot midpoints: 02:00, 06:00, 10:00, 14:00, 18:00, 22:00."""
    filenames = [
        "plant_20260224_020000_001.jpg",  # slot 0 midpoint (00:00–04:00 → 02:00)
        "plant_20260224_060000_001.jpg",  # slot 1 midpoint (04:00–08:00 → 06:00)
        "plant_20260224_100000_001.jpg",  # slot 2
        "plant_20260224_140000_001.jpg",  # slot 3 (noon anchor)
        "plant_20260224_180000_001.jpg",  # slot 4
        "plant_20260224_220000_001.jpg",  # slot 5
    ]
    selected = select_photos_for_day(filenames)
    assert len(selected) == 6
    assert "plant_20260224_020000_001.jpg" in selected


def test_select_photos_for_day_empty_input():
    assert select_photos_for_day([]) == []


def test_build_photo_url():
    url = build_photo_url("2026/02/24/plant_20260224_120000_001.jpg", "https://gardener-photos.cynexia.com")
    assert url == "https://gardener-photos.cynexia.com/2026/02/24/plant_20260224_120000_001.jpg"
