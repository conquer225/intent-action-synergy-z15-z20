#ifndef MULTICONTROL_HAND_CONFIG_H
#define MULTICONTROL_HAND_CONFIG_H
#include <stdint.h>
// Edit BOTH copies (Nano and ESP32) identically before flashing.
// Existing 180-degree open targets retained at the user's request.
// This setting does not measure the mechanism; check angles before servo power.
constexpr bool SAFE_POSE_VERIFIED = true;
constexpr uint8_t SAFE_SERVO_ANGLES[6] = {180,180,180,180,180,180};
#endif
