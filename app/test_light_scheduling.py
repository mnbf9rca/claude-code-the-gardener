"""
Tests for Light Scheduling Features

Tests the new scheduled turn-off functionality including:
- Background task creation and cancellation
- State persistence to disk
- Startup reconciliation and crash recovery
"""
import pytest
import pytest_asyncio
import json
import httpx
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from freezegun import freeze_time
from fastmcp import FastMCP
import tools.light as light_module
from tools.light import setup_light_tools
from shared_state import reset_cycle, current_cycle_status
from pytest_httpx import HTTPXMock

# Apply to all tests in this module
pytestmark = pytest.mark.httpx_mock(assert_all_responses_were_requested=False)


@pytest_asyncio.fixture(autouse=True)
async def setup_scheduling_test_state(httpx_mock: HTTPXMock, tmp_path):
    """Reset state before each test and use temp directory for state file"""
    # Reset cycle state
    reset_cycle()
    current_cycle_status["written"] = True

    # Reset light state
    light_module.light_state["status"] = "off"
    light_module.light_state["last_on"] = None
    light_module.light_state["last_off"] = None
    light_module.light_state["scheduled_off"] = None

    # Reset light history (uses JsonlHistory utility)
    light_module.light_history.clear()
    light_module.light_history._loaded = False

    # Reset state loaded flag
    light_module._state_loaded = False

    # Reset reconciliation flag
    light_module._reconciliation_done = False

    # Cancel any existing scheduled tasks
    if light_module.scheduled_task and not light_module.scheduled_task.done():
        light_module.scheduled_task.cancel()
        try:
            await light_module.scheduled_task
        except asyncio.CancelledError:
            pass
    light_module.scheduled_task = None

    # Use temp directory for state and history files
    original_state_file = light_module.STATE_FILE
    original_history_file = light_module.light_history.file_path
    light_module.STATE_FILE = tmp_path / "light_state.json"
    light_module.light_history.file_path = tmp_path / "light_history.jsonl"

    # Reset HTTP client
    light_module.http_client = None

    # Setup default Home Assistant mocks
    def mock_turn_on(request):
        return httpx.Response(200, json=[{"entity_id": light_module.LIGHT_ENTITY_ID, "state": "on"}])

    def mock_turn_off(request):
        return httpx.Response(200, json=[{"entity_id": light_module.LIGHT_ENTITY_ID, "state": "off"}])

    def mock_get_state(request):
        return httpx.Response(200, json={"entity_id": light_module.LIGHT_ENTITY_ID, "state": light_module.light_state["status"]})

    for _ in range(20):
        httpx_mock.add_callback(mock_turn_on, url=f"{light_module.HA_URL}/api/services/switch/turn_on")
        httpx_mock.add_callback(mock_turn_off, url=f"{light_module.HA_URL}/api/services/switch/turn_off")
        httpx_mock.add_callback(mock_get_state, url=f"{light_module.HA_URL}/api/states/{light_module.LIGHT_ENTITY_ID}")

    # Create MCP instance
    mcp = FastMCP("test-scheduling")
    setup_light_tools(mcp)

    yield mcp

    # Cleanup
    if light_module.scheduled_task and not light_module.scheduled_task.done():
        light_module.scheduled_task.cancel()
        try:
            await light_module.scheduled_task
        except asyncio.CancelledError:
            pass
    light_module.scheduled_task = None

    if light_module.http_client:
        await light_module.http_client.aclose()
        light_module.http_client = None

    # Restore original file paths
    light_module.STATE_FILE = original_state_file
    light_module.light_history.file_path = original_history_file


# =============================================================================
# Background Task Tests
# =============================================================================

@pytest.mark.asyncio
async def test_turn_on_creates_background_task(setup_scheduling_test_state):
    """Test that turn_on creates a scheduled background task"""
    mcp = setup_scheduling_test_state
    turn_on_tool = mcp._tool_manager._tools["turn_on"]

    # Verify no task exists initially
    assert light_module.scheduled_task is None

    # Turn on light
    await turn_on_tool.run(arguments={"minutes": 30})

    # Verify background task was created
    assert light_module.scheduled_task is not None
    assert isinstance(light_module.scheduled_task, asyncio.Task)
    assert not light_module.scheduled_task.done()


