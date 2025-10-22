# ESP32 Plant Controller Implementation Plan

## Overview
Minimal, lightweight firmware for M5Stack CoreS3-SE that provides HTTP REST API for moisture sensing and pump control.

## Hardware Configuration
- **Board**: M5Stack CoreS3-SE (ESP32-S3)
- **GPIO10** (M5-Bus pin 2) → Moisture sensor (ADC1_CH9)
- **GPIO7** (M5-Bus pin 22) → Relay control (digital output)

## Architecture

### Core Components
1. **HTTP Server** (ESPAsyncWebServer)
   - Lightweight async server
   - Two endpoints: `/moisture` (GET), `/pump` (POST)
   - JSON request/response using ArduinoJson

2. **Display UI** (M5Unified)
   - WiFi status and IP address
   - Live moisture reading (refresh every 2s)
   - Pump status with countdown timer

3. **WiFi Management** (WiFiManager)
   - Captive portal on first boot
   - Credentials stored in NVS flash
   - Auto-reconnect on disconnect

4. **OTA Updates** (ArduinoOTA)
   - Enable wireless firmware updates
   - Reduces need for USB cable access

### Design Principles
- **KISS**: Simple, single-file implementation where possible
- **YAGNI**: No features not explicitly needed (no web UI, no authentication, no logging)
- **Safety First**: 30-second pump timeout enforced in firmware
- **Fail Gracefully**: Display shows errors, HTTP returns proper status codes

## Implementation Steps

### Phase 1: Basic Hardware Setup
**Goal**: Verify GPIO pins work for ADC and digital output

**Steps**:
1. Create `config.h` with pin definitions
2. Initialize M5Unified
3. Configure GPIO10 as ADC input (12-bit resolution)
4. Configure GPIO7 as digital output
5. Test: Read ADC, toggle relay every 5 seconds
6. Display readings on screen

**Validation**: Can read moisture sensor and manually activate relay

---

### Phase 2: HTTP Server
**Goal**: Implement REST API endpoints

**Steps**:
1. Include ESPAsyncWebServer and ArduinoJson libraries
2. Initialize async web server on port 80
3. Implement `GET /moisture` endpoint:
   - Read ADC from GPIO10
   - Return JSON: `{"value": N, "timestamp": "ISO8601", "status": "ok"}`
4. Implement `POST /pump` endpoint:
   - Parse JSON body: `{"seconds": N}`
   - Validate: 1 <= N <= 30 (safety limit)
   - Activate GPIO7 for N seconds (blocking with delay)
   - Return JSON: `{"success": true, "duration": N, "timestamp": "ISO8601"}`
5. Add error handling:
   - Invalid JSON → 400 Bad Request
   - Duration out of range → 400 Bad Request
   - Server errors → 500 Internal Server Error

**Validation**: Can call endpoints with curl/Postman

---

### Phase 3: WiFi Management
**Goal**: Easy WiFi configuration without hardcoded credentials

**Steps**:
1. Include WiFiManager library
2. On boot, attempt to connect with saved credentials
3. If no credentials or connection fails:
   - Start AP: "GardenerSetup"
   - Launch captive portal at 192.168.4.1
   - Wait for user to configure WiFi
4. Once connected:
   - Display IP address on screen
   - Start HTTP server
   - Enable mDNS (hostname: `gardener.local`)
5. Add reconnection logic:
   - Check WiFi status every 30 seconds
   - Auto-reconnect if disconnected
   - Display "Disconnected" status

**Validation**: Can configure WiFi via captive portal, reconnects after router reboot

---

### Phase 4: Display UI
**Goal**: Show system status and live sensor data

**Steps**:
1. Design simple text-based layout:
   ```
   WiFi: Connected
   IP: 192.168.1.100

   Moisture: 2047 (54%)
   [▓▓▓▓▓░░░░░]

   Pump: OFF / ON (5s)
   ```
2. Update display every 2 seconds:
   - WiFi status (Connected/Disconnected/Setup)
   - IP address (or "N/A")
   - Moisture reading + percentage bar
   - Pump status (OFF or countdown)
3. Use M5Unified LCD functions:
   - `M5.Display.fillScreen()` to clear
   - `M5.Display.setCursor()` and `M5.Display.println()` for text
   - Use different colors for status (green=OK, red=error, yellow=setup)

**Validation**: Display updates correctly, shows pump countdown during activation

---

### Phase 5: OTA Updates
**Goal**: Enable wireless firmware updates

**Steps**:
1. Include ArduinoOTA library
2. Initialize OTA after WiFi connects:
   - Set hostname: "gardener-esp32"
   - Set no password (private network)
   - Configure callbacks: onStart, onEnd, onProgress, onError
3. Call `ArduinoOTA.handle()` in main loop
4. Display "OTA Update..." message during updates

