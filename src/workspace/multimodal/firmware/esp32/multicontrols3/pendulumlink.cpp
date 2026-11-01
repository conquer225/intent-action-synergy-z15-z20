#include "PendulumLink.h"
#include <esp_system.h>

using namespace pendulum_bridge;

void PendulumLink::begin() {
  udp.stop(); socketReady = observedLink = statusSeen = neutralPending = false;
  transitions = 0; session.disconnect();
}

bool PendulumLink::stmFresh(uint32_t nowMs) const {
  return session.linked() && statusSeen && status.fresh && uint32_t(nowMs - statusAt) < STATUS_FRESH_MS;
}

void PendulumLink::observeTransition() {
  if (session.linked() != observedLink) {
    observedLink = session.linked(); ++transitions;
    if (!observedLink) { statusSeen = false; neutralPending = false; }
  }
}

void PendulumLink::startSession(uint32_t nowMs) {
  uint32_t id = esp_random();
  if (!id || id == session.sessionId()) id ^= 0x6e1d9ac3UL;
  if (!id) id = 1;
  session.begin(id, nowMs); lastRetry = nowMs - RETRY_MS; lastSend = nowMs - SEND_MS;
  statusSeen = false;
}

void PendulumLink::transmit(const Message &message, uint32_t ip, uint16_t port) {
  uint8_t bytes[WIRE_SIZE]; encode(message, bytes);
  if (udp.beginPacket(IPAddress(ip), port)) { udp.write(bytes, sizeof(bytes)); udp.endPacket(); }
}

void PendulumLink::acceptStatus(const Message &message, uint32_t nowMs) {
  StmStatus incoming;
  if (!readStatus(message, incoming) || !incoming.fresh || !incoming.report) return;
  if (statusSeen && !newer(incoming.report, status.report)) return;
  status = incoming; statusSeen = true; statusAt = nowMs - incoming.age;
}

void PendulumLink::tick(uint32_t nowMs, const ControlFrame &desired) {
  if (WiFi.status() != WL_CONNECTED) {
    session.disconnect(); observeTransition();
    if (socketReady) { udp.stop(); socketReady = false; }
    return;
  }
  if (!socketReady) {
    if (!udp.begin(PORT)) return;
    socketReady = true; startSession(nowMs);
  }
  if (session.expired(nowMs)) {
    session.disconnect(); observeTransition(); startSession(nowMs);
  }
  // A bounded batch keeps UDP floods from starving the 500 Hz muscle sampler.
  for (unsigned n = 0; n < 4; ++n) {
    int length = udp.parsePacket(); if (!length) break;
    const uint32_t ip = uint32_t(udp.remoteIP()); const uint16_t port = udp.remotePort();
    if (length != int(WIRE_SIZE)) { udp.flush(); continue; }
    uint8_t bytes[WIRE_SIZE]; int received = udp.read(bytes, sizeof(bytes));
    Message message;
    if (received != int(WIRE_SIZE) || !decode(bytes, sizeof(bytes), message) || !session.receive(message, ip, port, nowMs)) continue;
    if (message.type == CHALLENGE) {
      transmit(session.handshake(), session.peer(), session.port()); lastRetry = nowMs;
    } else {
      acceptStatus(message, nowMs);
      if (neutralPending && message.type == ACK &&
          (message.sequence == neutralSequence || newer(message.sequence,neutralSequence)))
        neutralPending = false;
    }
    observeTransition();
  }
  if (session.linked()) {
    if (uint32_t(nowMs - lastSend) >= SEND_MS) {
      ControlFrame neutral = {0, CONTROL_VALID, 0, 0};
      transmit(session.control(neutralPending ? neutral : desired), session.peer(), session.port()); lastSend = nowMs;
    }
  } else if (uint32_t(nowMs - lastRetry) >= RETRY_MS) {
    uint32_t destination;
    if (session.state() == ClientSession::CONFIRM) destination = session.peer();
    else {
      IPAddress local = WiFi.localIP(), mask = WiFi.subnetMask(), broadcast;
      for (unsigned i = 0; i < 4; ++i) broadcast[i] = uint8_t(local[i] | uint8_t(~mask[i]));
      destination = uint32_t(broadcast);
    }
    transmit(session.handshake(), destination, PORT); lastRetry = nowMs;
  }
}

void PendulumLink::forceStop() {
  neutralPending = false;
  if (!session.linked() || !socketReady || WiFi.status() != WL_CONNECTED) return;
  ControlFrame stopped = {0, 0, 0, 0};
  transmit(session.control(stopped), session.peer(), session.port()); lastSend = millis();
}

void PendulumLink::armNeutral() {
  if (!session.linked() || !socketReady || WiFi.status() != WL_CONNECTED) return;
  ControlFrame neutral = {0, CONTROL_VALID, 0, 0};
  Message message = session.control(neutral);
  neutralPending = true; neutralSequence = message.sequence;
  transmit(message,session.peer(),session.port()); lastSend = millis();
}
