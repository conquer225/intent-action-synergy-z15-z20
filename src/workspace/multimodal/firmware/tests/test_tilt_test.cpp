#include <cassert>
#include <cstdio>
#include "../esp32/MultiControlS3/TiltTestInput.h"
static float center[3]={0,0,1}, still[3]={0,0,0}, rotation[3]={0,0,20};
static unsigned now=0;
static int run(TiltTestInput &in,const float *a,const float *g,unsigned ms) {
  int transition=0;
  for(unsigned t=0;t<ms;t+=10) { now+=10; int x=in.update(a,g,now,true); if(x) transition=x; }
  return transition;
}
int main() {
  TiltTestInput in;
  assert(!in.setZero(center,rotation)); assert(in.setZero(center,still));
  run(in,center,rotation,800); assert(!in.armed && !in.moving); // Held motion at enable cannot start.
  run(in,center,still,1000); assert(in.ready() && in.armed);
  for(unsigned i=0;i<100;++i) { float noise[3]={i%2?.003f:-.003f,0,1}; assert(!run(in,noise,still,10)); }
  assert(run(in,center,rotation,200)==1 && in.moving);
  assert(!run(in,center,rotation,4000) && in.moving); // Keep moving, no repeated start.
  assert(run(in,center,still,400)==-1 && !in.moving && in.armed);
  // Any new tilt is motion, but holding a LARGE static tilt stops without returning.
  float tilted[3]={.5f,0,.8660254f};
  assert(run(in,tilted,still,150)==1 && in.moving);
  assert(run(in,tilted,still,700)==-1 && !in.moving && in.armed && in.angle>29);
  assert(!run(in,tilted,still,1000));
  // A second movement can start at the tilted pose, no center requirement.
  assert(run(in,tilted,rotation,200)==1 && in.moving);
  assert(in.update(tilted,still,now+10,false)==-1 && !in.moving && !in.armed);
  now+=10; run(in,tilted,rotation,1000); assert(!in.moving && !in.armed);
  run(in,tilted,still,1000); assert(in.armed);
  float spike[3]={.8f,0,.6f}; run(in,spike,still,10); run(in,tilted,still,500); assert(!in.moving);
  in.resetGate(); assert(in.ready() && !in.armed);
  now=UINT32_MAX-200; run(in,tilted,still,800); assert(in.armed);
  assert(run(in,tilted,rotation,200)==1);
  float bad[3]={NAN,0,1}; assert(in.update(bad,still,now+10,true)==-1);
  in.clear(); assert(!in.ready() && !in.moving);
  // Linear acceleration during valid motion must not clear the static arming.
  float accelerated[3]={0,0,1.5f};
  assert(!in.setZero(accelerated,still)); // Zero still requires near-1g.
  assert(in.setZero(center,still)); run(in,center,still,800);
  assert(run(in,accelerated,rotation,300)==1 && in.armed && in.moving);
  assert(!run(in,accelerated,rotation,2000) && in.moving);
  assert(run(in,center,still,700)==-1 && !in.moving && in.armed);
  float impossible[3]={4,0,0};
  run(in,center,rotation,300); assert(in.moving);
  assert(in.update(impossible,rotation,now+10,true)==-1 && !in.armed);
  // Slow rotation and gentle translation, below the old thresholds, both start.
  assert(in.setZero(center,still)); run(in,center,still,800);
  float slow[3]={0,0,4};
  assert(run(in,center,slow,300)==1 && in.moving);
  assert(!run(in,center,slow,1000) && in.moving);
  run(in,center,still,800); assert(!in.moving && in.armed);
  for(unsigned n=0;n<40;++n) {
    float gentle[3]={.002f*n,0,1}; run(in,gentle,still,10);
  }
  assert(in.moving);
  float gentleEnd[3]={.078f,0,1}; run(in,gentleEnd,still,800);
  assert(!in.moving && in.armed);
  float cancellingGravity[3]={0,0,0}, hard[3]={0,0,240};
  assert(run(in,cancellingGravity,hard,300)==1 && in.moving && !in.angleValid);
  assert(!run(in,accelerated,hard,1000) && in.moving);
  run(in,center,still,800); assert(!in.moving && in.armed);
  // Recorded stationary noise must not become a movement request.
  float gyroNoise[3]={0,0,.9f};
  for(unsigned n=0;n<100;++n) {
    float noise[3]={n%2?.003f:-.003f,0,1}; run(in,noise,gyroNoise,10);
    assert(!in.moving && in.armed);
  }
  puts("Motion-held MPU: move keeps driving, static tilt stops, restart at any pose, spike/noise rejection, stale/held reconnect and rollover PASS");
}
