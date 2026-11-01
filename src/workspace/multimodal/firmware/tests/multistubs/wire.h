#pragma once
#include "Arduino.h"
inline bool fakeMpuConnected = true;
inline int16_t fakeAccel[3] = {0,0,16384}, fakeGyro[3] = {0,0,0};
class TwoWire {
 public:
  int sda = -1, scl = -1;
  uint8_t addr = 0, reg = 0;
  bool first = true;
  std::deque<uint8_t> data;
  void begin(int a, int b, unsigned) { sda=a; scl=b; }
  void setTimeOut(int) {}
  void beginTransmission(uint8_t a) { addr=a; first=true; }
  void write(uint8_t b) { if (first) reg=b; first=false; }
  int endTransmission(bool = true) { return fakeMpuConnected && addr==0x68 ? 0 : 4; }
  size_t requestFrom(uint8_t, size_t count, bool) {
    data.clear();
    if (!fakeMpuConnected) return 0;
    if (reg==0x75) data.push_back(0x68);
    else {
      uint8_t bytes[14] = {};
      for (unsigned i=0;i<3;++i) {
        bytes[2*i]=(uint8_t)((uint16_t)fakeAccel[i]>>8); bytes[2*i+1]=(uint8_t)fakeAccel[i];
        bytes[8+2*i]=(uint8_t)((uint16_t)fakeGyro[i]>>8); bytes[9+2*i]=(uint8_t)fakeGyro[i];
      }
      for (size_t i=0;i<count;++i) data.push_back(bytes[i]);
    }
    return data.size();
  }
  int read() { int b=data.front(); data.pop_front(); return b; }
};
inline TwoWire Wire;
