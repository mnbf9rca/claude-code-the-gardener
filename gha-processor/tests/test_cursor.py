import json

from processor.cursor import EPOCH, SENSOR_FILES, load_cursor, save_cursor


def test_load_cursor_missing_file_returns_epoch_watermarks(s3):
    """Missing current_state.json → all watermarks default to epoch."""
    state = load_cursor(s3, "test-bucket")
    assert state["watermarks"]["sessions_last_modified"] == EPOCH
    assert state["watermarks"]["photos_last_modified"] == EPOCH
    assert state["watermarks"]["notes_last_modified"] == EPOCH
    for fname in SENSOR_FILES:
        assert state["watermarks"]["sensor_files"][fname] == EPOCH


def test_load_cursor_preserves_existing_watermarks(s3):
    """Existing watermarks are preserved; missing sensor files default to EPOCH."""
    existing = {
        "last_run": "2026-02-24T12:00:00Z",
        "watermarks": {
            "sessions_last_modified": "2026-02-24T10:00:00Z",
            "photos_last_modified": "2026-02-24T09:00:00Z",
            "notes_last_modified": EPOCH,
            "sensor_files": {
                "moisture_sensor_history.jsonl": "2026-02-24T11:00:00Z",
                "light_history.jsonl": EPOCH,
            },
        },
    }
    s3.put_object(
        Bucket="test-bucket",
        Key="state/current_state.json",
        Body=json.dumps(existing).encode(),
    )
    state = load_cursor(s3, "test-bucket")
    assert state["watermarks"]["sessions_last_modified"] == "2026-02-24T10:00:00Z"
    moisture_wm = state["watermarks"]["sensor_files"]["moisture_sensor_history.jsonl"]
    assert moisture_wm == "2026-02-24T11:00:00Z"
    # All sensor files not in existing state must default to EPOCH
    known = {"moisture_sensor_history.jsonl", "light_history.jsonl"}
    for fname in SENSOR_FILES:
        if fname not in known:
            actual = state["watermarks"]["sensor_files"][fname]
            assert actual == EPOCH, f"{fname} should be EPOCH but got {actual!r}"


def test_save_cursor_writes_last_run(s3):
    """save_cursor writes last_run timestamp and preserves watermarks."""
    state = {"watermarks": {"sessions_last_modified": "2026-02-24T10:00:00Z"}}
    save_cursor(s3, "test-bucket", state)
    obj = s3.get_object(Bucket="test-bucket", Key="state/current_state.json")
    saved = json.loads(obj["Body"].read())
    assert "last_run" in saved
    assert saved["watermarks"]["sessions_last_modified"] == "2026-02-24T10:00:00Z"
