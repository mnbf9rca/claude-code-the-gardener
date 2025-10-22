# ESP32 Plant Controller

ESP32-S3 firmware for M5Stack CoreS3-SE that provides HTTP REST API to control soil moisture sensor and water pump relay.

## Hardware Requirements

- **M5Stack CoreS3-SE** (ESP32-S3 development board with 2.0" display)
- **Capacitive Soil Moisture Sensor** (analog output, 3.3V compatible)
- **5V Relay Module** (for controlling peristaltic pump)
- **Peristaltic Pump** (5-6V DC)
- **Wiring supplies**: Dupont wires or soldering kit for M5-Bus connections

## Wiring Diagram

### M5-Bus Pin Connections

The M5Stack CoreS3-SE has a 30-pin M5-Bus connector on the bottom. You'll need to access these pins:

| Component | Connect To | M5-Bus Pin | ESP32 GPIO | Notes |
|-----------|------------|------------|------------|-------|
| Moisture Sensor Signal | Pin 2 (right side) | GPIO10 | ADC1_CH9 | Analog input |
| Moisture Sensor VCC | 3.3V on bus | Pin 12 (right) | 3V3 | Power |
| Moisture Sensor GND | Any GND pin | Pins 1,3,5 (left) | GND | Ground |
| Relay Control | Pin 22 (right side) | GPIO7 | Digital out | 3.3V logic |
| Relay VCC | 5V on bus | Pin 28 (right) | 5V | Power |
| Relay GND | Any GND pin | Pins 1,3,5 (left) | GND | Ground |

**Important:** GPIO10 and GPIO7 are on the **M5-Bus connector**, not the Grove port. You'll need to solder wires or use a breakout board to access these pins.

### Connection Notes

1. **Moisture Sensor**:
   - Analog output connects to GPIO10 (ADC)
   - Operates at 3.3V
   - Returns 0-4095 reading (12-bit ADC)
   - Lower values = drier soil, higher values = wetter soil

2. **Relay Module**:
   - Control signal from GPIO7 (3.3V logic)
   - Most 5V relay modules work with 3.3V logic
   - Relay switches the pump's power circuit
   - **Never connect pump directly to ESP32!**

3. **Pump Power**:
   - Pump should have separate 5V power supply
   - Relay switches the pump's ground or power line
   - Keep pump power separate from ESP32 power

## Software Setup

### Step 1: Install Arduino IDE

Download and install **Arduino IDE 2.x** or later from https://www.arduino.cc/en/software

### Step 2: Add M5Stack Board Support

1. Open **Arduino IDE → Preferences** (or **Arduino IDE → Settings** on some versions)
2. In "Additional Board Manager URLs", add:
   ```
   https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/arduino/package_m5stack_index.json
   ```
3. Go to **Tools → Board → Boards Manager**
4. Search for "**M5Stack**"
5. Click **Install** on "M5Stack by M5Stack official"
6. After installation, select board: **Tools → Board → M5Stack → M5Stack-CoreS3**

### Step 3: Install Required Libraries

Open **Tools → Manage Libraries** (or **Sketch → Include Library → Manage Libraries**)

Search for and install each of these libraries:

| Library | Version | Notes |
|---------|---------|-------|
| **M5Unified** | 0.1.0+ | M5Stack hardware abstraction |
| **WiFiManager** | 2.0.0+ | By tzapu - WiFi configuration portal |
| **ESPAsyncWebServer** | Latest | Async HTTP web server |
| **AsyncTCP** | Latest | Required for ESPAsyncWebServer |
| **ArduinoJson** | **6.x only** | ⚠️ **Must be <7.0** - see below |

**⚠️ Important: ArduinoJson Version**

You **must install ArduinoJson 6.x** (e.g., 6.21.5), **NOT version 7.x**.

**Why?** ArduinoJson 7.0 introduced breaking API changes:
- Removed `StaticJsonDocument` (replaced with `JsonDocument`)
- Changed memory allocation model
- Our code uses `StaticJsonDocument<256>` which only exists in v6.x

If you accidentally install v7.x, the code will fail to compile with errors like:
```
error: 'StaticJsonDocument' was not declared in this scope
```

To install the correct version:
1. In Library Manager, search "ArduinoJson"
2. Click the version dropdown
3. Select any **6.x version** (e.g., 6.21.5)
4. Click Install

### Step 4: Verify Installation

Open `esp32/gardener-controller/gardener-controller.ino` and click **Verify** (checkmark icon). If it compiles successfully, all libraries are installed correctly.

**Note:** See `libraries.json` in the project folder for the complete list of dependencies

### Step 5: Flash Firmware

1. Open `esp32/gardener-controller/gardener-controller.ino` in Arduino IDE
2. Ensure board is selected: **Tools → Board → M5Stack → M5Stack-CoreS3**
3. Connect M5Stack CoreS3-SE via USB-C cable
4. Select port: **Tools → Port → (your USB port)**
5. Click **Upload** button (right arrow icon)

### First Boot - WiFi Configuration

On first boot, the device creates a WiFi access point:

1. LED/display shows "WiFi Setup Mode"
2. Connect to WiFi network: **"GardenerSetup"**
3. Browser should auto-open to configuration portal (if not, go to http://192.168.4.1)
4. Select your WiFi network and enter password
5. Device saves credentials and connects
6. Display shows IP address once connected

**Note:** WiFi credentials are stored in flash memory. To reset, hold the reset button during boot (or use the WiFiManager reset function).

### Over-the-Air (OTA) Updates

After initial flashing, you can update firmware wirelessly:

1. Ensure ESP32 and computer are on same network
2. Arduino IDE → Tools → Port → Select network port (shows IP address)
3. Click Upload
4. Enter OTA password if prompted (default: none in this firmware)

## HTTP API Reference

Base URL: `http://<ESP32_IP_ADDRESS>/`

### GET /moisture

Read current soil moisture sensor value.

**Response:**
```json
{
  "value": 2047,
  "timestamp": "2025-01-23T14:30:00Z",
  "status": "ok"
}
```

- `value`: Raw ADC reading (0-4095)
  - 0 = 0V (very dry)
  - 4095 = 3.3V (very wet)
  - Typical range: 1500 (dry) to 3000 (wet)
- `timestamp`: ISO8601 UTC timestamp
- `status`: "ok" or "error"

### POST /pump

Activate water pump for specified duration.

**Request:**
```json
{
  "seconds": 5
}
```

**Response:**
```json
{
  "success": true,
  "duration": 5,
  "timestamp": "2025-01-23T14:30:05Z"
}
```

**Safety Limits:**
- Minimum: 1 second
- Maximum: 30 seconds per request
- Requests over 30 seconds are rejected with error

**Error Response:**
```json
{
  "success": false,
  "error": "Duration exceeds safety limit (max 30s)"
}
```

## Display Information

The 2.0" LCD display shows:

```
╔════════════════════════════╗
║ WiFi: Connected            ║
║ IP: 192.168.1.100          ║
║                            ║
║ Moisture: 2047             ║
║ Status: ▓▓▓▓▓░░░░░ (54%)   ║
║                            ║
║ Pump: OFF                  ║
║                            ║
╚════════════════════════════╝
```

- **WiFi Status**: Connected / Disconnected / Setup Mode
- **IP Address**: Current network address
- **Moisture**: Live ADC reading (updates every 2 seconds)
- **Status Bar**: Visual moisture level indicator
- **Pump**: OFF / ON (countdown in seconds when active)

## Calibration

### Moisture Sensor Calibration

1. Read sensor in **dry soil**: `GET /moisture` → note value (e.g., 1500)
2. Water the soil thoroughly
3. Read sensor in **wet soil**: `GET /moisture` → note value (e.g., 3000)
4. Update these values in your FastAPI `.env` configuration:
   ```
   MOISTURE_DRY=1500
   MOISTURE_WET=3000
   ```

### Pump Calibration

The pump dispenses water at a certain rate (ML per second). To calibrate:

1. Place pump tube in measuring container
2. Run pump for exactly 10 seconds:
   ```bash
   curl -X POST http://<ESP32_IP>/pump -H "Content-Type: application/json" -d '{"seconds": 10}'
   ```
3. Measure the water dispensed (e.g., 35ml)
4. Calculate rate: `35ml / 10s = 3.5 ml/s`
5. Update `.env` in FastAPI app:
   ```
   PUMP_ML_PER_SECOND=3.5
   ```

## Troubleshooting

### WiFi Won't Connect
- Hold reset button during boot to force WiFi setup mode
- Check WiFi network is 2.4GHz (ESP32 doesn't support 5GHz)
- Ensure SSID and password are correct

### Moisture Reading Always 0 or 4095
- Check sensor wiring to GPIO10
- Verify sensor is powered (3.3V)
- Test sensor with multimeter (should output ~1-3V analog signal)

### Pump Won't Activate
- Check GPIO7 connection to relay
- Verify relay has power (5V)
- Test relay manually (connect control pin to 3.3V directly)
- Check relay module is normally-open (NO) type

### Display Shows Garbage
- M5Unified initialization failed
- Try: Power cycle the device
- Verify M5Unified library is installed correctly

### OTA Updates Fail
- Ensure device and computer on same network
- Check firewall isn't blocking port 3232
- Try uploading via USB if OTA continues to fail

## Development

See [`implementation_plan.md`](implementation_plan.md) for detailed development steps and architecture notes.

## Safety Features

1. **Pump Timeout**: Maximum 30 seconds per activation (hardware enforced)
2. **Watchdog Timer**: Auto-restart if firmware hangs
3. **Brownout Detection**: Prevents corruption during power drops
4. **Display Feedback**: Always shows pump status to prevent surprises

## Power Consumption

- **Idle**: ~100mA (WiFi connected, display on)
- **Pump Active**: Depends on pump (typically 200-500mA for peristaltic pump)
- **WiFi Disconnected**: ~80mA

**Note:** CoreS3-SE does not include a battery. Use USB-C power adapter (5V 2A recommended).

## License

See main project README for license information.
