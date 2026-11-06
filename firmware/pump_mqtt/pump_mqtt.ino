/*
 * Bom that Trụ ADN qua MQTT TLS.
 * Thu vien Arduino IDE can cai: PubSubClient (Nick O'Leary) va WiFiManager (tzapu).
 * WiFi.h va WiFiClientSecure.h co san trong bo ESP32 Arduino core.
 * Tao secrets.h tu secrets.h.example truoc khi nap (chi chua thong tin MQTT).
 * WiFi duoc cau hinh qua dien thoai: ESP32 phat WiFi "ADN-Pump-Setup" khi chua co mang.
 * Giu nut BOOT (GPIO 0) 3 giay de xoa WiFi da luu va mo lai trang cau hinh.
 */
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <WiFiManager.h>
#include <PubSubClient.h>
#include <string.h>
#include <stdio.h>
#include "secrets.h"

const int PUMP_PIN = 23;
const int RELAY_ACTIVE_LEVEL = HIGH;
const int RELAY_INACTIVE_LEVEL = (RELAY_ACTIVE_LEVEL == HIGH) ? LOW : HIGH;
const unsigned long PUMP_MAX_RUN_MS = 300000UL;
const unsigned long FAILSAFE_DISCONNECT_MS = 30000UL;
const unsigned long STATUS_INTERVAL_MS = 10000UL;
const unsigned long WIFI_PORTAL_AFTER_MS = 120000UL;  // mat WiFi lau thi mo lai trang cau hinh
const unsigned long PORTAL_TIMEOUT_S = 180;
const unsigned long RESET_HOLD_MS = 3000UL;
const int RESET_PIN = 0;  // nut BOOT tren ESP32
const char *PORTAL_NAME = "ADN-Pump-Setup";
const unsigned long MQTT_RETRY_MS = 3000UL;

const char *TOPIC_CMD = "adn/pump/cmd";
const char *TOPIC_STATUS = "adn/pump/status";
const char *TOPIC_ONLINE = "adn/pump/online";

WiFiClientSecure secureClient;
PubSubClient mqtt(secureClient);
bool pumpOn = false;
unsigned long pumpStartedAt = 0;
unsigned long lastGoodConnectionAt = 0;
unsigned long connectedSinceAt = 0;
unsigned long lastStatusAt = 0;
unsigned long wifiLostAt = 0;
unsigned long resetPressedAt = 0;
WiFiManager wifiManager;
unsigned long lastMqttAttemptAt = 0;

void publishStatus() {
  if (mqtt.connected()) {
    mqtt.publish(TOPIC_STATUS, pumpOn ? "ON" : "OFF", true);
    lastStatusAt = millis();
  }
}

void setPump(bool turnOn) {
  if (turnOn == pumpOn) {
    publishStatus();  // van bao lai de web nhan duoc xac nhan khi lenh trung trang thai
    return;
  }
  pumpOn = turnOn;
  digitalWrite(PUMP_PIN, pumpOn ? RELAY_ACTIVE_LEVEL : RELAY_INACTIVE_LEVEL);
  if (pumpOn) {
    pumpStartedAt = millis();
    Serial.println("Bom bat theo lenh MQTT");
  } else {
    Serial.println("Bom tat");
  }
  publishStatus();
}

void messageCallback(char *topic, byte *payload, unsigned int length) {
  if (strcmp(topic, TOPIC_CMD) != 0 || length > 8) return;
  char command[9] = {0};
  memcpy(command, payload, length);
  if (strcmp(command, "ON") == 0) setPump(true);
  else if (strcmp(command, "OFF") == 0) setPump(false);
  else Serial.println("Bo qua lenh khong hop le");
}

