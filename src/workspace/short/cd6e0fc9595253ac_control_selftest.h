#pragma once
#define GL_MOUSE_CHECK(condition) do { if (!(condition)) return #condition; } while (0)
#include <initializer_list>
#include "mouse_control.h"
#include "hid_report_map.h"
#include "network_guard.h"

namespace eye_mouse_test {
using namespace eye_mouse;

static const char *prepare(Controller &control, uint32_t now) {
  control.resetLink(true);
  Report release;
  GL_MOUSE_CHECK(control.poll(now, release));
  GL_MOUSE_CHECK(release.buttons == 0 && release.x == 0 && release.y == 0 && release.wheel == 0);
  GL_MOUSE_CHECK(control.arm(now));
  return nullptr;
}

inline const char *run() {
  Controller control;
  Report report;
  GL_MOUSE_CHECK(!control.arm(0));
  GL_MOUSE_CHECK(control.start(Action::Next, 0) == Result::NotReady);
  GL_MOUSE_CHECK(!control.poll(0, report));
  control.resetLink(true);
  GL_MOUSE_CHECK(control.start(Action::Next, 0) == Result::NotArmed);
  GL_MOUSE_CHECK(prepare(control, 100) == nullptr);
  GL_MOUSE_CHECK(control.start(Action::Next, 100) == Result::Accepted);
  GL_MOUSE_CHECK(control.poll(100, report) && report.wheel == -1 && report.buttons == 0);
  GL_MOUSE_CHECK(!control.poll(200, report));
  GL_MOUSE_CHECK(control.start(Action::Previous, 101) == Result::Cooldown);
  GL_MOUSE_CHECK(control.start(Action::Previous, 1100) == Result::Accepted);
  GL_MOUSE_CHECK(control.poll(1100, report) && report.wheel == 1);

  for (Action action : {Action::SwipeUp, Action::SwipeDown}) {
    GL_MOUSE_CHECK(prepare(control, 0) == nullptr);
    GL_MOUSE_CHECK(control.start(action, 0) == Result::Accepted);
    GL_MOUSE_CHECK(control.start(Action::Next, 0) == Result::Busy);
    GL_MOUSE_CHECK(control.poll(0, report) && report.buttons == 1 && report.y == 0);
    GL_MOUSE_CHECK(!control.poll(19, report));
    int distance = 0;
    for (unsigned phase = 1; phase <= Controller::DragSteps; ++phase) {
      GL_MOUSE_CHECK(control.poll(phase * 20, report));
      GL_MOUSE_CHECK(report.buttons == 1 && report.x == 0 && report.wheel == 0);
      distance += report.y;
    }
    GL_MOUSE_CHECK(distance == (action == Action::SwipeUp ? -288 : 288));
    GL_MOUSE_CHECK(control.poll(500, report) && report.buttons == 0 && report.y == 0);
    int returnDistance = 0;
    for (unsigned phase = 26; phase <= 49; ++phase) {
      GL_MOUSE_CHECK(control.poll(phase * 20, report));
      GL_MOUSE_CHECK(report.buttons == 0 && report.x == 0 && report.wheel == 0);
      returnDistance += report.y;
    }
    GL_MOUSE_CHECK(distance + returnDistance == 0);
    GL_MOUSE_CHECK(control.poll(1000, report) && report.buttons == 0 && report.y == 0);
    GL_MOUSE_CHECK(!control.active());
    GL_MOUSE_CHECK(!control.poll(1020, report));
  }

  GL_MOUSE_CHECK(prepare(control, 0) == nullptr);
  GL_MOUSE_CHECK(control.start(Action::SwipeUp, 0) == Result::Accepted);
  GL_MOUSE_CHECK(control.poll(0, report));
  control.stop();
  GL_MOUSE_CHECK(control.poll(1, report) && report.buttons == 0 && report.y == 0);
  GL_MOUSE_CHECK(!control.active() && !control.armed(1));
  GL_MOUSE_CHECK(!control.poll(20, report));
  GL_MOUSE_CHECK(control.start(Action::Next, 20) == Result::NotArmed);

  GL_MOUSE_CHECK(prepare(control, 0) == nullptr);
  GL_MOUSE_CHECK(control.start(Action::SwipeDown, 29990) == Result::Accepted);
  GL_MOUSE_CHECK(control.poll(29990, report) && report.buttons == 1);
  GL_MOUSE_CHECK(control.poll(30000, report) && report.buttons == 0);
  GL_MOUSE_CHECK(!control.armed(30000) && !control.active());

  GL_MOUSE_CHECK(prepare(control, 0) == nullptr);
  GL_MOUSE_CHECK(control.start(Action::SwipeUp, 0) == Result::Accepted);
  GL_MOUSE_CHECK(control.poll(0, report) && report.buttons == 1);
  GL_MOUSE_CHECK(control.poll(Controller::MaxActionMs, report) && report.buttons == 0);
  GL_MOUSE_CHECK(!control.active() && !control.armed(Controller::MaxActionMs));

  GL_MOUSE_CHECK(prepare(control, 0) == nullptr);
  GL_MOUSE_CHECK(control.start(Action::SwipeUp, 0) == Result::Accepted);
  GL_MOUSE_CHECK(control.poll(0, report));
  control.resetLink(false);
  GL_MOUSE_CHECK(!control.poll(20, report));
  control.resetLink(true);
  GL_MOUSE_CHECK(control.poll(21, report) && report.buttons == 0);
  GL_MOUSE_CHECK(!control.armed(21) && !control.active());
  GL_MOUSE_CHECK(!control.poll(40, report));

  uint32_t nearWrap = 0xfffffff0U;
  GL_MOUSE_CHECK(prepare(control, nearWrap) == nullptr);
  GL_MOUSE_CHECK(control.armed(nearWrap + 100U));
  GL_MOUSE_CHECK(control.start(Action::Next, nearWrap) == Result::Accepted);
  GL_MOUSE_CHECK(control.poll(nearWrap, report));
  GL_MOUSE_CHECK(control.start(Action::Next, nearWrap + 999U) == Result::Cooldown);
  GL_MOUSE_CHECK(control.start(Action::Next, nearWrap + 1000U) == Result::Accepted);
  GL_MOUSE_CHECK(!control.armed(nearWrap + Controller::ArmMs));

  for (Action action : {Action::Left, Action::Right, Action::Up, Action::Down}) {
    GL_MOUSE_CHECK(prepare(control, 0) == nullptr);
    GL_MOUSE_CHECK(control.start(action, 0) == Result::Accepted);
    GL_MOUSE_CHECK(control.poll(0, report));
    GL_MOUSE_CHECK(report.buttons == 0 && report.wheel == 0);
    GL_MOUSE_CHECK(!control.active());
  }

  // Verify the actual descriptor's report bit count, not a duplicate descriptor.
  unsigned bits = 0, size = 0, count = 0, reportId = 0;
  for (unsigned i = 0; i < sizeof(MouseReportMap);) {
    uint8_t tag = MouseReportMap[i++];
    unsigned width = tag & 3;
    if (width == 3) width = 4;
    unsigned value = 0;
    for (unsigned byte = 0; byte < width; ++byte) value |= MouseReportMap[i++] << (byte * 8);
    if (tag == 0x75) size = value;
    if (tag == 0x95) count = value;
    if (tag == 0x85) reportId = value;
    if ((tag & 0xfc) == 0x80) bits += size * count;
  }
  GL_MOUSE_CHECK(reportId == 1 && bits == 32 && sizeof(Report) == 4);

  eye_network::Guard guard;
  using NetOp = eye_network::Operation;
  using NetResult = eye_network::Result;
  GL_MOUSE_CHECK(guard.apply(1, NetOp::Next, 0, true) == NetResult::Disabled);
  GL_MOUSE_CHECK(guard.apply(1, NetOp::ArmVirtual, 0, true) == NetResult::Sequence);
  GL_MOUSE_CHECK(guard.apply(2, NetOp::ArmVirtual, 0, false) == NetResult::Armed);
  GL_MOUSE_CHECK(guard.apply(3, NetOp::Next, 1, false) == NetResult::Accepted);
  GL_MOUSE_CHECK(guard.apply(4, NetOp::Previous, 2, false) == NetResult::Cooldown);
  GL_MOUSE_CHECK(guard.tick(600, true, false));
  GL_MOUSE_CHECK(guard.mode() == eye_network::Mode::Off);
  GL_MOUSE_CHECK(guard.apply(5, NetOp::ArmHid, 1000, false) == NetResult::BleNotReady);
  GL_MOUSE_CHECK(guard.apply(6, NetOp::ArmHid, 1000, true) == NetResult::Armed);
  GL_MOUSE_CHECK(guard.apply(7, NetOp::Heartbeat, 1500, true) == NetResult::Heartbeat);
  GL_MOUSE_CHECK(!guard.tick(1501, true, true));
  GL_MOUSE_CHECK(guard.tick(1502, false, true));
  GL_MOUSE_CHECK(guard.apply(8, NetOp::ArmHid, nearWrap, true) == NetResult::Armed);
  GL_MOUSE_CHECK(guard.tick(nearWrap + 1U, true, false));
  eye_network::Frame frame;
  const char *valid = "G1|0123456789abcdef|0123456789abcdef|4294967295|NEXT|0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
  GL_MOUSE_CHECK(eye_network::parse(valid, frame) && frame.sequence == 0xffffffffU);
  GL_MOUSE_CHECK(!eye_network::parse("G1|missing", frame));
  GL_MOUSE_CHECK(!eye_network::parse("G1|0123456789abcdef|0123456789abcdef|4294967296|NEXT|0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", frame));
  return nullptr;
}


}  // namespace eye_mouse_test
#undef GL_MOUSE_CHECK
