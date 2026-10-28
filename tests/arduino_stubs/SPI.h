#pragma once
#include "Arduino.h"
#define FSPI 1
struct SPIClass { SPIClass(int) {} void begin(int, int, int, int) {} };
