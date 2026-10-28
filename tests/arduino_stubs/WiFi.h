#pragma once
#include "Arduino.h"
#define WL_CONNECTED 3
#define WIFI_STA 1
#define WIFI_AP 2
struct IPAddress { String toString() const { return String("192.168.4.1"); } };
struct WiFiClass {
  void mode(int) {} void setAutoReconnect(bool) {} void begin(const char*, const char*) {}
  int status() { return WL_CONNECTED; } IPAddress localIP() { return {}; }
  void softAP(const char*, const char*) {} IPAddress softAPIP() { return {}; }
};
static WiFiClass WiFi;
