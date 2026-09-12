const uint8_t PIR_PIN = D1;

// Keep recent activity active for 30 seconds after the latest motion.
const unsigned long ACTIVITY_HOLD_MS = 30000;

unsigned long lastMotionTime = 0;
bool motionEverDetected = false;

bool previousMotionState = false;
bool previousRecentActivityState = false;

void setup() {
  Serial.begin(115200);
  pinMode(PIR_PIN, INPUT);

  Serial.println();
  Serial.println("ESP-B PIR activity test");
  Serial.println("Wait 30-60 seconds for PIR stabilisation.");
}

void loop() {
  const unsigned long now = millis();
  const bool motionDetected = digitalRead(PIR_PIN) == HIGH;

  if (motionDetected) {
    lastMotionTime = now;
    motionEverDetected = true;
  }

  const bool recentActivity =
    motionEverDetected &&
    (now - lastMotionTime < ACTIVITY_HOLD_MS);

  if (motionDetected != previousMotionState) {
    Serial.print("PIR motion: ");
    Serial.println(motionDetected ? "DETECTED" : "NONE");

    previousMotionState = motionDetected;
  }

  if (recentActivity != previousRecentActivityState) {
    Serial.print("Recent activity: ");
    Serial.println(recentActivity ? "YES" : "NO");

    previousRecentActivityState = recentActivity;
  }

  delay(100);
}