#include <cassert>
#include <cstdio>
#include "../esp32/MultiControlS3/SwipeInput.h"

int main() {
  SwipeGate gate;
  assert(!gate.update(0.4f,0.4f,0,true)); // Cannot fire before stationary arming.
  assert(!gate.update(0,0,100,true));
  assert(!gate.update(0,0,350,true)); assert(gate.armed);
  assert(!gate.update(0.4f,0.4f,400,true));
  assert(!gate.update(0.4f,0.4f,429,true));
  assert(gate.update(0.4f,0.4f,430,true)==1);
  // Opposite braking lobe is part of the SAME motion, not a right command.
  assert(!gate.update(-0.8f,0.8f,460,true));
  assert(!gate.update(-0.8f,0.8f,550,true));
  gate.update(0,0,600,true); gate.update(0,0,850,true); assert(!gate.armed);
  gate.update(0,0,1130,true); assert(gate.armed);
  gate.update(-0.4f,0.4f,1140,true);
  assert(gate.update(-0.4f,0.4f,1170,true)==-1);
  gate.reset(); gate.update(0,0,0,true); gate.update(0,0,250,true);
  gate.update(0.1f,0.6f,300,true); assert(!gate.update(0.1f,0.6f,400,true)); // Forward pulse.
  gate.update(0.4f,0.4f,500,true); gate.update(0,0,510,true);
  gate.update(0.4f,0.4f,520,true); assert(!gate.update(0.4f,0.4f,549,true));
  assert(gate.update(0.4f,0.4f,550,true)==1); // Don't accumulate separate short pulses.
  gate.update(0,0,600,false); assert(!gate.armed);
  gate.update(0,0,UINT32_MAX-100,true); gate.update(0,0,150,true); assert(gate.armed);
  gate.update(-0.4f,0.4f,200,true); assert(gate.update(-0.4f,0.4f,230,true)==-1);

  SwipeLearner learn; SwipeAxis axis;
  float quiet[3]={0,0,0}, left[3]={0,0.5f,0};
  learn.start(0); learn.update(left,10,true,axis); assert(!learn.ready);
  learn.update(quiet,100,true,axis); learn.update(quiet,350,true,axis); assert(learn.ready);
  for(uint32_t n=400;n<=420;n+=10) assert(!learn.update(left,n,true,axis));
  assert(learn.update(left,430,true,axis)==1 && swipeAxisValid(axis));
  assert(fabsf(axis.left[1]-1)<0.001f); // Arbitrary installation, no hard-coded X axis.
  SwipeAxis bad=axis; bad.left[0]=NAN; assert(!swipeAxisValid(bad));
  bad=axis; bad.left[1]=0; assert(!swipeAxisValid(bad));
  learn.start(1000); assert(learn.update(quiet,11000,true,axis)==-1);
  assert(!learn.active);
  learn.start(20000); learn.update(quiet,20000,true,axis); learn.update(quiet,20250,true,axis);
  learn.update(left,20300,true,axis); learn.update(left,20310,false,axis);
  assert(!learn.ready && !learn.count); // Twisting or bad data cancels the candidate.
  puts("Swipe: stationary arming, braking rejection, direction learning, timeout and millis rollover PASS");
}
