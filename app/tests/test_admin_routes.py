"""
Tests for admin routes (reset-cycle endpoint)
"""
import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from admin_routes import add_admin_routes
from utils.shared_state import current_cycle_status, reset_cycle


@pytest.fixture
def admin_app():
    """Create a test Starlette app with admin routes"""
    app = Starlette()
    add_admin_routes(app)
    return app


@pytest.fixture
def client(admin_app):
    """Create a test client for the admin app"""
    return TestClient(admin_app)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset cycle state before each test"""
    reset_cycle()
    yield
    reset_cycle()


def test_reset_cycle_endpoint_success(client):
    """Test that reset-cycle endpoint successfully resets the cycle"""
    # Set the flag to written
    current_cycle_status["written"] = True
    current_cycle_status["timestamp"] = "2025-01-15T12:00:00Z"

    # Call the reset endpoint
    response = client.post("/admin/reset-cycle")

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "message" in data

    # Verify the flag was reset
    assert current_cycle_status["written"] is False


def test_reset_cycle_endpoint_idempotent(client):
    """Test that calling reset multiple times is safe (idempotent)"""
    # Set the flag to written
    current_cycle_status["written"] = True

    # Call reset twice
    response1 = client.post("/admin/reset-cycle")
    response2 = client.post("/admin/reset-cycle")

    # Both should succeed
    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response1.json()["success"] is True
    assert response2.json()["success"] is True

    # Flag should still be False
    assert current_cycle_status["written"] is False


def test_reset_cycle_when_already_false(client):
    """Test resetting when cycle flag is already False"""
    # Ensure flag is False
    current_cycle_status["written"] = False

    # Call reset
    response = client.post("/admin/reset-cycle")

    # Should still succeed
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert current_cycle_status["written"] is False


def test_reset_cycle_endpoint_wrong_method(client):
    """Test that GET requests to reset-cycle endpoint are rejected"""
    # Try GET instead of POST
    response = client.get("/admin/reset-cycle")

    # Should return 405 Method Not Allowed
    assert response.status_code == 405
