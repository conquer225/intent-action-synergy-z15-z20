#ifndef MULTI_GLOVE_LOGIC_H
#define MULTI_GLOVE_LOGIC_H
#include <stdint.h>
#include <stddef.h>
#include "PinMap.h"
#include "HandConfig.h"

constexpr uint32_t CAL_TAG = 0x31435347; // GSC1
constexpr uint16_t MIN_POT_SPAN = 80;
// Keep the original glove's mechanical angle ranges. Verify on the real hand.
constexpr int16_t SERVO_OPEN[POT_COUNT] = {180,180,180,180,180,180};
constexpr int16_t SERVO_CLOSED[POT_COUNT] = {110,110,110,110,110,0};
struct PotCalibration {
  uint32_t tag;
  uint16_t open[POT_COUNT];
  uint16_t closed[POT_COUNT];
};
inline bool calibrationValid(const PotCalibration &cal) {
  if (cal.tag != CAL_TAG) return false;
  for (uint8_t i = 0; i < POT_COUNT; ++i) {
    int span = (int)cal.closed[i] - cal.open[i];
    if (cal.open[i] > 4095 || cal.closed[i] > 4095 ||
        (span > -MIN_POT_SPAN && span < MIN_POT_SPAN)) return false;
  }
  return true;
}
inline int16_t potAngle(uint16_t raw, uint8_t channel, const PotCalibration &cal) {
  if (channel >= POT_COUNT || !calibrationValid(cal)) return 180;
  float fraction = ((int)raw - (int)cal.open[channel]) /
                   (float)((int)cal.closed[channel] - (int)cal.open[channel]);
  if (fraction < 0) fraction = 0;
  if (fraction > 1) fraction = 1;
  float angle = SERVO_OPEN[channel] + fraction *
                (SERVO_CLOSED[channel] - SERVO_OPEN[channel]);
  return (int16_t)(angle + 0.5f);
}
inline void writeLE16(uint8_t *bytes, uint16_t value) {
  bytes[0] = (uint8_t)value; bytes[1] = (uint8_t)(value >> 8);
}
inline uint16_t readLE16(const uint8_t *bytes) {
  return (uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8);
}
constexpr size_t HAND_CONTROL_SIZE = 14;
constexpr size_t HAND_FEEDBACK_SIZE = 13;
inline void encodeHand(uint16_t seq, const int16_t *angles, uint8_t *bytes) {
  writeLE16(bytes, seq);
  for (uint8_t i = 0; i < POT_COUNT; ++i) {
    int angle = angles[i];
    if (angle < 0) angle = 0;
    if (angle > 180) angle = 180;
    writeLE16(bytes + 2 + 2*i, (uint16_t)angle);
  }
}
struct HandFeedback { uint16_t sequence; uint16_t pressureRaw[5]; uint8_t flags; };
inline bool decodeFeedback(const uint8_t *bytes, size_t size, HandFeedback &out) {
  if (size != HAND_FEEDBACK_SIZE) return false;
  HandFeedback value = {}; value.sequence=readLE16(bytes); value.flags=bytes[12];
  if (value.flags & ~0x3fu) return false;
  for (uint8_t i=0;i<5;++i) {
    value.pressureRaw[i]=readLE16(bytes+2+2*i);
    if (value.pressureRaw[i]>1023) return false;
  }
  out = value;
  return true;
}

constexpr uint32_t POSE_TAG = 0x32455350; // PSE2: no automatic migration of unverified poses.
struct PoseCalibration { uint32_t tag; int16_t open[6], closed[6]; };
inline bool anglesValid(const int16_t *angles) {
  if (!angles) return false;
  for (uint8_t i=0;i<6;++i) if (angles[i]<0 || angles[i]>180) return false;
  return true;
}
inline bool poseMatchesSafe(const int16_t *angles) {
  if (!anglesValid(angles)) return false;
  for (uint8_t i=0;i<6;++i) if (angles[i]!=SAFE_SERVO_ANGLES[i]) return false;
  return true;
}
inline bool poseCalibrationValid(const PoseCalibration &cal) {
  return cal.tag==POSE_TAG && SAFE_POSE_VERIFIED && poseMatchesSafe(cal.open) && anglesValid(cal.closed);
}
inline int16_t potAngle(uint16_t raw, uint8_t channel, const PotCalibration &cal,
                       const PoseCalibration &poses) {
  if (channel>=6 || !calibrationValid(cal) || !poseCalibrationValid(poses))
    return channel<6 ? SAFE_SERVO_ANGLES[channel] : 0;
  float fraction=((int)raw-(int)cal.open[channel]) /
                 (float)((int)cal.closed[channel]-(int)cal.open[channel]);
  if (fraction<0) fraction=0;
  if (fraction>1) fraction=1;
  return (int16_t)(poses.open[channel]+fraction*(poses.closed[channel]-poses.open[channel])+0.5f);
}
constexpr uint32_t PRESSURE_TAG=0x32525048; // HPR2, five calibrated pressure channels.
struct PressureCalibration { uint32_t tag; uint16_t zero[5], span[5]; };
inline bool pressureChannelValid(uint16_t zero, uint16_t span) {
  return zero<=1023 && span<=1023 && zero>=span+30u;
}
inline bool pressureCalibrationValid(const PressureCalibration &cal) {
  if (cal.tag!=PRESSURE_TAG) return false;
  for (uint8_t i=0;i<5;++i) if (!pressureChannelValid(cal.zero[i],cal.span[i])) return false;
  return true;
}
inline uint8_t pressureDuty(uint16_t raw, uint16_t zero, uint16_t span) {
  if (!pressureChannelValid(zero,span) || raw>1023) return 0;
  const uint16_t contact=zero-10; // Ten ADC counts of no-contact deadband.
  if (raw>=contact) return 0;
  if (raw<=span) return 255;
  return (uint8_t)((255UL*(contact-raw))/(contact-span));
}
#endif
