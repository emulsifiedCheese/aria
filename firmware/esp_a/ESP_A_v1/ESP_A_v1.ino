#include <ESP8266WiFi.h>
#include <WiFiUdp.h>
#include <math.h>

//wifi
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
IPAddress LAPTOP_IP(10, 100, 5, 66);

constexpr uint16_t LAPTOP_UDP_PORT = 5005;
constexpr uint16_t ESP_LOCAL_UDP_PORT = 4210;

uint32_t bootId = 0;

bool hasConnectedBefore = false;
bool wifiWasConnected = false;
bool udpReady = false;

uint32_t wifiReconnectCount = 0;
uint8_t wifiReconnectAttemptCount = 0;
uint8_t wifiRadioResetCount = 0;

unsigned long wifiDisconnectedAt = 0;
unsigned long lastWifiOutageMs = 0;

//eps a1
const char* FIRMWARE_VERSION = "1.1.1";
const char* SENSOR_CONFIG = "A_PIR_US_MIC";
const char* NODE_ID = "ESP-A1";
const char* ZONE_ID = "A";
const char* WIFI_HOSTNAME = "aria-esp-a1";

//pin config
constexpr uint8_t PIR_PIN = D1;
constexpr uint8_t ULTRASONIC_TRIG_PIN = D5;
constexpr uint8_t ULTRASONIC_ECHO_PIN = D6;
constexpr uint8_t MICROPHONE_PIN = A0;

//timing
//send one packet/second
constexpr unsigned long SEND_INTERVAL_MS = 1000;

//allow each explicit wifi connection attempt time to complete
constexpr unsigned long WIFI_RETRY_INTERVAL_MS = 15000;
constexpr uint8_t WIFI_RADIO_RESET_AFTER_ATTEMPTS = 3;
constexpr uint8_t WIFI_BOARD_RESTART_AFTER_RADIO_RESETS = 2;
constexpr unsigned long WIFI_RADIO_OFF_MS = 1000;

//ultrasonic timeout
constexpr unsigned long ULTRASONIC_TIMEOUT_US = 30000;

//mic sampling window
constexpr unsigned long AUDIO_SAMPLE_WINDOW_MS = 900;

//max number of stored mic samples
constexpr size_t MAX_AUDIO_SAMPLES = 500;

//keep recent seat activity true for 10 sec after pir motion
constexpr unsigned long PIR_HOLD_MS = 10000;

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
  float distanceCm;
  bool distanceValid;
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
  Serial.print("Connecting to public Wi-Fi network: ");
  Serial.println(WIFI_SSID);

  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.hostname(WIFI_HOSTNAME);
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
        "Wi-Fi recovery failed; restarting ESP-A1 automatically");
      Serial.flush();
      delay(100);
      ESP.restart();
      return;
    }

    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    delay(WIFI_RADIO_OFF_MS);
    WiFi.mode(WIFI_STA);
    WiFi.hostname(WIFI_HOSTNAME);
    WiFi.setAutoReconnect(true);

    wifiReconnectAttemptCount = 0;
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

//pir
void readPir(
  bool& motionDetected,
  bool& recentActivity
) {
  motionDetected = digitalRead(PIR_PIN) == HIGH;

  const unsigned long now = millis();

  if (motionDetected) {
    lastPirMotionTime = now;
  }

  recentActivity =
    lastPirMotionTime > 0 &&
    now - lastPirMotionTime < PIR_HOLD_MS;
}

//ultrasonic
float readUltrasonicDistanceCm() {
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
  delayMicroseconds(3);

  digitalWrite(ULTRASONIC_TRIG_PIN, HIGH);
  delayMicroseconds(10);

  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);

  const unsigned long durationUs = pulseIn(
    ULTRASONIC_ECHO_PIN,
    HIGH,
    ULTRASONIC_TIMEOUT_US
  );

  if (durationUs == 0) {
    return -1.0F;
  }

  const float distanceCm =
    static_cast<float>(durationUs) * 0.0343F / 2.0F;

  if (distanceCm < 2.0F || distanceCm > 400.0F) {
    return -1.0F;
  }

  return distanceCm;
}

