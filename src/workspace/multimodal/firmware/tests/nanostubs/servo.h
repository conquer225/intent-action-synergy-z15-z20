#pragma once
#include "Arduino.h"
inline unsigned attachedServos=0;
class Servo {
 public: int value=-1; void write(int v) {value=v;} void attach(int) {++attachedServos;}
};
