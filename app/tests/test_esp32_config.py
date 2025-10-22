"""
Unit tests for esp32_config module
"""
import os
import pytest
from utils.esp32_config import ESP32Config, get_esp32_config, _config


def reset_singleton():
    """Reset the singleton for testing"""
    global _config
    import utils.esp32_config
    utils.esp32_config._config = None


@pytest.fixture(autouse=True)
def clean_env():
    """Clean environment variables before each test"""
    # Save original values
    original_host = os.environ.get("ESP32_HOST")
    original_port = os.environ.get("ESP32_PORT")

    # Clean for test
    os.environ.pop("ESP32_HOST", None)
    os.environ.pop("ESP32_PORT", None)
    reset_singleton()

    yield

    # Restore original values
    if original_host is not None:
        os.environ["ESP32_HOST"] = original_host
    else:
        os.environ.pop("ESP32_HOST", None)

    if original_port is not None:
        os.environ["ESP32_PORT"] = original_port
    else:
        os.environ.pop("ESP32_PORT", None)

    reset_singleton()


def test_esp32_config_basic():
    """Test basic ESP32 config with host and default port"""
    os.environ["ESP32_HOST"] = "192.168.1.100"

    config = ESP32Config()

    assert config.host == "192.168.1.100"
    assert config.port == 80
    assert config.base_url == "http://192.168.1.100:80"


def test_esp32_config_custom_port():
    """Test ESP32 config with custom port via ESP32_PORT"""
    os.environ["ESP32_HOST"] = "192.168.1.100"
    os.environ["ESP32_PORT"] = "8080"

    config = ESP32Config()

    assert config.host == "192.168.1.100"
    assert config.port == 8080
    assert config.base_url == "http://192.168.1.100:8080"


def test_esp32_config_port_in_host():
    """Test ESP32 config with port specified in host"""
    os.environ["ESP32_HOST"] = "192.168.1.100:8080"

    config = ESP32Config()

    assert config.port == 8080
    assert config.base_url == "http://192.168.1.100:8080"


def test_esp32_config_strips_http_prefix():
    """Test that http:// prefix is stripped from host"""
    os.environ["ESP32_HOST"] = "http://192.168.1.100"

    config = ESP32Config()

    assert config.base_url == "http://192.168.1.100:80"


def test_esp32_config_strips_https_prefix():
    """Test that https:// prefix is stripped from host"""
    os.environ["ESP32_HOST"] = "https://192.168.1.100"

    config = ESP32Config()

    assert config.base_url == "http://192.168.1.100:80"


def test_esp32_config_strips_protocol_and_uses_port_from_host():
    """Test that protocol is stripped and port from host is used"""
    os.environ["ESP32_HOST"] = "http://192.168.1.100:8080"

    config = ESP32Config()

    assert config.port == 8080
    assert config.base_url == "http://192.168.1.100:8080"


def test_esp32_config_missing_host():
    """Test that missing ESP32_HOST raises error"""
    # ESP32_HOST not set

    with pytest.raises(ValueError, match="ESP32_HOST environment variable is required"):
        ESP32Config()


def test_esp32_config_port_conflict():
    """Test that specifying port in both host and ESP32_PORT raises error"""
    os.environ["ESP32_HOST"] = "192.168.1.100:8080"
    os.environ["ESP32_PORT"] = "9090"

    with pytest.raises(ValueError, match="Port specified in both ESP32_HOST and ESP32_PORT"):
        ESP32Config()


def test_esp32_config_hostname():
    """Test ESP32 config with hostname instead of IP"""
    os.environ["ESP32_HOST"] = "esp32.local"

    config = ESP32Config()

    assert config.host == "esp32.local"
    assert config.port == 80
    assert config.base_url == "http://esp32.local:80"


def test_esp32_config_hostname_with_port():
    """Test ESP32 config with hostname and port"""
    os.environ["ESP32_HOST"] = "esp32.local:8080"

    config = ESP32Config()

    assert config.port == 8080
    assert config.base_url == "http://esp32.local:8080"


def test_get_client():
    """Test get_client returns AsyncClient with correct timeout"""
    os.environ["ESP32_HOST"] = "192.168.1.100"

    config = ESP32Config()
    client = config.get_client(timeout=10.0)

    assert client is not None
    assert client.timeout.read == 10.0


def test_get_client_default_timeout():
    """Test get_client uses default timeout"""
    os.environ["ESP32_HOST"] = "192.168.1.100"

    config = ESP32Config()
    client = config.get_client()

    assert client is not None
    assert client.timeout.read == 5.0


def test_singleton_pattern():
    """Test that get_esp32_config returns the same instance"""
    os.environ["ESP32_HOST"] = "192.168.1.100"

    config1 = get_esp32_config()
    config2 = get_esp32_config()

    assert config1 is config2


def test_invalid_port_in_env():
    """Test that invalid port in ESP32_PORT raises error"""
    os.environ["ESP32_HOST"] = "192.168.1.100"
    os.environ["ESP32_PORT"] = "not_a_number"

    with pytest.raises(ValueError):
        ESP32Config()


def test_invalid_port_in_host():
    """Test that invalid port in host raises error"""
    os.environ["ESP32_HOST"] = "192.168.1.100:not_a_number"

    with pytest.raises(ValueError):
        ESP32Config()


def test_ipv6_address():
    """Test ESP32 config with IPv6 address"""
    os.environ["ESP32_HOST"] = "[::1]"

    config = ESP32Config()

    assert config.clean_host == "[::1]"
    assert config.port == 80
    assert config.base_url == "http://[::1]:80"


def test_ipv6_address_with_port():
    """Test ESP32 config with IPv6 address and port"""
    os.environ["ESP32_HOST"] = "[::1]:8080"

    config = ESP32Config()

    assert config.clean_host == "[::1]"
    assert config.port == 8080
    assert config.base_url == "http://[::1]:8080"


def test_ipv6_address_with_protocol():
    """Test ESP32 config with IPv6 address and protocol prefix"""
    os.environ["ESP32_HOST"] = "http://[2001:db8::1]:8080"

    config = ESP32Config()

    assert config.clean_host == "[2001:db8::1]"
    assert config.port == 8080
    assert config.base_url == "http://[2001:db8::1]:8080"


def test_ipv6_invalid_format():
    """Test that invalid IPv6 format raises error"""
    os.environ["ESP32_HOST"] = "[::1"  # Missing closing bracket

    # urlparse will catch this first and raise "Invalid IPv6 URL"
    with pytest.raises(ValueError, match="Invalid IPv6"):
        ESP32Config()


def test_ipv6_port_conflict():
    """Test that specifying port in both IPv6 host and ESP32_PORT raises error"""
    os.environ["ESP32_HOST"] = "[::1]:8080"
    os.environ["ESP32_PORT"] = "9090"

    with pytest.raises(ValueError, match="Port specified in both"):
        ESP32Config()


def test_client_base_url():
    """Test that AsyncClient is created with base_url"""
    os.environ["ESP32_HOST"] = "192.168.1.100:8080"

    config = ESP32Config()
    client = config.get_client()

    # httpx normalizes base_url
    assert str(client.base_url) == "http://192.168.1.100:8080"
