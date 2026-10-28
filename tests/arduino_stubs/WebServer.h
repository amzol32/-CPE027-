#pragma once
#include "Arduino.h"
#define CONTENT_LENGTH_UNKNOWN (size_t)-1
struct WebServer {
  WebServer(int) {}
  void on(const char*, std::function<void()>) {}
  void begin() {}
  void handleClient() {}
  String arg(const char*) { return String(); }
  void send(int, const char*, const char*) {}
  void send_P(int, const char*, const char*) {}
  void setContentLength(size_t) {}
  void sendContent(const String&) {}
  void sendContent(const char*) {}
};
