#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7789.h>

// Iteration 0: the original working 3-sensor read-out + relay test (kept for reference).
// ---------- TFT DISPLAY ----------
#define TFT_SCK   12
#define TFT_MOSI  11
#define TFT_CS    10
#define TFT_DC    14
#define TFT_RST   21

SPIClass tftSPI(FSPI);
Adafruit_ST7789 tft(&tftSPI, TFT_CS, TFT_DC, TFT_RST);

// ---------- SOIL MOISTURE SENSORS ----------
#define SENSOR_V1   2
#define SENSOR_V2A  1
#define SENSOR_V2B  3

// ---------- RELAY ----------
#define RELAY_PIN  20

// Many relay modules are active LOW.
// Change these if your module works in reverse.
const int RELAY_ON  = LOW;
const int RELAY_OFF = HIGH;

// Set true only for the initial pump test.
// The pump runs 3 seconds, then stops 3 seconds.
const bool PUMP_TEST_MODE = false;

unsigned long lastDisplayUpdate = 0;
unsigned long lastPumpToggle = 0;
bool pumpRunning = false;

void setup() {
  Serial.begin(115200);
  delay(500);

  // Ensure the pump starts OFF
  digitalWrite(RELAY_PIN, RELAY_OFF);
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, RELAY_OFF);

  // Initialize TFT
  tftSPI.begin(TFT_SCK, -1, TFT_MOSI, TFT_CS);
  tft.init(240, 320);
  tft.setRotation(0);
  tft.fillScreen(ST77XX_BLACK);
  tft.setTextColor(ST77XX_WHITE);
  tft.setTextSize(2);

  tft.setCursor(10, 15);
  tft.println("Soil Monitor");
  tft.drawFastHLine(10, 42, 220, ST77XX_WHITE);

  analogReadResolution(12);
  analogSetPinAttenuation(SENSOR_V1, ADC_11db);
  analogSetPinAttenuation(SENSOR_V2A, ADC_11db);
  analogSetPinAttenuation(SENSOR_V2B, ADC_11db);

  Serial.println("ESP32-S3 Soil Monitor Started");
}

void loop() {
  unsigned long now = millis();

  // Update sensor readings and display every 500 ms
  if (now - lastDisplayUpdate >= 500) {
    lastDisplayUpdate = now;

    int moistureV1  = analogRead(SENSOR_V1);
    int moistureV2A = analogRead(SENSOR_V2A);
    int moistureV2B = analogRead(SENSOR_V2B);

    Serial.print("V1.2: ");
    Serial.print(moistureV1);
    Serial.print(" | V2 A: ");
    Serial.print(moistureV2A);
    Serial.print(" | V2 B: ");
    Serial.println(moistureV2B);

    tft.fillRect(10, 55, 220, 180, ST77XX_BLACK);
    tft.setCursor(10, 65);
    tft.println("Sensor Readings");

    tft.setCursor(10, 105);
    tft.print("V1.2: ");
    tft.println(moistureV1);

    tft.setCursor(10, 145);
    tft.print("V2-A: ");
    tft.println(moistureV2A);

    tft.setCursor(10, 185);
    tft.print("V2-B: ");
    tft.println(moistureV2B);
  }

  // Optional temporary relay/pump test
  if (PUMP_TEST_MODE) {
    if (now - lastPumpToggle >= 3000) {
      lastPumpToggle = now;
      pumpRunning = !pumpRunning;

      digitalWrite(
        RELAY_PIN,
        pumpRunning ? RELAY_ON : RELAY_OFF
      );

      Serial.println(pumpRunning ? "Pump ON" : "Pump OFF");
    }
  } else {
    // Monitoring mode: keep pump OFF for now
    digitalWrite(RELAY_PIN, RELAY_OFF);
  }
}
