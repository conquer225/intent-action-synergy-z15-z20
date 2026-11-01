#ifndef HAND_NANO_WIRE_H
#define HAND_NANO_WIRE_H
#include <stdint.h>
#include <stddef.h>
namespace HandWire {
const uint8_t ServoCount = 6, PressureCount = 5;
const size_t ControlSize = 14, FeedbackSize = 13;
struct Control { uint16_t sequence; int16_t angle[ServoCount]; };
inline uint16_t read16(const uint8_t *p) { return (uint16_t)p[0] | ((uint16_t)p[1] << 8); }
inline void write16(uint8_t *p, uint16_t n) { p[0] = (uint8_t)n; p[1] = (uint8_t)(n >> 8); }
inline bool newer(uint16_t next, uint16_t previous) {
  uint16_t delta = (uint16_t)(next - previous);
  return delta != 0 && delta < 0x8000u;
}
inline uint16_t filter(uint16_t raw,uint16_t previous,bool sampled) {
  return sampled ? (uint16_t)((3UL*previous+raw)/4UL) : raw;
}
inline bool decode(const uint8_t *p, size_t size, Control &out) {
  if (size != ControlSize) return false;
  Control value = {}; value.sequence = read16(p);
  for (uint8_t i = 0; i < ServoCount; ++i) {
    uint16_t angle = read16(p + 2 + 2*i);
    if (angle > 180) return false;
    value.angle[i] = (int16_t)angle;
  }
  out = value; return true;
}
inline void feedback(uint16_t sequence, const uint16_t *pressure, uint8_t flags, uint8_t *out) {
  write16(out, sequence);
  for (uint8_t i = 0; i < PressureCount; ++i) write16(out + 2 + 2*i, pressure[i]);
  out[12] = flags & 0x3fu; // bit5 = verified actuator configuration; bits0..4 = alarms.
}
}
#endif
