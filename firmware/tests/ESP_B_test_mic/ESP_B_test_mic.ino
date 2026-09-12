#include <math.h>

const uint8_t MIC_PIN = A0;

constexpr unsigned long SAMPLE_WINDOW_MS = 250;
constexpr size_t MAX_SAMPLES = 500;

uint16_t samples[MAX_SAMPLES];

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println();
  Serial.println("ESP-A MAX4466 microphone test");
}

void loop() {
  size_t sampleCount = 0;
  unsigned long sampleTotal = 0;

  uint16_t minimumValue = 1023;
  uint16_t maximumValue = 0;

  const unsigned long windowStart = millis();

  while (
    millis() - windowStart < SAMPLE_WINDOW_MS &&
    sampleCount < MAX_SAMPLES
  ) {
    const uint16_t sample = analogRead(MIC_PIN);

    samples[sampleCount] = sample;
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
    Serial.println("No microphone samples");
    delay(250);
    return;
  }

  const float meanValue =
    static_cast<float>(sampleTotal) /
    static_cast<float>(sampleCount);

  float squaredDeviationTotal = 0.0F;
  float absoluteDeviationTotal = 0.0F;

  for (size_t i = 0; i < sampleCount; i++) {
    const float deviation =
      static_cast<float>(samples[i]) - meanValue;

    squaredDeviationTotal += deviation * deviation;
    absoluteDeviationTotal += fabs(deviation);
  }

  const uint16_t peakToPeak =
    maximumValue - minimumValue;

  const float rmsActivity =
    sqrt(squaredDeviationTotal / sampleCount);

  const float meanAbsoluteDeviation =
    absoluteDeviationTotal / sampleCount;

  Serial.print(" | Peak-to-peak: ");  //sudden/loud event feature
  Serial.print(peakToPeak);

  Serial.print(" | Activity: ");
  Serial.print(meanAbsoluteDeviation, 2);

  Serial.print(" | RMS: "); //primary sound intensity feature
  Serial.println(rmsActivity, 2);

  /*
  Peak-to-peak - strongest single sound swing in the window
  Activity - average amount of variation
  RMS - primary sound-intensity feature
  */

  delay(100);
}