#include <cassert>
#include <cstdio>
#include "../esp32/MultiControlS3/MotionInput.h"

int main() {
  const float mounts[][3]={{0,0,1},{0,0,-1},{1,0,0},{-1,0,0},
                           {0,1,0},{0,-1,0},{-0.975f,-0.022f,0.113f}};
  const float noGyro[3]={0,0,0};
  for (const auto &mount:mounts) {
    MotionInput input;
    assert(input.begin(mount));
    float h[3],vertical;
    for (unsigned i=0;i<500;++i) {
      assert(input.update(mount,noGyro,0.01f,h,vertical));
      assert(vectorNorm(h)<0.0001f && fabsf(vertical)<0.0001f);
    }
  }
  // Tilt through the former pitch=90-degree singularity, with accelerometer
  // data derived directly from sin/cos rather than the rotation helper.
  MotionInput input;
  const float down[3]={0,0,1}, gyroY[3]={0,30,0};
  assert(input.begin(down));
  SwipeGate gate;
  float left[3]={0,1,0},h[3],vertical;
  unsigned now=0;
  for (unsigned n=1;n<=700;++n) {
    float angle=n*0.3f*0.01745329252f;
    float accel[3]={-sinf(angle),0,cosf(angle)};
    assert(input.update(accel,gyroY,0.01f,h,vertical,left));
    assert(vectorNorm(h)<0.0001f);
    assert(!gate.update(vectorDot(h,left),vectorNorm(h),now+=10,true));
  }
  // Rotate vertical sensor by 90 degrees; the taught side axis travels with it.
  const float upright[3]={-1,0,0}, spin[3]={0,0,45};
  assert(input.begin(upright));
  left[0]=0; left[1]=1; left[2]=0;
  for (unsigned n=1;n<=200;++n) {
    float angle=n*0.45f*0.01745329252f;
    float accel[3]={-cosf(angle),sinf(angle),0};
    assert(input.update(accel,spin,0.01f,h,vertical,left));
    assert(vectorNorm(h)<0.0001f);
  }
  assert(fabsf(left[0]-1)<0.0001f && fabsf(left[1])<0.0001f);
  gate.reset();
  for (unsigned n=0;n<30;++n) {
    const float accel[3]={0,1,0};
    assert(input.update(accel,noGyro,0.01f,h,vertical,left));
    gate.update(vectorDot(h,left),vectorNorm(h),now+=10,true);
  }
  assert(gate.armed);
  unsigned events=0;
  for (unsigned n=0;n<6;++n) {
    const float accel[3]={0.16f,1,0};
    assert(input.update(accel,noGyro,0.01f,h,vertical,left));
    int direction=gate.update(vectorDot(h,left),vectorNorm(h),now+=10,true);
    if (direction) { assert(direction==1); ++events; }
  }
  assert(events==1); // 0.16g is below the former 0.25g threshold.
  for (unsigned n=0;n<20;++n) {
    const float accel[3]={-0.3f,1,0};
    assert(input.update(accel,noGyro,0.01f,h,vertical,left));
    assert(!gate.update(vectorDot(h,left),vectorNorm(h),now+=10,true));
  }
  const float invalid[3]={NAN,0,1}, zero[3]={0,0,0};
  assert(!input.update(invalid,noGyro,0.01f,h,vertical));
  assert(!input.update(down,noGyro,0.2f,h,vertical));
  assert(!input.begin(zero));
  puts("MPU vectors: all mounting directions, vertical crossing, rotation rejection, axis transport and light swipe PASS");
}
