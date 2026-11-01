#ifndef MULTI_GLOVE_INPUT_CONFIG_H
#define MULTI_GLOVE_INPUT_CONFIG_H
#include "GloveLogic.h"

// Four bend ranges were recorded on this S3 glove. GPIO9 is verified thumb
// abduction, routed to servo 6. Pinky was moved from non-ADC GPIO46 to GPIO10.
// Thumb-side range retains old Nano 0..750 / 1023 scaled to S3 0..3002 / 4095.
// Pinky retains the old Nano input 900..1023 scaled to S3 3603..4095.
constexpr PotCalibration DIRECT_GLOVE_RANGE = {
  CAL_TAG, {4095,4095,4095,4095,4095,0}, {3593,3319,3208,3111,3603,3002}
};
constexpr uint8_t DIRECT_GLOVE_INPUT_INDEX[POT_COUNT] = {0,1,2,3,5,4};
constexpr uint8_t DIRECT_GLOVE_CHANNELS = 0x3f;
static_assert(DIRECT_GLOVE_INPUT_INDEX[5]==4, "Thumb abduction must use GPIO9/P5");

// Reproduce the original Nano integer map() curves in 10-bit input units.
// 0..180 is Servo.write()'s effective angle range, not a verified closed pose.
inline int16_t nanoGloveAngle(uint16_t raw,uint8_t servo) {
  if (servo>=POT_COUNT) return 180;
  if (raw>4095) return SAFE_SERVO_ANGLES[servo];
  // Drop the two low bits: 12-bit ADC codes become 10-bit Nano-equivalent codes.
  int32_t nanoRaw=raw>>2;
  int32_t angle;
  if (servo<5) {
    int32_t low=servo==0?130:125;
    angle=(nanoRaw-900)*(180-low)/123+low;
  } else angle=180-(nanoRaw*180)/750;
  if (angle<0) angle=0;
  if (angle>180) angle=180;
  return int16_t(angle);
}
#endif
