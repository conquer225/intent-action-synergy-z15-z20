#ifndef MULTI_SWIPE_INPUT_H
#define MULTI_SWIPE_INPUT_H
#include <stdint.h>
#include <math.h>

constexpr float SWIPE_TRIGGER_G = 0.12f;
constexpr float SWIPE_QUIET_G = 0.04f;
constexpr float SWIPE_MAX_GYRO_DPS = 60.0f;
constexpr uint32_t SWIPE_HOLD_MS = 30;
constexpr uint32_t SWIPE_QUIET_MS = 250;
constexpr uint32_t SWIPE_LOCKOUT_MS = 700;
constexpr uint32_t SWIPE_AXIS_TAG = 0x31505753; // SWP1
struct SwipeAxis {
  uint32_t tag = 0;
  float left[3] = {0,0,0};
};
inline float vectorNorm(const float *v) {
  return sqrtf(v[0]*v[0] + v[1]*v[1] + v[2]*v[2]);
}
inline float vectorDot(const float *a, const float *b) {
  return a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
}
inline bool swipeAxisValid(const SwipeAxis &axis) {
  return axis.tag == SWIPE_AXIS_TAG && isfinite(axis.left[0]) &&
         isfinite(axis.left[1]) && isfinite(axis.left[2]) &&
         fabsf(vectorNorm(axis.left) - 1.0f) < 0.05f;
}

// Detect the initial acceleration lobe. A cooldown suppresses opposite braking.
struct SwipeGate {
  bool armed = false, quietTiming = false, lockout = false;
  int candidate = 0;
  uint32_t quietSince = 0, candidateSince = 0, firedAt = 0;
  void reset() { armed = quietTiming = lockout = false; candidate = 0; }
  int update(float side, float motion, uint32_t now, bool valid) {
    if (!valid || !isfinite(side) || !isfinite(motion)) { reset(); return 0; }
    if (motion <= SWIPE_QUIET_G) {
      candidate = 0;
      if (!quietTiming) { quietSince = now; quietTiming = true; }
      if ((uint32_t)(now - quietSince) >= SWIPE_QUIET_MS &&
          (!lockout || (uint32_t)(now - firedAt) >= SWIPE_LOCKOUT_MS)) {
        armed = true; lockout = false;
      }
      return 0;
    }
    quietTiming = false;
    if (!armed) return 0;
    // Reject forward/backward movement: the taught side axis must dominate.
    int direction = fabsf(side) >= 0.8f*motion && fabsf(side) >= SWIPE_TRIGGER_G ?
                    (side > 0 ? 1 : -1) : 0;
    if (!direction) { candidate = 0; return 0; }
    if (candidate != direction) { candidate = direction; candidateSince = now; }
    if ((uint32_t)(now - candidateSince) < SWIPE_HOLD_MS) return 0;
    armed = quietTiming = false; lockout = true; candidate = 0; firedAt = now;
    return direction;
  }
};

// Learn the first coherent acceleration lobe after a stationary interval.
struct SwipeLearner {
  bool active = false, ready = false, quietTiming = false;
  uint8_t count = 0;
  uint32_t startedAt = 0, quietSince = 0;
  float sum[3] = {0,0,0};
  void start(uint32_t now) {
    active = true; ready = quietTiming = false; count = 0; startedAt = now;
    sum[0] = sum[1] = sum[2] = 0;
  }
  // 1=learned, -1=timeout, 0=waiting. Calling code persists only a valid result.
  int update(const float *horizontal, uint32_t now, bool valid, SwipeAxis &out) {
    if (!active) return 0;
    if ((uint32_t)(now - startedAt) >= 10000) { active = false; return -1; }
    float magnitude = vectorNorm(horizontal);
    if (!valid || !isfinite(magnitude)) {
      ready = quietTiming = false; count = 0; return 0;
    }
    if (!ready) {
      if (magnitude <= SWIPE_QUIET_G) {
        if (!quietTiming) { quietSince = now; quietTiming = true; }
        if ((uint32_t)(now - quietSince) >= SWIPE_QUIET_MS) ready = true;
      } else quietTiming = false;
      return 0;
    }
    if (magnitude < SWIPE_TRIGGER_G) { count = 0; return 0; }
    if (count && vectorDot(sum, horizontal) < 0.8f*vectorNorm(sum)*magnitude) count = 0;
    if (!count) sum[0] = sum[1] = sum[2] = 0;
    for (uint8_t i = 0; i < 3; ++i) sum[i] += horizontal[i];
    if (++count < 4) return 0; // 4 consecutive 100 Hz samples, about 30 ms.
    float norm = vectorNorm(sum);
    if (norm < 0.01f) { count = 0; return 0; }
    out.tag = SWIPE_AXIS_TAG;
    for (uint8_t i = 0; i < 3; ++i) out.left[i] = sum[i]/norm;
    active = false;
    return swipeAxisValid(out) ? 1 : -1;
  }
};
#endif
