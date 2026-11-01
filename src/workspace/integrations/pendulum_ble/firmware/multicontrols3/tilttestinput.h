#ifndef MULTI_TILT_TEST_INPUT_H
#define MULTI_TILT_TEST_INPUT_H
#include "SwipeInput.h"
// S3-only bench mode: STILL at any angle stops and rearms. Never require CENTER.
struct TiltTestInput {
  bool zeroReady=false, armed=false, moving=false, quietTiming=false, angleValid=false;
  bool historyReady=false, startTiming=false;
  uint32_t quietSince=0, startSince=0;
  uint8_t head=0, samples=0;
  float neutral[3]={0,0,1}, filtered[3]={0,0,1}, history[16][3]={};
  float angle=0, motion=0, rotation=0;
  bool ready() const { return zeroReady; }
  void resetGate() {
    armed=moving=quietTiming=angleValid=historyReady=startTiming=false;
    head=samples=0; angle=motion=rotation=0;
  }
  void clear() { zeroReady=false; resetGate(); }
  static bool unitAccel(const float *accel,float *unit,bool stationary=true) {
    float norm=vectorNorm(accel);
    // Calibration needs gravity only; valid movement includes linear acceleration.
    // The MPU is configured for +/-2g per axis (vector magnitude <= sqrt(12)).
    if (!isfinite(norm) || norm<(stationary?0.8f:0.0f) ||
        norm>(stationary?1.2f:3.5f)) return false;
    for (uint8_t i=0;i<3;++i) unit[i]=norm>0.0001f?accel[i]/norm:0;
    return true;
  }
  bool setZero(const float *accel,const float *gyro) {
    clear(); float unit[3], speed=vectorNorm(gyro);
    if (!isfinite(speed) || speed>8 || !unitAccel(accel,unit)) return false;
    for (uint8_t i=0;i<3;++i) neutral[i]=unit[i];
    zeroReady=true; return true;
  }
  // +1 = movement began; -1 = stopped; moving is the continuously checked level.
  int update(const float *accel,const float *gyro,uint32_t now,bool fresh) {
    bool wasMoving=moving;
    float unit[3], speed=vectorNorm(gyro);
    if (!fresh || !ready() || !isfinite(speed) || !unitAccel(accel,unit,false)) {
      resetGate(); return wasMoving?-1:0;
    }
    // Near-zero apparent gravity can occur during a shake; it only invalidates
    // the angle display, not finite gyro/acceleration movement detection.
    angleValid=vectorNorm(unit)>0.5f;
    angle=angleValid?acosf(fmaxf(-1.0f,fminf(1.0f,vectorDot(unit,neutral))))*57.29577951f:0;
    if (!historyReady) {
      for (uint8_t i=0;i<3;++i) filtered[i]=accel[i];
      for (uint8_t j=0;j<16;++j)
        for (uint8_t i=0;i<3;++i) history[j][i]=accel[i];
      rotation=speed; historyReady=true;
    }
    float delta[3];
    for (uint8_t i=0;i<3;++i) {
      filtered[i]+=0.25f*(accel[i]-filtered[i]);
      delta[i]=filtered[i]-history[head][i];
      history[head][i]=filtered[i];
    }
    head=(head+1)%16; if (samples<16) ++samples;
    motion=vectorNorm(delta); rotation+=0.25f*(speed-rotation);
    if (samples<16) return 0;
    bool quiet=motion<=0.010f && rotation<=1.5f;
    if (quiet) {
      startTiming=false;
      if (!quietTiming) { quietTiming=true; quietSince=now; }
      if (moving && uint32_t(now-quietSince)>=150) {
        moving=false; armed=true; return -1;
      }
      if (!moving && uint32_t(now-quietSince)>=350) armed=true;
      return 0;
    }
    quietTiming=false;
    if (!armed || moving) return 0;
    if (motion<0.020f && rotation<3.0f) { startTiming=false; return 0; }
    if (!startTiming) { startTiming=true; startSince=now; }
    if (uint32_t(now-startSince)<80) return 0;
    moving=true; startTiming=false; return 1;
  }
};
#endif
