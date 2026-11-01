#ifndef PENDULUM_LINK_H
#define PENDULUM_LINK_H
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include "BridgeProtocol.h"

class PendulumLink {
 public:
  void begin();
  void tick(uint32_t nowMs, const ControlFrame &desired);
  bool linked() const { return session.linked(); }
  uint32_t reconnectCount() const { return transitions; }
  int stmState() const { return statusSeen ? status.state : -1; }
  int stmBlocked() const { return statusSeen ? status.blocked : -1; }
  int stmLinked() const { return statusSeen ? status.linked : -1; }
  bool neutralWaiting() const { return neutralPending; }
  bool stmFresh(uint32_t nowMs) const;
  void forceStop();
  void armNeutral();
  bool neutralReady() const { return linked() && !neutralPending; }
 private:
  WiFiUDP udp;
  pendulum_bridge::ClientSession session;
  pendulum_bridge::StmStatus status;
  bool socketReady = false, observedLink = false, statusSeen = false;
  bool neutralPending = false;
  uint32_t neutralSequence = 0;
  uint32_t transitions = 0, lastSend = 0, lastRetry = 0, statusAt = 0;
  void startSession(uint32_t nowMs);
  void observeTransition();
  void transmit(const pendulum_bridge::Message &message, uint32_t ip, uint16_t port);
  void acceptStatus(const pendulum_bridge::Message &message, uint32_t nowMs);
};
#endif
