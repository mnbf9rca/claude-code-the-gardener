from processor.photos import (
    build_photo_url,
    filter_lit_filenames,
    get_noon_photo,
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


# ── filter_lit_filenames ──────────────────────────────────────────────────────

def test_filter_lit_filenames_no_events_returns_all():
    """No light event data → fall back to all filenames."""
    filenames = ["plant_20260224_100000_001.jpg", "plant_20260224_200000_001.jpg"]
    assert filter_lit_filenames(filenames, []) == filenames


def test_filter_lit_filenames_photo_before_first_event_falls_back_to_all():
    """Photo taken before the first light event → no lit photos found → falls back to all filenames."""
    filenames = ["plant_20260224_060000_001.jpg"]
    events = [{"timestamp": "2026-02-24T08:00:00Z", "event_type": "turn_on"}]
    result = filter_lit_filenames(filenames, events)
    # Light was never turned on before 08:00; photo at 06:00 is in darkness.
    # No lit photos → falls back to all filenames.
    assert result == filenames


def test_filter_lit_filenames_exact_boundary():
    """Photo at the exact turn_on timestamp is included (evt_ts <= photo_ts)."""
    filenames = ["plant_20260224_080000_001.jpg"]
    events = [{"timestamp": "2026-02-24T08:00:00Z", "event_type": "turn_on"}]
    result = filter_lit_filenames(filenames, events)
    assert result == filenames


def test_filter_lit_filenames_interleaved_events():
    """Only photos taken while the light is on are returned."""
    filenames = [
        "plant_20260224_070000_001.jpg",  # before first event → off
        "plant_20260224_090000_001.jpg",  # after turn_on at 08:00 → on
        "plant_20260224_130000_001.jpg",  # after turn_off_scheduled at 12:00 → off
        "plant_20260224_150000_001.jpg",  # after turn_on at 14:00 → on
    ]
    events = [
        {"timestamp": "2026-02-24T08:00:00Z", "event_type": "turn_on"},
        {"timestamp": "2026-02-24T12:00:00Z", "event_type": "turn_off_scheduled"},
        {"timestamp": "2026-02-24T14:00:00Z", "event_type": "turn_on"},
    ]
    result = filter_lit_filenames(filenames, events)
    assert "plant_20260224_090000_001.jpg" in result
    assert "plant_20260224_150000_001.jpg" in result
    assert "plant_20260224_070000_001.jpg" not in result
    assert "plant_20260224_130000_001.jpg" not in result


def test_filter_lit_filenames_all_dark_falls_back():
    """If no photos are lit, return all filenames rather than empty list."""
    filenames = ["plant_20260224_030000_001.jpg", "plant_20260224_040000_001.jpg"]
    events = [
        {"timestamp": "2026-02-24T08:00:00Z", "event_type": "turn_on"},
        {"timestamp": "2026-02-24T20:00:00Z", "event_type": "turn_off"},
    ]
    result = filter_lit_filenames(filenames, events)
    # Both photos are before the light turns on → fall back to all
    assert result == filenames


def test_filter_lit_filenames_mixed_timestamp_formats():
    """Timestamps with Z and +00:00 suffixes must sort by parsed datetime, not string.

    String ordering: "...+00:00" < "...Z", so if events are sorted lexicographically,
    the turn_off at 12:00+00:00 would appear BEFORE the turn_on at 08:00Z — meaning
    the light appears never on, and a photo at 10:00 would be incorrectly excluded.
    Datetime ordering correctly places turn_on (08:00) before turn_off (12:00).
    """
    filenames = ["plant_20260224_100000_001.jpg"]  # 10:00 UTC, between turn_on and turn_off
    events = [
        {"timestamp": "2026-02-24T08:00:00Z", "event_type": "turn_on"},
        {"timestamp": "2026-02-24T12:00:00+00:00", "event_type": "turn_off_scheduled"},
    ]
    result = filter_lit_filenames(filenames, events)
    # Photo at 10:00 is between turn_on (08:00) and turn_off_scheduled (12:00) → lit → included
    assert result == filenames


# ── recovery_reschedule does not change light state ───────────────────────────

def test_filter_lit_filenames_recovery_reschedule_does_not_turn_off():
    """recovery_reschedule fires while the light is still physically on.

    The old code did `light_on = event_type == "turn_on"`, so a recovery_reschedule
    event between turn_on and turn_off_scheduled would incorrectly mark photos dark.
    """
    filenames = [
        "plant_20260224_090000_001.jpg",  # before recovery_reschedule: lit
        "plant_20260224_093000_001.jpg",  # after recovery_reschedule, before turn_off: still lit
        "plant_20260224_110000_001.jpg",  # after turn_off_scheduled: dark
    ]
    events = [
        {"timestamp": "2026-02-24T08:00:00Z", "event_type": "turn_on"},
        {"timestamp": "2026-02-24T09:00:00Z", "event_type": "recovery_reschedule"},
        {"timestamp": "2026-02-24T10:00:00Z", "event_type": "turn_off_scheduled"},
    ]
    result = filter_lit_filenames(filenames, events)
    assert "plant_20260224_090000_001.jpg" in result
    assert "plant_20260224_093000_001.jpg" in result  # was incorrectly excluded before fix
    assert "plant_20260224_110000_001.jpg" not in result


def test_filter_lit_filenames_recovery_turn_off_ends_lit_window():
    """recovery_turn_off is an actual turn-off event and must end the lit window."""
    filenames = [
        "plant_20260224_083000_001.jpg",  # lit
        "plant_20260224_093000_001.jpg",  # after recovery_turn_off: dark
        "plant_20260224_103000_001.jpg",  # after next turn_on: lit again
    ]
    events = [
        {"timestamp": "2026-02-24T08:00:00Z", "event_type": "turn_on"},
        {"timestamp": "2026-02-24T09:00:00Z", "event_type": "recovery_turn_off"},
        {"timestamp": "2026-02-24T10:00:00Z", "event_type": "turn_on"},
    ]
    result = filter_lit_filenames(filenames, events)
    assert "plant_20260224_083000_001.jpg" in result
    assert "plant_20260224_093000_001.jpg" not in result
    assert "plant_20260224_103000_001.jpg" in result


# ── get_noon_photo slot drift ─────────────────────────────────────────────────

def test_get_noon_photo_returns_photo_nearest_14h_not_list_index():
    """Noon photo must be the photo nearest 14:00, not selected[3].

    When slots skip duplicate photos, selected[3] drifts to a later slot.
    E.g. with photos at [06:07, 11:09, 13:39, 18:40, 21:11], slot 0 and 1
    both want 06:07; slot 1 is skipped; selected[3] = 18:40 not 13:39.
    The correct noon photo is 13:39 (nearest to 14:00 midpoint).
    """
    filenames = [
        "plant_20260224_060700_001.jpg",
        "plant_20260224_110900_001.jpg",
        "plant_20260224_133900_001.jpg",
        "plant_20260224_184000_001.jpg",
        "plant_20260224_211100_001.jpg",
    ]
    result = get_noon_photo(filenames)
    assert result == "plant_20260224_133900_001.jpg"


def test_get_noon_photo_all_six_slots_no_drift():
    """With exactly 6 evenly-spaced photos no skipping occurs; index-3 == 14:00."""
    filenames = [
        "plant_20260224_020000_001.jpg",
        "plant_20260224_060000_001.jpg",
        "plant_20260224_100000_001.jpg",
        "plant_20260224_140000_001.jpg",
        "plant_20260224_180000_001.jpg",
        "plant_20260224_220000_001.jpg",
    ]
    result = get_noon_photo(filenames)
    assert result == "plant_20260224_140000_001.jpg"


def test_get_noon_photo_single_photo_returns_it():
    """With one photo available it must be returned regardless of time."""
    filenames = ["plant_20260224_210000_001.jpg"]
    result = get_noon_photo(filenames)
    assert result == "plant_20260224_210000_001.jpg"