@pytest.mark.asyncio
async def test_turn_off_cancels_background_task(setup_scheduling_test_state):
    """Test that turn_off cancels the scheduled background task"""
    mcp = setup_scheduling_test_state
    turn_on_tool = mcp._tool_manager._tools["turn_on"]
    turn_off_tool = mcp._tool_manager._tools["turn_off"]

    # Turn on light (creates background task)
    await turn_on_tool.run(arguments={"minutes": 60})
    task = light_module.scheduled_task
    assert task is not None
    assert not task.done()

    # Turn off light
    await turn_off_tool.run(arguments={})

    # Give the task a moment to process cancellation
    try:
        await asyncio.wait_for(task, timeout=0.1)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass

    # Task should be cancelled
    assert task.cancelled() or task.done()
    assert light_module.scheduled_task is None


@pytest.mark.asyncio
async def test_background_task_executes_turn_off(setup_scheduling_test_state):
    """Test that background task executes turn-off logic when invoked"""
    # Setup state as if light is on with scheduled off time
    with freeze_time("2024-01-01 12:00:00"):
        light_module.light_state["status"] = "on"
        light_module.light_state["last_on"] = datetime.now().isoformat()
        light_module.light_state["scheduled_off"] = (datetime.now() + timedelta(seconds=1)).isoformat()

    # Create and run the background task
    task = asyncio.create_task(light_module.execute_scheduled_turn_off())

    # Wait for task to complete (should happen quickly with 1 second delay)
    await asyncio.wait_for(task, timeout=5.0)

    # Verify light was turned off
    assert light_module.light_state["status"] == "off"
    assert light_module.light_state["last_off"] is not None
    assert light_module.light_state["scheduled_off"] is None


@pytest.mark.asyncio
async def test_background_task_handles_past_scheduled_time(setup_scheduling_test_state):
    """Test that background task turns off immediately if scheduled time already passed"""
    with freeze_time("2024-01-01 12:00:00"):
        # Set scheduled time in the past
        light_module.light_state["status"] = "on"
        light_module.light_state["scheduled_off"] = (datetime.now() - timedelta(minutes=5)).isoformat()

    # Run background task
    task = asyncio.create_task(light_module.execute_scheduled_turn_off())
    await asyncio.wait_for(task, timeout=2.0)

    # Should turn off immediately without waiting
    assert light_module.light_state["status"] == "off"
    assert light_module.light_state["scheduled_off"] is None


@pytest.mark.asyncio
async def test_background_task_cancellation_during_sleep(setup_scheduling_test_state):
    """Test that background task can be cancelled during sleep phase and cleanup properly"""
    # Set scheduled time in the real future (not using freezegun so task actually sleeps)
    light_module.light_state["status"] = "on"
    light_module.light_state["last_on"] = datetime.now().isoformat()
    # Schedule for 30 seconds in the future to ensure task will be sleeping
    scheduled_time = datetime.now() + timedelta(seconds=30)
    light_module.light_state["scheduled_off"] = scheduled_time.isoformat()

    # Create background task
    task = asyncio.create_task(light_module.execute_scheduled_turn_off())

    # Let task start and begin sleeping
    await asyncio.sleep(0.2)

    # Verify task is running (not done) - should be in the sleep phase
    assert not task.done()

    # Cancel the task during sleep
    task.cancel()

    # Wait for cancellation to process
    try:
        await asyncio.wait_for(task, timeout=0.5)
    except asyncio.CancelledError:
        pass  # Expected

    # Verify task was cancelled
    assert task.cancelled()

    # Verify system state is still consistent (light should remain on since cancel happened mid-sleep)
    assert light_module.light_state["status"] == "on"
    # Scheduled off should still be set since cancellation interrupted the process
    assert light_module.light_state["scheduled_off"] == scheduled_time.isoformat()


# =============================================================================
# State Persistence Tests
# =============================================================================

@pytest.mark.asyncio
async def test_state_file_initialization(setup_scheduling_test_state):
    """Test that state file is created with safe defaults if missing"""
    # Ensure file doesn't exist
    assert not light_module.STATE_FILE.exists()

    # Initialize state file
    light_module.initialize_state_file()

    # Verify file was created
    assert light_module.STATE_FILE.exists()

    # Verify contents
    with open(light_module.STATE_FILE, 'r') as f:
        state = json.load(f)

    assert state["status"] == "off"
    assert state["last_on"] is None
    assert state["last_off"] is None
    assert state["scheduled_off"] is None


