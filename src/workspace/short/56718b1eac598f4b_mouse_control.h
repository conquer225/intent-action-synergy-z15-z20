#pragma once

#include <stdint.h>

namespace eye_mouse {

struct Report {
  uint8_t buttons;
  int8_t x;
  int8_t y;
  int8_t wheel;
};
static_assert(sizeof(Report) == 4, "Mouse input report must contain exactly four bytes");

enum class Action { Next, Previous, SwipeUp, SwipeDown, Left, Right, Up, Down };
enum class Result { Accepted, NotReady, NotArmed, Busy, Cooldown };

inline bool reached(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}

class Controller {
 public:
  static constexpr uint32_t ArmMs = 30000;
  static constexpr uint32_t CooldownMs = 1000;
  static constexpr uint32_t ReportIntervalMs = 20;
  static constexpr uint32_t MaxActionMs = 1500;
  static constexpr uint8_t DragSteps = 24;

  void resetLink(bool ready) {
    ready_ = ready;
    armed_ = false;
    active_ = false;
    releasePending_ = true;
    cooling_ = false;
  }

  bool arm(uint32_t now) {
    if (!ready_) return false;
    armed_ = true;
    armedUntil_ = now + ArmMs;
    return true;
  }

  void stop() {
    armed_ = false;
    active_ = false;
    releasePending_ = true;
  }

  bool armed(uint32_t now) const {
    return ready_ && armed_ && !reached(now, armedUntil_);
  }
  bool active() const { return active_; }
  bool ready() const { return ready_; }

  Result start(Action action, uint32_t now) {
    if (!ready_) return Result::NotReady;
    if (!armed(now)) return Result::NotArmed;
    if (active_) return Result::Busy;
    if (cooling_ && !reached(now, cooldownUntil_)) return Result::Cooldown;
    action_ = action;
    phase_ = 0;
    nextReport_ = now;
    actionUntil_ = now + MaxActionMs;
    active_ = true;
    return Result::Accepted;
  }

  bool poll(uint32_t now, Report &report) {
    if (armed_ && reached(now, armedUntil_)) stop();
    if (active_ && reached(now, actionUntil_)) stop();
    if (!ready_) return false;
    if (releasePending_) {
      releasePending_ = false;
      report = {0, 0, 0, 0};
      return true;
    }
    if (!active_ || !reached(now, nextReport_)) return false;
    nextReport_ = now + ReportIntervalMs;
    report = {0, 0, 0, 0};
    switch (action_) {
      case Action::Next: report.wheel = -1; break;
      case Action::Previous: report.wheel = 1; break;
      case Action::Left: report.x = -20; break;
      case Action::Right: report.x = 20; break;
      case Action::Up: report.y = -20; break;
      case Action::Down: report.y = 20; break;
      case Action::SwipeUp:
      case Action::SwipeDown:
        if (phase_ == 0) {
          report.buttons = 1;
        } else if (phase_ <= DragSteps) {
          report.buttons = 1;
          report.y = action_ == Action::SwipeUp ? -12 : 12;
        } else if (phase_ == DragSteps + 1) {
          // Release before retracing. Return motion never holds a button.
        } else if (phase_ <= 2 * DragSteps + 1) {
          report.y = action_ == Action::SwipeUp ? 12 : -12;
        } else {
          finish(now);
        }
        ++phase_;
        return true;
    }
    finish(now);
    return true;
  }

 private:
  void finish(uint32_t now) {
    active_ = false;
    cooling_ = true;
    cooldownUntil_ = now + CooldownMs;
  }

  bool ready_ = false;
  bool armed_ = false;
  bool active_ = false;
  bool releasePending_ = true;
  bool cooling_ = false;
  uint32_t armedUntil_ = 0;
  uint32_t nextReport_ = 0;
  uint32_t cooldownUntil_ = 0;
  uint32_t actionUntil_ = 0;
  uint8_t phase_ = 0;
  Action action_ = Action::Next;
};

}  // namespace eye_mouse