// Mo trang cau hinh WiFi (chan trong luc cho). Luon tat bom truoc de an toan.
void openWifiPortal(bool forgetSaved) {
  setPump(false);
  if (mqtt.connected()) mqtt.disconnect();
  if (forgetSaved) wifiManager.resetSettings();
  wifiManager.setConfigPortalTimeout(PORTAL_TIMEOUT_S);
  wifiManager.setConnectTimeout(20);
  Serial.println(forgetSaved ? "Xoa WiFi da luu, mo trang cau hinh..." : "Mo trang cau hinh WiFi neu can...");
  if (forgetSaved) wifiManager.startConfigPortal(PORTAL_NAME);
  else wifiManager.autoConnect(PORTAL_NAME);
  wifiLostAt = 0;
  lastGoodConnectionAt = millis();
}

void checkResetButton(unsigned long now) {
  if (digitalRead(RESET_PIN) == LOW) {
    if (resetPressedAt == 0) resetPressedAt = now;
    else if (now - resetPressedAt >= RESET_HOLD_MS) {
      resetPressedAt = 0;
      openWifiPortal(true);
    }
  } else {
    resetPressedAt = 0;
  }
}

void connectMqtt() {
  uint8_t mac[6];
  WiFi.macAddress(mac);
  char clientId[32];
  snprintf(clientId, sizeof(clientId), "adn_pump_%02X%02X%02X%02X%02X%02X",
           mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  // setInsecure phu hop cho ban thi; khi trien khai that hay thay bang setCACert.
  secureClient.setInsecure();
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(messageCallback);
  mqtt.setKeepAlive(15);
  // Ket noi MQTT co gioi han timeout ngan; vong lap khong dung delay cho retry.
  if (mqtt.connect(clientId, MQTT_USER, MQTT_PASS, TOPIC_ONLINE, 1, true, "offline")) {
    connectedSinceAt = millis();
    lastGoodConnectionAt = connectedSinceAt;
    mqtt.publish(TOPIC_ONLINE, "online", true);
    mqtt.subscribe(TOPIC_CMD, 1);
    // Bao cao lai trang thai vat ly, khong phat lai lenh cu.
    publishStatus();
    Serial.println("Da ket noi MQTT, bom khong tu bat khi ket noi lai");
  } else {
    Serial.printf("Ket noi MQTT that bai, ma loi: %d\n", mqtt.state());
  }
  lastMqttAttemptAt = millis();
}

void setup() {
  Serial.begin(115200);
  pinMode(PUMP_PIN, OUTPUT);
  digitalWrite(PUMP_PIN, RELAY_INACTIVE_LEVEL);
  pumpOn = false;
  pinMode(RESET_PIN, INPUT_PULLUP);
  Serial.println("Khoi dong: relay tat, trang thai OFF");
  WiFi.mode(WIFI_STA);
  openWifiPortal(false);
}

void loop() {
  const unsigned long now = millis();
  checkResetButton(now);
  if (WiFi.status() == WL_CONNECTED) {
    wifiLostAt = 0;
    if (!mqtt.connected() && now - lastMqttAttemptAt >= MQTT_RETRY_MS) connectMqtt();
    if (mqtt.connected()) {
      mqtt.loop();
      lastGoodConnectionAt = millis();
      if (millis() - lastStatusAt >= STATUS_INTERVAL_MS) publishStatus();
    } else if (pumpOn && now - lastGoodConnectionAt >= FAILSAFE_DISCONNECT_MS) {
      setPump(false);
      Serial.println("Failsafe: mat MQTT, da tat bom");
    }
  } else {
    if (pumpOn && now - lastGoodConnectionAt >= FAILSAFE_DISCONNECT_MS) {
      setPump(false);
      Serial.println("Failsafe: mat WiFi, da tat bom");
    }
    // ESP32 tu dong ket noi lai WiFi da luu; neu mat mang qua lau thi mo lai trang cau hinh.
    if (wifiLostAt == 0) wifiLostAt = now;
    else if (now - wifiLostAt >= WIFI_PORTAL_AFTER_MS) openWifiPortal(false);
  }

  if (pumpOn && now - pumpStartedAt >= PUMP_MAX_RUN_MS) {
    setPump(false);
    Serial.println("Het gio toi da 5 phut, da tat bom");
  }
}
