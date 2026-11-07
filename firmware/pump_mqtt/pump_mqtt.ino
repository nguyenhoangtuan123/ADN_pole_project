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
#include <esp_task_wdt.h>
#include "secrets.h"

const int PUMP_PIN = 23;
const int RELAY_ACTIVE_LEVEL = HIGH;
const int RELAY_INACTIVE_LEVEL = (RELAY_ACTIVE_LEVEL == HIGH) ? LOW : HIGH;
const unsigned long PUMP_MAX_RUN_MS = 300000UL;
const unsigned long FAILSAFE_DISCONNECT_MS = 30000UL;
const unsigned long STATUS_INTERVAL_MS = 10000UL;       // khi bom tat
const unsigned long STATUS_INTERVAL_ON_MS = 5000UL;     // khi bom dang chay (de web hien thoi gian chinh xac)
const uint32_t WDT_TIMEOUT_S = 20;                      // treo qua 20 giay thi tu khoi dong lai
const uint32_t MQTT_SOCKET_TIMEOUT_S = 5;
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
unsigned long lastStatusAt = 0;
unsigned long wifiLostAt = 0;
unsigned long resetPressedAt = 0;
WiFiManager wifiManager;
unsigned long lastMqttAttemptAt = 0;

// Dinh dang status: "OFF" hoac "ON:<giay_da_chay>:<giay_toi_da>" (web dung de hien thoi gian that).
void publishStatus() {
  if (mqtt.connected()) {
    char payload[32];
    if (pumpOn) {
      snprintf(payload, sizeof(payload), "ON:%lu:%lu",
               (millis() - pumpStartedAt) / 1000UL, PUMP_MAX_RUN_MS / 1000UL);
    } else {
      snprintf(payload, sizeof(payload), "OFF");
    }
    mqtt.publish(TOPIC_STATUS, payload, true);
    lastStatusAt = millis();
  }
}

// Watchdog: loop() ngung chay qua WDT_TIMEOUT_S thi ESP32 tu khoi dong lai (relay ve OFF).
void watchdogStart() {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  esp_task_wdt_config_t cfg = {};
  cfg.timeout_ms = WDT_TIMEOUT_S * 1000;
  cfg.idle_core_mask = 0;
  cfg.trigger_panic = true;
  if (esp_task_wdt_reconfigure(&cfg) != ESP_OK) esp_task_wdt_init(&cfg);
#else
  esp_task_wdt_init(WDT_TIMEOUT_S, true);
#endif
  esp_task_wdt_add(NULL);
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
  esp_task_wdt_delete(NULL);  // trang cau hinh chan toi 3 phut, tam tat watchdog (bom da tat)
  if (forgetSaved) wifiManager.resetSettings();
  wifiManager.setConfigPortalTimeout(PORTAL_TIMEOUT_S);
  wifiManager.setConnectTimeout(20);
  Serial.println(forgetSaved ? "Xoa WiFi da luu, mo trang cau hinh..." : "Mo trang cau hinh WiFi neu can...");
  if (forgetSaved) wifiManager.startConfigPortal(PORTAL_NAME);
  else wifiManager.autoConnect(PORTAL_NAME);
  wifiLostAt = 0;
  lastGoodConnectionAt = millis();
  esp_task_wdt_add(NULL);
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
  secureClient.setTimeout(MQTT_SOCKET_TIMEOUT_S);
  mqtt.setSocketTimeout(MQTT_SOCKET_TIMEOUT_S);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(messageCallback);
  mqtt.setKeepAlive(15);
  // Ket noi MQTT co gioi han timeout ngan; vong lap khong dung delay cho retry.
  if (mqtt.connect(clientId, MQTT_USER, MQTT_PASS, TOPIC_ONLINE, 1, true, "offline")) {
    lastGoodConnectionAt = millis();
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
  watchdogStart();
}

void loop() {
  esp_task_wdt_reset();
  const unsigned long now = millis();
  checkResetButton(now);
  if (WiFi.status() == WL_CONNECTED) {
    wifiLostAt = 0;
    if (!mqtt.connected() && now - lastMqttAttemptAt >= MQTT_RETRY_MS) connectMqtt();
    if (mqtt.connected()) {
      mqtt.loop();
      lastGoodConnectionAt = millis();
      if (millis() - lastStatusAt >= (pumpOn ? STATUS_INTERVAL_ON_MS : STATUS_INTERVAL_MS)) publishStatus();
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
