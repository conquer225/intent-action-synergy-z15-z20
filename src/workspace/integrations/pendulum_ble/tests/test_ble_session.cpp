#include <assert.h>
#include <stdio.h>
#include "BlePendulumSession.h"
#include "BootConfig.h"

int main() {
  assert(!BOOT_AUTO_START && BOOT_HAND_AUTO_START);
  BlePendulumSession s;
  s.connection(true,100);
  const char *a="S,0,0,"; const char *b="0,1\n";
  s.receive(reinterpret_cast<const uint8_t*>(a),6,110);
  assert(!s.fresh(110));
  s.receive(reinterpret_cast<const uint8_t*>(b),4,120);
  assert(s.fresh(120) && s.state()==0 && s.blocked()==1 && s.stmLinked()==0);
  assert(s.fresh(1119) && !s.fresh(1120));
  s.connection(false,1121);
  assert(!s.linked() && !s.fresh(1121) && s.state()==-1);
  puts("BLE session fragmented status, feedback age and disconnect passed");

  BlePendulumSession drive; drive.connection(true,2000);
  const uint8_t stopped[]="S,0,0,1,1\n";
  drive.receive(stopped,sizeof(stopped)-1,2010);
  BlePendulumInput input;
  input.revision=drive.revision(); input.producedAt=2010;
  input.frame={0,CONTROL_VALID|CONTROL_GRIP,9,CONTROL_LEFT};
  assert(drive.output(2010,input).flags==0); // Explicit neutral request is required.
  input.arm=1;
  ControlFrame f=drive.output(2020,input);
  assert(f.flags==CONTROL_VALID && f.direction==0 && !drive.neutralReady());
  drive.receive(stopped,sizeof(stopped)-1,2030);
  assert(!drive.neutralReady());
  const uint8_t neutral[]="S,0,0,1,0\n";
  drive.receive(neutral,sizeof(neutral)-1,2040);
  assert(drive.neutralReady());
  input.producedAt=2050; f=drive.output(2050,input);
  assert(f.flags==(CONTROL_VALID|CONTROL_GRIP) && f.direction==0);
  input.frame.event_id=10;input.frame.direction=CONTROL_RIGHT;
  f=drive.output(2060,input); assert(f.direction==CONTROL_RIGHT && f.event_id==1);
  assert(drive.output(2200,input).flags==0 && !drive.neutralReady());
  input.producedAt=2210; assert(drive.output(2210,input).flags==0);
  drive.connection(false,2220);drive.connection(true,2230);
  drive.receive(neutral,sizeof(neutral)-1,2240);
  input.producedAt=2240;
  assert(drive.output(2240,input).flags==0); // Old connection generation cannot replay.
  input.revision=drive.revision(); input.arm=2;
  assert(drive.output(2250,input).flags==CONTROL_VALID && !drive.neutralReady());
  puts("BLE explicit neutral, event synchronization, stale mailbox and reconnect passed");

  BlePendulumSession lock;lock.connection(true,3000);
  lock.receive(stopped,sizeof(stopped)-1,3010);
  BlePendulumInput active;active.revision=lock.revision();active.producedAt=3020;
  active.arm=1;active.frame.flags=CONTROL_VALID;
  lock.output(3020,active);lock.receive(neutral,sizeof(neutral)-1,3030);
  assert(lock.neutralReady());
  const uint32_t generation=lock.revision();
  lock.receive(stopped,sizeof(stopped)-1,3040);
  assert(!lock.neutralReady() && lock.revision()!=generation);
  active.producedAt=3050;assert(lock.output(3050,active).flags==0);
  const uint8_t garbage[]="S,0,0,1,0garbage\nS,0,0,2,0\nT,99,4,0,0\n";
  lock.receive(garbage,sizeof(garbage)-1,5000);assert(!lock.fresh(5000));
  puts("BLE STM relock revokes generation; malformed and non-status data cannot renew freshness passed");
}