//mic
void readMicrophoneFeatures(
  uint16_t& peakToPeak,
  float& activity,
  float& rms
) {
  size_t sampleCount = 0;
  unsigned long sampleTotal = 0;

  uint16_t minimumValue = 1023;
  uint16_t maximumValue = 0;

  const unsigned long windowStart = millis();

  while (
    millis() - windowStart < AUDIO_SAMPLE_WINDOW_MS &&
    sampleCount < MAX_AUDIO_SAMPLES
  ) {
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
    static_cast<float>(sampleTotal) /
    static_cast<float>(sampleCount);

  float absoluteDeviationTotal = 0.0F;
  float squaredDeviationTotal = 0.0F;

  for (size_t i = 0; i < sampleCount; i++) {
    const float deviation =
      static_cast<float>(audioSamples[i]) - meanValue;

    absoluteDeviationTotal += fabs(deviation);
    squaredDeviationTotal += deviation * deviation;
  }

  peakToPeak = maximumValue - minimumValue;

  activity =
    absoluteDeviationTotal /
    static_cast<float>(sampleCount);

  rms = sqrt(
    squaredDeviationTotal /
    static_cast<float>(sampleCount)
  );
}

//collect sensor data
SensorData collectSensorData() {
  SensorData data;

  readPir(
    data.pirMotion,
    data.pirRecentActivity
  );

  data.distanceCm = readUltrasonicDistanceCm();
  data.distanceValid = data.distanceCm >= 0.0F;

  readMicrophoneFeatures(
    data.audioPeakToPeak,
    data.audioActivity,
    data.audioRms
  );

  return data;
}

//json
bool createJsonPacket(
  const SensorData& data,
  char* buffer,
  size_t bufferSize
) {
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
      "\"distance_cm\":%.2f,"
      "\"distance_valid\":%s,"
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
    data.distanceCm,
    data.distanceValid ? "true" : "false",
    data.audioPeakToPeak,
    data.audioActivity,
    data.audioRms
  );

  return (
    charactersWritten >= 0 &&
    charactersWritten < static_cast<int>(bufferSize)
  );
}

//udp send

bool sendUdpPacket(const char* jsonPacket) {
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  if (!udp.beginPacket(LAPTOP_IP, LAPTOP_UDP_PORT)) {
    return false;
  }

  udp.write(
    reinterpret_cast<const uint8_t*>(jsonPacket),
    strlen(jsonPacket)
  );

  return udp.endPacket() == 1;
}

//sensor cycle

void runSensorCycle() {
  sequenceNumber++;

  const SensorData data = collectSensorData();

  char jsonPacket[512];

  if (!createJsonPacket(
    data,
    jsonPacket,
    sizeof(jsonPacket)
  )) {
    Serial.println("ERROR: JSON packet too large");
    return;
  }

  //print 1 clean json packet/second
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
  milliseconds
);

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
  Serial.println("ARIA ESP-A1 starting");
  Serial.println("====================================");

  Serial.print("Boot ID: ");
  Serial.println(bootId);

  pinMode(PIR_PIN, INPUT);

  pinMode(ULTRASONIC_TRIG_PIN, OUTPUT);
  pinMode(ULTRASONIC_ECHO_PIN, INPUT);

  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);

  connectToWiFi();

  Serial.println();
  Serial.println("ESP-A1 sensors:");
  Serial.println("PIR: D1");
  Serial.println("Ultrasonic TRIG: D5");
  Serial.println("Ultrasonic ECHO: D6");
  Serial.println("MAX4466: A0");
  Serial.println();
  Serial.println("Allow PIR 30-60 seconds to stabilise.");
}

void loop() {
  maintainWiFiConnection();

  const unsigned long now = millis();

  if (now - lastSendTime >= SEND_INTERVAL_MS) {
    lastSendTime = now;
    runSensorCycle();
  }

  yield();
}
