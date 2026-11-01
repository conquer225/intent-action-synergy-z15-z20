#pragma once
#include "BridgeProtocol.h"

struct BlePendulumInput {
  ControlFrame frame={};
  uint32_t producedAt=0,revision=0,arm=0;
};

// Single-owner session; the worker publishes immutable snapshots to the loop.
class BlePendulumSession {
 public:
  void connection(bool up, uint32_t) {
    if (up == connected_) return;
    connected_ = up; ++revision_;
    seen_ = false; used_ = 0; overflow_ = false;
    pending_=armed_=neutralSent_=false;
  }
  void receive(const uint8_t *data, size_t length, uint32_t now) {
    if (!connected_) return;
    if (used_ && uint32_t(now-lastByte_) > 100) { used_=0; overflow_=false; }
    for (size_t i=0;i<length;++i) {
      const char c=char(data[i]); lastByte_=now;
      if(c=='\r') continue;
      if(c=='\n') {
        pendulum_bridge::StmStatus next;
        if(!overflow_ && pendulum_bridge::parseStatusLine(line_,used_,next)) {
          status_=next; seen_=true; statusAt_=now; ++reports_;
          if(armed_ && (!next.linked || next.blocked)) {
            armed_=pending_=neutralSent_=false;++revision_;
          }
          if(pending_ && neutralSent_ && reports_!=reportBeforeNeutral_ &&
             next.state==0 && next.linked==1 && next.blocked==0) {
            pending_=false;armed_=true;
          }
        }
        used_=0;overflow_=false;
      } else if(!overflow_) {
        if(used_<sizeof(line_)) line_[used_++]=c;
        else { used_=0;overflow_=true; }
      }
    }
  }
  bool linked() const { return connected_; }
  bool fresh(uint32_t now) const { return connected_ && seen_ && uint32_t(now-statusAt_)<1000; }
  int state() const { return seen_?status_.state:-1; }
  int blocked() const { return seen_?status_.blocked:-1; }
  int stmLinked() const { return seen_?status_.linked:-1; }
  uint32_t revision() const { return revision_; }
  uint32_t statusAt() const { return statusAt_; }
  bool neutralReady() const { return connected_ && armed_ && !pending_; }
  ControlFrame output(uint32_t now,const BlePendulumInput &in) {
    ControlFrame out={++sequence_,0,event_,0};
    const bool legal=(in.frame.flags & ~3u)==0 && in.frame.flags!=CONTROL_GRIP && in.frame.direction<=CONTROL_RIGHT;
    if(!connected_ || !fresh(now) || in.revision!=revision_ ||
       uint32_t(now-in.producedAt)>=150 || !legal || !(in.frame.flags&CONTROL_VALID)) {
      pending_=armed_=neutralSent_=false;armSeen_=in.arm;
      return out;
    }
    if(in.arm && in.arm!=armSeen_) {
      armSeen_=in.arm; pending_=true;armed_=false;neutralSent_=false;
      event_=0;sourceEvent_=in.frame.event_id;
    }
    if(pending_) {
      if(!neutralSent_) { reportBeforeNeutral_=reports_;neutralSent_=true; }
      sourceEvent_=in.frame.event_id;
      out.flags=CONTROL_VALID;out.event_id=event_;return out;
    }
    if(!armed_) return out;
    out.flags=in.frame.flags;
    if(in.frame.event_id!=sourceEvent_) {
      sourceEvent_=in.frame.event_id; ++event_;direction_=in.frame.direction;
    }
    out.event_id=event_;out.direction=event_?direction_:0;
    return out;
  }
 private:
  bool connected_=false,seen_=false,overflow_=false;
  char line_[48]={}; size_t used_=0;
  uint32_t revision_=0,statusAt_=0,reports_=0,lastByte_=0;
  pendulum_bridge::StmStatus status_;
  bool pending_=false,armed_=false,neutralSent_=false;
  uint32_t armSeen_=0,reportBeforeNeutral_=0;
  uint8_t sequence_=0,event_=0,sourceEvent_=0,direction_=0;
};
