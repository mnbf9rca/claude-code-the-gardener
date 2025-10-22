"""
Shared ESP32 configuration and HTTP client setup.
Centralizes ESP32_HOST/PORT parsing and URL construction.
"""
import os
from urllib.parse import urlparse, urlunparse
import httpx


class ESP32Config:
    """ESP32 connection configuration"""

    def __init__(self):
        # ESP32 configuration from environment
        self.host = os.getenv("ESP32_HOST")
        if not self.host:
            raise ValueError("ESP32_HOST environment variable is required but not set")

        env_port_set = os.getenv("ESP32_PORT") is not None

        # Use urlparse for robust protocol and host extraction
        # Add scheme if missing to help urlparse work correctly
        parse_target = self.host
        if not parse_target.startswith("http://") and not parse_target.startswith("https://"):
            parse_target = f"http://{parse_target}"

        parsed = urlparse(parse_target)

        # Extract netloc (host:port combination)
        # If netloc is empty, urlparse put the host in path (e.g., for bare "localhost:8080")
        netloc = parsed.netloc if parsed.netloc else parsed.path

        # Parse host and port, handling IPv6 addresses
        if netloc.startswith('['):
            # IPv6 address format: [::1]:8080 or [::1]
            bracket_end = netloc.find(']')
            if bracket_end == -1:
                raise ValueError(f"Invalid IPv6 address format in ESP32_HOST: {self.host}")

            extracted_host = netloc[:bracket_end + 1]  # Include the closing bracket
            remainder = netloc[bracket_end + 1:]

            if remainder.startswith(':'):
                # Port specified after IPv6 address
                extracted_port = remainder[1:]
                if env_port_set:
                    raise ValueError(
                        "Port specified in both ESP32_HOST and ESP32_PORT. "
                        "Please use only one method to specify the port."
                    )
            else:
                # No port in host
                extracted_port = None
        else:
            # IPv4 address or hostname
            if ':' in netloc:
                # Port specified
                extracted_host, extracted_port = netloc.rsplit(':', 1)
                if env_port_set:
                    raise ValueError(
                        "Port specified in both ESP32_HOST and ESP32_PORT. "
                        "Please use only one method to specify the port."
                    )
            else:
                # No port in host
                extracted_host = netloc
                extracted_port = None

        # Set the port
        if extracted_port:
            self.port = int(extracted_port)
        else:
            self.port = int(os.getenv("ESP32_PORT", "80"))

        # Store clean host (without port)
        self.clean_host = extracted_host

        # Construct base URL
        self.base_url = urlunparse(("http", f"{self.clean_host}:{self.port}", "", "", "", ""))

    def get_client(self, timeout: float = 5.0) -> httpx.AsyncClient:
        """
        Create an async HTTP client with the specified timeout and base_url.

        Args:
            timeout: Request timeout in seconds

        Returns:
            Configured AsyncClient instance with base_url set
        """
        return httpx.AsyncClient(timeout=timeout, base_url=self.base_url)


# Singleton instance for reuse across modules
_config = None


def get_esp32_config() -> ESP32Config:
    """Get or create the ESP32 configuration singleton"""
    global _config
    if _config is None:
        _config = ESP32Config()
    return _config
