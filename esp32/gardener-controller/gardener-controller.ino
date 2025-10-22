/**
 * Gardener Controller - ESP32-S3 Plant Care System
 *
 * HTTP REST API server for soil moisture sensing and water pump control
 * Designed for M5Stack CoreS3-SE
 *
 * API Endpoints:
 *   GET  /moisture - Read soil moisture sensor
 *   POST /pump     - Activate water pump for N seconds
 *   GET  /status   - System health check
 */

#include <M5Unified.h>
#include <WiFi.h>
#include <WiFiManager.h>
#include <ESPAsyncWebServer.h>
#include <ArduinoOTA.h>
#include <ArduinoJson.h>
#include <ESPmDNS.h>
#include <time.h>
#include "config.h"

// ============================================================================
// Global Objects
// ============================================================================

AsyncWebServer server(HTTP_PORT);
WiFiManager wifiManager;

// ============================================================================
// State Variables
// ============================================================================

// Pump control
bool pumpActive = false;
time_t pumpStartTime = 0;  // Unix timestamp from RTC
int pumpDurationSeconds = 0;

// Display update
unsigned long lastDisplayUpdate = 0;

// Moisture reading cache
int lastMoistureReading = 0;
unsigned long lastMoistureReadTime = 0;

// WiFi connection tracking
unsigned long lastWiFiCheck = 0;
bool wifiConnected = false;

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Read moisture sensor ADC value
 * Returns: 0-4095 (12-bit ADC)
 */
int readMoisture() {
  // Read analog value from GPIO10
  int reading = analogRead(PIN_MOISTURE_SENSOR);

  #if DEBUG_SERIAL
  Serial.printf("ADC Reading: %d\n", reading);
  #endif

  return reading;
}

/**
 * Activate water pump for specified duration
 * Returns: true if activated, false if invalid duration or pump already active
 */
bool activatePump(int seconds) {
  // Validate duration
  if (seconds < PUMP_MIN_SECONDS || seconds > PUMP_MAX_SECONDS) {
    #if DEBUG_SERIAL
    Serial.printf("Invalid pump duration: %d (must be %d-%d)\n",
                  seconds, PUMP_MIN_SECONDS, PUMP_MAX_SECONDS);
    #endif
    return false;
  }

  // Check if pump already active
  if (pumpActive) {
    #if DEBUG_SERIAL
    Serial.println("Pump already active");
    #endif
    return false;
  }

  // Activate pump
  digitalWrite(PIN_RELAY_PUMP, HIGH);
  pumpActive = true;

  // Record start time (Unix epoch seconds - avoids millis() wraparound)
  time(&pumpStartTime);
  pumpDurationSeconds = seconds;

  #if DEBUG_SERIAL
  Serial.printf("Pump activated for %d seconds\n", seconds);
  #endif

  return true;
}

/**
 * Deactivate water pump
 */
void deactivatePump() {
  if (pumpActive) {
    digitalWrite(PIN_RELAY_PUMP, LOW);
    pumpActive = false;

    #if DEBUG_SERIAL
    Serial.println("Pump deactivated");
    #endif
  }
}

/**
 * Check if pump should be turned off
 * Uses system time (NTP-synced) to avoid millis() wraparound issues
 */
void checkPumpTimeout() {
  if (pumpActive) {
    time_t now;
    time(&now);

    time_t elapsed = now - pumpStartTime;
    if (elapsed >= pumpDurationSeconds) {
      deactivatePump();
    }
  }
}

/**
 * Calculate moisture percentage (0-100%)
 * Based on calibrated dry/wet values
 */
int getMoisturePercent(int rawValue) {
  if (rawValue <= MOISTURE_DRY_VALUE) return 0;
  if (rawValue >= MOISTURE_WET_VALUE) return 100;

  int range = MOISTURE_WET_VALUE - MOISTURE_DRY_VALUE;
  int adjusted = rawValue - MOISTURE_DRY_VALUE;
  return (adjusted * 100) / range;
}

/**
 * Get ISO8601 formatted timestamp (UTC) from RTC
 */
