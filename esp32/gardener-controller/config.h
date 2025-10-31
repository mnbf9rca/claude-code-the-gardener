/**
 * Configuration file for Gardener Controller
 * M5Stack CoreS3-SE ESP32-S3 Plant Care System
 */

#ifndef CONFIG_H
#define CONFIG_H

// ============================================================================
// GPIO Pin Assignments
// ============================================================================

// Moisture sensor connected to GPIO10 (M5-Bus pin 2, right side)
// This pin supports ADC1_CH9 for analog readings
#define PIN_MOISTURE_SENSOR 10

// Relay control connected to GPIO7 (M5-Bus pin 22, right side)
// Digital output to control 5V relay module
#define PIN_RELAY_PUMP 7

// ============================================================================
// ADC Configuration
// ============================================================================

// ESP32-S3 ADC resolution: 12-bit (0-4095)
#define ADC_RESOLUTION 12
#define ADC_MAX_VALUE 4095
#define ADC_MIN_VALUE 0

// ADC channel for GPIO10
#define ADC_CHANNEL ADC1_CHANNEL_9

// ============================================================================
// Safety Limits
// ============================================================================

// Maximum pump activation time per request (seconds)
// Prevents flooding in case of bugs or malicious requests
#define PUMP_MAX_SECONDS 30

// Minimum pump activation time (seconds)
// Prevents very short pulses that might not prime the pump
#define PUMP_MIN_SECONDS 1

// ============================================================================
// WiFi Configuration
// ============================================================================

// Access point name for WiFi configuration portal (first boot)
#define WIFI_AP_NAME "GardenerSetup"

// WiFi connection timeout (milliseconds)
#define WIFI_CONNECT_TIMEOUT 30000

// WiFi reconnection check interval (milliseconds)
#define WIFI_RECONNECT_INTERVAL 30000

// ============================================================================
// NTP and RTC Configuration
// ============================================================================

// RTC resync interval (seconds)
// How often to update RTC from NTP-synced system time
// ESP32 system time auto-syncs with NTP in background, we copy to RTC periodically
#define RTC_RESYNC_INTERVAL 3600  // 1 hour (3600 seconds)

// ============================================================================
// HTTP Server Configuration
// ============================================================================

// HTTP server listening port
#define HTTP_PORT 80

// mDNS hostname (accessible as gardener.local on local network)
#define OTA_HOSTNAME "gardener-esp32"

// JSON buffer size for request/response parsing
#define JSON_BUFFER_SIZE 256

// ============================================================================
// Display Configuration
// ============================================================================

// Display update interval (milliseconds)
// How often to refresh the screen with new sensor readings
#define DISPLAY_UPDATE_INTERVAL 2000

// Display colors (RGB565 format)
#define COLOR_BACKGROUND 0x0000   // Black
#define COLOR_TEXT 0xFFFF         // White
#define COLOR_OK 0x07E0           // Green
#define COLOR_WARNING 0xFFE0      // Yellow
#define COLOR_ERROR 0xF800        // Red
#define COLOR_INFO 0x07FF         // Cyan

// Display text size
#define TEXT_SIZE_SMALL 1
#define TEXT_SIZE_MEDIUM 2
#define TEXT_SIZE_LARGE 3

// ============================================================================
// Debug Configuration
// ============================================================================

// Enable serial debug output (115200 baud)
#define DEBUG_SERIAL true

// Serial baud rate
#define SERIAL_BAUD 115200

#endif // CONFIG_H