**Validation**: Can see device in Arduino IDE network ports, upload firmware wirelessly

---

### Phase 6: Final Polish
**Goal**: Error handling and user experience improvements

**Steps**:
1. Add watchdog timer to auto-restart on hangs
2. Add HTTP CORS headers (allow FastAPI to call from any origin)
3. Improve error messages on display:
   - "ADC Read Failed" if sensor disconnected
   - "WiFi Failed - Check Config" if can't connect
4. Add `/status` endpoint for health checks:
   - Return: `{"uptime": N, "wifi_rssi": -60, "free_heap": 100000}`
5. Test edge cases:
   - Sensor disconnected (ADC reads 0 or 4095)
   - Pump called while already running (reject with 409 Conflict)
   - Very long JSON payloads (reject with 413 Payload Too Large)

**Validation**: System handles errors gracefully, doesn't crash

---

## Code Structure

### `config.h` (30 lines)
```cpp
// Pin definitions
#define PIN_MOISTURE_SENSOR 10  // GPIO10 - ADC1_CH9
#define PIN_RELAY_PUMP 7        // GPIO7 - Digital out

// Constants
#define ADC_RESOLUTION 12       // 12-bit ADC (0-4095)
#define PUMP_MAX_SECONDS 30     // Safety limit
#define WIFI_AP_NAME "GardenerSetup"
#define OTA_HOSTNAME "gardener-esp32"
#define HTTP_PORT 80
```

### `gardener-controller.ino` (~250 lines)
```cpp
// Includes (M5Unified, WiFiManager, ESPAsyncWebServer, ArduinoOTA, ArduinoJson)
// Global variables (server, pumpActive, pumpEndTime, lastMoistureReading)
// setup() - initialize hardware, WiFi, HTTP server, OTA
// loop() - handle OTA, update display, check pump timeout
// HTTP handlers (handleGetMoisture, handlePostPump)
// Helper functions (readMoisture, activatePump, updateDisplay)
```

**Key Functions**:
- `setup()`: Initialize M5, WiFi, server, OTA (runs once)
- `loop()`: Update display, handle OTA, check pump timer (runs continuously)
- `readMoisture()`: Read GPIO10 ADC, return 0-4095 value
- `activatePump(int seconds)`: Set GPIO7 HIGH, schedule turn-off
- `updateDisplay()`: Refresh screen with current status
- `handleGetMoisture(AsyncWebServerRequest *request)`: `/moisture` endpoint
- `handlePostPump(AsyncWebServerRequest *request)`: `/pump` endpoint

## Libraries Required

Install via Arduino Library Manager:
- **M5Unified** (v0.1.0+) - Hardware abstraction for M5Stack
- **WiFiManager** (v2.0.0+) - Captive portal WiFi configuration
- **ESPAsyncWebServer** - Async HTTP server
- **AsyncTCP** - Dependency for ESPAsyncWebServer
- **ArduinoJson** (v6.x) - JSON serialization/deserialization
- **ArduinoOTA** - Over-the-air updates (included with ESP32 core)

## Testing Strategy

### Unit Testing (manual)
1. **ADC Reading**: Connect sensor, verify values change when moisture changes
2. **Relay Control**: Connect LED to GPIO7, verify it turns on/off
3. **Safety Limit**: Try `POST /pump {"seconds": 60}`, verify it's rejected

### Integration Testing
1. **End-to-End**: FastAPI → ESP32 → Physical pump → Measure water dispensed
2. **WiFi Recovery**: Unplug router, verify ESP32 reconnects when back online
3. **OTA Update**: Upload new firmware via WiFi, verify it works

### Calibration
1. **Moisture Sensor**: Test in dry soil (note value) and wet soil (note value)
2. **Pump Rate**: Run pump for 10 seconds, measure ML dispensed, calculate rate

## Safety Considerations

1. **Pump Timeout**: 30-second hard limit in ESP32 firmware
2. **Watchdog Timer**: Auto-restart if firmware hangs
3. **Display Feedback**: Always show pump status to user
4. **No Authentication**: Acceptable for private network hobby project
5. **Daily Limit**: Enforced by FastAPI (500ml/24h), not ESP32

## Estimated Effort

- **Phase 1** (Basic Hardware): 30 minutes
- **Phase 2** (HTTP Server): 45 minutes
- **Phase 3** (WiFi Management): 30 minutes
- **Phase 4** (Display UI): 30 minutes
- **Phase 5** (OTA Updates): 15 minutes
- **Phase 6** (Final Polish): 30 minutes

**Total**: ~3 hours for ESP32 firmware

## Next Steps After ESP32 Completion

1. Update FastAPI tools to call ESP32 HTTP API
2. Deploy to Raspberry Pi
3. Calibrate pump and moisture sensor
4. Test with real plant
5. Let Claude keep the plant alive!
