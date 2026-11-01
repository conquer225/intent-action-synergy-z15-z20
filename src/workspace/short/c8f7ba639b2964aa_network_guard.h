#pragma once
#include <stdint.h>
#include <string.h>
#include "mouse_control.h"

namespace eye_network {
enum class Mode { Off, Virtual, Hid };
enum class Operation { ArmVirtual, ArmHid, Heartbeat, Next, Previous, Stop };
enum class Result { Armed, Heartbeat, Accepted, Stopped, Sequence, Disabled, Cooldown, BleNotReady };

struct Frame {
  char boot[17];
  char ticket[17];
  uint32_t sequence;
  Operation operation;
  char signature[65];
  char signedText[96];
};

inline bool lowerHex(const char *text, size_t length) {
  for (size_t i = 0; i < length; ++i) {
    if (!((text[i] >= '0' && text[i] <= '9') || (text[i] >= 'a' && text[i] <= 'f'))) return false;
  }
  return text[length] == '\0';
}

inline bool parse(const char *text, Frame &frame) {
  size_t length = strlen(text);
  if (length < 108 || length >= 160) return false;
  char copy[160];
  memcpy(copy, text, length + 1);
  char *fields[6];
  fields[0] = copy;
  unsigned field = 1;
  for (size_t i = 0; i < length; ++i) {
    if (copy[i] == '|') {
      if (field >= 6) return false;
      copy[i] = '\0';
      fields[field++] = copy + i + 1;
    }
  }
  if (field != 6 || strcmp(fields[0], "G1") || !lowerHex(fields[1], 16)
      || !lowerHex(fields[2], 16) || !lowerHex(fields[5], 64)) return false;
  size_t digits = strlen(fields[3]);
  if (!digits || digits > 10 || fields[3][0] == '0') return false;
  uint64_t sequence = 0;
  for (size_t i = 0; i < digits; ++i) {
    if (fields[3][i] < '0' || fields[3][i] > '9') return false;
    sequence = sequence * 10 + fields[3][i] - '0';
  }
  if (sequence > 0xffffffffULL) return false;
  if (!strcmp(fields[4], "ARM_VIRTUAL")) frame.operation = Operation::ArmVirtual;
  else if (!strcmp(fields[4], "ARM_HID")) frame.operation = Operation::ArmHid;
  else if (!strcmp(fields[4], "HEARTBEAT")) frame.operation = Operation::Heartbeat;
  else if (!strcmp(fields[4], "NEXT")) frame.operation = Operation::Next;
  else if (!strcmp(fields[4], "PREV")) frame.operation = Operation::Previous;
  else if (!strcmp(fields[4], "STOP")) frame.operation = Operation::Stop;
  else return false;
  size_t signedLength = length - 65;
  if (signedLength >= sizeof(frame.signedText)) return false;
  memcpy(frame.signedText, text, signedLength);
  frame.signedText[signedLength] = '\0';
  memcpy(frame.boot, fields[1], 17);
  memcpy(frame.ticket, fields[2], 17);
  memcpy(frame.signature, fields[5], 65);
  frame.sequence = static_cast<uint32_t>(sequence);
  return true;
}

class Guard {
 public:
  static constexpr uint32_t LeaseMs = 30000;
  static constexpr uint32_t HeartbeatMs = 600;
  static constexpr uint32_t TicketMs = 200;
  Mode mode() const { return mode_; }
  uint32_t sequence() const { return sequence_; }
  void stop() { mode_ = Mode::Off; }
  bool tick(uint32_t now, bool wifi, bool ble) {
    if (mode_ == Mode::Off) return false;
    if (!wifi || (mode_ == Mode::Hid && !ble) || eye_mouse::reached(now, until_)
        || static_cast<uint32_t>(now - heartbeat_) >= HeartbeatMs) {
      stop();
      return true;
    }
    return false;
  }
  Result apply(uint32_t sequence, Operation operation, uint32_t now, bool ble) {
    if (!sequence || sequence <= sequence_) return Result::Sequence;
    sequence_ = sequence;
    if (operation == Operation::Stop) { stop(); return Result::Stopped; }
    if (operation == Operation::ArmHid || operation == Operation::ArmVirtual) {
      if (operation == Operation::ArmHid && !ble) return Result::BleNotReady;
      mode_ = operation == Operation::ArmHid ? Mode::Hid : Mode::Virtual;
      until_ = now + LeaseMs;
      heartbeat_ = now;
      cooling_ = false;
      return Result::Armed;
    }
    tick(now, true, ble);
    if (mode_ == Mode::Off) return Result::Disabled;
    if (operation == Operation::Heartbeat) { heartbeat_ = now; return Result::Heartbeat; }
    if (cooling_ && !eye_mouse::reached(now, cooldownUntil_)) return Result::Cooldown;
    cooling_ = true;
    cooldownUntil_ = now + 2000;
    return Result::Accepted;
  }
 private:
  Mode mode_ = Mode::Off;
  uint32_t sequence_ = 0, until_ = 0, heartbeat_ = 0, cooldownUntil_ = 0;
  bool cooling_ = false;
};
}
