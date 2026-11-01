#include <cassert>
#include <cstdio>
#include <cstring>
#include "../esp32/MultiControlS3/GloveLogic.h"
#include "../esp32/MultiControlS3/ControlInput.h"
#include "../esp32/MultiControlS3/ControlProtocol.h"

int main() {
  assert(distinctPins());
  PotCalibration cal = {};
  cal.tag = CAL_TAG;
  for (uint8_t i = 0; i < POT_COUNT; ++i) {
    cal.open[i] = (i & 1) ? 3000 : 1000;
    cal.closed[i] = (i & 1) ? 1000 : 3000;
  }
  assert(calibrationValid(cal));
  for (uint8_t i = 0; i < POT_COUNT; ++i) {
    assert(potAngle(cal.open[i], i, cal) == SERVO_OPEN[i]);
    assert(potAngle(cal.closed[i], i, cal) == SERVO_CLOSED[i]);
    assert(potAngle(2000, i, cal) == (SERVO_OPEN[i] + SERVO_CLOSED[i]) / 2);
    // Outside the measured travel, clamp instead of moving beyond servo limits.
    assert(potAngle(0, i, cal) == ((i & 1) ? SERVO_CLOSED[i] : SERVO_OPEN[i]));
    assert(potAngle(4095, i, cal) == ((i & 1) ? SERVO_OPEN[i] : SERVO_CLOSED[i]));
  }
  PotCalibration bad = cal;
  bad.closed[5] = bad.open[5]; assert(!calibrationValid(bad));
  assert(potAngle(1000, 5, bad) == 180);
  bad = cal; bad.open[0] = 4096; assert(!calibrationValid(bad));
  bad = cal; bad.tag ^= 1; assert(!calibrationValid(bad));
  bad = cal; bad.closed[0] = bad.open[0] + 79; assert(!calibrationValid(bad));
  bad.closed[0]++; assert(calibrationValid(bad));
  bad = cal; bad.closed[1] = bad.open[1] - 79; assert(!calibrationValid(bad));
  bad.closed[1]--; assert(calibrationValid(bad));

  // Golden AVR wire format: 2-byte sequence + six little-endian int16 angles.
  int16_t angles[] = {180,110,145,0,181,-3};
  uint8_t bytes[HAND_CONTROL_SIZE] = {};
  encodeHand(0x1234, angles, bytes);
  const uint8_t expected[] = {0x34,0x12,180,0,110,0,145,0,0,0,180,0,0,0};
  static_assert(sizeof(expected) == 14, "Nano packet size changed");
  assert(memcmp(bytes, expected, sizeof(expected)) == 0);
  encodeHand(0xffff, angles, bytes); assert(readLE16(bytes) == 0xffff);
  encodeHand(0, angles, bytes); assert(readLE16(bytes) == 0);

  HandFeedback feedback = {};
  uint8_t ack[] = {0x34,0x12,0xff,0x03,0,0,0,0,0,0,0,0,0x21};
  assert(decodeFeedback(ack, 13, feedback));
  assert(feedback.sequence == 0x1234 && feedback.pressureRaw[0] == 1023 && feedback.flags == 0x21);
  assert(!decodeFeedback(ack, 5, feedback)); // Legacy one-channel ACK is incompatible.
  assert(!decodeFeedback(ack, 14, feedback)); // Struct padding must never affect wire size.
  ack[2] = 0; ack[3] = 4; assert(!decodeFeedback(ack, 13, feedback));
  ack[3] = 0; ack[12] = 0x40; assert(!decodeFeedback(ack, 13, feedback));

  GripGate grip;
  grip.update(110, true); grip.update(110, true); assert(!grip.gripped);
  grip.update(40, true); grip.update(40, true); assert(grip.armed);
  grip.update(100, true); grip.update(100, true); assert(grip.gripped);
  grip.update(75, true); assert(grip.gripped);
  grip.update(50, true); grip.update(50, true); assert(!grip.gripped);
  grip.update(110, false); assert(!grip.armed);
  TurnGate turn;
  turn.update(0, 0, true); turn.update(0, 200, true);
  turn.update(30, 300, true); assert(turn.update(30, 450, true) == 1);
  assert(turn.update(30, 900, true) == 0);
  turn.update(0, 1000, true); turn.update(0, 1200, true);
  turn.update(-30, 1300, true); assert(turn.update(-30, 1450, true) == -1);

  ControlFrame frame = {1, CONTROL_VALID, 2, CONTROL_LEFT}, decoded = {};
  uint8_t pendulum[CONTROL_FRAME_SIZE]; Control_Encode(&frame, pendulum);
  ControlParser parser = {}; int accepted = 0;
  for (uint8_t byte : pendulum) accepted += Control_ParseByte(&parser, byte, &decoded);
  assert(accepted == 1 && decoded.event_id == 2 && decoded.direction == CONTROL_LEFT);
  puts("MultiControlS3: calibration, AVR packets, input gates and UART protocol PASS");
}
