# Testing Guide

This directory contains comprehensive tests for the Plant Care MCP Server system.

## Test Structure

### Unit Tests (Fast, Mocked)
These tests run quickly and don't require external services:

- **`test_plant_status.py`** - Plant status tracking and history
- **`test_moisture_sensor.py`** - Moisture sensor with mocked ESP32 HTTP responses (8 tests)
- **`test_water_pump.py`** - Water pump with mocked ESP32 HTTP responses (16 tests)
- **`test_light.py`** - Light control with mocked Home Assistant HTTP responses
- **`test_camera.py`** - Camera capture and photo history
- **`test_esp32_config.py`** - ESP32 configuration parsing and validation (21 tests)
- **`test_server.py`** - Full MCP server integration with all mocked services (13 tests)

### Integration Tests (Slow, Real Hardware)
These tests connect to real devices and are skipped if hardware is unavailable:

- **`test_esp32_integration.py`** - Real ESP32 hardware tests (4 tests)
  - Requires: ESP32 device running on network with `ESP32_HOST` configured
  - Tests: status endpoint, moisture ADC read, pump activation, error handling
  - Note: Only tests hardware connectivity, NOT business logic (that's in unit tests)

- **`test_light_integration.py`** - Real Home Assistant integration tests
  - Requires: Home Assistant running with `HOME_ASSISTANT_URL` and `HOME_ASSISTANT_TOKEN`
  - Tests: light control, state synchronization, timing constraints

## Running Tests

### Run All Fast Tests (Default)
```bash
pytest
# or
uv run python -m pytest
```

### Run Specific Test Files
```bash
# Unit tests
pytest tests/test_moisture_sensor.py -v
pytest tests/test_water_pump.py -v
pytest tests/test_esp32_config.py -v

# Server integration (mocked)
pytest tests/test_server.py -v
```

### Run Integration Tests (Real Hardware)
```bash
# Run all integration tests
pytest -m slow

# Run specific integration tests
pytest tests/test_esp32_integration.py -v
pytest tests/test_light_integration.py -v
```

### Run Everything (Unit + Integration)
```bash
pytest --ignore=tests/test_light_integration.py --ignore=tests/test_esp32_integration.py -v  # Fast tests only
pytest -v  # All tests (integration tests will skip if hardware unavailable)
```

## Test Configuration

### ESP32 Integration Tests
Create a `.env` file in the `app` directory:
```bash
ESP32_HOST=192.168.1.100  # Your ESP32 IP address
ESP32_PORT=80             # Optional, defaults to 80
PUMP_ML_PER_SECOND=3.5    # Your pump calibration
```

The tests will automatically skip if:
- ESP32_HOST is not set
- ESP32 device is not reachable
- `/status` endpoint doesn't respond

### Home Assistant Integration Tests
Add to your `.env` file:
```bash
HOME_ASSISTANT_URL=http://homeassistant.local:8123
HOME_ASSISTANT_TOKEN=your_long_lived_access_token
LIGHT_ENTITY_ID=switch.smart_plug_mini
```

## Test Markers

- **`@pytest.mark.slow`** - Marks integration tests that require real hardware
- Use `-m slow` to run only integration tests
- Use `-m "not slow"` to skip integration tests

## Coverage

### Moisture Sensor
- **Unit tests** (8 tests): HTTP mocking, error handling, history management, JSON parsing, state persistence
- **Integration tests** (1 test): Real sensor ADC reading (GPIO10)

### Water Pump
- **Unit tests** (16 tests): ML-to-seconds conversion, 24h limits, state persistence, HTTP mocking, error handling
- **Integration tests** (1 test): Real pump activation (2 seconds for safety)

### ESP32 Config
- **Unit tests** (21 tests): URL parsing, IPv6 support, port conflicts, protocol stripping, singleton pattern
- **Integration tests** (2 tests): Status endpoint validation, error handling

## Best Practices

1. **Write unit tests first** - Mock external dependencies for fast, reliable tests
2. **Minimal integration tests** - Only verify real hardware connectivity, not business logic
3. **Safety first** - Integration tests use minimal water (10ml) and check availability before running
4. **Isolation** - Each test resets state and cleans up after itself
5. **Clear names** - Test names describe what they verify

## Debugging

### Tests Skip Unexpectedly
```bash
# Check if ESP32 is reachable (with debug output)
pytest tests/test_esp32_integration.py::test_esp32_status_endpoint -vs

# The -s flag shows why the test was skipped, e.g.:
#   "ESP32 timeout: No response from http://192.168.1.100:80 within 3s"
#   "ESP32 config error: ESP32_HOST environment variable is required but not set"
#   "ESP32 at http://192.168.1.100:80 returned invalid status format"

# Check environment variables
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('ESP32_HOST'))"
```

### View Test Output
```bash
# Show print statements and skip reasons
pytest -vs

# Show detailed output for failures
pytest -v --tb=short

# Stop on first failure
pytest -x

# Run integration tests with debug output
pytest -m slow -vs
```

## Adding New Tests

### For New Feature with External Service
1. Create unit tests in `test_<feature>.py` with mocked HTTP responses
2. Add integration test to `test_<service>_integration.py` if it requires real hardware
3. Mark integration tests with `@pytest.mark.slow`
4. Add availability check using pattern from existing integration tests

Example:
```python
async def check_service_available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{SERVICE_URL}/health")
            return response.status_code == 200
    except Exception:
        return False

@pytest_asyncio.fixture(scope="session")
async def service_availability():
    return await check_service_available()

@pytest_asyncio.fixture(autouse=True)
async def setup_test(service_availability):
    if not service_availability:
        pytest.skip("Service not available")
    # ... setup code
```
