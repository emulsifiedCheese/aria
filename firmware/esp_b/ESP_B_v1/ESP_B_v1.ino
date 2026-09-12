#include <ESP8266WiFi.h>
#include <WiFiUdp.h>
#include <math.h>
#include <string.h>

//wifi, laptop config
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
//gram IPAddress LAPTOP_IP(172, 20, 10, 11);
IPAddress LAPTOP_IP(172, 20, 10, 2);
constexpr uint16_t LAPTOP_UDP_PORT = 5005;
constexpr uint16_t ESP_LOCAL_UDP_PORT = 4211;

uint32_t bootId = 0;

bool hasConnectedBefore = false;
bool wifiWasConnected = false;
bool udpReady = false;

uint32_t wifiReconnectCount = 0;
uint8_t wifiReconnectAttemptCount = 0;
uint8_t wifiRadioResetCount = 0;

unsigned long wifiDisconnectedAt = 0;
unsigned long lastWifiOutageMs = 0;

//esp b identity
const char* FIRMWARE_VERSION = "1.0.0";
const char* SENSOR_CONFIG = "B_PIR_MIC";
const char* NODE_ID = "ESP-B";
const char* ZONE_ID = "B";

//pin config
constexpr uint8_t PIR_PIN = D1;
constexpr uint8_t MICROPHONE_PIN = A0;

//timing config
//send one json packet/second
constexpr unsigned long SEND_INTERVAL_MS = 1000;

//allow each explicit wifi connection attempt time to complete
constexpr unsigned long WIFI_RETRY_INTERVAL_MS = 15000;
constexpr uint8_t WIFI_RADIO_RESET_AFTER_ATTEMPTS = 3;
constexpr uint8_t WIFI_BOARD_RESTART_AFTER_RADIO_RESETS = 2;
constexpr unsigned long WIFI_RADIO_OFF_MS = 1000;

//mic feature sampling window
constexpr unsigned long AUDIO_SAMPLE_WINDOW_MS = 900;

//max stored mic samples
constexpr size_t MAX_AUDIO_SAMPLES = 3000;

//keep recent activity true for 10sec after pir motion
constexpr unsigned long PIR_HOLD_MS = 10000;

constexpr unsigned long HEAP_LOG_INTERVAL_MS = 60000;
unsigned long lastHeapLogTime = 0;
uint32_t minimumFreeHeap = 0xFFFFFFFFUL;

WiFiUDP udp;
unsigned long lastSendTime = 0;
unsigned long lastWiFiRetryTime = 0;
unsigned long lastPirMotionTime = 0;
uint32_t sequenceNumber = 0;
uint16_t audioSamples[MAX_AUDIO_SAMPLES];

//sensor data structure
struct SensorData {
  bool pirMotion;
  bool pirRecentActivity;
  uint16_t audioPeakToPeak;
  float audioActivity;
  float audioRms;
};

bool startUdp() {
  udp.stop();

  if (udp.begin(ESP_LOCAL_UDP_PORT)) {
    udpReady = true;

    Serial.print("UDP listener started on local port ");
    Serial.println(ESP_LOCAL_UDP_PORT);

    return true;
  }

  udpReady = false;
  Serial.println("WARNING: UDP listener failed to start");

  return false;
}

//wifi
void connectToWiFi() {
  Serial.println();
  Serial.print("Connecting to hotspot: ");
  Serial.println(WIFI_SSID);

  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.hostname("aria-esp-b");
  WiFi.setAutoReconnect(true);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  const unsigned long startTime = millis();
  constexpr unsigned long timeoutMs = 20000;

  while (
    WiFi.status() != WL_CONNECTED &&
    millis() - startTime < timeoutMs
  ) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    wifiWasConnected = true;
    hasConnectedBefore = true;

    Serial.println("Wi-Fi connected");

    Serial.print("Local IP: ");
    Serial.println(WiFi.localIP());

    Serial.print("Laptop IP: ");
    Serial.println(LAPTOP_IP);

    Serial.print("Laptop UDP port: ");
    Serial.println(LAPTOP_UDP_PORT);

    Serial.print("Local UDP port: ");
    Serial.println(ESP_LOCAL_UDP_PORT);

    startUdp();
  } else {
    wifiWasConnected = false;
    wifiDisconnectedAt = millis();

    Serial.println("Wi-Fi connection timed out");
    Serial.println("The node will retry automatically");
  }
}

