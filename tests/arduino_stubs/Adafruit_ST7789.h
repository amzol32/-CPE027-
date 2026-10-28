#pragma once
#include "Arduino.h"
#include "SPI.h"
#define ST77XX_BLACK 0
#define ST77XX_WHITE 1
#define ST77XX_RED 2
#define ST77XX_GREEN 3
#define ST77XX_CYAN 4
#define ST77XX_YELLOW 5
#define ST77XX_ORANGE 6
struct Adafruit_ST7789 {
  Adafruit_ST7789(SPIClass*, int, int, int) {}
  void init(int, int) {}
  void setRotation(int) {}
  void fillScreen(uint16_t) {}
  void setTextColor(uint16_t) {}
  void setTextColor(uint16_t, uint16_t) {}
  void setTextSize(uint8_t) {}
  void setCursor(int, int) {}
  void println(const char*) {}
  void print(const String&) {}
  void print(const char*) {}
  void fillRect(int, int, int, int, uint16_t) {}
  void drawFastHLine(int, int, int, uint16_t) {}
};