@pytest.mark.asyncio
async def test_save_and_load_state(setup_scheduling_test_state):
    """Test saving and loading state to/from disk"""
    # Set up some state
    with freeze_time("2024-01-01 12:00:00"):
        light_module.light_state["status"] = "on"
        light_module.light_state["last_on"] = datetime.now().isoformat()
        light_module.light_state["scheduled_off"] = (datetime.now() + timedelta(minutes=30)).isoformat()

    # Save state
    light_module.save_state()

    # Verify file exists
    assert light_module.STATE_FILE.exists()

    # Load state
    loaded_state = light_module.load_state()

    # Verify loaded state matches
    assert loaded_state["status"] == "on"
    assert loaded_state["last_on"] == light_module.light_state["last_on"]
    assert loaded_state["scheduled_off"] == light_module.light_state["scheduled_off"]


@pytest.mark.asyncio
async def test_clear_scheduled_state(setup_scheduling_test_state):
    """Test clearing only scheduled_off while preserving history"""
    with freeze_time("2024-01-01 12:00:00"):
        light_module.light_state["status"] = "off"
        light_module.light_state["last_on"] = "2024-01-01T11:00:00"
        light_module.light_state["last_off"] = datetime.now().isoformat()
        light_module.light_state["scheduled_off"] = "2024-01-01T12:30:00"

    # Save initial state
    light_module.save_state()

    # Clear scheduled state
    light_module.clear_scheduled_state()

    # Reload from disk
    loaded_state = light_module.load_state()

    # Verify scheduled_off is cleared but history preserved
    assert loaded_state["scheduled_off"] is None
    assert loaded_state["last_on"] == "2024-01-01T11:00:00"
    assert loaded_state["last_off"] is not None
    assert loaded_state["status"] == "off"


@pytest.mark.asyncio
async def test_turn_on_persists_state(setup_scheduling_test_state):
    """Test that turn_on persists state to disk"""
    mcp = setup_scheduling_test_state
    turn_on_tool = mcp._tool_manager._tools["turn_on"]

    # Verify file doesn't exist yet
    assert not light_module.STATE_FILE.exists()

    # Turn on light and verify state while time is frozen
    # (prevents background task from executing immediately)
    with freeze_time("2024-01-01 12:00:00"):
        await turn_on_tool.run(arguments={"minutes": 60})

        # Small yield to allow state file to be written before checking
        import asyncio
        await asyncio.sleep(0)

        # Verify state was persisted
        assert light_module.STATE_FILE.exists()

        # Load and verify
        with open(light_module.STATE_FILE, 'r') as f:
            state = json.load(f)

        assert state["status"] == "on"
        assert state["scheduled_off"] is not None


# =============================================================================
# Startup Reconciliation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_reconciliation_runs_once(setup_scheduling_test_state):
    """Test that reconciliation runs exactly once on first tool call"""
    mcp = setup_scheduling_test_state
    status_tool = mcp._tool_manager._tools["get_light_status"]

    # Verify flag is initially False
    assert light_module._reconciliation_done is False

    # First call should trigger reconciliation
    await status_tool.run(arguments={})
    assert light_module._reconciliation_done is True

    # Subsequent calls should not trigger it again
    # (We can verify by the flag remaining True)
    await status_tool.run(arguments={})
    assert light_module._reconciliation_done is True


@pytest.mark.asyncio
async def test_reconciliation_past_scheduled_off_turns_off_light(setup_scheduling_test_state, httpx_mock: HTTPXMock):
    """Test reconciliation turns off light if scheduled_off time has passed"""
    with freeze_time("2024-01-01 12:00:00"):
        # Create persisted state with past scheduled_off time
        past_state = {
            "status": "on",
            "last_on": "2024-01-01T11:00:00",
            "last_off": None,
            "scheduled_off": "2024-01-01T11:30:00"  # 30 minutes ago
        }
        light_module.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(light_module.STATE_FILE, 'w') as f:
            json.dump(past_state, f)

        # Setup mock to show light is still on in HA
        httpx_mock.reset()

        def mock_get_state_on(request):
            return httpx.Response(200, json={"entity_id": light_module.LIGHT_ENTITY_ID, "state": "on"})

        def mock_turn_off(request):
            return httpx.Response(200, json=[])

        httpx_mock.add_callback(mock_get_state_on, url=f"{light_module.HA_URL}/api/states/{light_module.LIGHT_ENTITY_ID}")
        httpx_mock.add_callback(mock_turn_off, url=f"{light_module.HA_URL}/api/services/switch/turn_off")

        # Run reconciliation
        await light_module.reconcile_state_on_startup()

        # Verify light was turned off
        assert light_module.light_state["status"] == "off"
        assert light_module.light_state["scheduled_off"] is None


