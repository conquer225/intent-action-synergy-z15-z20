#ifndef MULTI_PIN_MAP_H
#define MULTI_PIN_MAP_H
#include <stdint.h>

// GPIO numbers, not physical header positions. Matches the final wiring table.
constexpr int EMG_PIN = 1, WEAR_PIN = 2;
constexpr int SDA_PIN = 11, SCL_PIN = 12;
constexpr int RF_CE = 42, RF_CSN = 41, RF_SCK = 40;
constexpr int RF_MOSI = 39, RF_MISO = 38;
constexpr uint8_t POT_COUNT = 6;
constexpr int POT_PINS[POT_COUNT] = {4, 5, 6, 7, 9, 10};
constexpr uint8_t PRESSURE_COUNT = 5;
constexpr int MOTOR_PINS[PRESSURE_COUNT] = {15,16,17,18,8};
constexpr uint32_t PENDULUM_BAUD = 9600;
constexpr int ASSIGNED_PINS[] = {1,2,11,12,42,41,40,39,38,4,5,6,7,9,10,15,16,17,18,8};
constexpr bool distinctPins() {
  for (unsigned i = 0; i < sizeof(ASSIGNED_PINS)/sizeof(int); ++i)
    for (unsigned j = i + 1; j < sizeof(ASSIGNED_PINS)/sizeof(int); ++j)
      if (ASSIGNED_PINS[i] == ASSIGNED_PINS[j]) return false;
  return true;
}
static_assert(distinctPins(), "Duplicate GPIO assignment");
#endif
