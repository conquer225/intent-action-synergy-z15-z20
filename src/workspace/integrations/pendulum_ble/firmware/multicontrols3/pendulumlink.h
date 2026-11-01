#pragma once
#include <Arduino.h>
#include "ControlProtocol.h"

// Same upper interface as the retained C3 UDP adapter.
class PendulumLink {
 public:
  void begin();
  void tick(uint32_t nowMs,const ControlFrame &desired);
  bool linked() const { return snapshot_.connected; }
  uint32_t reconnectCount() const { return snapshot_.revision; }
  int stmState() const { return snapshot_.state; }
  int stmBlocked() const { return snapshot_.blocked; }
  int stmLinked() const { return snapshot_.stmLinked; }
  bool neutralWaiting() const { return arm_ && snapshot_.armed!=arm_; }
  bool neutralReady() const { return linked() && arm_ && snapshot_.armed==arm_; }
  bool stmFresh(uint32_t nowMs) const { return linked() && snapshot_.seen && uint32_t(nowMs-snapshot_.statusAt)<1000; }
  void forceStop();
  void armNeutral();
  struct Snapshot {
    uint32_t revision=0,armed=0,statusAt=0;
    bool connected=false,seen=false;
    int state=-1,blocked=-1,stmLinked=-1;
  };
 private:
  Snapshot snapshot_;
  uint32_t arm_=0;
};
