"""
Integration test for HTTP photo serving

Tests that photos captured by the camera tool are accessible via HTTP.
"""
from pathlib import Path
from starlette.staticfiles import StaticFiles
from starlette.testclient import TestClient
from fastmcp import FastMCP
import pytest


@pytest.fixture
def photo_server_fixture():
    """Provide photos directory and sample photo for HTTP serving tests"""
    # Use test fixtures photos directory
    photos_dir = Path(__file__).parent / "fixtures" / "photos"

    # Ensure directory exists and has at least one photo
    if not photos_dir.exists() or not list(photos_dir.glob("*.jpg")):
        raise FileNotFoundError("Test fixtures photos directory not available")

    # Get first available photo for testing
    test_photo = next(photos_dir.glob("*.jpg"))

    return photos_dir, test_photo


def test_static_files_accessible_via_http(photo_server_fixture):
    """Test that mounted static files are accessible via HTTP"""
    photos_dir, test_photo = photo_server_fixture

    # Create MCP server
    mcp = FastMCP("test")

    # Get underlying Starlette app and mount static files
    app = mcp.http_app()
    app.mount("/photos", StaticFiles(directory=str(photos_dir)), name="photos")

    # Create test client (doesn't start actual server)
    client = TestClient(app)

    # Try to fetch the test photo
    response = client.get(f"/photos/{test_photo.name}")

    # Verify photo is accessible
    assert response.status_code == 200
    # Verify we got actual image data (should be larger than a few bytes)
    assert len(response.content) > 100
    # Verify it's a JPEG file
    assert response.content[:2] == b'\xff\xd8'  # JPEG magic bytes


def test_http_404_for_missing_photo(photo_server_fixture):
    """Test that HTTP returns 404 for non-existent photos"""
    photos_dir, _ = photo_server_fixture

    # Create MCP server
    mcp = FastMCP("test")

    # Get underlying Starlette app and mount static files
    app = mcp.http_app()
    app.mount("/photos", StaticFiles(directory=str(photos_dir)), name="photos")

    # Create test client (doesn't start actual server)
    client = TestClient(app)

    # Try to fetch a non-existent photo
    response = client.get("/photos/nonexistent.jpg")

    # Verify we get 404
    assert response.status_code == 404
