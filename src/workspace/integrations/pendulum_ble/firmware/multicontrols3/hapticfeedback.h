#ifndef MULTI_HAPTIC_FEEDBACK_H
#define MULTI_HAPTIC_FEEDBACK_H
#include <Arduino.h>
#include <Preferences.h>
#include "GloveLogic.h"
class HapticFeedback {
 public:
  bool begin();
  void stop();
  void releasePinForInput(int pin);
  void tick(bool enabled,bool fresh,const HandFeedback &feedback);
  bool command(char *line,bool fresh,const HandFeedback &feedback);
  bool calibrated=false,ready=false,calibrating=false;
  uint8_t duty[5]={};
 private:
  Preferences prefs;
  bool storageReady=false,attached[5]={};
  bool released[5]={};
  uint8_t zeroMask=0,spanMask=0;
  PressureCalibration cal={},draft={};
  void show();
};
#endif
