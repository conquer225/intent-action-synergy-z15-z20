#ifndef MULTI_GLOVE_CONTROLLER_H
#define MULTI_GLOVE_CONTROLLER_H
#include <Arduino.h>
#include <Preferences.h>
#include "GloveRadio.h"
#include "HapticFeedback.h"
enum class HandMode : uint8_t { GLOVE, EMG, NETWORK };
enum class GloveMapping : uint8_t { CALIBRATED, DIRECT, NANO };
class GloveController {
 public:
  void begin();
  void sample();
  void tick();
  void setMode(HandMode value);
  bool enable();
  void stop();
  void setGrip(bool gripped, bool valid);
  bool setNetworkPose(const int16_t *target);
  bool preset(bool closed);
  bool capturePose(bool closed,const int16_t *target);
  bool savePoses();
  bool command(char *line, void (*stopPendulum)());
  void printTelemetry();
  void printPots();
  void showCalibration();
  const char *modeName() const;
  const char *mappingName() const {
    return mapping==GloveMapping::NANO?"nano":mapping==GloveMapping::DIRECT?"direct":"calibrated";
  }
  bool enabled=false, calibrated=false, posesReady=false, pressureCalibrated=false;
  bool pcMode=false; // Compatibility alias for old USB clients; NETWORK includes PC.
  HandMode mode=HandMode::GLOVE;
  uint16_t raw[POT_COUNT]={},filtered[POT_COUNT]={};
  int16_t angles[POT_COUNT]={};
  uint8_t motorDuty[5]={};
  GloveRadio radio;
 private:
  Preferences prefs;
  HapticFeedback haptics;
  bool storageReady=false,openCaptured=false,closedCaptured=false;
  GloveMapping mapping=GloveMapping::CALIBRATED;
  bool locating=false;
  bool poseOpenCaptured=false,poseClosedCaptured=false;
  bool stopping=false,pressurePolling=false,gripValid=false,gripClosed=false,gripArmed=false;
  uint32_t stopStartedMs=0, enabledSinceMs=0;
  PotCalibration calibration={},draft={};
  PoseCalibration poses={},poseDraft={};
  uint8_t nextPot=0,captureKind=0,captureFrames=0,seen[POT_COUNT]={};
  uint32_t lastPotUs=0,potFrames=0,captureSum[POT_COUNT]={};
  void startCapture(uint8_t kind,void (*stopPendulum)());
  void updateAngles();
  void openAngles();
  void syncHapticStatus();
  bool pcCommand(char *line);
};
#endif
