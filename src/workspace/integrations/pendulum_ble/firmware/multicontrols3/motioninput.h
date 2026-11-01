#ifndef MULTI_MOTION_INPUT_H
#define MULTI_MOTION_INPUT_H
#include "SwipeInput.h"

// Rotate an earth-fixed vector expressed in the moving sensor's coordinates.
// Its derivative is vector x gyro, so no Euler angles or vertical singularity
// are needed. The same rotation transports the taught LEFT direction.
inline void rotateBodyVector(float *v, const float *gyroDps, float dt) {
  constexpr float radiansPerDegree = 0.01745329252f;
  float omega[3];
  for (uint8_t i=0;i<3;++i)
    omega[i] = gyroDps[i]*radiansPerDegree;
  float speed=vectorNorm(omega);
  if (speed<0.000001f) return;
  float axis[3]={omega[0]/speed,omega[1]/speed,omega[2]/speed};
  float angle=speed*dt, c=cosf(angle), s=sinf(angle);
  float dot=vectorDot(v,axis);
  float cross[3]={v[1]*axis[2]-v[2]*axis[1],
                  v[2]*axis[0]-v[0]*axis[2],
                  v[0]*axis[1]-v[1]*axis[0]};
  for (uint8_t i=0;i<3;++i)
    v[i]=v[i]*c+cross[i]*s+axis[i]*dot*(1-c);
}

struct MotionInput {
  float gravity[3]={0,0,1};
  float magnitude=1;
  bool ready=false;
  bool begin(const float *stationaryAccel) {
    ready=false;
    magnitude=vectorNorm(stationaryAccel);
    if (!isfinite(magnitude) || magnitude<0.8f || magnitude>1.2f) return false;
    for (uint8_t i=0;i<3;++i) gravity[i]=stationaryAccel[i];
    ready=true;
    return true;
  }
  bool update(const float *accel,const float *gyroDps,float dt,
              float *horizontal,float &vertical,float *leftAxis=nullptr) {
    if (!ready || !isfinite(dt) || dt<=0 || dt>0.1f) return false;
    for (uint8_t i=0;i<3;++i)
      if (!isfinite(accel[i]) || !isfinite(gyroDps[i])) return false;
    rotateBodyVector(gravity,gyroDps,dt);
    if (leftAxis) rotateBodyVector(leftAxis,gyroDps,dt);
    float linear[3];
    for (uint8_t i=0;i<3;++i) linear[i]=accel[i]-gravity[i];
    vertical=vectorDot(linear,gravity)/magnitude;
    for (uint8_t i=0;i<3;++i)
      horizontal[i]=linear[i]-vertical*gravity[i]/magnitude;
    // Only stationary data corrects drift; a swipe must not become gravity.
    if (vectorNorm(horizontal)<=SWIPE_QUIET_G && fabsf(vertical)<0.08f &&
        vectorNorm(gyroDps)<8.0f) {
      for (uint8_t i=0;i<3;++i) gravity[i]+=0.04f*(accel[i]-gravity[i]);
      float norm=vectorNorm(gravity);
      if (!isfinite(norm) || norm<0.01f) { ready=false; return false; }
      for (uint8_t i=0;i<3;++i) gravity[i]*=magnitude/norm;
    }
    return true;
  }
};
#endif
