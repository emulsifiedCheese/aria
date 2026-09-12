const uint8_t TRIG_PIN = D5;
const uint8_t ECHO_PIN = D6;

void setup() {
  Serial.begin(115200);

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  digitalWrite(TRIG_PIN, LOW);

  delay(500);

  Serial.println();
  Serial.println("ESP-A HC-SR04 ultrasonic test started");
}

void loop() {
  // Send trigger pulse
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(3);

  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);

  digitalWrite(TRIG_PIN, LOW);

  // Wait for echo pulse, timeout after 30 ms
  const unsigned long duration =
    pulseIn(ECHO_PIN, HIGH, 30000);

  if (duration == 0) {
    Serial.println("No echo detected");
  } else {
    const float distanceCm =
      duration * 0.0343F / 2.0F;

    Serial.print("Distance: ");
    Serial.print(distanceCm, 1);
    Serial.println(" cm");
  }

  delay(1000);
}