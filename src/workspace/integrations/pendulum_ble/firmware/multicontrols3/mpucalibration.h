#pragma once
#include <stdint.h>
#include <math.h>
// Feed at 100 Hz. Two continuous quiet seconds are required, in any mounting.
struct StationaryMpuCalibration {
  uint16_t samples=0;
  float accelMean[3]={}, gyroMean[3]={}, accelM2[3]={}, gyroM2[3]={};
  void reset() {
    samples=0;
    for (uint8_t i=0;i<3;++i) accelMean[i]=gyroMean[i]=accelM2[i]=gyroM2[i]=0;
  }
  // -1 rejected/reset, 0 collecting, 1 complete.
  int update(const float *accel,const float *gyro) {
    float norm=sqrtf(accel[0]*accel[0]+accel[1]*accel[1]+accel[2]*accel[2]);
    if (!isfinite(norm) || norm<0.8f || norm>1.2f) { reset(); return -1; }
    for (uint8_t i=0;i<3;++i)
      if (!isfinite(gyro[i]) || fabsf(gyro[i])>8.0f) { reset(); return -1; }
    ++samples;
    for (uint8_t i=0;i<3;++i) {
      float a=accel[i]-accelMean[i], g=gyro[i]-gyroMean[i];
      accelMean[i]+=a/samples; gyroMean[i]+=g/samples;
      accelM2[i]+=a*(accel[i]-accelMean[i]); gyroM2[i]+=g*(gyro[i]-gyroMean[i]);
    }
    if (samples<200) return 0;
    for (uint8_t i=0;i<3;++i)
      if (sqrtf(gyroM2[i]/samples)>1.5f || sqrtf(accelM2[i]/samples)>0.015f) {
        reset(); return -1;
      }
    return 1;
  }
};
