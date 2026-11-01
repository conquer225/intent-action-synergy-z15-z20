#ifndef PENDULUM_BRIDGE_PROTOCOL_H
#define PENDULUM_BRIDGE_PROTOCOL_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "ControlProtocol.h"

// Fixed-size, explicitly encoded wire data: no C++ structure layout on the wire.
namespace pendulum_bridge {
constexpr uint16_t PORT = 9001;
constexpr size_t WIRE_SIZE = 32;
constexpr uint32_t LEASE_MS = 250;
constexpr uint32_t SEND_MS = 50;
constexpr uint32_t RETRY_MS = 100;
constexpr uint32_t STATUS_FRESH_MS = 1000;
constexpr uint32_t BOOT_GUARD_MS = CONTROL_TIMEOUT_MS + 50;
enum Type : uint8_t { HELLO = 1, CHALLENGE, READY, CONTROL, ACK, STATUS };
struct Message {
  Type type = HELLO;
  uint32_t session = 0, nonce = 0, sequence = 0;
  uint8_t payload[14] = {};
};
struct StmStatus {
  uint8_t state = 0, linked = 0, blocked = 1, fresh = 0;
  int16_t target = 0;
  uint32_t report = 0;
  uint16_t age = 65535;
};
inline bool newer(uint32_t next, uint32_t previous) {
  const uint32_t delta = next - previous;
  return delta != 0 && delta < 0x80000000UL;
}
inline uint32_t read32(const uint8_t *p) {
  return uint32_t(p[0]) | (uint32_t(p[1]) << 8) | (uint32_t(p[2]) << 16) | (uint32_t(p[3]) << 24);
}
inline void write32(uint8_t *p, uint32_t value) {
  for (unsigned i = 0; i < 4; ++i) p[i] = uint8_t(value >> (8 * i));
}
inline uint16_t read16(const uint8_t *p) { return uint16_t(p[0]) | (uint16_t(p[1]) << 8); }
inline void write16(uint8_t *p, uint16_t value) { p[0] = uint8_t(value); p[1] = uint8_t(value >> 8); }
inline Message make(Type type, uint32_t session, uint32_t nonce, uint32_t sequence) {
  Message m; m.type = type; m.session = session; m.nonce = nonce; m.sequence = sequence; return m;
}
inline void encode(const Message &m, uint8_t *out) {
  out[0] = 'P'; out[1] = 'B'; out[2] = 1; out[3] = uint8_t(m.type);
  write32(out + 4, m.session); write32(out + 8, m.nonce); write32(out + 12, m.sequence);
  memcpy(out + 16, m.payload, sizeof(m.payload));
  write16(out + 30, Control_Crc(out, 30));
}
inline bool zeros(const uint8_t *p, size_t size) {
  while (size--) if (*p++) return false;
  return true;
}
inline bool readControl(const Message &m, ControlFrame &out) {
  if (m.type != CONTROL || !zeros(m.payload + CONTROL_FRAME_SIZE, sizeof(m.payload) - CONTROL_FRAME_SIZE)) return false;
  ControlParser parser = {};
  for (unsigned i = 0; i < CONTROL_FRAME_SIZE; ++i) {
    bool complete = Control_ParseByte(&parser, m.payload[i], &out) != 0;
    if (complete) return i + 1 == CONTROL_FRAME_SIZE;
  }
  return false;
}
inline void setControl(Message &m, const ControlFrame &frame) { Control_Encode(&frame, m.payload); }
inline void setStatus(Message &m, const StmStatus &s) {
  m.payload[0] = s.state; write16(m.payload + 1, uint16_t(s.target));
  m.payload[3] = s.linked; m.payload[4] = s.blocked; m.payload[5] = s.fresh;
  write32(m.payload + 6, s.report); write16(m.payload + 10, s.age);
  m.payload[12] = m.payload[13] = 0;
}
inline bool readStatus(const Message &m, StmStatus &s) {
  if ((m.type != ACK && m.type != STATUS) || m.payload[3] > 1 || m.payload[4] > 1 ||
      m.payload[5] > 1 || !zeros(m.payload + 12, 2)) return false;
  s.state = m.payload[0]; s.target = int16_t(read16(m.payload + 1));
  s.linked = m.payload[3]; s.blocked = m.payload[4]; s.fresh = m.payload[5];
  s.report = read32(m.payload + 6); s.age = read16(m.payload + 10);
  return s.target >= -8999 && s.target <= 8999 && (!s.fresh || s.age < STATUS_FRESH_MS);
}
inline bool decode(const uint8_t *bytes, size_t size, Message &m) {
  if (size != WIRE_SIZE || bytes[0] != 'P' || bytes[1] != 'B' || bytes[2] != 1 ||
      bytes[3] < HELLO || bytes[3] > STATUS || read16(bytes + 30) != Control_Crc(bytes, 30)) return false;
  m.type = Type(bytes[3]); m.session = read32(bytes + 4); m.nonce = read32(bytes + 8);
  m.sequence = read32(bytes + 12); memcpy(m.payload, bytes + 16, sizeof(m.payload));
  if (!m.session) return false;
  if (m.type == HELLO) return m.nonce == 0 && m.sequence == 0 && zeros(m.payload, sizeof(m.payload));
  if (!m.nonce) return false;
  if (m.type == CHALLENGE) return m.sequence == 0 && zeros(m.payload, sizeof(m.payload));
  if (m.type == READY) return m.sequence == 1 && zeros(m.payload, sizeof(m.payload));
  if (m.type == CONTROL) { ControlFrame frame; return readControl(m, frame); }
  StmStatus status; return readStatus(m, status);
}

// Strict, bounded STM32 status parser. No accepted prefixes or trailing text.
inline bool parseStatusLine(const char *line, size_t length, StmStatus &status) {
  if (!line || length < 9 || length > 47 || line[0] != 'S' || line[1] != ',') return false;
  size_t pos = 2;
  int32_t fields[4] = {};
  for (unsigned field = 0; field < 4; ++field) {
    bool negative = pos < length && line[pos] == '-';
    if (negative) ++pos;
    const size_t first = pos;
    int32_t value = 0;
    while (pos < length && line[pos] >= '0' && line[pos] <= '9') {
      if (pos - first >= 5) return false;
      value = value * 10 + (line[pos++] - '0');
    }
    if (pos == first) return false;
    fields[field] = negative ? -value : value;
    if (field < 3 && (pos == length || line[pos++] != ',')) return false;
  }
  if (pos != length || fields[0] < 0 || fields[0] > 255 || fields[1] < -8999 || fields[1] > 8999 ||
      fields[2] < 0 || fields[2] > 1 || fields[3] < 0 || fields[3] > 1) return false;
  status.state = uint8_t(fields[0]); status.target = int16_t(fields[1]);
  status.linked = uint8_t(fields[2]); status.blocked = uint8_t(fields[3]); return true;
}

struct GatewayAction {
  bool reply = false, serial = false;
  Message response;
  ControlFrame output = {};
};
// This is the actual gateway lease/arming logic used by the ESP-01S sketch.
// peer is an IPv4 address represented as uint32_t; the sender's UDP port is pinned too.
class GatewaySession {
 public:
  void begin(uint32_t now) { bootAt = now; reset(); serialSequence = 0; }
  bool active() const { return live; }
  bool isArmed() const { return armed; }
  uint32_t peer() const { return peerIp; }
  uint16_t port() const { return peerPort; }
  uint32_t currentSession() const { return session; }
  uint32_t currentNonce() const { return nonce; }
  uint32_t lastSequence() const { return receivedSequence; }
  GatewayAction expire(uint32_t now) {
    GatewayAction result;
    if (live && uint32_t(now - lastControl) >= LEASE_MS) {
      result.serial = true; result.output = stopFrame(); reset();
    } else if (pending && uint32_t(now - pendingAt) >= LEASE_MS) reset();
    return result;
  }
  GatewayAction disconnect() {
    GatewayAction result;
    if (live) { result.serial = true; result.output = stopFrame(); }
    reset(); return result;
  }
  GatewayAction receive(const Message &m, uint32_t ip, uint16_t senderPort, uint32_t now, uint32_t randomNonce) {
    GatewayAction result;
    // Avoid inheriting a still-live pre-reboot STM command while UART sequence restarts.
    if (uint32_t(now - bootAt) < BOOT_GUARD_MS || !ip || !senderPort) return result;
    if (m.type == HELLO && !live && m.session && m.nonce == 0 && m.sequence == 0 && zeros(m.payload, sizeof(m.payload))) {
      if (!pending) {
        if (!randomNonce) return result;
        pending = true; peerIp = ip; peerPort = senderPort; session = m.session;
        nonce = randomNonce; pendingAt = now;
      }
      if (ip == peerIp && senderPort == peerPort && m.session == session) {
        result.reply = true; result.response = make(CHALLENGE, session, nonce, 0);
      }
      return result;
    }
    if (ip != peerIp || senderPort != peerPort || m.session != session || m.nonce != nonce || !nonce) return result;
    if (m.type == READY && m.sequence == 1 && zeros(m.payload, sizeof(m.payload))) {
      if (pending && uint32_t(now - pendingAt) < LEASE_MS) {
        pending = false; live = true; armed = false; receivedSequence = 1; lastControl = now;
        result.serial = true; result.output = stopFrame();
      }
      // Handshake retries can recover a lost ACK, but cannot extend the lease.
      if (live && receivedSequence == 1) {
        result.reply = true; result.response = make(ACK, session, nonce, 1);
      }
      return result;
    }
    if (!live || uint32_t(now - lastControl) >= LEASE_MS || m.type != CONTROL || !newer(m.sequence, receivedSequence)) return result;
    ControlFrame frame;
    if (!readControl(m, frame)) return result;
    receivedSequence = m.sequence; lastControl = now;
    const bool valid = (frame.flags & CONTROL_VALID) != 0;
    const bool grip = (frame.flags & CONTROL_GRIP) != 0;
    if (!valid) {
      armed = false; event = frame.event_id; result.output = stopFrame();
      result.output.event_id = event;
    } else if (!armed) {
      event = frame.event_id;
      if (!grip) {
        // First release establishes the event baseline, never replays an old turn.
        armed = true; result.output = frame; result.output.sequence = serialSequence++;
        result.output.direction = 0;
      } else {
        result.output = stopFrame(); result.output.event_id = event;
      }
    } else {
      result.output = frame; result.output.sequence = serialSequence++;
      if (frame.event_id == event) result.output.direction = 0;
      event = frame.event_id;
    }
    result.serial = true; result.reply = true;
    result.response = make(ACK, session, nonce, receivedSequence); return result;
  }
 private:
  bool pending = false, live = false, armed = false;
  uint32_t bootAt = 0, peerIp = 0, session = 0, nonce = 0, pendingAt = 0, lastControl = 0, receivedSequence = 0;
  uint16_t peerPort = 0;
  uint8_t serialSequence = 0, event = 0;
  ControlFrame stopFrame() { ControlFrame f = {serialSequence++, 0, event, 0}; return f; }
  void reset() {
    pending = live = armed = false; peerIp = session = nonce = receivedSequence = 0;
    peerPort = 0; event = 0;
  }
};

// The S3 adapter delegates reply acceptance and lease timing to this tested class.
class ClientSession {
 public:
  enum Phase : uint8_t { IDLE, DISCOVER, CONFIRM, LINKED };
  void begin(uint32_t newSession, uint32_t now) {
    phase = newSession ? DISCOVER : IDLE; session = newSession; nonce = peerIp = 0;
    peerPort = 0; sent = acknowledged = 0; started = lastAck = now;
  }
  void disconnect() { phase = IDLE; }
  bool linked() const { return phase == LINKED; }
  Phase state() const { return phase; }
  uint32_t peer() const { return peerIp; }
  uint16_t port() const { return peerPort; }
  uint32_t sessionId() const { return session; }
  uint32_t nonceId() const { return nonce; }
  bool expired(uint32_t now) const {
    return (phase == LINKED && uint32_t(now - lastAck) >= LEASE_MS) ||
           ((phase == DISCOVER || phase == CONFIRM) && uint32_t(now - started) >= 1000);
  }
  Message handshake() const { return make(phase == CONFIRM ? READY : HELLO, session, phase == CONFIRM ? nonce : 0, phase == CONFIRM ? 1 : 0); }
  Message control(const ControlFrame &frame) {
    Message m = make(CONTROL, session, nonce, ++sent); setControl(m, frame); return m;
  }
  bool receive(const Message &m, uint32_t ip, uint16_t senderPort, uint32_t now) {
    if (!session || m.session != session || !ip || senderPort != PORT) return false;
    if (phase == DISCOVER && m.type == CHALLENGE && m.nonce && m.sequence == 0 && zeros(m.payload, sizeof(m.payload))) {
      nonce = m.nonce; peerIp = ip; peerPort = senderPort; phase = CONFIRM; return true;
    }
    if (ip != peerIp || senderPort != peerPort || m.nonce != nonce || !nonce) return false;
    StmStatus status;
    if (!readStatus(m, status)) return false;
    if (phase == CONFIRM && m.type == ACK && m.sequence == 1) {
      phase = LINKED; sent = acknowledged = 1; lastAck = now; return true;
    }
    if (phase != LINKED || uint32_t(now - lastAck) >= LEASE_MS || newer(m.sequence, sent)) return false;
    if (m.type == STATUS) return true; // Feedback never substitutes for a fresh control ACK.
    if (m.type != ACK || !newer(m.sequence, acknowledged)) return false;
    acknowledged = m.sequence; lastAck = now; return true;
  }
 private:
  Phase phase = IDLE;
  uint32_t session = 0, nonce = 0, peerIp = 0, sent = 0, acknowledged = 0, started = 0, lastAck = 0;
  uint16_t peerPort = 0;
};
} // namespace pendulum_bridge
#endif