String getTimestamp() {
  auto dt = M5.Rtc.getDateTime();

  char buffer[32];
  sprintf(buffer, "%04d-%02d-%02dT%02d:%02d:%02dZ",
          dt.date.year, dt.date.month, dt.date.date,
          dt.time.hours, dt.time.minutes, dt.time.seconds);
  return String(buffer);
}

/**
 * Update display with current status
 */
void updateDisplay() {
  M5.Display.fillScreen(COLOR_BACKGROUND);
  M5.Display.setTextColor(COLOR_TEXT);
  M5.Display.setTextSize(TEXT_SIZE_MEDIUM);
  M5.Display.setCursor(10, 10);

  // WiFi status
  if (WiFi.status() == WL_CONNECTED) {
    M5.Display.setTextColor(COLOR_OK);
    M5.Display.println("WiFi: Connected");
    M5.Display.setTextColor(COLOR_INFO);
    M5.Display.printf("IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    M5.Display.setTextColor(COLOR_ERROR);
    M5.Display.println("WiFi: Disconnected");
  }

  M5.Display.println();

  // Moisture sensor
  M5.Display.setTextColor(COLOR_TEXT);
  int moisture = lastMoistureReading;
  int percent = getMoisturePercent(moisture);
  M5.Display.printf("Moisture: %d\n", moisture);

  // Moisture bar
  int barWidth = 200;
  int barHeight = 20;
  int barX = 10;
  int barY = M5.Display.getCursorY() + 5;

  M5.Display.drawRect(barX, barY, barWidth, barHeight, COLOR_TEXT);
  int fillWidth = (barWidth * percent) / 100;
  M5.Display.fillRect(barX + 2, barY + 2, fillWidth - 4, barHeight - 4, COLOR_OK);

  M5.Display.setCursor(barX + barWidth + 10, barY + 5);
  M5.Display.printf("%d%%", percent);

  M5.Display.setCursor(10, barY + barHeight + 20);
  M5.Display.println();

  // Pump status
  if (pumpActive) {
    time_t now;
    time(&now);

    time_t elapsed = now - pumpStartTime;
    int remaining = pumpDurationSeconds - elapsed;
    if (remaining < 0) remaining = 0;
    M5.Display.setTextColor(COLOR_WARNING);
    M5.Display.printf("Pump: ON (%ds)\n", remaining);
  } else {
    M5.Display.setTextColor(COLOR_TEXT);
    M5.Display.println("Pump: OFF");
  }
}

// ============================================================================
// HTTP Request Handlers
// ============================================================================

/**
 * GET /moisture - Read moisture sensor
 */
void handleGetMoisture(AsyncWebServerRequest *request) {
  // Read sensor
  int moisture = readMoisture();
  lastMoistureReading = moisture;
  lastMoistureReadTime = millis();

  // Build JSON response
  StaticJsonDocument<JSON_BUFFER_SIZE> doc;
  doc["value"] = moisture;
  doc["timestamp"] = getTimestamp();
  doc["status"] = "ok";

  String response;
  serializeJson(doc, response);

  request->send(200, "application/json", response);
}

/**
 * POST /pump - Activate water pump
 * Body: {"seconds": N}
 */
void handlePostPumpBody(AsyncWebServerRequest *request, uint8_t *data, size_t len, size_t index, size_t total) {
  // Parse JSON body
  StaticJsonDocument<JSON_BUFFER_SIZE> doc;
  DeserializationError error = deserializeJson(doc, (char*)data);

  if (error) {
    StaticJsonDocument<JSON_BUFFER_SIZE> errorDoc;
    errorDoc["success"] = false;
    errorDoc["error"] = "Invalid JSON";

    String response;
    serializeJson(errorDoc, response);
    request->send(400, "application/json", response);
    return;
  }

  // Validate seconds parameter
  if (!doc.containsKey("seconds")) {
    StaticJsonDocument<JSON_BUFFER_SIZE> errorDoc;
    errorDoc["success"] = false;
    errorDoc["error"] = "Missing 'seconds' parameter";

    String response;
    serializeJson(errorDoc, response);
    request->send(400, "application/json", response);
    return;
  }

  int seconds = doc["seconds"];

  // Check if pump already active
  if (pumpActive) {
    StaticJsonDocument<JSON_BUFFER_SIZE> errorDoc;
    errorDoc["success"] = false;
    errorDoc["error"] = "Pump already active";

    String response;
    serializeJson(errorDoc, response);
    request->send(409, "application/json", response);
    return;
  }

  // Validate duration
  if (seconds < PUMP_MIN_SECONDS || seconds > PUMP_MAX_SECONDS) {
    StaticJsonDocument<JSON_BUFFER_SIZE> errorDoc;
    errorDoc["success"] = false;
    errorDoc["error"] = String("Duration must be ") + PUMP_MIN_SECONDS +
                        "-" + PUMP_MAX_SECONDS + " seconds";

    String response;
    serializeJson(errorDoc, response);
    request->send(400, "application/json", response);
    return;
  }

  // Activate pump
  bool activated = activatePump(seconds);

  if (activated) {
    StaticJsonDocument<JSON_BUFFER_SIZE> responseDoc;
    responseDoc["success"] = true;
    responseDoc["duration"] = seconds;
    responseDoc["timestamp"] = getTimestamp();

    String response;
    serializeJson(responseDoc, response);
    request->send(200, "application/json", response);
  } else {
    StaticJsonDocument<JSON_BUFFER_SIZE> errorDoc;
    errorDoc["success"] = false;
    errorDoc["error"] = "Failed to activate pump";

    String response;
    serializeJson(errorDoc, response);
    request->send(500, "application/json", response);
  }
}

/**
 * GET /status - System health check
 */
void handleGetStatus(AsyncWebServerRequest *request) {
  StaticJsonDocument<JSON_BUFFER_SIZE> doc;
  doc["rtc_time"] = getTimestamp();
  doc["wifi_connected"] = (WiFi.status() == WL_CONNECTED);
  doc["wifi_rssi"] = WiFi.RSSI();
  doc["free_heap"] = ESP.getFreeHeap();
  doc["pump_active"] = pumpActive;
  doc["moisture"] = lastMoistureReading;

  String response;
  serializeJson(doc, response);

  request->send(200, "application/json", response);
}

/**
 * 404 Not Found handler
 */
void handleNotFound(AsyncWebServerRequest *request) {
  StaticJsonDocument<JSON_BUFFER_SIZE> doc;
  doc["error"] = "Not Found";
  doc["path"] = request->url();

  String response;
  serializeJson(doc, response);

  request->send(404, "application/json", response);
}

// ============================================================================
// Setup Functions
// ============================================================================

void setupSerial() {
  #if DEBUG_SERIAL
  Serial.begin(SERIAL_BAUD);
  Serial.println("\n\n=================================");
  Serial.println("Gardener Controller Starting...");
  Serial.println("=================================");
  #endif
}

void setupM5() {
  auto cfg = M5.config();
  M5.begin(cfg);

  M5.Display.fillScreen(COLOR_BACKGROUND);
  M5.Display.setTextColor(COLOR_INFO);
  M5.Display.setTextSize(TEXT_SIZE_MEDIUM);
  M5.Display.setCursor(10, 10);
  M5.Display.println("Gardener Controller");
  M5.Display.println("Initializing...");

  #if DEBUG_SERIAL
  Serial.println("M5Unified initialized");
  #endif
}

void setupGPIO() {
  // Configure moisture sensor pin as analog input
  pinMode(PIN_MOISTURE_SENSOR, INPUT);
  analogReadResolution(ADC_RESOLUTION);

  // Configure relay pin as digital output
  pinMode(PIN_RELAY_PUMP, OUTPUT);
  digitalWrite(PIN_RELAY_PUMP, LOW);  // Ensure pump is off

  #if DEBUG_SERIAL
  Serial.printf("GPIO configured: Moisture=%d, Relay=%d\n",
                PIN_MOISTURE_SENSOR, PIN_RELAY_PUMP);
  #endif
}

void setupWiFi() {
  M5.Display.fillScreen(COLOR_BACKGROUND);
  M5.Display.setCursor(10, 10);
  M5.Display.setTextColor(COLOR_WARNING);
  M5.Display.setTextSize(TEXT_SIZE_SMALL);
  M5.Display.println("WiFi Setup Mode");
  M5.Display.println();
  M5.Display.setTextColor(COLOR_INFO);
  M5.Display.println("1. Connect to WiFi:");
  M5.Display.setTextColor(COLOR_TEXT);
  M5.Display.printf("   %s\n", WIFI_AP_NAME);
  M5.Display.println();
  M5.Display.setTextColor(COLOR_INFO);
  M5.Display.println("2. Browser opens auto");
  M5.Display.println("   Or go to:");
  M5.Display.setTextColor(COLOR_TEXT);
  M5.Display.println("   192.168.4.1");
  M5.Display.println();
  M5.Display.setTextColor(COLOR_INFO);
  M5.Display.println("3. Select your WiFi");
  M5.Display.println("   and enter password");
  M5.Display.println();
  M5.Display.setTextColor(COLOR_WARNING);
  M5.Display.println("Waiting (3 min)...");
  M5.Display.setTextSize(TEXT_SIZE_MEDIUM);

  // Configure WiFiManager
  wifiManager.setConfigPortalTimeout(180);  // 3 minute timeout

  // Try to connect
  #if DEBUG_SERIAL
  Serial.println("Connecting to WiFi...");
  #endif

  if (!wifiManager.autoConnect(WIFI_AP_NAME)) {
    #if DEBUG_SERIAL
    Serial.println("Failed to connect, restarting...");
    #endif

    M5.Display.setTextColor(COLOR_ERROR);
    M5.Display.println("WiFi Failed!");
    M5.Display.println("Restarting...");
    delay(3000);
    ESP.restart();
  }

  wifiConnected = true;

  M5.Display.setTextColor(COLOR_OK);
  M5.Display.println("WiFi Connected!");
  M5.Display.printf("IP: %s\n", WiFi.localIP().toString().c_str());

  #if DEBUG_SERIAL
  Serial.println("WiFi connected");
  Serial.printf("IP: %s\n", WiFi.localIP().toString().c_str());
  Serial.printf("RSSI: %d dBm\n", WiFi.RSSI());
  #endif

  delay(2000);
}

void setupNTP() {
  #if DEBUG_SERIAL
  Serial.println("Syncing RTC with NTP...");
  #endif

  // Configure NTP (UTC timezone, no daylight saving)
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");

  // Wait for time sync (max 10 seconds)
  int retries = 0;
  time_t now = 0;
  struct tm timeinfo = { 0 };

  while (retries < 10) {
    time(&now);
    localtime_r(&now, &timeinfo);
    if (timeinfo.tm_year > (2020 - 1900)) {
      // Time is valid (year > 2020)
      break;
    }
    delay(1000);
    retries++;
  }

  if (timeinfo.tm_year > (2020 - 1900)) {
    // NTP sync successful - update RTC
    M5.Rtc.setDateTime( {
      { timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday },
      { timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec }
    });

    #if DEBUG_SERIAL
    Serial.printf("RTC synced: %04d-%02d-%02d %02d:%02d:%02d UTC\n",
                  timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday,
                  timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
    #endif
  } else {
    #if DEBUG_SERIAL
    Serial.println("NTP sync failed - using RTC current time");
    #endif
  }
}

void setupMDNS() {
  if (MDNS.begin(OTA_HOSTNAME)) {
    MDNS.addService("http", "tcp", HTTP_PORT);
    #if DEBUG_SERIAL
    Serial.printf("mDNS started: %s.local\n", OTA_HOSTNAME);
    #endif
  }
}

void setupOTA() {
  ArduinoOTA.setHostname(OTA_HOSTNAME);

  ArduinoOTA.onStart([]() {
    String type = (ArduinoOTA.getCommand() == U_FLASH) ? "sketch" : "filesystem";
    #if DEBUG_SERIAL
    Serial.println("OTA update started: " + type);
    #endif

    M5.Display.fillScreen(COLOR_BACKGROUND);
    M5.Display.setCursor(10, 10);
    M5.Display.setTextColor(COLOR_INFO);
    M5.Display.println("OTA Update...");
  });

  ArduinoOTA.onEnd([]() {
    #if DEBUG_SERIAL
    Serial.println("\nOTA update complete");
    #endif

    M5.Display.setTextColor(COLOR_OK);
    M5.Display.println("Complete!");
  });

  ArduinoOTA.onError([](ota_error_t error) {
    #if DEBUG_SERIAL
    Serial.printf("OTA Error[%u]: ", error);
    if (error == OTA_AUTH_ERROR) Serial.println("Auth Failed");
    else if (error == OTA_BEGIN_ERROR) Serial.println("Begin Failed");
    else if (error == OTA_CONNECT_ERROR) Serial.println("Connect Failed");
    else if (error == OTA_RECEIVE_ERROR) Serial.println("Receive Failed");
    else if (error == OTA_END_ERROR) Serial.println("End Failed");
    #endif

    M5.Display.setTextColor(COLOR_ERROR);
    M5.Display.println("OTA Error!");
  });

  ArduinoOTA.begin();

  #if DEBUG_SERIAL
  Serial.println("OTA ready");
  #endif
}

void setupHTTPServer() {
  // Enable CORS for all origins
  DefaultHeaders::Instance().addHeader("Access-Control-Allow-Origin", "*");
  DefaultHeaders::Instance().addHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  DefaultHeaders::Instance().addHeader("Access-Control-Allow-Headers", "Content-Type");

  // Register endpoints
  server.on("/moisture", HTTP_GET, handleGetMoisture);

  // POST /pump with JSON body handler
  // Note: Third parameter must be an empty lambda (cannot be NULL)
  server.on("/pump", HTTP_POST,
    [](AsyncWebServerRequest *request){},
    NULL,
    handlePostPumpBody);

  server.on("/status", HTTP_GET, handleGetStatus);
  server.onNotFound(handleNotFound);

  // Start server
  server.begin();

  #if DEBUG_SERIAL
  Serial.printf("HTTP server started on port %d\n", HTTP_PORT);
  #endif
}

// ============================================================================
// Arduino Setup & Loop
// ============================================================================

void setup() {
  setupSerial();
  setupM5();
  setupGPIO();
  setupWiFi();
  setupNTP();   // Sync RTC with NTP after WiFi connects
  setupMDNS();
  setupOTA();
  setupHTTPServer();

  // Initial moisture reading
  lastMoistureReading = readMoisture();

  M5.Display.fillScreen(COLOR_BACKGROUND);
  M5.Display.setCursor(10, 10);
  M5.Display.setTextColor(COLOR_OK);
  M5.Display.println("Ready!");
  delay(1000);

  #if DEBUG_SERIAL
  Serial.println("Setup complete - system ready");
  Serial.println("=================================\n");
  #endif
}

void loop() {
  // Handle OTA updates
  ArduinoOTA.handle();

  // Check pump timeout
  checkPumpTimeout();

  // Update display periodically
  unsigned long now = millis();
  if (now - lastDisplayUpdate >= DISPLAY_UPDATE_INTERVAL) {
    lastMoistureReading = readMoisture();
    updateDisplay();
    lastDisplayUpdate = now;
  }

  // Check WiFi connection periodically
  if (now - lastWiFiCheck >= WIFI_RECONNECT_INTERVAL) {
    if (WiFi.status() != WL_CONNECTED) {
      #if DEBUG_SERIAL
      Serial.println("WiFi disconnected, attempting reconnect...");
      #endif
      WiFi.reconnect();
    }
    lastWiFiCheck = now;
  }

  // Small delay to prevent watchdog timeout
  delay(10);
}
