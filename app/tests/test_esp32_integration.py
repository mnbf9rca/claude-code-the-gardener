"""
Real Integration Tests for ESP32 Hardware Controller

These tests connect to a real ESP32 device and are kept MINIMAL.
They ONLY verify hardware connectivity and basic HTTP API functionality.

All business logic (history tracking, usage limits, ML calculations, etc.)
is tested via comprehensive unit tests in test_moisture_sensor.py and test_water_pump.py.

These integration tests verify:
1. ESP32 /status endpoint returns expected data structure
2. Moisture sensor ADC can be read (GPIO10)
3. Water pump relay can be activated (GPIO7)
4. ESP32 properly rejects invalid requests

They are skipped if ESP32 is not reachable.

To run these tests, ensure:
1. .env file exists with ESP32_HOST (and optionally ESP32_PORT)
2. ESP32 device is running and reachable on the network
3. Moisture sensor is connected to GPIO10
4. Water pump relay is connected to GPIO7
"""
import pytest
import pytest_asyncio
import httpx
from dotenv import load_dotenv
from utils.esp32_config import get_esp32_config

# Load environment variables
load_dotenv()


async def check_esp32_available() -> tuple[bool, str]:
    """
    Check if ESP32 is reachable via /status endpoint.

    Returns:
        Tuple of (is_available, message)
    """
    config = None
    try:
        # Try to get ESP32 config
        config = get_esp32_config()
        url = f"{config.base_url}/status"

        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                # Verify it has expected fields from actual ESP32 response
                # Expected fields: rtc_time, wifi_connected, free_heap, pump_active, moisture
                if "wifi_connected" in data and "free_heap" in data:
                    return True, f"ESP32 available at {config.base_url} (WiFi: {data.get('wifi_connected')}, Heap: {data.get('free_heap')})"
                return False, f"ESP32 at {config.base_url} returned invalid status format (got: {list(data.keys())})"
            return False, f"ESP32 status check failed: HTTP {response.status_code} from {url}"
    except ValueError as e:
        # Config error (e.g., ESP32_HOST not set)
        return False, f"ESP32 config error: {e}"
    except httpx.TimeoutException:
        base_url = config.base_url if config else "unknown"
        return False, f"ESP32 timeout: No response from {base_url} within 3s"
    except httpx.ConnectError as e:
        base_url = config.base_url if config else "unknown"
        return False, f"ESP32 connection failed: Cannot reach {base_url} - {e}"
    except Exception as e:
        return False, f"ESP32 availability check error: {type(e).__name__}: {e}"


@pytest_asyncio.fixture(scope="session")
async def esp32_availability():
    """Check ESP32 availability once per test session"""
    available, message = await check_esp32_available()
    # Print message so it shows in pytest output with -v
    print(f"\n{message}")
    return available, message


@pytest_asyncio.fixture(autouse=True)
async def setup_integration_state(esp32_availability):
    """Check ESP32 availability before each integration test"""
    available, message = esp32_availability
    if not available:
        pytest.skip(f"ESP32 device is not available: {message}")

    # Reset ESP32 config singleton
    import utils.esp32_config
    utils.esp32_config._config = None

    yield

    # Cleanup
    utils.esp32_config._config = None


@pytest.mark.asyncio
async def test_esp32_status_endpoint():
    """Test that ESP32 status endpoint returns valid data"""
    config = get_esp32_config()

    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{config.base_url}/status")
        response.raise_for_status()
        data = response.json()

    # Verify expected fields (based on actual ESP32 response)
    assert "rtc_time" in data
    assert "wifi_connected" in data
    assert "wifi_rssi" in data
    assert "free_heap" in data
    assert "pump_active" in data
    assert "moisture" in data

    # Verify types
    assert isinstance(data["wifi_connected"], bool)
    assert isinstance(data["wifi_rssi"], int)
    assert isinstance(data["free_heap"], int)
    assert isinstance(data["pump_active"], bool)
    assert isinstance(data["moisture"], int)

    # Verify reasonable values
    assert data["free_heap"] > 0
    assert 0 <= data["moisture"] <= 4095  # 12-bit ADC
    assert -100 <= data["wifi_rssi"] <= 0  # WiFi RSSI range

    print(f"✓ ESP32 status: WiFi={data['wifi_connected']}, RSSI={data['wifi_rssi']}dBm, "
          f"Heap={data['free_heap']} bytes, Moisture={data['moisture']}, Pump={data['pump_active']}")


@pytest.mark.asyncio
async def test_read_moisture_adc():
    """Test reading moisture sensor ADC value from ESP32 (GPIO10)"""
    config = get_esp32_config()

    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{config.base_url}/moisture")
        response.raise_for_status()
        data = response.json()

    # Verify response structure
    assert "value" in data
    assert "timestamp" in data
    assert "status" in data

    # Verify value is in valid ADC range (12-bit: 0-4095)
    assert isinstance(data["value"], int)
    assert 0 <= data["value"] <= 4095

    # Verify status is ok
    assert data["status"].lower() == "ok"

    print(f"✓ Moisture ADC reading: {data['value']}")


@pytest.mark.asyncio
async def test_activate_pump():
    """Test activating water pump relay (GPIO7) with minimal duration for safety"""
    config = get_esp32_config()

    # Activate pump for minimal duration (2 seconds for safety)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{config.base_url}/pump",
            json={"seconds": 2},
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        data = response.json()

    # Verify ESP32 reports success
    assert "success" in data
    assert data["success"] is True

    # Verify duration was recorded
    assert "duration" in data or "seconds" in data

    print("✓ Water pump activated successfully")


@pytest.mark.asyncio
async def test_esp32_error_handling():
    """Test that invalid requests to ESP32 are handled gracefully"""
    config = get_esp32_config()

    # Try to activate pump with invalid seconds (should fail validation on ESP32)
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.post(
            f"{config.base_url}/pump",
            json={"seconds": 100},  # Exceeds 30s safety limit
            headers={"Content-Type": "application/json"}
        )

        # Should return error
        assert response.status_code in [400, 409]
        data = response.json()
        assert data["success"] is False
        assert "error" in data

    print("✓ Error handling: ESP32 rejected invalid request")


# Optional: Mark tests as slow for filtering
pytestmark = pytest.mark.slow


if __name__ == "__main__":
    # Run with: pytest test_esp32_integration.py -v
    # Or skip if ESP32 not available: pytest test_esp32_integration.py -v -m "not slow"
    pytest.main([__file__, "-v"])
