#ifndef MULTICONTROL_HAND_CONFIG_H
#define MULTICONTROL_HAND_CONFIG_H
#include <stdint.h>
// Host simulation only; production configs remain unverified.
constexpr bool SAFE_POSE_VERIFIED=true;
constexpr uint8_t SAFE_SERVO_ANGLES[6]={180,180,180,180,180,180};
#endif
