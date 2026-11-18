/*
  BLAZE ESP32 + MAX6675 READ-ONLY BENCH MONITOR

  This sketch ONLY reads the thermocouple and sends telemetry to a Python API.
  It contains NO servo, valve, relay, heater, burner, or actuator code.

  Use only for supervised low-voltage ambient-temperature bench testing.
  Keep all gas/thermal equipment disconnected.
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <max6675.h>
#include <math.h>

// MAX6675 SPI pins (change only to match your documented ESP32 wiring).
constexpr int PIN_SCK = 18;
constexpr int PIN_CS  = 23;
constexpr int PIN_SO  = 19;

// Replace these values before uploading.
// Keep this device and computer on the same trusted private Wi-Fi network.
const char* WIFI_SSID = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* API_URL = "http://192.168.1.100:8000/telemetry";
const char* DEVICE_TOKEN = "PASTE_YOUR_DEMO_TOKEN";
const char* DEVICE_ID = "BLAZE-ESP32-01";

MAX6675 thermocouple(PIN_SCK, PIN_CS, PIN_SO);

unsigned long lastSend = 0;
const unsigned long SEND_INTERVAL_MS = 2000;

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connecting to Wi-Fi");
  unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 15000) {
    delay(300);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Wi-Fi connected. ESP32 IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Wi-Fi not connected; will retry.");
  }
}

void sendReading(float temperature, bool sensorFault) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("No Wi-Fi; packet not sent.");
    return;
  }

  HTTPClient http;
  http.setTimeout(3000);
  http.begin(API_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Token", DEVICE_TOKEN);

  String body = "{\"device_id\":\"";
  body += DEVICE_ID;
  body += "\",\"sensor_status\":\"";
  body += sensorFault ? "FAULT" : "NORMAL";
  body += "\",\"temperature\":";

  if (sensorFault) {
    body += "null";
  } else {
    body += String(temperature, 2);
  }
  body += "}";

  int responseCode = http.POST(body);
  Serial.print("API response: ");
  Serial.println(responseCode);
  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(500);

  // MAX6675 requires a short settling period after power-up.
  delay(300);
  connectWiFi();

  Serial.println("BLAZE read-only sensor monitor ready.");
  Serial.println("Ambient bench test only; no actuators are connected.");
}

void loop() {
  if (millis() - lastSend >= SEND_INTERVAL_MS) {
    lastSend = millis();

    connectWiFi();

    float tempC = thermocouple.readCelsius();
    bool fault = isnan(tempC) || tempC < 0.0f || tempC > 1024.0f;

    if (fault) {
      Serial.println("Sensor status: FAULT");
      sendReading(NAN, true);
    } else {
      Serial.print("Temperature C: ");
      Serial.println(tempC, 2);
      sendReading(tempC, false);
    }
  }
  delay(20);
}
