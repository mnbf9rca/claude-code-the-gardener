"""
Shared test fixtures for the plant care system tests
"""
import tempfile
import shutil
from pathlib import Path
from typing import Generator, List
import pytest
import cv2


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "httpx_mock: Configure httpx mock behavior"
    )
    config.addinivalue_line(
        "markers", "integration: Mark test as integration test (may require external services)"
    )


@pytest.fixture
def test_photos_dir() -> Generator[Path, None, None]:
    """Create and provide a temporary directory for test photos."""
    temp_dir = tempfile.mkdtemp(prefix="test_photos_")
    yield Path(temp_dir)
    # Cleanup after test
    if Path(temp_dir).exists():
        shutil.rmtree(temp_dir)


@pytest.fixture
def sample_photos() -> List[Path]:
    """Provide paths to pre-captured test photos."""
    fixtures_dir = Path(__file__).parent / "tests" / "fixtures" / "photos"
    if photos := sorted(fixtures_dir.glob("test_plant_*.jpg")):
        return photos
    raise FileNotFoundError("No sample photos available in tests/fixtures/photos/")


@pytest.fixture
def camera_config(test_photos_dir: Path, monkeypatch, reset_camera_module) -> dict:
    """Provide test-specific camera configuration."""
    import tools.camera as camera_module

    config = {
        "CAMERA_ENABLED": "true",
        "CAMERA_DEVICE_INDEX": "0",
        "CAMERA_SAVE_PATH": str(test_photos_dir),
        "CAMERA_IMAGE_WIDTH": "1920",
        "CAMERA_IMAGE_HEIGHT": "1080",
        "CAMERA_IMAGE_QUALITY": "85",
        "CAMERA_CAPTURE_TIMEOUT": "5",
    }

    # Apply configuration to environment
    for key, value in config.items():
        monkeypatch.setenv(key, value)

    # Update camera module configuration
    camera_module.CAMERA_CONFIG["enabled"] = True
    camera_module.CAMERA_CONFIG["device_index"] = 0
    camera_module.CAMERA_CONFIG["save_path"] = test_photos_dir
    camera_module.CAMERA_CONFIG["image_width"] = 1920
    camera_module.CAMERA_CONFIG["image_height"] = 1080
    camera_module.CAMERA_CONFIG["image_quality"] = 85
    camera_module.CAMERA_CONFIG["capture_timeout"] = 5

    return config


@pytest.fixture
def camera_config_disabled(test_photos_dir: Path, monkeypatch, reset_camera_module) -> dict:
    """Provide test configuration with camera disabled."""
    import tools.camera as camera_module

    config = {
        "CAMERA_ENABLED": "false",
        "CAMERA_DEVICE_INDEX": "0",
        "CAMERA_SAVE_PATH": str(test_photos_dir),
        "CAMERA_IMAGE_WIDTH": "1920",
        "CAMERA_IMAGE_HEIGHT": "1080",
        "CAMERA_IMAGE_QUALITY": "85",
        "CAMERA_CAPTURE_TIMEOUT": "5",
    }

    # Apply configuration to environment
    for key, value in config.items():
        monkeypatch.setenv(key, value)

    # Update camera module configuration
    camera_module.CAMERA_CONFIG["enabled"] = False
    camera_module.CAMERA_CONFIG["device_index"] = 0
    camera_module.CAMERA_CONFIG["save_path"] = test_photos_dir
    camera_module.CAMERA_CONFIG["image_width"] = 1920
    camera_module.CAMERA_CONFIG["image_height"] = 1080
    camera_module.CAMERA_CONFIG["image_quality"] = 85
    camera_module.CAMERA_CONFIG["capture_timeout"] = 5

    # Reset camera state for disabled test
    camera_module.camera = None
    camera_module.camera_available = False
    camera_module.camera_error = None

    return config


def has_real_camera() -> bool:
    """Check if a real camera is available on the system."""
    try:
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            ret, _ = cap.read()
            cap.release()
            return ret
        return False
    except Exception:
        return False


# Mark to skip tests that require a real camera
requires_camera = pytest.mark.skipif(
    not has_real_camera(),
    reason="No real camera available on this system"
)


def has_sample_photos() -> bool:
    """Check if sample photos are available in tests/fixtures/photos/."""
    fixtures_dir = Path(__file__).parent / "tests" / "fixtures" / "photos"
    return fixtures_dir.exists() and len(list(fixtures_dir.glob("*.jpg"))) > 0


# Mark to skip tests that require sample photos
requires_sample_photos = pytest.mark.skipif(
    not has_sample_photos(),
    reason="No sample photos available in tests/fixtures/photos/"
)


@pytest.fixture
def reset_camera_module():
    """Reset camera module state between tests."""
    import tools.camera as camera_module

    # Save original state
    original_camera = camera_module.camera
    original_available = camera_module.camera_available
    original_error = camera_module.camera_error
    original_history = camera_module.photo_history.copy()

    # Clear photo history for tests (tests expect a clean slate)
    camera_module.photo_history.clear()

    yield

    # Restore original state
    if camera_module.camera is not None and camera_module.camera != original_camera:
        camera_module.camera.release()

    camera_module.camera = original_camera
    camera_module.camera_available = original_available
    camera_module.camera_error = original_error
    camera_module.photo_history = original_history


@pytest.fixture
def reset_cycle_state():
    """Reset the cycle state for tests."""
    from utils.shared_state import current_cycle_status, reset_cycle

    # Save original state
    original_written = current_cycle_status["written"]
    original_timestamp = current_cycle_status["timestamp"]

    # Reset for test
    reset_cycle()

    yield

    # Restore original state
    current_cycle_status["written"] = original_written
    current_cycle_status["timestamp"] = original_timestamp


@pytest.fixture
def allow_camera_capture(reset_cycle_state):
    """Allow camera capture by marking status as written."""
    from utils.shared_state import current_cycle_status
    current_cycle_status["written"] = True
    yield