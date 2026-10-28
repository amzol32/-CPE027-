#pragma once
#include "Arduino.h"
struct Preferences {
  bool begin(const char*, bool) { return true; }
  bool getBool(const char*, bool d) { return d; }
  float getFloat(const char*, float d) { return d; }
  uint32_t getUInt(const char*, uint32_t d) { return d; }
  void putBool(const char*, bool) {} void putFloat(const char*, float) {} void putUInt(const char*, uint32_t) {}
};
