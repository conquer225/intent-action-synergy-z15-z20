#pragma once
#include <stdint.h>
// From the user's 2026-08 gloves/firmware/glove_controller source.
// Reference ADC thresholds, not a calibrated force measurement.
inline uint8_t legacyPressurePwm(uint16_t raw) {
  if(raw>1023 || raw>=950)return 0;
  if(raw<=250)return 255;
  return uint8_t(120+(950-int32_t(raw))*135/700);
}
