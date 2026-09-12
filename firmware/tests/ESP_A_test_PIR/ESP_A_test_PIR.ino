const uint8_t PIR_PIN = D1;

// Keep the seat marked occupied for 10 seconds after the last detected motion.
const unsigned long OCCUPANCY_HOLD_MS = 10000;

unsigned long lastMotionTime = 0;
bool previousMotionState = false;
bool previousOccupiedState = false;

void setup() {
  Serial.begin(115200);
  pinMode(PIR_PIN, INPUT);

  Serial.println();
  Serial.println("ESP-A PIR seat-presence test");
  Serial.println("Wait 30-60 seconds for PIR stabilisation.");
}

void loop() {
  const bool motionDetected = digitalRead(PIR_PIN) == HIGH;
  const unsigned long now = millis();

  if (motionDetected) {
    lastMotionTime = now;
  }

  const bool seatRecentlyOccupied =
    lastMotionTime > 0 &&
    now - lastMotionTime < OCCUPANCY_HOLD_MS;

  if (motionDetected != previousMotionState) {
    Serial.print("PIR motion: ");
    Serial.println(motionDetected ? "DETECTED" : "NONE");

    previousMotionState = motionDetected;
  }

  if (seatRecentlyOccupied != previousOccupiedState) {
    Serial.print("Seat status: ");
    Serial.println(
      seatRecentlyOccupied ? "OCCUPIED / RECENT ACTIVITY" : "NO RECENT ACTIVITY"
    );

    previousOccupiedState = seatRecentlyOccupied;
  }

  delay(100);
}