@pytest.mark.asyncio
async def test_reconciliation_future_scheduled_off_reschedules_task(setup_scheduling_test_state, httpx_mock: HTTPXMock):
    """Test reconciliation reschedules task if scheduled_off is in the future"""
    with freeze_time("2024-01-01 12:00:00"):
        # Create persisted state with future scheduled_off time
        future_state = {
            "status": "on",
            "last_on": "2024-01-01T11:30:00",
            "last_off": None,
            "scheduled_off": "2024-01-01T13:00:00"  # 1 hour in future
        }
        light_module.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(light_module.STATE_FILE, 'w') as f:
            json.dump(future_state, f)

        # Setup mock to show light is on in HA
        httpx_mock.reset()

        def mock_get_state_on(request):
            return httpx.Response(200, json={"entity_id": light_module.LIGHT_ENTITY_ID, "state": "on"})

        # Add turn_off mock for cleanup (task may execute during teardown)
        def mock_turn_off(request):
            return httpx.Response(200, json=[])

        httpx_mock.add_callback(mock_get_state_on, url=f"{light_module.HA_URL}/api/states/{light_module.LIGHT_ENTITY_ID}")
        for _ in range(10):
            httpx_mock.add_callback(mock_turn_off, url=f"{light_module.HA_URL}/api/services/switch/turn_off")

        # Run reconciliation
        await light_module.reconcile_state_on_startup()

        # Verify task was rescheduled
        assert light_module.scheduled_task is not None
        assert not light_module.scheduled_task.done()
        assert light_module.light_state["status"] == "on"
        assert light_module.light_state["scheduled_off"] == "2024-01-01T13:00:00"


@pytest.mark.asyncio
async def test_reconciliation_clears_schedule_if_light_manually_turned_off(setup_scheduling_test_state, httpx_mock: HTTPXMock):
    """Test reconciliation clears schedule if light was manually turned off"""
    with freeze_time("2024-01-01 12:00:00"):
        # Create persisted state showing light should be on, but HA shows it's off
        state = {
            "status": "on",
            "last_on": "2024-01-01T11:30:00",
            "last_off": None,
            "scheduled_off": "2024-01-01T13:00:00"  # Future
        }
        light_module.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(light_module.STATE_FILE, 'w') as f:
            json.dump(state, f)

        # Setup mock to show light is OFF in HA (manual turn-off)
        httpx_mock.reset()

        def mock_get_state_off(request):
            return httpx.Response(200, json={"entity_id": light_module.LIGHT_ENTITY_ID, "state": "off"})

        httpx_mock.add_callback(mock_get_state_off, url=f"{light_module.HA_URL}/api/states/{light_module.LIGHT_ENTITY_ID}")

        # Run reconciliation
        await light_module.reconcile_state_on_startup()

        # Verify schedule was cleared
        assert light_module.light_state["status"] == "off"
        assert light_module.light_state["scheduled_off"] is None
        assert light_module.scheduled_task is None


@pytest.mark.asyncio
async def test_reconciliation_no_scheduled_off_syncs_with_ha(setup_scheduling_test_state, httpx_mock: HTTPXMock):
    """Test reconciliation just syncs with HA if no scheduled_off exists"""
    # Create persisted state with no scheduled_off
    state = {
        "status": "off",
        "last_on": "2024-01-01T10:00:00",
        "last_off": "2024-01-01T10:30:00",
        "scheduled_off": None
    }
    light_module.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(light_module.STATE_FILE, 'w') as f:
        json.dump(state, f)

    # Setup mock
    httpx_mock.reset()

    def mock_get_state(request):
        return httpx.Response(200, json={"entity_id": light_module.LIGHT_ENTITY_ID, "state": "off"})

    httpx_mock.add_callback(mock_get_state, url=f"{light_module.HA_URL}/api/states/{light_module.LIGHT_ENTITY_ID}")

    # Run reconciliation
    await light_module.reconcile_state_on_startup()

    # Verify state was synced but no tasks created
    assert light_module.light_state["status"] == "off"
    assert light_module.scheduled_task is None