void maintainWiFiConnection() {
  const bool currentlyConnected =
    WiFi.status() == WL_CONNECTED;

  if (currentlyConnected) {
    if (!wifiWasConnected) {
      const unsigned long now = millis();

      if (wifiDisconnectedAt > 0) {
        lastWifiOutageMs = now - wifiDisconnectedAt;
      }

      if (hasConnectedBefore) {
        wifiReconnectCount++;
      }

      hasConnectedBefore = true;
      wifiWasConnected = true;
      wifiReconnectAttemptCount = 0;
      wifiRadioResetCount = 0;

      Serial.println();
      Serial.println("Wi-Fi reconnected");

      Serial.print("New local IP: ");
      Serial.println(WiFi.localIP());

      Serial.print("Wi-Fi outage duration: ");
      Serial.print(lastWifiOutageMs);
      Serial.println(" ms");

      Serial.print("Wi-Fi reconnect count: ");
      Serial.println(wifiReconnectCount);

      startUdp();
    }

    return;
  }

  if (wifiWasConnected) {
    wifiWasConnected = false;
    udpReady = false;
    wifiDisconnectedAt = millis();

    Serial.println();
    Serial.println("WARNING: Wi-Fi connection lost");
  }

  const unsigned long now = millis();

  if (now - lastWiFiRetryTime < WIFI_RETRY_INTERVAL_MS) {
    return;
  }

  lastWiFiRetryTime = now;
  wifiReconnectAttemptCount++;

  Serial.print("Attempting Wi-Fi reconnection; status=");
  Serial.print(static_cast<int>(WiFi.status()));
  Serial.print(" attempt=");
  Serial.println(wifiReconnectAttemptCount);

  if (
    wifiReconnectAttemptCount >=
    WIFI_RADIO_RESET_AFTER_ATTEMPTS
  ) {
    Serial.println(
      "Resetting Wi-Fi radio after repeated connection failures");

    udp.stop();
    udpReady = false;

    wifiRadioResetCount++;

    if (
      wifiRadioResetCount >=
      WIFI_BOARD_RESTART_AFTER_RADIO_RESETS
    ) {
      Serial.println(
        "Wi-Fi recovery failed; restarting ESP-B automatically");
      Serial.flush();
      delay(100);
      ESP.restart();
      return;
    }

    // Fully clear and power-cycle the station interface. A longer off period
    // gives the ESP8266 radio stack time to reset before a fresh association.
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    delay(WIFI_RADIO_OFF_MS);
    WiFi.mode(WIFI_STA);
    WiFi.hostname("aria-esp-b");
    WiFi.setAutoReconnect(true);

    wifiReconnectAttemptCount = 0;
  }

  // Start a fresh credential-based association attempt. Calling reconnect()
  // alone can leave the station disconnected after an access point restart.
  // Persistence is disabled, so this does not rewrite credentials to flash.
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

//pir
void readPir(
  bool& motionDetected,
  bool& recentActivity) {
  motionDetected = digitalRead(PIR_PIN) == HIGH;

  const unsigned long now = millis();

  if (motionDetected) {
    lastPirMotionTime = now;
  }

  recentActivity =
    lastPirMotionTime > 0 && now - lastPirMotionTime < PIR_HOLD_MS;
}

//mic
void readMicrophoneFeatures(
  uint16_t& peakToPeak,
  float& activity,
  float& rms) {
  size_t sampleCount = 0;
  uint32_t sampleTotal = 0;

  uint16_t minimumValue = 1023;
  uint16_t maximumValue = 0;

  const unsigned long windowStart = millis();

  while (
    millis() - windowStart < AUDIO_SAMPLE_WINDOW_MS && sampleCount < MAX_AUDIO_SAMPLES) {
    const uint16_t sample = analogRead(MICROPHONE_PIN);

    audioSamples[sampleCount] = sample;
    sampleTotal += sample;

    if (sample < minimumValue) {
      minimumValue = sample;
    }

    if (sample > maximumValue) {
      maximumValue = sample;
    }

    sampleCount++;

    delayMicroseconds(200);
    yield();
  }

  if (sampleCount == 0) {
    peakToPeak = 0;
    activity = 0.0F;
    rms = 0.0F;
    return;
  }

  const float meanValue =
    static_cast<float>(sampleTotal) / static_cast<float>(sampleCount);

  float absoluteDeviationTotal = 0.0F;
  float squaredDeviationTotal = 0.0F;

  for (size_t i = 0; i < sampleCount; i++) {
    const float deviation =
      static_cast<float>(audioSamples[i]) - meanValue;

    absoluteDeviationTotal += fabsf(deviation);
    squaredDeviationTotal += deviation * deviation;
  }

  peakToPeak = maximumValue - minimumValue;

  activity =
    absoluteDeviationTotal / static_cast<float>(sampleCount);

  rms = sqrtf(
    squaredDeviationTotal / static_cast<float>(sampleCount));
}

//collect sensor data
SensorData collectSensorData() {
  SensorData data;

  readPir(
    data.pirMotion,
    data.pirRecentActivity);

  readMicrophoneFeatures(
    data.audioPeakToPeak,
    data.audioActivity,
    data.audioRms);

  return data;
}

//json
bool createJsonPacket(
  const SensorData& data,
  char* buffer,
  size_t bufferSize) {
  const int charactersWritten = snprintf(
    buffer,
    bufferSize,
    "{"
    "\"schema_version\":1,"
    "\"firmware_version\":\"%s\","
    "\"sensor_config\":\"%s\","
    "\"boot_id\":%lu,"
    "\"node_id\":\"%s\","
    "\"zone\":\"%s\","
    "\"sequence\":%lu,"
    "\"timestamp_ms\":%lu,"
    "\"wifi_connected\":%s,"
    "\"wifi_rssi_dbm\":%d,"
    "\"pir_motion\":%s,"
    "\"pir_recent_activity\":%s,"
    "\"audio_peak_to_peak\":%u,"
    "\"audio_activity\":%.2f,"
    "\"audio_rms\":%.2f"
    "}",
    FIRMWARE_VERSION,
    SENSOR_CONFIG,
    static_cast<unsigned long>(bootId),
    NODE_ID,
    ZONE_ID,
    static_cast<unsigned long>(sequenceNumber),
    millis(),
    WiFi.status() == WL_CONNECTED ? "true" : "false",
    WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0,
    data.pirMotion ? "true" : "false",
    data.pirRecentActivity ? "true" : "false",
    data.audioPeakToPeak,
    data.audioActivity,
    data.audioRms);

  return (
    charactersWritten >= 0 && charactersWritten < static_cast<int>(bufferSize));
}

//udp transmission
bool sendUdpPacket(const char* jsonPacket) {
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  if (!udp.beginPacket(LAPTOP_IP, LAPTOP_UDP_PORT)) {
    return false;
  }

  udp.write(
    reinterpret_cast<const uint8_t*>(jsonPacket),
    strlen(jsonPacket));

  return udp.endPacket() == 1;
}

//sensor cycle
void runSensorCycle() {
  sequenceNumber++;

  const SensorData data = collectSensorData();

  char jsonPacket[384];

  if (!createJsonPacket(
        data,
        jsonPacket,
        sizeof(jsonPacket))) {
    Serial.println("ERROR: JSON packet too large");
    return;
  }

  const unsigned long timestampMs = millis();

  const unsigned long totalSeconds = timestampMs / 1000;
  const unsigned long hours = totalSeconds / 3600;
  const unsigned long minutes = (totalSeconds % 3600) / 60;
  const unsigned long seconds = totalSeconds % 60;
  const unsigned long milliseconds = timestampMs % 1000;

  char terminalTimestamp[20];

  snprintf(
    terminalTimestamp,
    sizeof(terminalTimestamp),
    "%02lu:%02lu:%02lu.%03lu",
    hours,
    minutes,
    seconds,
    milliseconds);

  Serial.print("[");
  Serial.print(terminalTimestamp);
  Serial.print("] ");
  Serial.println(jsonPacket);

  if (WiFi.status() == WL_CONNECTED) {
    if (!sendUdpPacket(jsonPacket)) {
      Serial.println("WARNING: UDP send failed");
    }
  }
}

void logMemoryStatus(const char* context) {
  const uint32_t freeHeap = ESP.getFreeHeap();

  if (freeHeap < minimumFreeHeap) {
    minimumFreeHeap = freeHeap;
  }

  Serial.print("[MEMORY] context=");
  Serial.print(context);
  Serial.print(" uptime_ms=");
  Serial.print(millis());
  Serial.print(" free_heap_bytes=");
  Serial.print(freeHeap);
  Serial.print(" minimum_free_heap_bytes=");
  Serial.print(minimumFreeHeap);
  Serial.print(" audio_buffer_bytes=");
  Serial.println(sizeof(audioSamples));
}

uint32_t generateBootId() {
  return (
    static_cast<uint32_t>(ESP.getChipId()) ^
    static_cast<uint32_t>(ESP.getCycleCount()) ^
    micros()
  );
}

void setup() {
  Serial.begin(115200);
  delay(500);

  bootId = generateBootId();

  Serial.println();
  Serial.println("====================================");
  Serial.println("ARIA ESP-B starting");
  Serial.println("====================================");

  Serial.print("Boot ID: ");
  Serial.println(bootId);

  Serial.print("Reset reason: ");
  Serial.println(ESP.getResetReason());

  pinMode(PIR_PIN, INPUT);

  connectToWiFi();
  logMemoryStatus("startup");
  lastHeapLogTime = millis();

  Serial.println();
  Serial.println("ESP-B sensors:");
  Serial.println("PIR: D1");
  Serial.println("MAX4466: A0");
  Serial.println();
  Serial.println("Allow PIR 30-60 seconds to stabilise.");
}

void loop() {
  maintainWiFiConnection();
  const unsigned long now = millis();

  if (now - lastHeapLogTime >= HEAP_LOG_INTERVAL_MS) {
    lastHeapLogTime = now;
    logMemoryStatus("periodic");
  }

  if (now - lastSendTime >= SEND_INTERVAL_MS) {
    lastSendTime = now;
    runSensorCycle();
  }

  yield();
}