@pytest.mark.asyncio
async def test_reconciliation_handles_missing_state_file(setup_scheduling_test_state, httpx_mock: HTTPXMock):
    """Test reconciliation handles missing state file gracefully"""
    # Ensure no state file exists
    assert not light_module.STATE_FILE.exists()

    # Setup HA mock
    httpx_mock.reset()

    def mock_get_state(request):
        return httpx.Response(200, json={"entity_id": light_module.LIGHT_ENTITY_ID, "state": "off"})

    httpx_mock.add_callback(mock_get_state, url=f"{light_module.HA_URL}/api/states/{light_module.LIGHT_ENTITY_ID}")

    # Run reconciliation - should not crash
    await light_module.reconcile_state_on_startup()

    # Should create file with safe defaults
    assert light_module.STATE_FILE.exists()
    assert light_module.light_state["status"] == "off"


# =============================================================================
# Integration Tests for Complete Flow
# =============================================================================

@pytest.mark.asyncio
async def test_complete_flow_with_persistence(setup_scheduling_test_state):
    """Test complete flow: turn on → persist → turn off → verify persistence"""
    mcp = setup_scheduling_test_state
    turn_on_tool = mcp._tool_manager._tools["turn_on"]
    turn_off_tool = mcp._tool_manager._tools["turn_off"]

    with freeze_time("2024-01-01 12:00:00"):
        # Turn on light
        await turn_on_tool.run(arguments={"minutes": 60})

        # Verify state was persisted
        assert light_module.STATE_FILE.exists()
        loaded = light_module.load_state()
        assert loaded["status"] == "on"
        assert loaded["scheduled_off"] is not None

        # Turn off light
        await turn_off_tool.run(arguments={})

        # Verify scheduled_off was cleared in persistence
        loaded = light_module.load_state()
        assert loaded["status"] == "off"
        assert loaded["scheduled_off"] is None


@pytest.mark.asyncio
async def test_crash_recovery_simulation(setup_scheduling_test_state, httpx_mock: HTTPXMock):
    """Simulate server crash and recovery scenario"""
    with freeze_time("2024-01-01 12:00:00") as frozen_time:
        # Step 1: Turn on light for 60 minutes
        mcp = setup_scheduling_test_state
        turn_on_tool = mcp._tool_manager._tools["turn_on"]
        await turn_on_tool.run(arguments={"minutes": 60})

        # Verify state persisted
        assert light_module.STATE_FILE.exists()
        task_before_crash = light_module.scheduled_task

        # Step 2: Simulate crash - kill task, reset flag
        if task_before_crash:
            task_before_crash.cancel()
            try:
                await task_before_crash
            except asyncio.CancelledError:
                pass
        light_module.scheduled_task = None
        light_module._reconciliation_done = False

        # Step 3: Advance time by 30 minutes (still have 30 min left)
        frozen_time.move_to("2024-01-01 12:30:00")

        # Step 4: Server "restarts" - reconciliation runs
        httpx_mock.reset()

        def mock_get_state_on(request):
            return httpx.Response(200, json={"entity_id": light_module.LIGHT_ENTITY_ID, "state": "on"})

        # Add turn_off mock for cleanup
        def mock_turn_off(request):
            return httpx.Response(200, json=[])

        httpx_mock.add_callback(mock_get_state_on, url=f"{light_module.HA_URL}/api/states/{light_module.LIGHT_ENTITY_ID}")
        for _ in range(10):
            httpx_mock.add_callback(mock_turn_off, url=f"{light_module.HA_URL}/api/services/switch/turn_off")

        await light_module.reconcile_state_on_startup()

        # Verify: Task was rescheduled (light still has 30 min to go)
        assert light_module.scheduled_task is not None
        assert light_module.light_state["status"] == "on"
        assert light_module.light_state["scheduled_off"] == "2024-01-01T13:00:00"
